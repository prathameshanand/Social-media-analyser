# main3_fixed.py
import streamlit as st
import subprocess
import sys
import importlib
import os
import json
import time
import platform
from datetime import datetime
import traceback

# Try to import your Streamlit UI module (the multiverse_insights_streamlit.py you previously created)
# Update the module name if you saved it under a different filename.
MSI_MODULE_FILENAME = "streamlit_app.py"
MSI_MODULE_NAME = "streamlit_app"

# Set environment variables to reduce display issues in some environments
os.environ.setdefault('DISPLAY', ':99')
os.environ.setdefault('PYAUTOGUI_FAILSAFE', 'False')


# ---------------------------
# Package check / installer
# ---------------------------
def check_and_install_packages():
    """
    Ensure required external packages are installed. This will attempt pip installs for missing
    packages that are truly external. Avoid installing stdlib modules.
    """
    required_packages = [
        'streamlit',
        'playwright',
        'google-api-python-client',  # googleapiclient
        'youtube-transcript-api',
        'deep-translator',
        'langdetect',
        'yt-dlp',
        'openai-whisper',
        'soundfile',
        'pyvirtualdisplay',  # if we need a virtual display
    ]

    missing = []
    for pkg in required_packages:
        try:
            # Map a package name to an importable module for quick check
            if pkg == "google-api-python-client":
                importlib.import_module('googleapiclient.discovery')
            elif pkg == "youtube-transcript-api":
                importlib.import_module('youtube_transcript_api')
            elif pkg == "deep-translator":
                importlib.import_module('deep_translator')
            elif pkg == "yt-dlp":
                importlib.import_module('yt_dlp')
            elif pkg == "openai-whisper":
                importlib.import_module('whisper')
            elif pkg == "soundfile":
                importlib.import_module('soundfile')
            elif pkg == "pyvirtualdisplay":
                importlib.import_module('pyvirtualdisplay')
            else:
                # default; check by package name import (streamlit, playwright, langdetect)
                base_import_name = pkg.split('-')[0]
                importlib.import_module(base_import_name)
        except Exception:
            missing.append(pkg)

    if missing:
        st.write(f"Installing missing packages: {', '.join(missing)}")
        for pkg in missing:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
                st.success(f"Installed {pkg}")
            except subprocess.CalledProcessError as e:
                st.error(f"Failed to install {pkg}: {e}")
                return False

    # Playwright browsers
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        st.success("Playwright browsers installed")
    except Exception as e:
        # not fatal; user may not need playwright in all environments
        st.warning(f"Could not auto-install Playwright browsers: {e}")

    return True


# ---------------------------
# Dynamic imports for scrapers
# ---------------------------
def import_scrapers():
    """
    Import scraper modules from local files:
      - advance_twitter.py  (optional, modified fallback)
      - youtube.py (required)
    Returns (TwitterScraperClass or None, YouTubeScraperClass or None)
    """
    TwitterScraper = None
    YouTubeScraper = None

    # Import youtube.py
    try:
        spec = importlib.util.spec_from_file_location("youtube", os.path.join(os.getcwd(), "youtube.py"))
        youtube_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(youtube_module)
        YouTubeScraper = getattr(youtube_module, "YouTubeScraper", None)
    except Exception as e:
        st.warning(f"Could not import youtube.py: {e}")

    # Import advance_twitter.py if present (best-effort)
    try:
        twitter_path = os.path.join(os.getcwd(), "advance_twitter.py")
        if os.path.exists(twitter_path):
            spec = importlib.util.spec_from_file_location("advance_twitter", twitter_path)
            twitter_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(twitter_module)
            TwitterScraper = getattr(twitter_module, "TwitterScraper", None)
        else:
            st.info("advance_twitter.py not found — Twitter scraper unavailable.")
    except Exception as e:
        st.warning(f"Could not import advance_twitter.py: {e}")

    return TwitterScraper, YouTubeScraper


