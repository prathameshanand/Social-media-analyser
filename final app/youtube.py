from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
# Although TooManyRequests isn't directly importable, we can catch it by its full path if it's raised
# Or rely on the base Exception if its exact location isn't stable.
# For now, we'll rely on catching Exception and checking the error message if needed.

import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import os
import json
import sys
import random
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try importing potentially missing modules with helpful error messages
try:
    from deep_translator import GoogleTranslator
except ImportError:
    logger.error("deep_translator module not found. Please install using: pip install deep-translator")
    print("Error: 'deep_translator' module not installed. Please run: pip install deep-translator")
    sys.exit(1)

try:
    from langdetect import detect
except ImportError:
    logger.error("langdetect module not found. Please install using: pip install langdetect")
    print("Error: 'langdetect' module not installed. Please run: pip install langdetect")
    sys.exit(1)

try:
    import yt_dlp
except ImportError:
    logger.error("yt-dlp module not found. Please install using: pip install yt-dlp")
    print("Error: 'yt-dlp' module not installed. Please run: pip install yt-dlp")
    sys.exit(1)

try:
    import whisper
except ImportError:
    logger.error("whisper module not found. Please install using: pip install openai-whisper")
    print("Error: 'whisper' module not installed. Please run: pip install openai-whisper")
    sys.exit(1)

try:
    import soundfile as sf
except ImportError:
    logger.error("soundfile module not found. Please install using: pip install soundfile")
    print("Error: 'soundfile' module not installed. Please run: pip install soundfile")
    sys.exit(1)

try:
    from search import SearchQueryGenerator
except ImportError:
    print("Warning: 'search.py' or 'SearchQueryGenerator' not found. The generate_search_queries method will not work as intended.")
    # Define a dummy class or handle this gracefully if SearchQueryGenerator is not essential for this subtask test
    class SearchQueryGenerator:
        def generate_search_query(self, text):
            print("Using dummy SearchQueryGenerator.")
            # Simple keyword extraction and joining for a fallback
            words = text.lower().split()
            # Remove common stop words (a very basic list)
            stop_words = set(["i", "want", "the", "information", "about", "and", "on", "what", "are", "new", "required"])
            filtered_words = [word for word in words if word not in stop_words]
            return " ".join(filtered_words)


# Your YouTube API Keys
API_KEYS = [
    "AIzaSyDMNPDf4ShMb6Y8TDcNC9SYNNePPj_wPGw",
    "AIzaSyBAXPZUN8imEBIYXBCL0r3eIW7Dyz56uZw",
    "AIzaSyB9UmH-8pKtZIiwf8VFx6LjU6e6-eOpNes",
    "AIzaSyBFwL_u9ag5IjNWkR4kQ-rQjUi8BFme1k" # Corrected a potential typo in one key - PLEASE VERIFY YOUR KEYS ARE CORRECT
]

# Quota costs per API call type
QUOTA_COSTS = {
    "search": 100,
    "videos": 1,
    "channels": 1,
    "commentThreads": 1,
    "comments": 1
}

# Default daily quota per key (10,000 units)
DAILY_QUOTA = 10000

