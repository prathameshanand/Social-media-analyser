#!/usr/bin/env python3
# Re-written test.py with memory management and multi-source JSON extraction
# Updated to use a single model instance with parallel processing
import datetime
import json
import gc
import sys
import logging
import threading
import queue
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain.text_splitter import RecursiveCharacterTextSplitter
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
from llama_cpp import Llama

# --- CONFIG ---
# Update JSON_PATH to point to your desired file
JSON_PATH = "/home/anand/Documents/data/reddit_search_output1.json"
GGUF_PATH = "/home/anand/Downloads/Qwen2.5-7B-Instruct.Q5_K_M.gguf"
# Increased context length for Qwen2.5 model
QWEN_MAX_CONTEXT = 32768
# Settings for concurrent processing
MAX_WORKERS = 8 # Matches your CPU threads
MODEL_THREADS = 8 # Dedicate threads to the model, leaving some for other tasks
CHUNK_SIZE = 1800
CHUNK_OVERLAP = 180
BATCH_SIZE_TOKENS = 14000

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

def chunk_texts(texts, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Splits texts into larger, overlapping chunks for better context utilization."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
    return [d.page_content for d in splitter.create_documents(texts)]

def estimate_tokens(text):
    """Rough estimation of token count (1 token ≈ 4 characters for most models)."""
    return len(text) // 7

def create_processing_batches(chunks, max_tokens_per_batch=BATCH_SIZE_TOKENS):
    """Creates batches of chunks that fit within the token limit."""
    batches = []
    current_batch = []
    current_tokens = 0
    
    for chunk in chunks:
        chunk_tokens = estimate_tokens(chunk)
        if current_tokens + chunk_tokens > max_tokens_per_batch and current_batch:
            batches.append(current_batch)
            current_batch = [chunk]
            current_tokens = chunk_tokens
        else:
            current_batch.append(chunk)
            current_tokens += chunk_tokens
    
    if current_batch:
        batches.append(current_batch)
    
    return batches

def is_english(txt):
    """Checks if a string is predominantly English."""
    return sum(1 for c in txt if ord(c) < 128) / max(1, len(txt)) > 0.9

def translate(chunks):
    """Translates non-English text chunks to English using an ML model."""
    try:
        tok = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-mul-en")
        model = AutoModelForSeq2SeqLM.from_pretrained("Helsinki-NLP/opus-mt-mul-en")
        trans = pipeline("translation", model=model, tokenizer=tok)
    except Exception as e:
        logging.error(f"Failed to load translation model: {e}")
        return chunks
    out = []
    for c in tqdm(chunks, desc="Translating"):
        try:
            if is_english(c):
                out.append(c)
            else:
                out.append(trans(c, max_length=512)[0]["translation_text"])
        except Exception as e:
            logging.warning(f"Translation failed for chunk: {e}")
            out.append(c)
    return out

# --- Single Model Manager ---
class SingleModelManager:
    """Manages a single LLM instance for concurrent requests."""
    def __init__(self, model_path, n_ctx):
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.model = None
        self.lock = threading.Lock()
        self._load_model()
    
    def _load_model(self):
        try:
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=MODEL_THREADS,
                verbose=False,
                n_gpu_layers=0,
                n_parallel=2
            )
            logging.info(f"Single model instance loaded with {self.n_ctx} context length.")
        except Exception as e:
            logging.error(f"Failed to load LLM: {e}")
            sys.exit(1)
            
    def generate(self, prompt, max_tokens):
        with self.lock:
            try:
                response = self.model(prompt, max_tokens=max_tokens, echo=False)
                return response["choices"][0]["text"].strip()
            except Exception as e:
                return f"ERROR: {str(e)}"

# --- New parallel processing functions ---
def process_batch(model_manager, batch, batch_id):
    """Processes a single batch and returns a partial result."""
    text_batch = "\n\n".join(batch)
    prompt = f"Analyze the following text content and provide a summary of the key points:\n\n{text_batch}\n\nSummary:"
    result = model_manager.generate(prompt, max_tokens=1500)
    
    return {
        'batch_id': batch_id,
        'result': result,
        'status': 'success' if 'ERROR' not in result else 'error'
    }

def concurrent_batch_processing(model_manager, batches):
    """
    Processes all batches in parallel using a single model instance.
    """
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_batch, model_manager, batch, i): i for i, batch in enumerate(batches)}
        
        for future in tqdm(as_completed(futures), total=len(batches), desc="Processing batches concurrently"):
            results.append(future.result())
            
    results.sort(key=lambda x: x['batch_id'])
    return [r['result'] for r in results]

