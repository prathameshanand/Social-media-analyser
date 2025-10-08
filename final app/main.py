#!/usr/bin/env python3
"""
Main orchestration file for the analysis pipeline.
"""

import logging
import sys
import gc
import json
import re
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path

# Import configuration and modules
from config import (
    JSON_PATH, GGUF_PATH, PHI4_MAX_CONTEXT, NUM_MODELS, MAX_WORKERS,
    CHUNK_SIZE, CHUNK_OVERLAP, BATCH_SIZE_TOKENS, 
    TRANSLATION_MAX_LENGTH, TRANSLATION_RETRIES
)
from utils import (
    load_json, extract_texts, chunk_texts, create_processing_batches,
    translate, get_free_memory_mb
)
from cache import load_cache, save_cache
from model_manager import SingleModelManager
from analysis import process_batch, combined_analysis
print(GGUF_PATH)
# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout), # Log to console
        logging.FileHandler("analysis_log.txt")       # Log to file
    ]
)

def _robust_json_parser(text):
    """
    Attempts to extract and parse the main JSON object, which is often wrapped
    in other text or markdown by the LLM.
    
    The expected core structure is: {"multiverse_combined": {...}}
    """
    response = text.strip()
    
    try:
        # First, try to load the whole text (easiest case)
        return json.loads(response)
    except json.JSONDecodeError:
        pass # Continue to more complex extraction
        
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
        
        # Try to clean up and parse the extracted string
        # This handles common LLM errors like trailing commas or escaped quotes inside the main object
        return json.loads(json_str)

    except (ValueError, json.JSONDecodeError) as e:
        # If all extraction attempts fail, return a structured error
        logging.error(f"Failed to parse JSON: {e}")
        return {"error": "JSON_PARSE_ERROR", "message": str(e), "raw_text_start": response[:100] + "..."}