class YouTubeScraper:
    def __init__(self):
        self.lock = Lock()
        self.api_keys = API_KEYS
        self.quota_usage = {key: {"usage": 0, "last_reset": datetime.now().date()} for key in API_KEYS}
        self.translator = GoogleTranslator(source='auto', target='en')
        # Initialize SearchQueryGenerator
        try:
            self.search_query_generator = SearchQueryGenerator()
        except Exception as e:
            print(f"Error initializing SearchQueryGenerator: {e}. Using dummy generator.")
            self.search_query_generator = SearchQueryGenerator() # Use dummy if init fails

        # Initialize Whisper model
        self.whisper_model = None
        try:
            print("⏳ Loading Whisper model...")
            # Load the medium Whisper model, forcing CPU and FP32 for stability
            self.whisper_model = whisper.load_model("medium", device="cpu").float()
            print("✅ Whisper model ready (running on CPU).")
        except Exception as e:
            print(f"Error loading Whisper model: {e}. Whisper transcription will not be available.")


        # Add counter for Whisper usage
        self.whisper_usage_count = 0
        self.max_whisper_usage = 10 # Limit Whisper transcriptions per search to manage resources

    def reset_quota_if_needed(self):
        today = datetime.now().date()
        with self.lock:
            for key in self.quota_usage:
                if self.quota_usage[key]["last_reset"] != today:
                    self.quota_usage[key]["usage"] = 0
                    self.quota_usage[key]["last_reset"] = today
                    logger.info(f"Quota reset for key {key} on {today}")

    def get_available_key(self, required_units=1):
        self.reset_quota_if_needed()
        with self.lock:
            for key in self.quota_usage:
                remaining = DAILY_QUOTA - self.quota_usage[key]["usage"]
                if remaining >= required_units:
                    return key
            raise Exception("All API keys have exceeded their quota limit for today")

    def update_quota_usage(self, key, call_type):
        units = QUOTA_COSTS.get(call_type, 1)
        with self.lock:
            self.quota_usage[key]["usage"] += units
            logger.info(f"Key {key} used {units} units for {call_type}. Total usage: {self.quota_usage[key]['usage']}")

    def build_service(self, key):
        return build('youtube', 'v3', developerKey=key)

    def generate_search_queries(self, text):
        if hasattr(self, 'search_query_generator') and self.search_query_generator:
            return self.search_query_generator.generate_search_query(text)
        else:
            # Fallback to a simple method if the generator is not available
            words = text.lower().split()
            stop_words = set(["i", "want", "the", "information", "about", "and", "on", "what", "are", "new", "required"])
            filtered_words = [word for word in words if word not in stop_words]
            return " ".join(filtered_words)


    def fetch_youtube_videos(self, query, max_results=10, max_limit=5, published_after=None):
        try:
            key = self.get_available_key(QUOTA_COSTS["search"])
            youtube = self.build_service(key)
            response = youtube.search().list(
                part="snippet",
                q=query,
                type="video",
                maxResults=max_results,
                order="viewCount",
                publishedAfter=published_after
            ).execute()
            self.update_quota_usage(key, "search")
            video_ids = [item["id"]["videoId"] for item in response.get("items", [])]

            videos = []
            complete_videos = 0
            processed_video_ids = set() # Keep track of processed videos

            # Process videos sequentially for clearer output, but can be parallelized
            for video_id in video_ids:
                if video_id in processed_video_ids:
                    continue # Skip if already processed

                try:
                    video_data = self.fetch_video_data(video_id)
                    if video_data:
                        videos.append(video_data)
                        processed_video_ids.add(video_id)
                        if video_data["transcript"] != "Transcript not available.":
                            complete_videos += 1
                            logger.info(f"Found video with transcript ({video_data['transcript_source']}): {video_data['title']}")
                            if complete_videos >= max_limit:
                                logger.info(f"Reached limit of {max_limit} videos with transcripts")
                                break # Stop fetching more if limit reached
                    # Add a small delay between processing videos to avoid hitting rate limits
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"Error processing video {video_id}: {str(e)}")
                    continue
            return videos
        except Exception as e:
            logger.error(f"Error fetching videos for '{query}': {str(e)}")
            return []


    def fetch_video_data(self, video_id):
        """Fetch video data, first trying YouTube transcript API, falling back to Whisper only if needed."""
        transcript = "Transcript not available."
        transcript_source = "None"
        title = "N/A" # Default title

        try:
            # Fetch basic video data first
            key = self.get_available_key(QUOTA_COSTS["videos"])
            youtube = self.build_service(key)
            video_response = youtube.videos().list(
                part="snippet,statistics",
                id=video_id
            ).execute()
            self.update_quota_usage(key, "videos")

            if not video_response["items"]:
                logger.warning(f"No video data found for ID {video_id}")
                return None

            snippet = video_response["items"][0]["snippet"]
            stats = video_response["items"][0]["statistics"]
            title = snippet.get("title", "N/A")

            channel_id = snippet["channelId"]
            channel_details = self.fetch_channel_details(channel_id)

            print(f"\n🎬 Processing video: {title} (ID: {video_id})")

            # Try to get transcript with retries and quality checks
            try:
                print(f"📝 Attempting to get transcript for: {title}")
                transcript, transcript_source, failure_reason = self.get_transcript_with_retries(video_id)

                if transcript != "Transcript not available.":
                    print(f"✅ Successfully got transcript from: {transcript_source}")
                else:
                     print(f"🔍 No transcript found via YouTube API after retries. Reason: {failure_reason}")
                     logger.info(f"No YouTube transcript found for {video_id}. Reason: {failure_reason}. Attempting Whisper fallback.")


            except Exception as e:
                logger.error(f"An unexpected error occurred during transcript fetching for {video_id}: {str(e)}")
                print(f"❌ An unexpected error occurred while trying to get transcript.")


            # Only attempt Whisper fallback if YouTube transcript is genuinely not available
            if transcript == "Transcript not available." and self.whisper_model and self.whisper_usage_count < self.max_whisper_usage:
                print(f"Attempting Whisper transcription (Usage: {self.whisper_usage_count + 1}/{self.max_whisper_usage})...")
                try:
                    audio_path = self.download_audio(video_id)

                    if audio_path and os.path.exists(audio_path):
                        try:
                            transcript = self.transcribe_audio(audio_path)
                            if transcript and transcript.strip():
                                transcript_source = "Whisper (fallback)"
                                self.whisper_usage_count += 1
                                print(f"✅ Successfully transcribed with Whisper")
                            else:
                                 print(f"❌ Whisper transcription returned empty text.")

                        except Exception as e:
                            print(f"❌ Whisper transcription failed: {str(e)}")
                            logger.error(f"Whisper transcription failed for {video_id}: {str(e)}")
                        finally:
                            # Clean up audio file regardless of transcription success
                            try:
                                if os.path.exists(audio_path):
                                     os.remove(audio_path)
                                     print(f"🗑️ Cleaned up temporary audio file: {os.path.basename(audio_path)}")
                            except Exception as e:
                                logger.warning(f"Error removing temporary audio file {audio_path}: {str(e)}")
                    else:
                        print(f"❌ Audio download failed, skipping Whisper transcription")
                        logger.error(f"Audio download failed for Whisper fallback: {video_id}")
                except Exception as e:
                    print(f"❌ Error during Whisper processing: {str(e)}")
                    logger.error(f"Error during Whisper processing for {video_id}: {str(e)}")
            elif transcript == "Transcript not available." and not self.whisper_model:
                 print("ℹ️ Skipping Whisper - model not loaded.")
                 logger.info(f"Skipping Whisper for {video_id} - model not loaded.")
            elif transcript == "Transcript not available." and self.whisper_usage_count >= self.max_whisper_usage:
                 print(f"ℹ️ Skipping Whisper - reached usage limit ({self.max_whisper_usage}) for this search.")
                 logger.info(f"Skipping Whisper for {video_id} - reached usage limit.")


            # Fetch comments
            comments = self.fetch_comments(video_id, max_comments=15)

            return {
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "views": stats.get("viewCount", "0"),
                "likes": stats.get("likeCount", "0"),
                "published_at": snippet.get("publishedAt", "N/A"),
                "channel_title": snippet.get("channelTitle", "N/A"),
                "channel_creation_date": channel_details["creation_date"],
                "subscribers": channel_details["subscribers"],
                "transcript": transcript,
                "transcript_source": transcript_source,
                "selftext": transcript, # Add transcript as selftext for compatibility
                "comments": comments
            }

        except Exception as e:
            logger.error(f"Error fetching data for video '{video_id}': {str(e)}")
            print(f"❌ Error fetching data for video {video_id}: {str(e)}")
            return None

    def validate_audio_file(self, file_path, min_size_bytes=1024, max_size_bytes=500 * 1024 * 1024): # 1KB to 500MB
        """Validate downloaded audio file."""
        if not os.path.exists(file_path):
            return False, "File not found"

        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size < min_size_bytes:
            return False, f"File too small ({file_size} bytes)"
        if file_size > max_size_bytes:
            return False, f"File too large ({file_size} bytes)"

        # Basic audio validation (can be slow for large files)
        # We'll skip detailed audio reading for now to avoid potential memory issues,
        # relying more on yt-dlp's download success and file size.
        # A more robust solution might involve reading just a small part of the file header.

        return True, "File size acceptable"

    def download_audio(self, video_id, max_retries=5, base_delay=2): # Increased retries, added base_delay
        """Download audio from YouTube video using yt-dlp to a temporary directory with exponential backoff."""
        if not yt_dlp:
            logger.error("yt_dlp not imported. Cannot download audio.")
            return None

        temp_dir = "temp_audio_downloads"
        for attempt in range(max_retries):
            try:
                os.makedirs(temp_dir, exist_ok=True)
                # Using %(ext)s ensures yt-dlp handles the extension correctly
                output_template = os.path.join(temp_dir, f'{video_id}.%(ext)s')

                ydl_opts = {
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'outtmpl': output_template,
                    'quiet': True,  # Suppress yt-dlp output
                    'no_warnings': True,
                    'restrictfilenames': True,
                    'extract_audio': True,
                    'audioformat': 'mp3',
                    'audio_quality': 0,
                    'prefer_ffmpeg': True,
                    'ffmpeg_location': None,
                    'cachedir': False,
                    'noplaylist': True,
                    'retries': 1, # Internal yt-dlp retries
                    'fragment_retries': 1,
                }

                print(f"⬇️ Downloading audio for Whisper (attempt {attempt + 1}/{max_retries})...")
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=True)
                    # Determine the actual filepath after download and conversion
                    # yt-dlp's prepare_filename gives the path based on the template and info_dict
                    downloaded_filepath = ydl.prepare_filename(info_dict)
                    # We expect the final file to be an mp3
                    final_filepath = f"{os.path.splitext(downloaded_filepath)[0]}.mp3"


                # Verify file exists and is not empty
                if os.path.exists(final_filepath) and os.path.getsize(final_filepath) > 0:
                    print(f"✅ Audio download successful: {os.path.basename(final_filepath)}")
                    return final_filepath
                else:
                    print(f"❌ Download failed - empty or missing file: {os.path.basename(final_filepath) if final_filepath else 'N/A'}")
                    if final_filepath and os.path.exists(final_filepath):
                        os.remove(final_filepath) # Clean up empty/partial file
                    if attempt < max_retries - 1:
                         # Exponential backoff with jitter
                         sleep_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                         print(f"Retrying download in {sleep_time:.2f} seconds...")
                         time.sleep(sleep_time)
                    continue # Try the next attempt

            except Exception as e:
                print(f"❌ Download attempt {attempt + 1} failed: {str(e)}")
                # Clean up potential partial downloads based on the video_id prefix in the temp directory
                try:
                    for fname in os.listdir(temp_dir):
                        if video_id in fname:
                            try:
                                os.remove(os.path.join(temp_dir, fname))
                                logger.debug(f"Cleaned up partial file: {fname}")
                            except OSError:
                                pass # Ignore errors during cleanup
                except OSError:
                     pass # Ignore if directory doesn't exist

                if attempt < max_retries - 1:
                     # Exponential backoff with jitter
                     sleep_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                     print(f"Retrying download in {sleep_time:.2f} seconds...")
                     time.sleep(sleep_time)
                if attempt == max_retries - 1:
                    logger.error(f"Failed to download audio for {video_id} after {max_retries} attempts: {str(e)}")
                    # Do not re-raise, return None

        return None # Return None if all attempts fail


    def transcribe_audio(self, audio_path):
        """Transcribe audio to text using Whisper model with built-in translation."""
        if not self.whisper_model:
            logger.error("Whisper model not loaded. Cannot transcribe audio.")
            # Clean up the temporary audio file if it exists
            if os.path.exists(audio_path):
                os.remove(audio_path)
            return "Transcript not available."

        try:
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found: {audio_path}")

            # Validate audio file
            is_valid, validation_message = self.validate_audio_file(audio_path)
            if not is_valid:
                logger.error(f"Audio file validation failed for {audio_path}: {validation_message}")
                # Clean up the invalid file
                try:
                     os.remove(audio_path)
                     print(f"🗑️ Cleaned up invalid audio file: {os.path.basename(audio_path)}")
                except OSError:
                     pass
                return "Transcript not available."


            logger.info(f"Starting Whisper transcription of audio file: {os.path.basename(audio_path)}")

            # Configure transcription options - 'translate' task automatically translates to English
            options = {
                "task": "translate",  # Transcribe and translate to English
                "fp16": False,         # Force FP32 mode
                "verbose": False       # Reduce output noise
            }

            # Perform transcription using the pre-loaded model
            logger.info("Running Whisper transcription (translate task)...")
            # Ensure model is on CPU and in FP32 before transcribing
            device = "cpu"
            self.whisper_model.to(device).float()
            result = self.whisper_model.transcribe(audio_path, **options)

            if not result or 'text' not in result:
                raise ValueError("Whisper transcription returned no text")

            transcription = result['text'].strip()
            if not transcription:
                raise ValueError("Whisper transcription returned empty text")

            # Log transcription stats
            transcription_length = len(transcription)
            preview = transcription[:100] + "..." if transcription_length > 100 else transcription
            logger.info(f"Whisper transcription successful: {transcription_length} characters")
            logger.info(f"Transcript preview: \"{preview}\"")

            # No need for separate translation step here as 'translate' task handles it

            return transcription

        except Exception as e:
            logger.error(f"Error during Whisper transcription for '{audio_path}': {str(e)}")
            # Clean up the temporary audio file on error as well
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    print(f"🗑️ Cleaned up temporary audio file after error: {os.path.basename(audio_path)}")
                except OSError:
                    pass
            # Do not re-raise, just return error message
            return "Transcript not available."

    def validate_audio_file(self, file_path, min_size_bytes=1024, max_size_bytes=500 * 1024 * 1024): # 1KB to 500MB
        """Validate downloaded audio file."""
        if not os.path.exists(file_path):
            return False, "File not found"

        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size < min_size_bytes:
            return False, f"File too small ({file_size} bytes)"
        if file_size > max_size_bytes:
            return False, f"File too large ({file_size} bytes)"

        # Basic audio validation (can be slow for large files)
        # We'll skip detailed audio reading for now to avoid potential memory issues,
        # relying more on yt-dlp's download success and file size.
        # A more robust solution might involve reading just a small part of the file header.

        return True, "File size acceptable"


    def translate_text(self, text, source_lang):
        """Translate text to English using GoogleTranslator."""
        try:
            # Use deep_translator's GoogleTranslator
            if not text or len(text.strip()) < 10:
                logger.warning("Text too short or empty for translation.")
                return text

            # Detect language if source_lang is 'auto' or None
            if source_lang in ['auto', None]:
                try:
                    source_lang = detect(text)
                    logger.info(f"Detected language for translation: {source_lang}")
                except Exception as e:
                    logger.warning(f"Language detection failed for translation: {e}. Assuming 'auto'.")
                    source_lang = 'auto' # Fallback to auto-detection in translator

            # Translate using the initialized translator
            translated = self.translator.translate(text, source=source_lang, target='en')
            return translated
        except Exception as e:
            logger.error(f"Error translating text: {str(e)}")
            return text # Return original text on error


    def fetch_channel_details(self, channel_id):
        """Fetch channel details with quota management."""
        try:
            key = self.get_available_key(QUOTA_COSTS["channels"])
            youtube = self.build_service(key)
            response = youtube.channels().list(
                part="snippet,statistics",
                id=channel_id
            ).execute()
            self.update_quota_usage(key, "channels")
            if not response["items"]:
                return {"creation_date": "Unknown", "subscribers": "0"}
            snippet = response["items"][0]["snippet"]
            stats = response["items"][0]["statistics"]
            return {
                "creation_date": snippet.get("publishedAt", "Unknown"),
                "subscribers": stats.get("subscriberCount", "0") # Return as string to match API
            }
        except HttpError as e:
            logger.error(f"API error fetching channel details for '{channel_id}': {str(e)}")
            return {"creation_date": "Unknown", "subscribers": "0"}
        except Exception as e:
            logger.error(f"Error fetching channel details for '{channel_id}': {str(e)}")
            return {"creation_date": "Unknown", "subscribers": "0"}

    def get_transcript(self, video_id):
        """Fetch and translate transcript from YouTube (no quota impact).
        Returns:
            tuple: (transcript_text, transcript_source, failure_reason)

        Raises:
            NoTranscriptFound: When no transcript is available and fallback fails
        """
        transcript_text = "Transcript not available."
        transcript_source = "None"
        failure_reason = "Unknown error"
        logger.info(f"Attempting to fetch YouTube transcript for video ID: {video_id}")

        try:
            # Attempt to get transcript list
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            available_languages = [f"{t.language} ({t.language_code})" for t in transcript_list]
            logger.info(f"Available transcript languages for {video_id}: {', '.join(available_languages) if available_languages else 'None'}")


            # Prioritize English transcripts
            try:
                logger.info(f"Attempting to find English transcript for {video_id}...")
                transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
                logger.info(f"Found English transcript for {video_id}.")
                fetched_transcript = transcript.fetch()
                full_text = " ".join([entry["text"] for entry in fetched_transcript])
                return full_text, "YouTube API (English)", None
            except NoTranscriptFound:
                logger.info(f"No English transcript found for {video_id}. Checking for others.")
                failure_reason = "No English transcript found"
                pass # Continue to check for other languages

            # If no English transcript, find any available transcript (manual or auto-generated)
            try:
                # Try finding any manually created transcript first
                logger.info(f"Attempting to find manual transcript for {video_id}...")
                manual_languages = ['zh-Hans', 'ja', 'ko', 'fr', 'de', 'es', 'it', 'ru'] # Common non-English manual languages
                transcript = transcript_list.find_manually_created_transcript(manual_languages)
                logger.info(f"Found non-English manually created transcript in {transcript.language} ({transcript.language_code}) for {video_id}, will translate.")
                fetched_transcript = transcript.fetch()
                full_text = " ".join([entry["text"] for entry in fetched_transcript])
                translated_text = self.translate_text(full_text, source_lang=transcript.language_code)
                return translated_text, f"YouTube API (Manual, Translated from {transcript.language})", None
            except NoTranscriptFound:
                logger.info(f"No manually created transcript found for {video_id}. Checking auto-generated.")
                failure_reason = "No manual transcript found"
                pass # Continue to check for auto-generated

            # If no manual transcript, find any auto-generated transcript
            try:
                logger.info(f"Attempting to find auto-generated transcript for {video_id}...")
                # Prioritize auto-generated in common languages, then any auto-generated
                auto_languages = ['en', 'en-US', 'en-GB', 'hi', 'es', 'fr', 'de', 'it', 'ru', 'ja', 'ko', 'zh-Hans']
                transcript = transcript_list.find_generated_transcript(auto_languages)
                logger.info(f"Found auto-generated transcript in {transcript.language} ({transcript.language_code}) for {video_id}. Translating.")
                fetched_transcript = transcript.fetch()
                full_text = " ".join([entry["text"] for entry in fetched_transcript])
                translated_text = self.translate_text(full_text, source_lang=transcript.language_code)
                return translated_text, f"YouTube API (Auto-generated, Translated from {transcript.language})", None
            except NoTranscriptFound:
                 logger.info(f"No auto-generated transcript found for {video_id}.")
                 failure_reason = "No auto-generated transcript found"
                 # If no manual or auto-generated transcript found, raise NoTranscriptFound
                 raise NoTranscriptFound(f"No transcripts found for video {video_id}.")


        except (NoTranscriptFound, TranscriptsDisabled) as e:
            failure_reason = str(e)
            logger.warning(f"Transcript not found or disabled for video {video_id} via YouTube API: {failure_reason}")
            # Re-raise to be caught by fetch_video_data for Whisper fallback
            raise NoTranscriptFound(f"No transcripts found for video {video_id}.")


        except Exception as e:
            failure_reason = str(e)
            logger.error(f"Unexpected error fetching or processing transcript for '{video_id}': {failure_reason}")
            # For unexpected errors, return "Transcript not available." and log the error
            return "Transcript not available.", "Error", failure_reason


    def verify_transcript_quality(self, transcript):
        """Verify the quality of a transcript (basic checks)."""
        if not transcript or not isinstance(transcript, str):
            return False, "Invalid transcript format"

        # Check minimum length (e.g., at least 50 characters)
        if len(transcript) < 50:
            return False, "Transcript too short"

        # Check for coherence (e.g., at least 10 words)
        words = transcript.split()
        if len(words) < 10:
            return False, "Too few words"

        # Basic check for repetitive patterns (e.g., same word repeated many times)
        word_counts = {}
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1
        most_common_word_count = max(word_counts.values()) if word_counts else 0
        if len(words) > 0 and most_common_word_count / len(words) > 0.5 and len(words) > 20: # If one word is more than 50% of a longer text
             return False, "Highly repetitive transcript"

        # Check for common issues (e.g., lack of punctuation, all caps) - can be complex
        # Skipping detailed punctuation/casing checks for simplicity for now.


        return True, "Transcript quality acceptable"

    def get_transcript_with_retries(self, video_id, max_retries=5, base_delay=1): # Increased retries, added base_delay
        """Get transcript with retries, exponential backoff, and basic quality checks."""
        failure_reason = "Transcript not available after retries"
        for attempt in range(max_retries):
            try:
                logger.info(f"Transcript fetch attempt {attempt + 1}/{max_retries} for video {video_id}")
                transcript, source, reason = self.get_transcript(video_id)
                if transcript != "Transcript not available.":
                    quality_ok, reason = self.verify_transcript_quality(transcript)

                    if quality_ok:
                        logger.info(f"Got quality transcript from {source} on attempt {attempt + 1}")
                        return transcript, source, None
                    else:
                        logger.warning(f"Low quality transcript from {source} for {video_id}: {reason}, attempt {attempt + 1}. Retrying...")
                        failure_reason = f"Low quality transcript after {attempt + 1} attempts: {reason}"
                        # Don't return, try again with delay
                        if attempt < max_retries - 1:
                            sleep_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                            logger.info(f"Retrying transcript fetch in {sleep_time:.2f} seconds...")
                            time.sleep(sleep_time)

                else:
                     # If get_transcript already returned "Transcript not available.", stop retrying API
                     logger.info(f"get_transcript returned 'Transcript not available.' on attempt {attempt + 1}. Stopping retries.")
                     failure_reason = f"get_transcript returned 'Transcript not available.' after {attempt + 1} attempts."
                     break # Exit retry loop

            except (NoTranscriptFound, TranscriptsDisabled) as e:
                 failure_reason = str(e)
                 logger.warning(f"Transcript not found/disabled for {video_id} on attempt {attempt + 1} via YouTube API: {failure_reason}. Retrying API...")
                 if attempt < max_retries - 1:
                     sleep_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                     logger.info(f"Retrying transcript fetch in {sleep_time:.2f} seconds...")
                     time.sleep(sleep_time)
                 if attempt == max_retries - 1:
                      logger.error(f"Failed to fetch transcript for {video_id} after {max_retries} attempts: {failure_reason}")
                      return "Transcript not available.", "None", failure_reason # Return and don't raise

            except Exception as e:
                failure_reason = str(e)
                logger.error(f"Unexpected error during transcript fetching for {video_id} on attempt {attempt + 1}: {failure_reason}. Retrying...")
                if attempt < max_retries - 1:
                    sleep_time = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.info(f"Retrying transcript fetch in {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                if attempt == max_retries - 1:
                    logger.error(f"Failed to fetch transcript for {video_id} after {max_retries} attempts: {failure_reason}")
                    return "Transcript not available.", "Error", failure_reason # Return and don't raise


        # If after retries, no quality transcript was found via API, indicate that
        logger.warning(f"Failed to get a suitable transcript for video {video_id} after {max_retries} attempts via YouTube API. Reason: {failure_reason}")
        return "Transcript not available.", "None", failure_reason


    def fetch_comments(self, video_id, max_comments=10): # Reduced max_comments
        """Fetch comments, sorted by engagement."""
        try:
            all_comments = []
            next_page_token = None
            # Fetch up to 2 times the max_comments to have enough to sort and filter
            while len(all_comments) < max_comments * 2:
                key = self.get_available_key(QUOTA_COSTS["commentThreads"])
                youtube = self.build_service(key)
                response = youtube.commentThreads().list(
                    part="snippet",
                    videoId=video_id,
                    maxResults=100, # Max results per page
                    pageToken=next_page_token,
                    order="relevance" # Order by relevance
                ).execute()
                self.update_quota_usage(key, "commentThreads")

                if not response.get("items"):
                    break # No more comments

                # Process comments concurrently
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_comment = {
                        executor.submit(self.process_comment, item): item
                        for item in response["items"]
                    }
                    for future in as_completed(future_to_comment):
                        comment_data = future.result()
                        if comment_data:
                            all_comments.append(comment_data)

                next_page_token = response.get("nextPageToken")
                if not next_page_token or len(all_comments) >= max_comments * 2:
                    break

            # Filter out short comments and sort by likes
            filtered_comments = [c for c in all_comments if len(c.get("comment", "").split()) > 5]
            sorted_comments = sorted(filtered_comments, key=lambda x: x.get("likes", 0), reverse=True)

            return sorted_comments[:max_comments] # Return only the top N

        except Exception as e:
            logger.error(f"Error fetching comments for '{video_id}': {str(e)}")
            return []

    def process_comment(self, item):
        """Process a single comment thread."""
        try:
            # Extract top-level comment details safely
            top_comment_snippet = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            if not top_comment_snippet:
                 logger.warning(f"Skipping comment thread {item.get('id', 'N/A')} due to missing top-level snippet.")
                 return None

            thread_id = item.get("id", "N/A")

            # Fetch subcomments concurrently
            subcomments = self.fetch_subcomments(thread_id)

            return {
                "author": top_comment_snippet.get("authorDisplayName", "N/A"),
                "comment": top_comment_snippet.get("textDisplay", "N/A"),
                "published_at": top_comment_snippet.get("publishedAt", "N/A"),
                "likes": top_comment_snippet.get("likeCount", 0),
                "subcomments": subcomments
            }
        except Exception as e:
            logger.error(f"Error processing comment thread {item.get('id', 'N/A')}: {str(e)}")
            return None


    def fetch_subcomments(self, parent_id, max_subcomments=5): # Reduced max_subcomments
        """Fetch subcomments for a parent comment."""
        subcomments_data = []
        try:
            next_page_token = None
            # Fetch up to 2 times the max_subcomments to have enough to sort and filter
            while len(subcomments_data) < max_subcomments * 2:
                key = self.get_available_key(QUOTA_COSTS["comments"])
                youtube = self.build_service(key)
                response = youtube.comments().list(
                    part='snippet',
                    parentId=parent_id,
                    textFormat='plainText',
                    maxResults=100, # Max results per page
                    pageToken=next_page_token
                ).execute()
                self.update_quota_usage(key, "comments")

                if not response.get("items"):
                    break # No more subcomments

                for item in response['items']:
                    # Add subcomment if we haven't reached the limit yet
                    if len(subcomments_data) >= max_subcomments * 2:
                         break
                    subcomment = item['snippet']
                    subcomments_data.append({
                        'author': subcomment.get('authorDisplayName', 'N/A'),
                        'comment': subcomment.get('textDisplay', 'N/A'),
                        'published_at': subcomment.get('publishedAt', 'N/A'),
                        'likes': subcomment.get('likeCount', 0)
                    })

                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
                # No need to get a new key if using the same one, but harmless

            # Sort subcomments by likes and return top N
            sorted_subcomments = sorted(subcomments_data, key=lambda x: x.get('likes', 0), reverse=True)
            return sorted_subcomments[:max_subcomments]

        except HttpError as e:
            logger.error(f"API error fetching subcomments for parent '{parent_id}': {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error fetching subcomments for parent '{parent_id}': {str(e)}")
            return []


    def cleanup_temp_files(self):
        """Clean up temporary audio files after processing."""
        temp_dir = "temp_audio_downloads"
        if os.path.exists(temp_dir):
            try:
                # Remove all files in the temp directory
                for file in os.listdir(temp_dir):
                    file_path = os.path.join(temp_dir, file)
                    if os.path.isfile(file_path):
                        try:
                             os.remove(file_path)
                             logger.info(f"Removed temporary file: {file_path}")
                        except OSError as e:
                             logger.warning(f"Could not remove temporary file {file_path}: {e}")


                # Try to remove the directory itself if empty
                if not os.listdir(temp_dir):
                     os.rmdir(temp_dir)
                     logger.info(f"Removed temporary directory: {temp_dir}")
                else:
                     logger.warning(f"Temporary directory {temp_dir} is not empty after cleanup.")

            except Exception as e:
                logger.warning(f"Error during cleanup of temporary files in {temp_dir}: {str(e)}")


# Example usage
if __name__ == "__main__":
    # Instantiate the scraper
    scraper = YouTubeScraper()

    


    # --- Original Example Usage ---
    # Get user input for search
    raw_prompt = input("Enter your search prompt for YouTube: ")

    if not raw_prompt.strip():
        print("Search prompt cannot be empty.")
    else:
        # Generate the query using the search query generator
        try:
            search_query = scraper.generate_search_queries(raw_prompt)
            print(f"Generated query: \"{search_query}\"")

            # Final approval before searching YouTube
            approval = input("\nDo you want to search YouTube with this query? (yes/no): ").strip().lower()

            if approval == 'yes' or approval == 'y':
                print(f"Searching YouTube for: \"{search_query}\"...")
                # Fetch top videos
                videos = scraper.fetch_youtube_videos(search_query, max_results=10, max_limit=5) # Fetch up to 10, limit to 5 with transcripts

                if videos:
                    output_filename = "data/youtube_search_output.json"
                    try:
                        # Ensure the data directory exists
                        os.makedirs(os.path.dirname(output_filename), exist_ok=True)

                        with open(output_filename, "w") as f:
                            json.dump(videos, f, indent=4)
                        print(f"Successfully saved {len(videos)} videos to {output_filename}")

                        # Display titles and transcript info of scraped videos
                        print("\n--- Scraped Video Information ---")
                        for i, video in enumerate(videos):
                            title = video.get('title', 'N/A')
                            url = video.get('url', 'N/A')
                            views = video.get('views', 'N/A')
                            transcript_preview = video.get('transcript', 'Transcript not available.')[:200] + "..." if len(video.get('transcript', '')) > 200 else video.get('transcript', 'Transcript not available.')
                            transcript_source = video.get('transcript_source', 'Unknown')

                            print(f"{i+1}. {title}")
                            print(f"   URL: {url}")
                            print(f"   Views: {views}")
                            print(f"   Transcript Source: {transcript_source}")
                            print(f"   Transcript Preview: \"{transcript_preview}\"")
                            print()
                        print("---------------------------\n")

                    except IOError as e:
                        print(f"Error saving data to JSON file: {e}")
                else:
                    print("No videos with transcripts were found, or an error occurred during scraping.")
            else:
                print("Search cancelled by user.")
        except Exception as e:
             print(f"An error occurred during query generation or setup: {e}")

        # Clean up temporary files regardless of success or failure
        print("Cleaning up temporary files...")
        scraper.cleanup_temp_files()
