#!/usr/bin/env python3
"""
Configuration constants for the analysis pipeline.
"""

# File paths
JSON_PATH = "/home/anand/Documents/data/reddit_search_output1.json"
GGUF_PATH = "/home/anand/Downloads/phi4.gguf"
CACHE_FILE = "partial_results.pkl"
LOG_FILE = "analysis_log.txt"

# Model settings
PHI4_MAX_CONTEXT = 16384
NUM_MODELS = 1
MAX_WORKERS = 8
MODEL_THREADS = 6

# Text processing settings
CHUNK_SIZE = 1800
CHUNK_OVERLAP = 180
BATCH_SIZE_TOKENS = 14000
FINAL_REPORT_TOKENS = 8000
TRANSLATION_MAX_LENGTH = 512
TRANSLATION_RETRIES = 3