def main(json_path=None):
    try:
        # Use the provided json_path or fall back to the default
        if json_path is None:
            json_path = JSON_PATH
            
        logging.info("Starting memory-optimized parallel processing pipeline...")
        
        # Step 1: Pre-flight memory check
        model_size_mb = 7500 # Phi-4 is approx. 7GB
        required_memory_mb = model_size_mb * NUM_MODELS * 1.2
        available_memory_mb = get_free_memory_mb()
        
        logging.info(f"Available Memory: {available_memory_mb:.2f} MB")
        logging.info(f"Required Memory for {NUM_MODELS} model: {required_memory_mb:.2f} MB")

        if available_memory_mb < required_memory_mb:
            logging.warning("Insufficient memory to run with configured parallel models. Attempting to reduce.")
            num_models_to_use = 1
            required_memory_mb = model_size_mb * num_models_to_use * 1.5
            if available_memory_mb < required_memory_mb:
                logging.error("Even a single model may not fit. Exiting to prevent crash.")
                sys.exit(1)
        else:
            num_models_to_use = NUM_MODELS

        # Step 2: Load data from the specified JSON file
        logging.info(f"Extracting data from: {json_path}")
        data = load_json(json_path)

        # Only keep the first N tokens worth of text from the JSON to limit downstream cost
        MAX_TOKENS_PER_FILE = 20000
        all_texts = extract_texts(data,             max_tokens_from_file=MAX_TOKENS_PER_FILE)

        
        # Step 3: Pre-process and chunk the consolidated text
        chunks = chunk_texts(all_texts, CHUNK_SIZE, CHUNK_OVERLAP)
        translated = translate(chunks, TRANSLATION_MAX_LENGTH, TRANSLATION_RETRIES)
        
        # Step 4: Create batches for processing
        batches = create_processing_batches(translated, BATCH_SIZE_TOKENS)
        
        # Step 5: Resume from cache or start new
        # Step 5: Resume from cache or start new (per-input cache file)
        cache_dir = Path(os.environ.get("PIPELINE_CACHE_DIR", "./cache"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        per_file_cache = cache_dir / (Path(json_path).name + ".partial_results.pkl")

        partial_results = load_cache(filepath=str(per_file_cache))
        if partial_results:
            processed_batches = [r.get('batch_id') for r in partial_results]
            batches_to_process = [b for i, b in enumerate(batches) if i not in processed_batches]
            logging.info(f"Resuming pipeline. {len(partial_results)} batches already processed. {len(batches_to_process)} batches remaining. Cache: {per_file_cache}")
        else:
            partial_results = []
            batches_to_process = batches
            logging.info(f"No cache found at {per_file_cache}. Starting new pipeline from scratch.")

            
        # Step 6: Load a single LLM instance
        model_managers = []
        try:
            for _ in range(num_models_to_use):
                model_managers.append(SingleModelManager(GGUF_PATH, PHI4_MAX_CONTEXT))
        except MemoryError:
            logging.error(f"Failed to load {num_models_to_use} models due to insufficient memory. Retrying with a single model.")
            for manager in model_managers:
                del manager.model
            del model_managers
            gc.collect()
            num_models_to_use = 1
            model_managers = [SingleModelManager(GGUF_PATH, PHI4_MAX_CONTEXT)]

        logging.info(f"Loaded {len(model_managers)} model instances for parallel processing.")

        # Step 7: Process all batches concurrently
        all_batches_to_process = []
        for i, batch in enumerate(batches):
            if not any(r['batch_id'] == i for r in partial_results):
                all_batches_to_process.append((i, batch))
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(
                process_batch, 
                model_managers[i % num_models_to_use],
                batch,
                i
            ): i for i, batch in all_batches_to_process}
            
            for future in tqdm(as_completed(futures), total=len(all_batches_to_process), desc="Processing batches concurrently"):
                partial_results.append(future.result())
                save_cache(partial_results)
                
                
        logging.info("Processing complete.")
        
        # Step 8: Generate the final JSON report with streaming
        logging.info("Generating the final JSON report with streaming...")
        
        # Get the first model manager
        if model_managers:
            model_manager = model_managers[0]
        else:
            model_manager = SingleModelManager(GGUF_PATH, PHI4_MAX_CONTEXT)

        # Initialize a dictionary to hold the analysis result
        final_output = None
        
        # --- Run Original Analysis ---
        try:
            logging.info("Running combined analysis...")
            original_output = combined_analysis(model_manager, partial_results, stream_llm_if_supported=True)
            # Validate and parse the output using the robust parser
            if original_output:
                parsed_original = _robust_json_parser(original_output)
                
                # Check if parsing failed
                if "error" in parsed_original:
                    logging.error(f"Failed to parse analysis JSON output: {parsed_original.get('message', 'Unknown error')}")
                    final_output = {
                        "error": f"Failed to generate valid JSON: {parsed_original.get('message', 'Unknown error')}",
                        "multiverse_combined": {
                            "executive_summary": "",
                            "sentiment_analysis": {},
                            "topics": {}
                        }
                    }
                else:
                    # Ensure the output has the expected structure
                    if "multiverse_combined" not in parsed_original:
                        logging.warning("Analysis output doesn't contain 'multiverse_combined' key. Adding empty structure.")
                        parsed_original["multiverse_combined"] = {
                            "executive_summary": "",
                            "sentiment_analysis": {},
                            "topics": {}
                        }
                    
                    final_output = parsed_original
            else:
                final_output = {"error": "Analysis failed to produce output."}
        except Exception as e:
            logging.error(f"Failed during combined analysis: {e}")
            final_output = {"error": f"Analysis failed: {str(e)}"}

        logging.info("Final report generation complete.")
        
        # Return the JSON output as a formatted string
        return json.dumps(final_output, indent=2)
        
    except Exception as e:
        logging.error(f"Pipeline failed at a high level: {e}")
        import traceback
        traceback.print_exc()
        
        # Return a valid JSON structure with error information
        error_output = {
            "error": f"Pipeline failed: {str(e)}",
            "multiverse_combined": {
                "executive_summary": "",
                "sentiment_analysis": {},
                "topics": {}
            }
        }
        return json.dumps(error_output, indent=2)

if __name__ == "__main__":
    main()
