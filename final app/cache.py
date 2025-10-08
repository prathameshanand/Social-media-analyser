#!/usr/bin/env python3
"""
Cache management functions for the analysis pipeline.
Robustly handles relative filenames (no empty dirname), configurable cache dir,
atomic writes, and per-input-file caches.
"""
import os
import pickle
import logging
from pathlib import Path
from config import CACHE_FILE  # keep existing default if you want

# Default cache dir (can be overridden by env var PIPELINE_CACHE_DIR)
_CACHE_DIR = Path(os.environ.get("PIPELINE_CACHE_DIR", "./cache"))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _resolve_path(filepath: str) -> Path:
    """
    Resolve a filepath to a Path under _CACHE_DIR if it has no directory component.
    Ensure parent directory exists.
    """
    p = Path(filepath)
    if str(p.parent) in (".", ""):
        # user supplied only filename -> place under cache dir
        p = _CACHE_DIR / p.name
    # Make sure parent dir exists
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def load_cache(filepath: str = CACHE_FILE):
    """Load data from pickle file or return None if not present/corrupt."""
    try:
        p = _resolve_path(filepath)
    except Exception as e:
        logging.error(f"Invalid cache path '{filepath}': {e}")
        return None

    if not p.exists():
        return None
    try:
        with p.open("rb") as f:
            data = pickle.load(f)
        logging.info(f"Successfully loaded progress from cache: {p}")
        return data
    except Exception as e:
        logging.error(f"Failed to load cache {p}: {e}")
        return None

def save_cache(data, filepath: str = CACHE_FILE):
    """Save data to pickle file (atomic write)."""
    try:
        p = _resolve_path(filepath)
        tmp = p.with_suffix(p.suffix + ".tmp")
        # write atomically
        with tmp.open("wb") as f:
            pickle.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(p)
        logging.info(f"Successfully saved progress to cache: {p}")
    except Exception as e:
        logging.error(f"Failed to save cache '{filepath}': {e}")
