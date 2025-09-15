#!/usr/bin/env python3
# Re-written test.py with memory management and multi-source JSON extraction

import json
import gc
import sys
import logging
from tqdm import tqdm
from langchain.text_splitter import RecursiveCharacterTextSplitter
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
from llama_cpp import Llama

# --- CONFIG ---
# Update JSON_PATH to point to your desired file
JSON_PATH = "/home/anand/Documents/data/reddit_search_output1.json"
GGUF_PATH = "/home/anand/Downloads/phi4.gguf"

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# --- Utils ---
def load_json(path):
    """Loads a JSON file from the specified path."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load JSON: {e}")
        sys.exit(1)

def extract_texts(data):
    """
    Extracts all text content from various JSON structures.
    It automatically identifies the file type and extracts relevant text fields.
    """
    texts = []
    
    # Try to extract from the YouTube JSON structure (more specific check)
    try:
        if "transcript" in data[0] or ("comments" in data[0] and "text" in data[0]["comments"][0]):
            logging.info("Detected YouTube JSON format.")
            for e in data:
                if e.get("transcript"):
                    texts.append(e["transcript"])
                for c in e.get("comments", []):
                    if c.get("text"):
                        texts.append(c["text"])
                    for sc in c.get("subcomments", []):
                        if sc.get("text"):
                            texts.append(sc["text"])
            return texts
    except (IndexError, TypeError):
        pass # Not a YouTube JSON file

    # Try to extract from the Tweets JSON structure (more specific check)
    try:
        if "user_handle" in data[0] and "content" in data[0]:
            logging.info("Detected Twitter (X) JSON format.")
            for tweet in data:
                if tweet.get("content"):
                    texts.append(tweet["content"])
            return texts
    except (IndexError, TypeError):
        pass # Not a Tweets JSON file

    # Try to extract from the Reddit JSON structure (more specific check)
    try:
        if "title" in data[0] and "selftext" in data[0]:
            logging.info("Detected Reddit JSON format.")
            for post in data:
                if post.get("title"):
                    texts.append(post["title"])
                if post.get("selftext"):
                    texts.append(post["selftext"])
                for comment in post.get("comments", []):
                    if comment.get("comment"):
                        texts.append(comment["comment"])
                    for subcomment in comment.get("subcomments", []):
                        if subcomment.get("comment"):
                            texts.append(subcomment["comment"])
            return texts
    except (IndexError, TypeError):
        pass # Not a Reddit JSON file
    
    logging.warning("Unknown JSON format. Falling back to generic string search.")
    # Generic extraction for unknown formats
    def find_all_strings(obj):
        if isinstance(obj, str) and obj.strip():
            texts.append(obj)
        elif isinstance(obj, dict):
            for value in obj.values():
                find_all_strings(value)
        elif isinstance(obj, list):
            for item in obj:
                find_all_strings(item)

    find_all_strings(data)
    return texts


def chunk_texts(texts, size=500, overlap=50):
    """Splits texts into smaller, overlapping chunks."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
    return [d.page_content for d in splitter.create_documents(texts)]

def is_english(txt):
    """Checks if a string is predominantly English based on ASCII characters."""
    return sum(1 for c in txt if ord(c) < 128) / max(1, len(txt)) > 0.9

# --- Translation ---
def translate(chunks):
    """Translates non-English text chunks to English using an ML model."""
    try:
        tok = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-mul-en")
        model = AutoModelForSeq2SeqLM.from_pretrained("Helsinki-NLP/opus-mt-mul-en")
        trans = pipeline("translation", model=model, tokenizer=tok)
    except Exception as e:
        logging.error(f"Failed to load translation model: {e}")
        return chunks  # fallback to original chunks

    out = []
    for c in tqdm(chunks, desc="Translating"):
        try:
            if is_english(c):
                out.append(c)
            else:
                out.append(trans(c, max_length=512)[0]["translation_text"])
        except Exception as e:
            logging.warning(f"Translation failed for chunk: {e}")
            out.append(c)  # fallback to original
    return out

# --- Phi4 ---
def load_phi4(path):
    """Loads the Phi-4 GGUF model for text generation."""
    try:
        llm = Llama(model_path=path, n_ctx=2048, n_threads=4, n_gpu_layers=0, verbose=False)
        return llm
    except Exception as e:
        logging.error(f"Failed to load Phi-4 model: {e}")
        sys.exit(1)

