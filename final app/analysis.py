#!/usr/bin/env python3
"""
Analysis functions for the analysis pipeline.
"""
import re
import logging
import json
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import PHI4_MAX_CONTEXT, FINAL_REPORT_TOKENS
from utils import estimate_tokens, _iso_now
from llm_interface import call_llm_and_stream_to_terminal_and_file

# --- add these imports near the top of analysis.py ---
import math
from typing import List, Dict

# --- helper: summarize a list of texts using a small summarization prompt ---
def _summarize_texts_with_llm(llm, texts: List[str], max_summary_tokens: int = 800, prompt_note: str = "") -> str:
    """
    Summarize the provided texts into a single concise summary using the LLM instance.
    Returns the summary string.
    - llm: model manager (must implement generate or generate_stream as used elsewhere)
    - texts: list of strings to summarize
    - max_summary_tokens: tokens allowed for the summary (small)
    """
    joined = "\n\n".join(texts)
    prompt = f"""Summarize the following texts into a concise, single-paragraph summary that preserves the most important points.
Do NOT add opinions or invent facts. Keep the summary short and factual.

{prompt_note}

Texts:
{joined}

Summary:
"""
    # Use a non-streaming short call (safe)
    try:
        # if llm has 'generate' method (SingleModelManager), use it
        if hasattr(llm, "generate"):
            raw = llm.generate(prompt, max_tokens=max_summary_tokens)
            # raw may be dict or string
            if isinstance(raw, dict) and "choices" in raw and len(raw["choices"]) > 0:
                return raw["choices"][0].get("text", "").strip()
            elif isinstance(raw, str):
                return raw.strip()
            else:
                return str(raw).strip()
        else:
            # fallback to lm_call_cached if llm object is a client expected elsewhere
            return lm_call_cached(llm, prompt, max_tokens=max_summary_tokens, stream=False)
    except Exception as e:
        logging.warning(f"Summarization call failed: {e}")
        # as fallback return joined truncated
        return joined[:1000] + ("..." if len(joined) > 1000 else "")

