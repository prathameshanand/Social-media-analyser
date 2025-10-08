#!/usr/bin/env python3
"""
Streamlit UI that integrates with either main1.run_v2_analysis or main.main.
It captures stdout/stderr emitted by the analysis function (so streamed JSON printed to console is captured)
and then attempts to extract the JSON object {"multiverse_combined": ...} for display.
"""

import streamlit as st
import json
import os
import tempfile
import logging
import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from typing import Optional

# Attempt imports from main1.py and main.py (try main1 first as user requested)
run_v2_analysis = None
main_analysis_fn = None
import_error_messages = []

try:
    from main1 import run_v2_analysis as _run_v2
    run_v2_analysis = _run_v2
except Exception as e:
    import_error_messages.append(f"main1 import failed: {e}")
    logging.debug(import_error_messages[-1])

# fallback: try main.main (some setups use main.main(path) -> returns JSON string)
try:
    if run_v2_analysis is None:
        from main import main as _main_fn
        main_analysis_fn = _main_fn
except Exception as e:
    import_error_messages.append(f"main import failed: {e}")
    logging.debug(import_error_messages[-1])

def _robust_json_parser(text: str) -> dict:
    """
    Attempts to extract and parse the main JSON object from arbitrary text.
    Expected core structure: {"multiverse_combined": {...}}
    Returns a dict or an error dict.
    """
    if not isinstance(text, str):
        text = str(text or "")

    response = text.strip()
    # fast path: whole-text JSON
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # find first '{' and attempt to find matching closing brace
    start_idx = response.find('{')
    if start_idx == -1:
        return {"error": "JSON_PARSE_ERROR", "message": "No '{' found in output", "raw_text_start": response[:200] + "..."}

    brace_count = 0
    end_idx = -1
    for i in range(start_idx, len(response)):
        ch = response[i]
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = i
                break

    if end_idx == -1:
        return {"error": "JSON_PARSE_ERROR", "message": "Unmatched braces in output", "raw_text_start": response[:200] + "..."}

    json_str = response[start_idx:end_idx + 1]
    # attempt direct parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # try small repairs: replace single quotes, remove trailing commas
        repaired = json_str.replace("'", "\"").replace(",}", "}").replace(",]", "]")
        try:
            return json.loads(repaired)
        except Exception as e:
            logging.exception("Failed to parse extracted JSON: %s", e)
            return {"error": "JSON_PARSE_ERROR", "message": str(e), "raw_text_start": response[:200] + "..."}

def _call_analysis_and_capture(func, input_path: str) -> str:
    """
    Calls the provided analysis function and captures any stdout/stderr produced.
    - func: callable that accepts one argument (path) or zero args (if main-like).
    Returns the most-likely JSON string output (either return value or captured stdout).
    """
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    result_value = None

    # Some functions accept a filepath argument; others may not.
    # We'll try calling with the path first, then fallback to calling without args.
    try:
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            try:
                # prefer calling with the input_path (main1.run_v2_analysis or main.main)
                result_value = func(input_path)
            except TypeError:
                # function may not accept args
                result_value = func()
    except Exception as e:
        # Capture any exception text and return it as captured output for debugging
        logging.exception("Analysis function raised an exception: %s", e)
        buf_err.write(f"\nException: {e}\n")
        # include traceback too
        import traceback
        buf_err.write(traceback.format_exc())

    captured_out = buf_out.getvalue() or ""
    captured_err = buf_err.getvalue() or ""
    # Prefer explicit return value if it's a non-empty string
    if isinstance(result_value, str) and result_value.strip():
        return result_value
    # If result_value is dict/json-like, stringify it
    if isinstance(result_value, (dict, list)):
        try:
            return json.dumps(result_value, ensure_ascii=False)
        except Exception:
            # fallback to string conversion
            return str(result_value)
    # else if nothing returned, but stdout captured, return that
    if captured_out.strip():
        # combine stdout and stderr (stdout first) to preserve streamed JSON lines
        if captured_err.strip():
            return captured_out + "\n---STDERR---\n" + captured_err
        return captured_out
    # if there's stderr only, return that
    if captured_err.strip():
        return captured_err
    # nothing captured
    return ""

