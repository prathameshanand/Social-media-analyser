from main import main
from main1 import run_v2_analysis

def combine_analysis(json_path):
	print("Analysis are starting")
	a = main(json_path)
	print(a)
	b = run_v2_analysis(json_path)
	print(b)
	print("Both analysis are comlete")


path = "/home/anand/Documents/data/reddit_search_output56498.json"
combine_analysis(path)
#!/usr/bin/env python3
"""
combine_to_single_json.py

# Controller script:
# - Scans /home/anand/Documents/data for your target files.
# - For each file (one at a time) calls:
#     a_result = main(json_path)            # from main.py
#     b_result = run_v2_analysis(json_path) # from main1.py
# - Token threshold: TOKEN_BUDGET (5000). If >= TOKEN_BUDGET treat as 'breached' and do NOT save the raw output (to avoid hallucination).
# - All results are stored as entries in a single combined JSON file: outputs/combined_results.json
# - Checkpoint file: processed_files.json
# """
# import os
# import json
# import time
# import importlib.util
# import math
# from pathlib import Path
# from typing import Any, Dict, Optional, List

# # ---------- CONFIG ----------
# DATA_DIR = Path("/home/anand/Documents/data")
# OUTPUT_DIR = Path("./outputs")
# OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
# COMBINED_OUTPUT_FILE = OUTPUT_DIR / "combined_results.json"
# CHECKPOINT_FILE = Path("processed_files.json")
# TOKEN_BUDGET = 1000  # threshold per-call
# # exact filenames you listed
# FILENAME_PATTERNS = [
#     "reddit_search_output1.json"
    
# ]


# # ---------- Helpers ----------
# def load_checkpoint() -> Dict[str, Any]:
#     if CHECKPOINT_FILE.exists():
#         try:
#             return json.loads(CHECKPOINT_FILE.read_text(encoding="utf-8"))
#         except Exception:
#             return {}
#     return {}

# def save_checkpoint(cp: Dict[str, Any]) -> None:
#     CHECKPOINT_FILE.write_text(json.dumps(cp, indent=2), encoding="utf-8")

# def list_target_files() -> List[Path]:
#     all_files = []
#     for name in FILENAME_PATTERNS:
#         p = DATA_DIR / name
#         if p.exists():
#             all_files.append(p)
#     # If you want fuzzy matching (e.g., prefixes), uncomment and adjust:
#     # for prefix in ("reddit_data", "tweets_output", "youtube_search_output"):
#     #     for p in sorted(DATA_DIR.glob(f"{prefix}*.json")):
#     #         if p not in all_files:
#     #             all_files.append(p)
#     return sorted(all_files)

# def safe_import(module_path: Path, module_name: str):
#     """Import a module by path and return it; raises informative error if not found."""
#     if not module_path.exists():
#         raise FileNotFoundError(f"Module file not found: {module_path}")
#     spec = importlib.util.spec_from_file_location(module_name, str(module_path))
#     module = importlib.util.module_from_spec(spec)
#     spec.loader.exec_module(module)
#     return module

# # Token estimation: use tiktoken if available; else fallback heuristic
# def estimate_tokens(text: str) -> int:
#     text = text or ""
#     try:
#         import tiktoken  # type: ignore
#         enc = tiktoken.get_encoding("cl100k_base")
#         return len(enc.encode(text))
#     except Exception:
#         # fallback heuristic: avg 4 chars per token
#         return max(0, math.ceil(len(text) / 4.0))

# def append_combined_entry(entry: Dict[str, Any]) -> None:
#     """
#     Append an entry to the combined JSON file (as an array).
#     This reads the existing file, appends, and writes atomically.
#     """
#     combined = []
#     if COMBINED_OUTPUT_FILE.exists():
#         try:
#             combined = json.loads(COMBINED_OUTPUT_FILE.read_text(encoding="utf-8"))
#             if not isinstance(combined, list):
#                 combined = []
#         except Exception:
#             combined = []
#     combined.append(entry)
#     COMBINED_OUTPUT_FILE.write_text(json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8")

# # ---------- Main flow ----------
# def main_loop():
#     # checkpoint structure: {"processed": { "<path>": {...} } }
#     cp = load_checkpoint()
#     processed = cp.get("processed", {})

#     # import analysis modules
#     try:
#         main_mod = safe_import(Path("main.py"), "main_module")
#     except Exception as e:
#         print(f"ERROR: could not import main.py: {e}")
#         return

#     try:
#         v2_mod = safe_import(Path("main1.py"), "main1_module")
#     except Exception as e:
#         print(f"ERROR: could not import main1.py: {e}")
#         return

#     # check functions exist
#     if not hasattr(main_mod, "main"):
#         print("ERROR: main.py does not expose `main(json_path)`")
#         return
#     if not hasattr(v2_mod, "run_v2_analysis"):
#         print("ERROR: main1.py does not expose `run_v2_analysis(json_path)`")
#         return

#     files = list_target_files()
#     if not files:
#         print(f"No target files found in {DATA_DIR}. Exiting.")
#         return