def ask(llm, prompt, max_tokens=1500):
    """Sends a prompt to the LLM and returns the generated text."""
    try:
        r = llm(prompt, max_tokens=max_tokens, echo=False)
        return r["choices"][0]["text"].strip()
    except Exception as e:
        logging.error(f"LLM call failed: {e}")
        return "ERROR"

# --- New Pipeline for Memory Management ---
def process_chunks_in_batches(llm, chunks, batch_size=5):
    """
    Processes chunks in small batches to avoid context overflow.
    Returns a list of partial summaries and sentiment analyses.
    """
    partial_results = []
    temp_prompt_template = """Analyze the following text and provide a concise summary and a brief sentiment analysis.
Text:
{text_batch}
Output:
Summary: <Summary>
Sentiment: <Positive/Negative/Neutral>, <Reason>
"""
    for i in tqdm(range(0, len(chunks), batch_size), desc="Processing chunks in batches"):
        batch = chunks[i:i + batch_size]
        text_batch = "\n".join(batch)
        
        prompt = temp_prompt_template.replace("{text_batch}", text_batch)
        result = ask(llm, prompt, max_tokens=500)
        partial_results.append(result)
        
    return partial_results

def consolidate_reports(llm, partial_results):
    """
    Consolidates partial results into a final, comprehensive report
    by processing in batches if the total text exceeds the context window.
    """
    intermediate_results = partial_results
    while len(intermediate_results) > 1:
        new_intermediate_results = []
        for i in tqdm(range(0, len(intermediate_results), 3), desc="Consolidating batches"): # Process 3 at a time to stay well under 2048 tokens
            batch = intermediate_results[i:i + 3]
            consolidated_text = "\n\n".join(batch)
            
            # This is the prompt for consolidating intermediate reports
            prompt = f"""You are an expert analyst. Consolidate the following partial analyses into a single, cohesive report.

Partial Analyses:
{consolidated_text}

Consolidated Report:
"""
            result = ask(llm, prompt, max_tokens=1500)
            new_intermediate_results.append(result)
        intermediate_results = new_intermediate_results
        
    final_prompt_template = """You are an expert analyst. Your task is to consolidate the following partial analyses and generate a comprehensive final report with a specific format.

Part 1: GLOBAL STORYLINE
Create a detailed, coherent narrative from the provided summaries. Use only the given facts. Integrate emotional tones and sentiment to enhance the story's depth.

Part 2: SENTIMENT ANALYSIS
Report on the overall emotional tone.
- Identify Positive, Negative, and Neutral sentiments.
- Provide a percentage for each.
- Explain the reason for each sentiment's presence.
- Include one or more direct text examples for each.

The entire output must strictly follow this format:
===== GLOBAL STORYLINE =====
<Your narrative>

===== SENTIMENT ANALYSIS =====
Positive: % - <Reason>
Example: "<quote>"

Negative: % - <Reason>
Example: "<quote>"

Neutral: % - <Reason>
Example: "<quote>"

Partial Analyses to Consolidate:
{consolidated_text}
"""
    final_prompt = final_prompt_template.replace("{consolidated_text}", intermediate_results[0])
    
    return ask(llm, final_prompt, max_tokens=1500)

# --- MAIN ---
def main():
    try:
        # Step 1: Data Pre-processing
        data = load_json(JSON_PATH)
        texts = extract_texts(data)
        chunks = chunk_texts(texts)
        logging.info(f"Texts: {len(texts)}, Chunks: {len(chunks)}")
        
        translated = translate(chunks)
        logging.info("Translation complete")
        
        # Step 2: Load LLM
        llm = load_phi4(GGUF_PATH)
        logging.info("Phi-4 model loaded")

        # Step 3: Process chunks in manageable batches
        partial_results = process_chunks_in_batches(llm, translated)
        logging.info(f"Processed {len(partial_results)} batches.")
        
        # Step 4: Consolidate and generate the final report
        logging.info("Consolidating and generating final report...")
        final_report = consolidate_reports(llm, partial_results)
        logging.info("Analysis complete.")

        # Step 5: Display the Final Result
        print("\n===== FINAL ANALYSIS REPORT =====\n")
        print(final_report)

    except Exception as e:
        logging.error(f"Pipeline failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