# ---------------------------
# Run scrapers
# ---------------------------
def run_twitter_scraper(search_query, start_date=None, end_date=None):
    TwitterScraper, _ = import_scrapers()
    if TwitterScraper is None:
        st.warning("Twitter scraper not available.")
        return None

    try:
        output_dir = "outputs"
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_output = f"twitter_{timestamp}.json"

        # initialize and run (signature depends on your advance_twitter implementation)
        scraper = TwitterScraper(
            search_query=search_query,
            cookies_path="twitter_cookies.json",
            json_output=json_output,
            output_dir=output_dir,
            start_date=start_date,
            end_date=end_date
        )
        scraper.run_pipeline()
        return os.path.join(output_dir, json_output)
    except Exception as e:
        st.error(f"Twitter scraper error: {e}")
        st.text(traceback.format_exc())
        return None


def run_youtube_scraper(search_query):
    _, YouTubeScraper = import_scrapers()
    if YouTubeScraper is None:
        st.warning("YouTubeScraper not available.")
        return None

    try:
        output_dir = "data"
        os.makedirs(output_dir, exist_ok=True)
        scraper = YouTubeScraper()
        query = scraper.generate_search_queries(search_query)
        videos = scraper.fetch_youtube_videos(query, max_results=10, max_limit=5)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = os.path.join(output_dir, f"youtube_{timestamp}.json")
        with open(output_filename, "w") as f:
            json.dump(videos, f, indent=2)
        scraper.cleanup_temp_files()
        return output_filename
    except Exception as e:
        st.error(f"YouTube scraper error: {e}")
        st.text(traceback.format_exc())
        return None


# ---------------------------
# Helper to load & render dummy pipelines
# ---------------------------
def load_and_render_dummy_pipeline():
    """
    Import the multiverse_insights_streamlit module and use its dummy outputs
    to render the V1 and V2 UI pipelines (showing all pipelines at once).
    """
    try:
        # Import module by filename
        import importlib.util
        spec = importlib.util.spec_from_file_location(MSI_MODULE_NAME, os.path.join(os.getcwd(), MSI_MODULE_FILENAME))
        msi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(msi)
    except Exception as e:
        st.error(f"Could not import {MSI_MODULE_FILENAME}: {e}")
        st.text(traceback.format_exc())
        return

    # Get dummy data functions
    try:
        v1_data = None
        v2_data = None

        if hasattr(msi, "run_v1_analysis_dummy"):
            v1_data = msi.run_v1_analysis_dummy("/path/to/dummy_input.json")
        if hasattr(msi, "run_v2_analysis_dummy"):
            v2_data = msi.run_v2_analysis_dummy("/path/to/dummy_input.json")

        # if functions not present, try to parse DUMMY_V*_OUTPUT strings
        if v1_data is None and hasattr(msi, "DUMMY_V1_OUTPUT"):
            try:
                v1_data = json.loads(msi.DUMMY_V1_OUTPUT)
            except Exception:
                v1_data = {}
        if v2_data is None and hasattr(msi, "DUMMY_V2_OUTPUT"):
            try:
                v2_data = json.loads(msi.DUMMY_V2_OUTPUT)
            except Exception:
                v2_data = {}

        # Safety defaults
        v1_data = v1_data or {}
        v2_data = v2_data or {}

        # Render both pipelines in the Streamlit page
        st.markdown("---")
        st.markdown("<h2 style='color:#3F51B5;'>Pipeline outputs (dummy) — all sections</h2>", unsafe_allow_html=True)
        # Render V1
        if hasattr(msi, "render_v1_features"):
            try:
                msi.render_v1_features(v1_data)
            except Exception as e:
                st.error(f"Error rendering V1 features: {e}")
                st.text(traceback.format_exc())
        else:
            st.info("render_v1_features not found in the multiverse module.")

        # Render V2 (some implementations expect v1_data as extra arg)
        if hasattr(msi, "render_v2_features"):
            try:
                # handle both possible signatures (v2) or (v2, v1)
                import inspect
                sig = inspect.signature(msi.render_v2_features)
                if len(sig.parameters) == 2:
                    msi.render_v2_features(v2_data, v1_data)
                else:
                    msi.render_v2_features(v2_data)
            except Exception as e:
                st.error(f"Error rendering V2 features: {e}")
                st.text(traceback.format_exc())
        else:
            st.info("render_v2_features not found in the multiverse module.")

    except Exception as e:
        st.error(f"Failed to load and render dummy pipeline: {e}")
        st.text(traceback.format_exc())