#     for fp in files:
#         fp_str = str(fp)
#         if fp_str in processed and processed[fp_str].get("status") == "done":
#             print(f"Skipping already processed: {fp.name}")
#             continue

#         print(f"\n=== Processing file: {fp.name} ===")
#         file_record = {"status": "processing", "file": fp.name, "steps": {}}
#         processed[fp_str] = file_record
#         save_checkpoint({"processed": processed})

#         combined_entry = {
#             "file_name": fp.name,
#             "file_path": fp_str,
#             "processed_at": None,
#             "main": None,   # will hold metadata and output or null
#             "v2": None,     # same for v2
#         }

#         # CALL A: main(json_path)
#         try:
#             print("Calling main(...) from main.py ...")
#             a_result = main_mod.main(fp_str)
#         except Exception as e:
#             print(f"Error running main({fp.name}): {e}")
#             file_record["steps"]["main_error"] = str(e)
#             a_result = None

#         # evaluate a_result token count and record
#         if a_result is None:
#             file_record["steps"]["main_status"] = "no_output"
#             combined_entry["main"] = {
#                 "status": "no_output",
#                 "tokens": 0,
#                 "output": None,
#                 "note": "main() raised exception or returned None"
#             }
#             print("main produced no output (exception).")
#         else:
#             # convert to text for tokenization
#             if isinstance(a_result, (dict, list)):
#                 try:
#                     a_text = json.dumps(a_result, ensure_ascii=False)
#                 except Exception:
#                     a_text = str(a_result)
#             else:
#                 a_text = str(a_result)

#             a_tokens = estimate_tokens(a_text)
#             file_record["steps"]["main_tokens"] = a_tokens
#             print(f"main() produced approx {a_tokens} tokens.")

#             if a_tokens >= TOKEN_BUDGET:
#                 file_record["steps"]["main_status"] = "breached_tokens"
#                 combined_entry["main"] = {
#                     "status": "breached_tokens",
#                     "tokens": a_tokens,
#                     "output": None,
#                     "note": f"Token budget >= {TOKEN_BUDGET}; output discarded"
#                 }
#                 print(f"Token budget breached for main() (>= {TOKEN_BUDGET}). Output not saved to combined file.")
#             else:
#                 file_record["steps"]["main_status"] = "saved"
#                 combined_entry["main"] = {
#                     "status": "saved",
#                     "tokens": a_tokens,
#                     "output": a_result
#                 }
#                 print("main output accepted and recorded in combined file.")

#         # CALL B: run_v2_analysis(json_path)
#         try:
#             print("Calling run_v2_analysis(...) from main1.py ...")
#             b_result = v2_mod.run_v2_analysis(fp_str)
#         except Exception as e:
#             print(f"Error running run_v2_analysis({fp.name}): {e}")
#             file_record["steps"]["v2_error"] = str(e)
#             b_result = None

#         if b_result is None:
#             file_record["steps"]["v2_status"] = "no_output"
#             combined_entry["v2"] = {
#                 "status": "no_output",
#                 "tokens": 0,
#                 "output": None,
#                 "note": "run_v2_analysis() raised exception or returned None"
#             }
#             print("run_v2_analysis produced no output (exception).")
#         else:
#             if isinstance(b_result, (dict, list)):
#                 try:
#                     b_text = json.dumps(b_result, ensure_ascii=False)
#                 except Exception:
#                     b_text = str(b_result)
#             else:
#                 b_text = str(b_result)

#             b_tokens = estimate_tokens(b_text)
#             file_record["steps"]["v2_tokens"] = b_tokens
#             print(f"run_v2_analysis() produced approx {b_tokens} tokens.")

#             if b_tokens >= TOKEN_BUDGET:
#                 file_record["steps"]["v2_status"] = "breached_tokens"
#                 combined_entry["v2"] = {
#                     "status": "breached_tokens",
#                     "tokens": b_tokens,
#                     "output": None,
#                     "note": f"Token budget >= {TOKEN_BUDGET}; output discarded"
#                 }
#                 print(f"Token budget breached for run_v2_analysis() (>= {TOKEN_BUDGET}). Output not saved to combined file.")
#             else:
#                 file_record["steps"]["v2_status"] = "saved"
#                 combined_entry["v2"] = {
#                     "status": "saved",
#                     "tokens": b_tokens,
#                     "output": b_result
#                 }
#                 print("run_v2_analysis output accepted and recorded in combined file.")

#         # finalize entry
#         now_ts = time.strftime("%Y-%m-%d %H:%M:%S")
#         combined_entry["processed_at"] = now_ts

#         # append entry to combined results file
#         append_combined_entry(combined_entry)
#         print(f"Appended combined entry for {fp.name} to {COMBINED_OUTPUT_FILE}")

#         # mark file processed in checkpoint
#         file_record["status"] = "done"
#         file_record["processed_at"] = now_ts
#         processed[fp_str] = file_record
#         save_checkpoint({"processed": processed})
#         print(f"Completed processing {fp.name}. Checkpoint updated.")

#     print("\nAll target files processed. Combined output available at:", COMBINED_OUTPUT_FILE)


# if __name__ == "__main__":
#     main_loop()
