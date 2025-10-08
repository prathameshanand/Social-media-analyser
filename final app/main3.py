import streamlit as st
import subprocess
import sys
import importlib
import os
import json
import asyncio
from datetime import datetime
import time
import platform
from streamlit_app import render_v1_features render_v2_features
# Set environment variables to prevent display connection issues
os.environ['DISPLAY'] = ':99'  # Use a virtual display
os.environ['PYAUTOGUI_FAILSAFE'] = 'False'  # Disable failsafe

# Function to check and install missing packages
def check_and_install_packages():
    required_packages = [
        'streamlit', 'playwright', 'googleapiclient', 'youtube_transcript_api', 
        'deep_translator', 'langdetect', 'yt_dlp', 'whisper', 'soundfile', 
        'asyncio', 're', 'urllib', 'random', 'concurrent.futures', 
        'threading', 'logging', 'datetime'
    ]
    
    # We'll handle pyautogui separately
    special_packages = {
        'pyautogui': False,  # Will handle separately
        'pyvirtualdisplay': False,  # For virtual display
    }
    
    missing_packages = []
    
    # Check regular packages
    for package in required_packages:
        try:
            if package == 'playwright':
                importlib.import_module('playwright.async_api')
            elif package == 'googleapiclient':
                importlib.import_module('googleapiclient.discovery')
            elif package == 'youtube_transcript_api':
                importlib.import_module('youtube_transcript_api')
            elif package == 'deep_translator':
                importlib.import_module('deep_translator')
            elif package == 'langdetect':
                importlib.import_module('langdetect')
            elif package == 'yt_dlp':
                importlib.import_module('yt_dlp')
            elif package == 'whisper':
                importlib.import_module('whisper')
            elif package == 'soundfile':
                importlib.import_module('soundfile')
            elif package == 'asyncio':
                importlib.import_module('asyncio')
            elif package == 're':
                importlib.import_module('re')
            elif package == 'urllib':
                importlib.import_module('urllib.parse')
            elif package == 'random':
                importlib.import_module('random')
            elif package == 'concurrent.futures':
                importlib.import_module('concurrent.futures')
            elif package == 'threading':
                importlib.import_module('threading')
            elif package == 'logging':
                importlib.import_module('logging')
            elif package == 'datetime':
                importlib.import_module('datetime')
            else:
                importlib.import_module(package)
        except ImportError:
            missing_packages.append(package)
    
    # Install missing regular packages
    if missing_packages:
        st.write(f"Installing missing packages: {', '.join(missing_packages)}")
        for package in missing_packages:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                st.success(f"Successfully installed {package}")
            except subprocess.CalledProcessError as e:
                st.error(f"Failed to install {package}: {e}")
                return False
    
    # Install playwright browsers if needed
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        st.success("Playwright browsers installed successfully")
    except subprocess.CalledProcessError as e:
        st.error(f"Failed to install Playwright browsers: {e}")
        return False
    
    # Check if we're in a headless environment
    is_headless = os.environ.get('DISPLAY') is None and platform.system() != 'Windows'
    
    if is_headless:
        # In headless environment, set up virtual display
        st.write("Setting up virtual display for headless environment...")
        try:
            # Install pyvirtualdisplay if not already installed
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyvirtualdisplay"])
            
            # Start virtual display
            from pyvirtualdisplay import Display
            display = Display(visible=0, size=(1920, 1080))
            display.start()
            st.success("Virtual display started successfully")
            
            # Now try to install and import pyautogui
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "pyautogui"])
                importlib.import_module('pyautogui')
                st.success("pyautogui imported successfully")
            except Exception as e:
                st.warning(f"Could not import pyautogui: {e}. Some features may not work properly.")
        except Exception as e:
            st.warning(f"Could not set up virtual display: {e}. Some features may not work properly.")
    else:
        # Not in headless environment, try to install pyautogui normally
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pyautogui"])
            importlib.import_module('pyautogui')
            st.success("pyautogui imported successfully")
        except Exception as e:
            st.warning(f"Could not import pyautogui: {e}. Some features may not work properly.")
    
    return True

# Import the scraper classes after ensuring packages are installed
def import_scrapers():
    try:
        # Import TwitterScraper with modified handling for headless environments
        import importlib.util
        spec = importlib.util.spec_from_file_location("advance_twitter", "advance_twitter.py")
        twitter_module = importlib.util.module_from_spec(spec)
        
        # Save the original code
        with open("advance_twitter.py", "r") as f:
            original_code = f.read()
        
        # Modify the code to handle headless environments
        modified_code = original_code.replace(
            "try:\n    import pyautogui\n    screen_width, screen_height = pyautogui.size()\nexcept:\n    screen_width, screen_height = 1920, 1080  # fallback",
            "# Using fallback screen dimensions for headless environment\nscreen_width, screen_height = 1920, 1080"
        )
        
        # Also modify the browser launch to use headless mode
        modified_code = modified_code.replace(
            "browser = await p.chromium.launch(headless=False, args=['--start-maximized'])",
            "browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])"
        )
        
        # Write the modified code to a temporary file
        with open("temp_advance_twitter.py", "w") as f:
            f.write(modified_code)
        
        # Import the modified module
        spec = importlib.util.spec_from_file_location("temp_advance_twitter", "temp_advance_twitter.py")
        twitter_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(twitter_module)
        TwitterScraper = twitter_module.TwitterScraper
        
        # Import YouTubeScraper
        spec = importlib.util.spec_from_file_location("youtube", "youtube.py")
        youtube_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(youtube_module)
        YouTubeScraper = youtube_module.YouTubeScraper
        
        return TwitterScraper, YouTubeScraper
    except Exception as e:
        st.error(f"Error importing scraper modules: {e}")
        return None, None