def consolidate_reports(llm, partial_results):
    """Consolidates partial reports into a final, comprehensive report with an XML structure."""
    consolidated_text = "\n\n---\n\n".join(partial_results)
    
    final_prompt = f"""<report>
<instructions>
Consolidate the following partial analyses into a single, comprehensive final report.
The output must ONLY contain the final report within the specified XML tags.
Do not include any other text, comments, or explanations.
</instructions>
<input>
{consolidated_text}
</input>
<output_format>
<final_report>
    <detailed_summary>
        [A single, comprehensive summary of all key points from the input. Synthesize findings and do not repeat information. Include specific examples and key takeaways from the data.]
    </detailed_summary>
    <sentiment_analysis>
        <sentiment_breakdown>
            [Provide a percentage breakdown for Positive, Negative, and Neutral sentiments based on the data.]
        </sentiment_breakdown>
        <reasoning_and_examples>
            [For each sentiment category, provide the reasoning for its classification and include specific quotes or examples from the data to support the analysis.]
        </reasoning_and_examples>
    </sentiment_analysis>
</final_report>
</output_format>
</report>
"""
    
    return llm.generate(final_prompt, max_tokens=5000)


def consolidate_reports(llm, partial_results):
    """Consolidates partial reports into a final, comprehensive report with an XML structure."""
    consolidated_text = "\n\n---\n\n".join(partial_results)
    
    final_prompt = f"""<report>
<instructions>
Consolidate the following partial analyses into a single, comprehensive final report.
The output must ONLY contain the final report within the specified XML tags.
Do not include any other text, comments, or explanations.
</instructions>
<input>
{consolidated_text}
</input>
<output_format>
<final_report>
    <Crises Detections>
        [Detect keywords and analysis the .]
    </detailed_summary>
    <sentiment_analysis>
        <sentiment_breakdown>
            [Provide a percentage breakdown for Positive, Negative, and Neutral sentiments based on the data.]
        </sentiment_breakdown>
        <reasoning_and_examples>
            [For each sentiment category, provide the reasoning for its classification and include specific quotes or examples from the data to support the analysis.]
        </reasoning_and_examples>
    </sentiment_analysis>
</final_report>
</output_format>
</report>
"""
    
    return llm.generate(final_prompt, max_tokens=2500)
    
    
    
    
def extract_topics_hierarchy(llm, partial_results):
    """
    Extract top-level topics and hierarchical subtopics from consolidated text.
    Input: partial_results - list[str] (each element is a text chunk or partial summary)
    Output: an XML document (string) matching the <topics_list> schema. The model MUST return
            ONLY the XML document (no extra text).
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()
    consolidated_text = "\n\n---\n\n".join(partial_results)
    
    final_prompt = f"""<request>
  <instructions>
    Extract up to 25 topics from <input>. For each topic return title, short description (1-3 sentences),
    relevance_score (0..1), up to 5 subtopics (title, description, relevance_score),
    up to 3 representative <snippet chunk_id="">...</snippet>, and supporting_chunks (CSV).
    OUTPUT ONLY a single well-formed <topics_list> XML document. No extra text.
  </instructions>

  <input>
{consolidated_text}
  </input>

  <output_schema>
    
      <topic id="">
        <title></title>
        <description></description>
        <relevance_score></relevance_score>
        <subtopics>
          <subtopic id="">
            <title></title>
            <description></description>
            <relevance_score></relevance_score>
          </subtopic>
        </subtopics>
        <representative_snippets>
          <snippet chunk_id="">...</snippet>
        </representative_snippets>
        <supporting_chunks></supporting_chunks>
      </topic>
      <prompt_snapshot></prompt_snapshot>
    </topics_list>
  </output_schema>
</request>
"""

    return llm.generate(final_prompt, max_tokens=3000)

# --- MAIN ---
def main():
    try:
        logging.info("Starting memory-optimized parallel processing pipeline...")
        
        # Step 1: Data Pre-processing
        data = load_json(JSON_PATH)
        texts = extract_texts(data)
        chunks = chunk_texts(texts)
        logging.info(f"Extracted {len(texts)} texts, created {len(chunks)} chunks.")
        
        translated = translate(chunks)
        logging.info("Translation complete.")
        
        # Step 2: Create batches
        batches = create_processing_batches(translated)
        logging.info(f"Created {len(batches)} processing batches.")

        # Step 3: Load single LLM instance
        model_manager = SingleModelManager(GGUF_PATH, QWEN_MAX_CONTEXT)
        logging.info("Single Qwen2.5 model instance ready.")

        # Step 4: Process batches concurrently with the single model
        logging.info(f"Starting concurrent processing with {MAX_WORKERS} workers.")
        partial_results = concurrent_batch_processing(model_manager, batches)
        logging.info(f"Processed {len(partial_results)} batches.")
        
        # Step 5: Consolidate and generate the final report
        logging.info("Consolidating and generating final report...")
        #final_report = consolidate_reports(model_manager, partial_results)
        final_report = extract_topics_hierarchy(model_manager, partial_results)
        logging.info("Analysis complete.")

        # Step 6: Display the Final Result
        print("\n===== FINAL ANALYSIS REPORT =====\n")
        print(final_report)
        print("\n" + "="*len("===== FINAL ANALYSIS REPORT =====") + "\n")
        
        # Cleanup
        del model_manager
        gc.collect()
        logging.info("Memory cleanup completed.")

    except Exception as e:
        logging.error(f"Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