def main_st():
    st.set_page_config(
        page_title="Multiverse AI Document Analyst",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.markdown("<h1 style='text-align: center; color: #4CAF50;'>🤖 Multiverse AI Document Analyst</h1>", unsafe_allow_html=True)
    st.info("Upload a JSON data file (e.g., search results) or paste JSON/text. The system will run the analysis pipeline and extract the structured JSON result.")

    uploaded_file = st.file_uploader("Upload JSON/Text file", type=["json", "txt"], key="file_uploader")
    corpus_textarea = st.text_area("Or paste JSON/text here (optional). If provided, this takes precedence over upload.", height=300)

    st.sidebar.header("Analysis settings")
    st.sidebar.write("This UI attempts to call `run_v2_analysis(path)` from main1.py, or `main(path)` from main.py as a fallback.")
    if import_error_messages:
        with st.sidebar.expander("Import diagnostics"):
            for m in import_error_messages:
                st.markdown(f"- `{m}`")

    max_tokens_info = st.sidebar.empty()
    run_button = st.button("Run Analysis")

    tmp_file_path = None
    tmp_created_for_run = False

    if run_button:
        # prepare input file
        if corpus_textarea and corpus_textarea.strip():
            # write pasted content to a temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as tmp:
                tmp.write(corpus_textarea)
                tmp_file_path = tmp.name
                tmp_created_for_run = True
        elif uploaded_file is not None:
            # write uploaded raw bytes to a temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
                tmp.write(uploaded_file.getvalue())
                tmp_file_path = tmp.name
                tmp_created_for_run = True
        else:
            st.error("Provide input by pasting text or uploading a file.")
            return

        # choose function to call
        analysis_fn = None
        if run_v2_analysis is not None:
            analysis_fn = run_v2_analysis
            st.sidebar.success("Using run_v2_analysis from main1.py")
        elif main_analysis_fn is not None:
            analysis_fn = main_analysis_fn
            st.sidebar.success("Using main from main.py")
        else:
            st.error("No analysis function available. Ensure main1.py or main.py is importable and contains the expected function.")
            return

        result_container = st.container()
        with result_container:
            st.info("Running analysis — capturing streaming output. This may take some time.")
            placeholder = st.empty()
            try:
                # run and capture
                raw_output = _call_analysis_and_capture(analysis_fn, tmp_file_path)
            except Exception as e:
                logging.exception("Error while running analysis function: %s", e)
                st.error(f"Analysis raised an error: {e}")
                raw_output = ""

            # display a small excerpt of raw_output as logs (collapsible)
            if raw_output:
                with st.expander("Show captured logs & raw output", expanded=False):
                    st.text_area("Captured output (truncated)", raw_output[:10000], height=300)

                # parse JSON from the captured output
                parsed = _robust_json_parser(raw_output)
                if parsed.get("error"):
                    st.error("Failed to parse JSON result from analysis output.")
                    st.markdown("**Parse error details:**")
                    st.json(parsed)
                    return
                # extract multiverse_combined
                result_data = parsed.get("multiverse_combined", parsed)

                # 1. Executive Summary
                summary_content = result_data.get('executive_summary', result_data.get('summary', 'N/A'))
                st.markdown("<h2 style='color: #2196F3;'>📰 Executive Summary</h2>", unsafe_allow_html=True)
                st.markdown(summary_content if summary_content else "N/A")
                st.markdown("---")

                # 2. Sentiment Analysis
                sentiment_data = result_data.get('sentiment_analysis', {})
                st.markdown("<h2 style='color: #FF9800;'>😊 Sentiment Analysis</h2>", unsafe_allow_html=True)
                if sentiment_data and isinstance(sentiment_data, dict):
                    col1, col2, col3 = st.columns(3)
                    for i, (sent_type, sent_data) in enumerate(sentiment_data.items()):
                        if not isinstance(sent_data, dict): continue
                        percentage = sent_data.get('percentage', 0)
                        reasoning = sent_data.get('reasoning', 'No specific reason provided.')
                        if sent_type.lower() == 'positive':
                            column, icon, color = col1, "👍", "#4CAF50"
                        elif sent_type.lower() == 'negative':
                            column, icon, color = col2, "👎", "#F44336"
                        elif sent_type.lower() == 'neutral':
                            column, icon, color = col3, "😐", "#9E9E9E"
                        else:
                            column, icon, color = col3, "ℹ️", "#607D8B"
                        with column:
                            st.markdown(f"### {icon} {sent_type.capitalize()} Sentiment", unsafe_allow_html=True)
                            st.markdown(f"<div style='background-color: {color}; padding: 10px; border-radius: 8px; color: white; text-align: center; font-size: 24px;'>{percentage}%</div>", unsafe_allow_html=True)
                            st.markdown(f"**Reasoning:** {reasoning}")
                else:
                    st.warning("Sentiment analysis data is missing or malformed.")
                st.markdown("---")

                # 3. Topics
                topics_data = result_data.get('topics', {})
                st.markdown("<h2 style='color: #673AB7;'>🎯 Key Topics</h2>", unsafe_allow_html=True)
                if isinstance(topics_data, dict) and not topics_data.keys():
                    st.warning("Topic analysis data is empty.")
                if isinstance(topics_data, dict):
                    normalized_topics = [{"topic_name": name, **details} for name, details in topics_data.items() if isinstance(details, dict)]
                elif isinstance(topics_data, list):
                    normalized_topics = topics_data
                else:
                    st.warning("Topic analysis data is missing or in an unexpected format.")
                    normalized_topics = []
                if normalized_topics:
                    for topic in normalized_topics:
                        topic_name = topic.get('topic_name', topic.get('topic', 'Unnamed Topic'))
                        relevance = topic.get('relevance_score', topic.get('relevance', 'N/A'))
                        with st.expander(f"**{topic_name}** (Relevance: {relevance})", expanded=False):
                            subtopics = topic.get('subtopics')
                            if isinstance(subtopics, list) and subtopics:
                                st.markdown("**Subtopics:**")
                                st.markdown("".join([f"- {s}\n" for s in subtopics]))
                            snippets = topic.get('representative_snippets')
                            if isinstance(snippets, list) and snippets:
                                st.markdown("**Representative Snippets:**")
                                for snippet in snippets:
                                    st.code(snippet, language='text')
                else:
                    st.warning("No key topics were successfully extracted.")
                st.markdown("---")

                # 4. Entities, Relationships, Anomalies, Controversy
                st.markdown("<h2 style='color: #009688;'>🔎 Entities & Relationships</h2>", unsafe_allow_html=True)
                entities = result_data.get('entity_recognition', [])
                relationships = result_data.get('relationship_extraction', [])
                anomalies = result_data.get('anomaly_detection', [])
                controversy = result_data.get('controversy_score', {})
                if entities:
                    st.markdown("**Entities:**")
                    for ent in entities:
                        st.write(f"- {ent.get('type', 'UNKNOWN')}: {ent.get('name', '')}")
                else:
                    st.info("No entities detected.")
                if relationships:
                    st.markdown("**Relationships:**")
                    for rel in relationships:
                        st.write(f"- {rel.get('entity1', '')} — {rel.get('relationship', '')} — {rel.get('entity2', '')}")
                else:
                    st.info("No relationships detected.")
                if anomalies:
                    st.markdown("**Anomalies / Outliers:**")
                    for a in anomalies:
                        st.write(f"- Section: {a.get('section', '')} — {a.get('description', '')}")
                else:
                    st.info("No anomalies detected.")
                if controversy:
                    try:
                        val = float(controversy.get('value', 0.0))
                    except Exception:
                        val = 0.0
                    explanation = controversy.get('explanation', '')
                    st.markdown(f"**Controversy Score:** {val} — {explanation}")
                else:
                    st.info("No controversy score provided.")

                # Raw JSON and download
                st.markdown("---")
                if st.checkbox("Show raw JSON"):
                    st.subheader("Raw JSON Output")
                    st.json(result_data)
                json_dump = json.dumps({"multiverse_combined": result_data}, indent=2, ensure_ascii=False)
                st.download_button("Download JSON", json_dump, file_name="multiverse_combined_output.json", mime="application/json")
            else:
                st.error("No output captured from the analysis function. Check server logs for details.")

        # cleanup
        try:
            if tmp_created_for_run and tmp_file_path and os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
        except Exception:
            logging.exception("Failed to remove temporary file: %s", tmp_file_path)

if __name__ == "__main__":
    main_st()
