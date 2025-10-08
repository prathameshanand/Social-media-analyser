#!/usr/bin/env python3
"""
Model management classes for the analysis pipeline.
"""

import logging
import sys
import threading
from config import MODEL_THREADS
from llm_interface import lm_call_cached

try:
    from llama_cpp import Llama
except ImportError:
    logging.error("The 'llama_cpp' library is not installed. Please install it using: pip install llama-cpp-python")
    sys.exit(1)

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
            logging.error(f"Please verify that the GGUF file path is correct: {self.model_path}")
            sys.exit(1)
            
    def generate(self, prompt, max_tokens):
        with self.lock:
            try:
                response = self.model(prompt, max_tokens=max_tokens, echo=False)
                return response["choices"][0]["text"].strip()
            except Exception as e:
                return f"ERROR: {str(e)}"
    
    def generate_stream(self, prompt, max_tokens, temperature):
        with self.lock:
            try:
                for chunk in self.model(prompt, max_tokens=max_tokens, echo=False, stream=True):
                    yield chunk['choices'][0]['text']
            except Exception as e:
                logging.error(f"Streaming failed: {e}")
                return