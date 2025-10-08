#!/usr/bin/env python3
"""
Main orchestration file for the analysis pipeline - V2 only.

The primary function has been renamed from 'main' to 'run_v2_analysis' 
to allow for clean import into Streamlit and distinguish it from main.py.
"""

import logging
import sys
import gc
import json
import re
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import os
from pathlib import Path

# Import configuration and modules (assuming these exist in your environment)
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
from analysis import process_batch, combined_analysis_V2 # combined_analysis_V2 generates the V2 schema

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout), # Log to console
        logging.FileHandler("analysis_log.txt")       # Log to file
    ]
)

def run_v2_analysis(json_path=None):
    """
    Runs the full V2 analysis pipeline (Entity Recognition, Relationships, Anomaly, Controversy)
    and returns the final result as a JSON string.
    """
    try:
        # Use the provided json_path or fall back to the default
        if json_path is None:
            json_path = JSON_PATH
            
        logging.info("Starting memory-optimized parallel processing pipeline...")
        
        # Step 1: Pre-flight memory check (simplified for code review, retaining original structure)
        model_size_mb = 7500 # Phi-4 is approx. 7GB
        required_memory_mb = model_size_mb * NUM_MODELS * 1.2
        available_memory_mb = get_free_memory_mb()
        
        logging.info(f"Available Memory: {available_memory_mb:.2f} MB")
        logging.info(f"Required Memory for {NUM_MODELS} model: {required_memory_mb:.2f} MB")

        if available_memory_mb < required_memory_mb:
            logging.warning("Insufficient memory to run with configured parallel models. Attempting to reduce.")
            num_models_to_use = 1
        else:
            num_models_to_use = NUM_MODELS

        # Step 2: Load data from the specified JSON file
        logging.info(f"Extracting data from: {json_path}")
        data = load_json(json_path)

# Only keep the first N tokens worth of text from the JSON to limit downstream cost
        MAX_TOKENS_PER_FILE = 20000
        all_texts = extract_texts(data,         max_tokens_from_file=MAX_TOKENS_PER_FILE)

        
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
            logging.info(f"Resuming pipeline. {len(partial_results)} batches already processed. Cache: {per_file_cache}")
            # determine which batches remain
            batches_to_process = [b for i, b in enumerate(batches) if not any(r.get('batch_id') == i for r in partial_results)]
        else:
            partial_results = []
            batches_to_process = batches
            logging.info(f"No cache found at {per_file_cache}. Starting new pipeline from scratch.")

            
        # Step 6: Load LLM instance(s)
        model_managers = [SingleModelManager(GGUF_PATH, PHI4_MAX_CONTEXT) for _ in range(num_models_to_use)]
        logging.info(f"Loaded {len(model_managers)} model instances for parallel processing.")

        # Step 7: Process all batches concurrently
        all_batches_to_process_indexed = [(i, batch) for i, batch in enumerate(batches) if not any(r['batch_id'] == i for r in partial_results)]
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(
                process_batch, 
                model_managers[i % num_models_to_use],
                batch,
                i
            ): i for i, batch in all_batches_to_process_indexed}
            
            for future in tqdm(as_completed(futures), total=len(all_batches_to_process_indexed), desc="Processing batches concurrently"):
                partial_results.append(future.result())
                save_cache(partial_results)
             
                
        logging.info("Processing complete.")
        print("length of partial results are this :",len(partial_results))
        
        # Step 8: Generate the final JSON report with streaming
        logging.info("Generating the final JSON report with streaming...")
        
        model_manager = model_managers[0] if model_managers else SingleModelManager(GGUF_PATH, PHI4_MAX_CONTEXT)
        final_json_output = combined_analysis_V2(model_manager, partial_results, stream_llm_if_supported=True)
        logging.info("Final JSON report generation complete.")
        
        # Validation and Formatting
        if final_json_output:
            try:
                parsed_output = json.loads(final_json_output)
                # Ensure the top-level key is 'multiverse_combined' as expected by Streamlit
                if "multiverse_combined" not in parsed_output:
                    parsed_output = {"multiverse_combined": parsed_output}
                final_json_output = json.dumps(parsed_output, indent=2)
                
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse JSON output: {e}")
                # Return a structured error
                error_output = {"multiverse_combined": {"error": f"Failed to generate valid JSON: {str(e)}"}}
                final_json_output = json.dumps(error_output, indent=2)
        
        return final_json_output
        
    except Exception as e:
        logging.error(f"Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Return a structured error
        error_output = {"multiverse_combined": {"error": f"Pipeline failed: {str(e)}"}}
        return json.dumps(error_output, indent=2)

if __name__ == "__main__":
    # If run directly, print the result to stdout
    print(run_v2_analysis())