# Function to run Twitter scraper
def run_twitter_scraper(search_query, start_date=None, end_date=None):
    try:
        TwitterScraper, _ = import_scrapers()
        if TwitterScraper is None:
            return None
        
        # Create output directory if it doesn't exist
        output_dir = "outputs"
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize scraper with provided parameters
        scraper = TwitterScraper(
            search_query=search_query,
            cookies_path="twitter_cookies.json",
            json_output=f"twitter_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            output_dir=output_dir,
            start_date=start_date,
            end_date=end_date
        )
        
        # Run the scraper
        scraper.run_pipeline()
        
        # Return the path to the output file
        return os.path.join(output_dir, scraper.json_output)
    except Exception as e:
        st.error(f"Error running Twitter scraper: {e}")
        return None

# Function to run YouTube scraper
def run_youtube_scraper(search_query):
    try:
        _, YouTubeScraper = import_scrapers()
        if YouTubeScraper is None:
            return None
        
        # Create output directory if it doesn't exist
        output_dir = "data"
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize scraper
        scraper = YouTubeScraper()
        
        # Generate search query
        query = scraper.generate_search_queries(search_query)
        
        # Fetch videos
        videos = scraper.fetch_youtube_videos(query, max_results=10, max_limit=5)
        
        # Save results to file
        output_filename = os.path.join(output_dir, f"youtube_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(output_filename, "w") as f:
            json.dump(videos, f, indent=4)
        
        # Clean up temporary files
        scraper.cleanup_temp_files()
        
        return output_filename
    except Exception as e:
        st.error(f"Error running YouTube scraper: {e}")
        return None

# Main Streamlit app
def main():
    st.set_page_config(page_title="Social Media Scraper", page_icon="🔍", layout="wide")
    
    st.title("Social Media Scraper")
    st.write("This app allows you to scrape data from Twitter and YouTube based on your search query.")
    
    # Check and install missing packages
    if not check_and_install_packages():
        st.error("Failed to install required packages. Please install them manually.")
        return
    
    # Sidebar for options
    st.sidebar.title("Scraping Options")
    
    # Platform selection
    platform = st.sidebar.selectbox(
        "Select platform to scrape:",
        ["Twitter", "YouTube", "Both"]
    )
    
    # Search query input
    search_query = st.text_input("Enter your search query:")
    
    # Date range for Twitter
    if platform in ["Twitter", "Both"]:
        st.write("### Twitter Options")
        use_date_range = st.checkbox("Specify date range for Twitter scraping")
        
        if use_date_range:
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start date")
            with col2:
                end_date = st.date_input("End date")
            
            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = end_date.strftime("%Y-%m-%d")
        else:
            start_date_str = None
            end_date_str = None
    
    # Start scraping button
    if st.button("Start Analysis"):
        if not search_query:
            st.error("Please enter a search query.")
            return
        
        # Create a placeholder for status updates
        status_placeholder = st.empty()
        results_placeholder = st.empty()
        
        # Initialize results
        twitter_results = None
        youtube_results = None
        
        # Run scrapers based on selection
        if platform in ["Twitter", "Both"]:
            status_placeholder.text("Running Twitter scraper...")
            twitter_results = run_twitter_scraper(search_query, start_date_str, end_date_str)
            if twitter_results:
                status_placeholder.text("Twitter scraping completed successfully!")
            else:
                status_placeholder.text("Twitter scraping failed.")
        
        if platform in ["YouTube", "Both"]:
            if platform == "Both" and twitter_results:
                status_placeholder.text("Running YouTube scraper...")
            else:
                status_placeholder.text("Running YouTube scraper...")
            
            youtube_results = run_youtube_scraper(search_query)
            if youtube_results:
                status_placeholder.text("YouTube scraping completed successfully!")
            else:
                status_placeholder.text("YouTube scraping failed.")
        
        # Display results
        if platform == "Twitter" and twitter_results:
            results_placeholder.success(f"Twitter results saved to: {twitter_results}")
        elif platform == "YouTube" and youtube_results:
            results_placeholder.success(f"YouTube results saved to: {youtube_results}")
        elif platform == "Both":
            if twitter_results and youtube_results:
                results_placeholder.success(f"Twitter results saved to: {twitter_results}\nYouTube results saved to: {youtube_results}")
            elif twitter_results:
                results_placeholder.success(f"Twitter results saved to: {twitter_results}\nYouTube scraping failed.")
            elif youtube_results:
                results_placeholder.success(f"Twitter scraping failed.\nYouTube results saved to: {youtube_results}")
            else:
                results_placeholder.error("Both Twitter and YouTube scraping failed.")
        
        # Clear status after a delay
        time.sleep(50)
        status_placeholder.empty()
        render_v1_features() 
        render_v2_features()

if __name__ == "__main__":
    main()