# --- helper: recursively compress partial_results until under token budget ---
def _ensure_under_token_budget(llm, partial_results: List[Dict], token_budget: int,
                               summary_max_tokens: int = 800, group_size: int = 8,
                               min_group_size: int = 2, max_rounds: int = 6) -> List[Dict]:
    """
    Reduce partial_results by summarizing groups until combined tokens <= token_budget.
    - partial_results: list of {'batch_id': int, 'result': str}
    - token_budget: allowed tokens for final joined_text
    - summary_max_tokens: max tokens to allocate to each summarization output
    - group_size: initial number of items to group per summarization
    Returns a new partial_results list (may contain summaries instead of raw results).
    """
    def combined_tokens(items):
        text = "\n\n".join([it.get("result", "") for it in items])
        return estimate_tokens(text)

    round_num = 0
    current = partial_results

    while combined_tokens(current) > token_budget and round_num < max_rounds:
        round_num += 1
        logging.info(f"Compression round {round_num}: total tokens {combined_tokens(current):,} > budget {token_budget:,}")
        new_items = []
        i = 0
        n = len(current)
        # dynamically adapt group size if too big
        gs = group_size
        if gs < min_group_size:
            gs = min_group_size
        while i < n:
            group = current[i:i+gs]
            # if group is small (like last tail) and too small to summarize, just append raw
            if len(group) == 1:
                # single element — keep as is
                new_items.append(group[0])
            else:
                texts = [g.get("result", "") for g in group]
                prompt_note = f"(This is an automatic intermediate summary round {round_num}. Summarize in concise bullet points or ~1-3 sentences.)"
                summary = _summarize_texts_with_llm(llm, texts, max_summary_tokens=summary_max_tokens, prompt_note=prompt_note)
                # create synthetic batch_id to indicate aggregated item (use min-max of group ids)
                batch_ids = [g.get("batch_id") for g in group if "batch_id" in g]
                agg_id = f"{batch_ids[0]}-{batch_ids[-1]}" if batch_ids else i
                new_items.append({"batch_id": agg_id, "result": summary})
            i += gs

        # If compression didn't reduce tokens (rare), lower group size to produce smaller summaries
        if combined_tokens(new_items) >= combined_tokens(current):
            if gs > min_group_size:
                group_size = max(min_group_size, gs // 2)
                logging.info(f"No token reduction this round; decreasing group_size to {group_size} and retrying.")
                # try again in next round with smaller groups
                current = current  # no change
            else:
                logging.warning("Cannot further compress results effectively. Breaking compression loop.")
                break
        else:
            # accept compressed version
            current = new_items

    logging.info(f"Compression finished after {round_num} rounds; final tokens: {combined_tokens(current):,}")
    return current


from utils import estimate_tokens
from config import PHI4_MAX_CONTEXT

def process_batch(llm_manager, batch, batch_id):
    """Processes a single batch using a specific LLM instance, keeping prompt under 16k tokens."""
    joined_text = " ".join(batch)

    # Estimate total tokens
    total_tokens = estimate_tokens(joined_text)
    max_safe_tokens = PHI4_MAX_CONTEXT - 1000  # leave headroom for prompt and response

    if total_tokens > max_safe_tokens:
        # Truncate to fit safely under the context limit
        logging.warning(f"[process_batch] Batch {batch_id} too large ({total_tokens} tokens). "
                        f"Truncating to {max_safe_tokens}.")
        truncated_ratio = max_safe_tokens / total_tokens
        cutoff_chars = int(len(joined_text) * truncated_ratio)
        joined_text = joined_text[:cutoff_chars]

    prompt = f"""Analyze the following text and provide a structured summary, sentiment, and key topics.

Text:
{joined_text}

---
Report:
- Summary:
- Sentiment:
- Topics:
"""

    # Generate safely
    result = llm_manager.generate(prompt, max_tokens=3000)
    return {"batch_id": batch_id, "result": result}

# --- main combined_analysis (replace existing one) ---
def combined_analysis(llm, partial_results, token_budget_single_call=PHI4_MAX_CONTEXT - 1000,
                     combined_token_budget=FINAL_REPORT_TOKENS, show_progress=True,
                     stream_llm_if_supported=True, custom_stream_handler=None):
    """
    Performs a combined analysis (summarization, sentiment, topics) on the input data.
    Ensures final prompt stays under token_budget_single_call by summarizing partial_results iteratively.
    """
    # initial joined text
    joined_text = "\n\n".join([res.get('result', '') for res in partial_results])
    if not joined_text.strip():
        logging.warning("No content found in partial results. Cannot generate final report.")
        return "{\"multiverse_combined\": \"No data to analyze.\"}"

    total_tokens = estimate_tokens(joined_text)

    if show_progress:
        if custom_stream_handler:
            custom_stream_handler(f"Starting combined analysis on {total_tokens:,} tokens...")
        print(f"[{_iso_now()}] Starting combined analysis on {total_tokens:,} tokens...")
        print("---")

    # If total tokens exceed the single-call budget, compress partial_results
    if total_tokens > token_budget_single_call:
        logging.info(f"Total tokens {total_tokens:,} exceed token_budget_single_call ({token_budget_single_call:,}). Starting compression.")
        # parameters you can tune:
        SUMMARY_MAX_TOKENS = min(1200, int(token_budget_single_call * 0.1))  # per-group summary allowance
        INITIAL_GROUP_SIZE = 8
        MIN_GROUP_SIZE = 2
        MAX_ROUNDS = 8

        compressed = _ensure_under_token_budget(
            llm,
            partial_results,
            token_budget=token_budget_single_call,
            summary_max_tokens=SUMMARY_MAX_TOKENS,
            group_size=INITIAL_GROUP_SIZE,
            min_group_size=MIN_GROUP_SIZE,
            max_rounds=MAX_ROUNDS
        )
        # replace partial_results and recompute joined_text
        partial_results = compressed
        joined_text = "\n\n".join([res.get('result', '') for res in partial_results])
        total_tokens = estimate_tokens(joined_text)
        logging.info(f"After compression, total tokens: {total_tokens:,}")

        # If still over budget after rounds, truncate conservatively by keeping highest-level summaries only
        if total_tokens > token_budget_single_call:
            logging.warning("Final compressed text still exceeds token budget. Truncating to fit.")
            # greedy trim: keep concatenated summaries until under budget
            kept = []
            for item in partial_results:
                kept.append(item)
                if estimate_tokens("\n\n".join([k.get("result", "") for k in kept])) > token_budget_single_call:
                    # remove last and break
                    kept.pop()
                    break
            partial_results = kept
            joined_text = "\n\n".join([res.get('result', '') for res in partial_results])
            total_tokens = estimate_tokens(joined_text)
            logging.info(f"After truncation, total tokens: {total_tokens:,}")

    # Now build the final prompt (same as your original prompt)
    prompt = f"""<instructions>
You are a highly specialized AI analyst. Your ONLY task is to analyze the provided text corpus and generate a comprehensive synthesis in a single, well-formed JSON document.

You MUST STRICTLY adhere to the following rules:
Rules: Output only valid JSON starting with '{{' and ending with '}}', having one key "multiverse_combined". Base analysis strictly on given text only. Include exactly one executive_summary, one sentiment_analysis, and one topics section. Sentiment must be accurate, not repeated. Use correct JSON syntax with proper quoting and escaping. No extra text or commentary outside JSON. Strictly generate the only one output, do not hallucinate.

</instructions>

<analysis_request>

  "executive_summary": {{
    "min_tokens": 4000,
    "max_tokens": 6000,
    "content": "Provide a comprehensive synthesis of the full input. Capture key arguments, trends, and nuances across all discussions. The summary must be cohesive and continuous, avoiding repetition, and maintaining clarity and readability. do not give the chunk or batch id"
  }},

  "sentiment_analysis": {{
    "positive": {{
      "percentage": [Fill here as a number],
      "reasoning": "Explain briefly why this sentiment appears, with 1–2 example snippets"
    }},
    "negative": {{
      "percentage": [Fill here as a number],
      "reasoning": "Explain briefly why this sentiment dominates, with 1–2 example snippets"
    }},
    "neutral": {{
      "percentage": [Fill here as a number],
      "reasoning": "Explain briefly why neutral sentiment is observed, with 1–2 example snippets"
    }}
  }},

  "topics": {{
    
    "include_subtopics": true,
    
    "instructions": "Extract high-level topics from the text with relevance scores. For each topic, list important subtopics, representative snippets, and the supporting chunk IDs."
  }}

</analysis_request>

<corpus>
{joined_text}
</corpus>

{{"multiverse_combined": """
        
    # Use the streaming function for the final report
    response = call_llm_and_stream_to_terminal_and_file(
        llm, 
        prompt, 
        max_tokens=combined_token_budget,
        out_filepath="final_analysis_report.json",
        enable_stream=stream_llm_if_supported,
        custom_stream_handler=custom_stream_handler
    )

    # Clean and validate the response (same as before)
    response = response.strip()
    
    # Try to extract valid JSON from the response
    try:
        # Find the start of JSON object
        start_idx = response.find('{')
        if start_idx == -1:
            raise ValueError("No JSON object found in response")
        
        # Find the end of JSON object
        brace_count = 0
        end_idx = -1
        for i in range(start_idx, len(response)):
            if response[i] == '{':
                brace_count += 1
            elif response[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break
        
        if end_idx == -1:
            raise ValueError("Incomplete JSON object")
        
        # Extract the JSON
        json_str = response[start_idx:end_idx+1]
        
        # Validate that it's valid JSON
        parsed_json = json.loads(json_str)
        return json_str
        
    except (ValueError, json.JSONDecodeError) as e:
        logging.error(f"Failed to extract valid JSON from response: {e}")
        logging.debug(f"Raw response: {response[:500]}...")
        
        # Return a simple valid JSON with error message
        return '{"multiverse_combined": {"error": "Failed to generate valid JSON analysis", "raw_response": "' + response.replace('"', '\\"') + '"}}'

        
        
        
        
def combined_analysis_V23(llm, partial_results, token_budget_single_call=PHI4_MAX_CONTEXT - 1000, 
                     combined_token_budget=FINAL_REPORT_TOKENS, show_progress=True, 
                     stream_llm_if_supported=True, custom_stream_handler=None):
    """
    Performs a combined analysis (summarization, sentiment, topics) on the input data.
    Modified to support custom stream handlers.
    """
    # The fix is here: correctly join the 'result' field from each dictionary
    joined_text = "\n\n".join([res.get('result', '') for res in partial_results])
    
    if not joined_text.strip():
        logging.warning("No content found in partial results. Cannot generate final report.")
        return "{\"multiverse_combined\": \"No data to analyze.\"}"
    
    total_tokens = estimate_tokens(joined_text)
    
    if show_progress:
        if custom_stream_handler:
            custom_stream_handler(f"Starting combined analysis on {total_tokens:,} tokens...")
        print(f"[{_iso_now()}] Starting combined analysis on {total_tokens:,} tokens...")
        print("---")
    
    # The prompt is modified to request JSON output
    prompt = f"""<instructions>
You are a highly specialized AI analyst. Your ONLY task is to analyze the provided text corpus and generate a comprehensive synthesis in a single, well-formed JSON document.

You MUST STRICTLY adhere to the following rules:
Rules: Output only valid JSON starting with '{{' and ending with '}}', having one key "multiverse_combined". Base analysis strictly on given text only. Include exactly one entity_recognition section, one relationship_extraction section, one anomaly_detection section, and one controversy_score section. Use correct JSON syntax with proper quoting and escaping. No extra text or commentary outside JSON.

</instructions>

<analysis_request>

  "entity_recognition": [
  "min_tokens": 400,
   "max_tokens": 600,
    {{
      
      "type": "PERSON|ORGANIZATION|LOCATION|DATE",
      "name": "string"
    }}
  ],

  "relationship_extraction": [
    {{
      "entity1": "string",
      "relationship": "string",
      "entity2": "string"
    }}
  ],

  "anomaly_detection": [
    {{
      "section": "string",
      "description": "string"
    }}
  ],

  "controversy_score": {{
    "value": 0.0,
    "explanation": "string"
  }}

</analysis_request>

<corpus>
{joined_text}
</corpus>

{{"multiverse_combined": """
        
    # Use the streaming function for the final report
    response = call_llm_and_stream_to_terminal_and_file(
        llm, 
        prompt, 
        max_tokens=combined_token_budget,
        out_filepath="final_analysis_report.json",
        enable_stream=stream_llm_if_supported,
        custom_stream_handler=custom_stream_handler
    )

    # Clean and validate the response
    response = response.strip()
    
    # Try to extract valid JSON from the response
    try:
        # Find the start of JSON object
        start_idx = response.find('{')
        if start_idx == -1:
            raise ValueError("No JSON object found in response")
        
        # Find the end of JSON object
        brace_count = 0
        end_idx = -1
        for i in range(start_idx, len(response)):
            if response[i] == '{':
                brace_count += 1
            elif response[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break
        
        if end_idx == -1:
            raise ValueError("Incomplete JSON object")
        
        # Extract the JSON
        json_str = response[start_idx:end_idx+1]
        
        # Validate that it's valid JSON
        parsed_json = json.loads(json_str)
        return json_str
        
    except (ValueError, json.JSONDecodeError) as e:
        logging.error(f"Failed to extract valid JSON from response: {e}")
        logging.debug(f"Raw response: {response[:500]}...")
        
        # Return a simple valid JSON with error message
        return '{"multiverse_combined": {"error": "Failed to generate valid JSON analysis", "raw_response": "' + response.replace('"', '\\"') + '"}}'
        
        
        
def combined_analysis_V2(llm, partial_results, token_budget_single_call=PHI4_MAX_CONTEXT - 1000, 
                     combined_token_budget=FINAL_REPORT_TOKENS, show_progress=True, 
                     stream_llm_if_supported=True, custom_stream_handler=None):
    """
    Performs a combined analysis (entity recognition, relationship extraction, anomaly detection, controversy score) on the input data.
    Modified to support custom stream handlers.
    """
    # The fix is here: correctly join the 'result' field from each dictionary
    joined_text = "\n\n".join([res.get('result', '') for res in partial_results])
    
    if not joined_text.strip():
        logging.warning("No content found in partial results. Cannot generate final report.")
        return "{\"multiverse_combined\": \"No data to analyze.\"}"
    
    total_tokens = estimate_tokens(joined_text)
    
    if show_progress:
        if custom_stream_handler:
            custom_stream_handler(f"Starting combined analysis on {total_tokens:,} tokens...")
        print(f"[{_iso_now()}] Starting combined analysis on {total_tokens:,} tokens...")
        print("---")
    
    # The prompt is modified to request JSON output
    prompt = f"""<instructions>
You are a highly specialized AI analyst. Your ONLY task is to analyze the provided text corpus and generate a comprehensive synthesis in a single, well-formed JSON document.

You MUST STRICTLY adhere to the following rules:
1. Output only valid JSON starting with '{{' and ending with '}}', having one key "multiverse_combined".
2. Base analysis strictly on given text only.
3. Include exactly one entity_recognition section, one relationship_extraction section, one anomaly_detection section, and one controversy_score section.
4. Use correct JSON syntax with proper quoting and escaping.
5. No extra text, numbers, or commentary outside the JSON structure.
6. The entire response must be a single valid JSON object.
7. Do not include any XML tags like <response> or </response>.

</instructions>

<analysis_request>

Generate a JSON with the following structure:
{{
  "multiverse_combined": {{
    "entity_recognition": [
      {{
        "type": "PERSON|ORGANIZATION|LOCATION|DATE",
        "name": "string"
      }}
    ],
    "relationship_extraction": [
      {{
        "entity1": "string",
        "relationship": "string",
        "entity2": "string"
      }}
    ],
    "anomaly_detection": [
      {{
        "section": "string",
        "description": "string"
      }}
    ],
    "controversy_score": {{
      "value": 0.0,
      "explanation": "string"
    }}
  }}
}}

</analysis_request>

<corpus>
{joined_text}
</corpus>

Your response must start with '{{' and end with '}}' and be valid JSON:"""
        
    # Use the streaming function for the final report
    response = call_llm_and_stream_to_terminal_and_file(
        llm, 
        prompt, 
        max_tokens=combined_token_budget,
        out_filepath="final_analysis_report.json",
        enable_stream=stream_llm_if_supported,
        custom_stream_handler=custom_stream_handler
    )

    # Clean and validate the response
    response = response.strip()
    
    # Try to extract valid JSON from the response
    try:
        # Remove any leading numbers or text
        fixed_response = response
        if response and not response.startswith('{'):
            # Find the first occurrence of '{'
            first_brace = response.find('{')
            if first_brace != -1:
                fixed_response = response[first_brace:]
        
        # Remove any XML tags
        fixed_response = re.sub(r'<[^>]+>', '', fixed_response)
        
        # Find the start of JSON object
        start_idx = fixed_response.find('{')
        if start_idx == -1:
            raise ValueError("No JSON object found in response")
        
        # Find the end of JSON object
        brace_count = 0
        end_idx = -1
        for i in range(start_idx, len(fixed_response)):
            if fixed_response[i] == '{':
                brace_count += 1
            elif fixed_response[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break
        
        if end_idx == -1:
            raise ValueError("Incomplete JSON object")
        
        # Extract the JSON
        json_str = fixed_response[start_idx:end_idx+1]
        
        # Validate that it's valid JSON
        parsed_json = json.loads(json_str)
        
        # Ensure the output has the expected structure
        if "multiverse_combined" not in parsed_json:
            logging.warning("Output doesn't contain 'multiverse_combined' key. Wrapping response.")
            return json.dumps({"multiverse_combined": parsed_json}, indent=2)
        
        return json.dumps(parsed_json, indent=2)
        
    except (ValueError, json.JSONDecodeError) as e:
        logging.error(f"Failed to extract valid JSON from response: {e}")
        logging.debug(f"Raw response: {response[:500]}...")
        
        # Try to fix common JSON issues
        try:
            # Remove any leading numbers or text
            fixed_response = response
            if response and not response.startswith('{'):
                # Find the first occurrence of '{'
                first_brace = response.find('{')
                if first_brace != -1:
                    fixed_response = response[first_brace:]
            
            # Remove any XML tags
            fixed_response = re.sub(r'<[^>]+>', '', fixed_response)
            
            # Try to parse the fixed response
            parsed_json = json.loads(fixed_response)
            
            # Ensure the output has the expected structure
            if "multiverse_combined" not in parsed_json:
                logging.warning("Output doesn't contain 'multiverse_combined' key. Wrapping response.")
                return json.dumps({"multiverse_combined": parsed_json}, indent=2)
            
            return json.dumps(parsed_json, indent=2)
        except:
            # If all attempts fail, return a simple valid JSON with error message
            return json.dumps({
                "multiverse_combined": {
                    "error": "Failed to generate valid JSON analysis",
                    "raw_response": response[:500] + "..." if len(response) > 500 else response
                }
            }, indent=2)