# ---------------------------
# Main Streamlit App
# ---------------------------
def main():
    st.set_page_config(page_title="Social Media Scraper", page_icon="🔍", layout="wide")
    st.title("Social Media Scraper")
    st.write("This app scrapes Twitter and YouTube (if available). After scraping completes, it will show the Multiverse Insights dummy pipeline outputs (all pipelines) so you can preview the full report.")

    # Ensure dependencies
    ok = check_and_install_packages()
    if not ok:
        st.error("Dependency installation failed or was incomplete. Please install required packages and reload.")
        # still allow the user to attempt to render the dummy pipeline
        if st.button("Try to render dummy pipeline anyway"):
            load_and_render_dummy_pipeline()
        return

    # Sidebar controls
    st.sidebar.title("Scraping Options")
    platform_choice = st.sidebar.selectbox("Platform", ["Twitter", "YouTube", "Both"])
    search_query = st.text_input("Search query (required)")

    start_date = None
    end_date = None
    if platform_choice in ("Twitter", "Both"):
        use_date = st.sidebar.checkbox("Specify date range for Twitter")
        if use_date:
            start_date = st.sidebar.date_input("Start date")
            end_date = st.sidebar.date_input("End date")
            start_date = start_date.strftime("%Y-%m-%d")
            end_date = end_date.strftime("%Y-%m-%d")

    if st.button("Start Analysis"):
        if not search_query:
            st.error("Please enter a search query.")
            return

        status_placeholder = st.empty()
        results_placeholder = st.empty()

        twitter_results = None
        youtube_results = None

        # Run Twitter scraper
        if platform_choice in ("Twitter", "Both"):
            status_placeholder.info("Running Twitter scraper (if available)...")
            twitter_results = run_twitter_scraper(search_query, start_date, end_date)
            if twitter_results:
                status_placeholder.success(f"Twitter scraping completed — saved to {twitter_results}")
            else:
                status_placeholder.warning("Twitter scraping not completed or unavailable.")

        # Run YouTube scraper
        if platform_choice in ("YouTube", "Both"):
            status_placeholder.info("Running YouTube scraper (if available)...")
            youtube_results = run_youtube_scraper(search_query)
            if youtube_results:
                status_placeholder.success(f"YouTube scraping completed — saved to {youtube_results}")
            else:
                status_placeholder.warning("YouTube scraping not completed or unavailable.")

        # After all scraping attempts complete, load and render the dummy pipeline (all pipelines)
        st.info("All scrapers finished (or attempted). Loading demo Multiverse Insights pipelines now...")
        load_and_render_dummy_pipeline()

        # Show links/paths for the produced outputs (if any)
        final_msgs = []
        if twitter_results:
            final_msgs.append(f"- Twitter: {twitter_results}")
        if youtube_results:
            final_msgs.append(f"- YouTube: {youtube_results}")

        if final_msgs:
            results_placeholder.success("Scraping outputs:\n" + "\n".join(final_msgs))
        else:
            results_placeholder.info("No scraper outputs were produced — dummy pipeline shown instead.")

    # Also allow a manual action to render the dummy pipeline without running scrapers
    st.sidebar.markdown("---")
    if st.sidebar.button("Render Dummy Multiverse Pipelines Now"):
        load_and_render_dummy_pipeline()


if __name__ == "__main__":
    main()
