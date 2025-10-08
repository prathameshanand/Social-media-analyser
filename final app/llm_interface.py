#!/usr/bin/env python3
"""
LLM interface functions for the analysis pipeline.
"""

import logging
import time
import hashlib
from utils import _iso_now

_prompt_cache = {}

def lm_call_cached(llm, prompt, max_tokens, temperature=0.0, stream=False, stream_handler=None, stop_phrases=None):
    """
    Calls the LLM with caching and optional streaming.
    - stop_phrases: list of strings; if any appears in a chunk, stop consuming further stream.
    - If stream_handler returns False, the stream is aborted.
    """
    import hashlib, time, logging
    prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
    if prompt_hash in _prompt_cache:
        logging.info(f"[{_iso_now()}] Cache hit for prompt hash {prompt_hash[:8]}")
        return _prompt_cache[prompt_hash]

    start_time = time.time()
    response = ""
    stop_phrases = stop_phrases or [
        "### Stop", "### Stopping now",
        "Stopping now as tokens remaining", "### Stop stream", "### Stop\""
    ]
    last_chunk = None
    repeated_counter = 0
    MAX_REPEATED = 6

    try:
        if stream and hasattr(llm, 'generate_stream'):
            logging.info(f"[{_iso_now()}] Calling LLM with streaming...")
            collected = []
            for chunk in llm.generate_stream(prompt, max_tokens=max_tokens, temperature=temperature):
                # normalize chunk to text
                if isinstance(chunk, dict):
                    text_chunk = ""
                    try:
                        if "choices" in chunk and isinstance(chunk["choices"], list) and len(chunk["choices"])>0:
                            text_chunk = chunk["choices"][0].get("text","")
                        elif "text" in chunk:
                            text_chunk = chunk.get("text","")
                        else:
                            text_chunk = str(chunk)
                    except Exception:
                        text_chunk = str(chunk)
                else:
                    text_chunk = str(chunk)

                if not text_chunk:
                    continue

                # deduplicate identical consecutive chunks
                if last_chunk is not None and text_chunk.strip() == last_chunk.strip():
                    repeated_counter += 1
                    if repeated_counter > MAX_REPEATED:
                        logging.warning("Detected many repeated identical chunks; breaking stream.")
                        break
                    # skip adding duplicate chunk
                    continue
                else:
                    repeated_counter = 0
                    last_chunk = text_chunk

                # call stream handler; if it returns False, abort
                if stream_handler:
                    try:
                        cont = stream_handler(text_chunk)
                        if cont is False:
                            logging.info("Stream handler requested abort. Stopping stream consumption.")
                            break
                    except Exception as e:
                        logging.warning(f"Stream handler error: {e}")

                collected.append(text_chunk)

                # stop if any configured stop phrase appears in chunk
                lowered = text_chunk.lower()
                if any(sp.lower() in lowered for sp in stop_phrases):
                    logging.info("Detected stop phrase in chunk; ending stream consumption.")
                    break

            response = "".join(collected)
        else:
            logging.info(f"[{_iso_now()}] Calling LLM without streaming...")
            raw = llm.generate(prompt, max_tokens=max_tokens, temperature=temperature)
            if isinstance(raw, dict) and 'choices' in raw and len(raw['choices']) > 0:
                response = raw['choices'][0]['text'].strip()
            elif isinstance(raw, str):
                response = raw
            else:
                logging.error(f"Unexpected response format from LLM: {type(raw)}")
                response = f"ERROR: Unexpected LLM response format."

    except Exception as e:
        logging.error(f"LLM call failed: {e}")
        response = f"ERROR: {str(e)}"

    elapsed_time = time.time() - start_time
    logging.info(f"[{_iso_now()}] LLM call completed in {elapsed_time:.2f} seconds.")
    _prompt_cache[prompt_hash] = response
    return response


def call_llm_and_stream_to_terminal_and_file(llm, prompt, max_tokens,
                                             out_filepath="final_analysis_report.json",
                                             temperature=0.0,
                                             enable_stream=True,
                                             custom_stream_handler=None,
                                             stop_phrases=None):
    """
    Call LLM with streaming, print to terminal and save to file.
    - custom_stream_handler: optional(user_func) that receives chunk text. If it returns False -> abort.
    - stop_phrases: list of phrases to detect end-of-stream markers inside chunks.
    """
    try:
        out_fp = open(out_filepath, "w", encoding="utf-8")
    except Exception as e:
        logging.error(f"Unable to open output file '{out_filepath}': {e}")
        out_fp = None

    streamed_any_chunk = {"value": False}
    last_printed = ""
    repeated_stop_count = 0
    MAX_STOP_REPEATS = 6

    def _stream_handler(chunk_text: str):
        nonlocal last_printed, repeated_stop_count
        text = "" if chunk_text is None else str(chunk_text)

        # avoid printing exact duplicate consecutive lines
        if text.strip() == last_printed.strip():
            repeated_stop_count += 1
            if repeated_stop_count > MAX_STOP_REPEATS:
                logging.warning("Repeated stop line detected many times; requesting abort.")
                return False
            return True

        last_printed = text
        repeated_stop_count = 0

        # print to console
        try:
            print(text, end="", flush=True)
        except Exception:
            try:
                import sys
                sys.stdout.write(text)
                sys.stdout.flush()
            except Exception as e:
                logging.debug(f"Failed to print chunk: {e}")

        # save to file
        if out_fp is not None:
            try:
                out_fp.write(text)
                out_fp.flush()
            except Exception as e:
                logging.warning(f"Failed to write chunk to file: {e}")

        # call custom handler; if it returns False, abort streaming
        if custom_stream_handler:
            try:
                cont = custom_stream_handler(text)
                if cont is False:
                    return False
            except Exception as e:
                logging.warning(f"Custom stream handler error: {e}")

        streamed_any_chunk["value"] = True
        return True

    # start marker
    print("\n===== START OF STREAMED ANALYSIS =====\n", flush=True)

    response = ""
    try:
        response = lm_call_cached(
            llm,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=enable_stream and hasattr(llm, "generate_stream"),
            stream_handler=_stream_handler,
            stop_phrases=stop_phrases
        )
    except TypeError as e:
        logging.warning(f"lm_call_cached signature mismatch: {e}. Falling back to non-streaming.")
        try:
            response = lm_call_cached(llm, prompt, max_tokens=max_tokens, temperature=temperature, stream=False)
        except Exception as e2:
            logging.exception(f"Non-streaming fallback failed: {e2}")
            response = f"ERROR: {e2}"
    except Exception as e:
        logging.exception(f"LLM call failed: {e}")
        try:
            response = lm_call_cached(llm, prompt, max_tokens=max_tokens, temperature=temperature, stream=False)
        except Exception as e2:
            logging.exception(f"Non-streaming fallback failed: {e2}")
            response = f"ERROR: {e2}"

    # ensure final output present if no streaming occurred
    try:
        if not streamed_any_chunk["value"]:
            if response:
                print(response, end="", flush=True)
                if out_fp is not None:
                    try:
                        out_fp.seek(0, 2)
                        if out_fp.tell() == 0:
                            out_fp.write(response)
                            out_fp.flush()
                    except Exception as e:
                        logging.warning(f"Failed to ensure final response in file: {e}")
        else:
            print("\n", flush=True)
    except Exception as e:
        logging.debug(f"Error ensuring final output: {e}")

    # end marker
    print("\n\n===== END OF STREAMED ANALYSIS =====\n", flush=True)

    try:
        if out_fp is not None:
            out_fp.close()
    except Exception:
        pass

    return response
