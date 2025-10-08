# reddit.py
import praw
import logging
import time
import json
import os  # Import os module for directory operations
import prawcore # Import prawcore for specific exceptions
#from search import SearchQueryGenerator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize the ML-based query generator
#ml_query_generator = SearchQueryGenerator()

# Define a function to generate Reddit queries using the ML model
# def generate_reddit_query(input_text):
#     return ml_query_generator.generate_search_query(input_text)

# Add at the top with other imports
import requests

GEMINI_API_KEY = "ENTER_YOUR_GEMINI_API"  # Replace with your actual Gemini API key
import requests # Make sure you have this import

#GEMINI_API_KEY = "YOUR_ACTUAL_GEMINI_API_KEY"  # !!! IMPORTANT: Replace with your actual, secure Gemini API key. Never share this publicly.
# Use gemini-2.0-flash model endpoint for query generation
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

def gemini_reduce_query(user_prompt, feedback=None):
    """
    Send user prompt (and optional feedback) to Gemini API to get a reduced, keyword-based query for Reddit search.
    """
    system_prompt = (
        "You are an expert at generating concise, keyword-based search queries for Reddit. "
        "Given a user prompt, reduce it to the most effective search query for Reddit's search engine. "
        "Only return the query string."
    )
    if feedback:
        system_prompt += f"\nUser feedback: {feedback}"
        
    # Combine system prompt and user prompt into a single user message
    full_prompt = system_prompt + "\n\n" + user_prompt

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": full_prompt}]
            }
        ]
    }
    try:
        response = requests.post(GEMINI_API_URL, json=payload)
        
        # Check for specific error codes for better debugging
        if response.status_code == 404:
            print("Error: Gemini API endpoint not found. Double-check the model name in the URL (e.g., gemini-1.0-pro, gemini-1.5-flash, gemini-2.0-flash) and the API version (v1beta).")
            return user_prompt
        if response.status_code == 403:
            print("Error: Gemini API key is invalid or quota exceeded. Verify your API key and check your usage limits.")
            return user_prompt
        if response.status_code == 400:
            print(f"Error: Gemini API request is malformed. Response: {response.text}. Please check your API key and payload format (especially the 'role' field in 'contents').")
            return user_prompt

        response.raise_for_status() # This will raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        
        # Extract the query from Gemini's response
        try:
            # Ensure the response structure is as expected
            if "candidates" in data and len(data["candidates"]) > 0 and \
               "content" in data["candidates"][0] and \
               "parts" in data["candidates"][0]["content"] and \
               len(data["candidates"][0]["content"]["parts"]) > 0 and \
               "text" in data["candidates"][0]["content"]["parts"][0]:
                query = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                return query
            else:
                print("Error: Unexpected Gemini API response format. Missing expected fields in 'candidates' or 'parts'.")
                return user_prompt
        except Exception as e:
            print(f"Error parsing Gemini API response: {e}. Raw response: {data}. Returning original prompt.")
            return user_prompt
    except requests.exceptions.RequestException as e:
        print(f"Error communicating with Gemini API (requests library error): {e}")
        return user_prompt # fallback to original prompt
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return user_prompt


class RedditScraper:
    def __init__(self):  # Removed credentials_file argument
        try:
            # Hardcoded credentials as per user request
            client_id = "ENTER CLIENT ID"
            client_secret = "ENTER_YOUR CLIENT SECRET"
            username = "REDDIT ACCOUNT USERNAME" # Ensure this is exactly your Reddit username
            password = "REDDIT ACCOUNT PASSWORD" # Ensure this is exactly your Reddit password
            
            user_agent = f"python:project1:v1.3.0 (by /u/{username})" # Updated user_agent version
            logger.info(f"Attempting to initialize PRAW with username: {username}, client_id: {client_id}, and user_agent: {user_agent}")

            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
                username=username,
                password=password,
                check_for_async=False # Added to avoid potential async-related issues if any
            )
            # Test authentication by trying to get current user's details
            authenticated_user = self.reddit.user.me()
            if authenticated_user:
                logger.info(f"Reddit instance created and successfully authenticated as /u/{authenticated_user.name}.")
            else:
                logger.error("Reddit authentication check failed: self.reddit.user.me() returned None. This indicates a problem despite no immediate exception.")
                self.reddit = None
        except prawcore.exceptions.Forbidden as fe: # Specific catch for 403 Forbidden from prawcore
            logger.error(f"PRAWCORE FORBIDDEN (403) Exception during RedditScraper initialization: {fe}")
            logger.error("This is a strong indicator of an issue with your Reddit App settings (MUST be type 'script', check redirect URI e.g. http://localhost:8080), or your account credentials/permissions. Please verify these on reddit.com/prefs/apps.")
            self.reddit = None
        except praw.exceptions.PRAWException as pe: # Catch other PRAW specific exceptions
            logger.error(f"PRAW Exception during RedditScraper initialization: {pe}")
            logger.error("This often indicates an issue with credentials, user agent, or Reddit app configuration. Double-check these on reddit.com/prefs/apps.")
            self.reddit = None
        except Exception as e: # Catch any other exceptions
            logger.error(f"Generic error initializing RedditScraper: {e}")
            if "403" in str(e).lower():
                logger.error("The generic error contains '403', strongly pointing to a permission/authentication issue with Reddit. See PRAWCORE FORBIDDEN advice.")
            self.reddit = None

    def rate_limit(self):
        time.sleep(1)

    def search_political_subreddits(self, query, limit=10):
        try:
            subreddit_results = list(self.reddit.subreddits.search(query, limit=limit))
            return [sub.display_name for sub in subreddit_results]
        except Exception as e:
            logger.error(f"Error searching subreddits for '{query}': {str(e)}")
            return []

    def get_post_data(self, post, num_comments=10, num_subcomments=5):
        try:
            # Only proceed if selftext is non-empty
            if not post.selftext or post.selftext.strip() == "":
                logger.info(f"Skipping post {post.id}: No selftext available.")
                return None

            post_data = {
                "title": post.title,
                "url": post.url,
                "score": post.score,
                "comments_count": post.num_comments,
                "author": post.author.name if post.author else "Unknown",
                "created_utc": post.created_utc,
                "selftext": post.selftext,
                "comments": []
            }
            post.comments.replace_more(limit=0)
            top_comments = sorted(post.comments, key=lambda c: c.score, reverse=True)[:num_comments]
            for comment in top_comments:
                comment.replies.replace_more(limit=None)
                comment_data = {
                    "author": comment.author.name if comment.author else "Unknown",
                    "comment": comment.body,
                    "published_at": comment.created_utc,
                    "likes": comment.score,
                    "subcomments": []
                }
                subcomments = sorted(comment.replies, key=lambda r: r.score, reverse=True)[:num_subcomments]
                for subcomment in subcomments:
                    subcomment_data = {
                        "author": subcomment.author.name if subcomment.author else "Unknown",
                        "comment": subcomment.body,
                        "published_at": subcomment.created_utc,
                        "likes": subcomment.score
                    }
                    comment_data["subcomments"].append(subcomment_data)
                post_data["comments"].append(comment_data)
            return post_data
        except Exception as e:
            logger.error(f"Error fetching data for post '{post.id}': {str(e)}")
            return None

    def fetch_reddit_posts(self, subreddits, limit_per_sub=15, num_comments=10, num_subcomments=5):
        posts = []
        seen_urls = set()  # For deduplication
        for sub in subreddits:
            try:
                self.rate_limit()
                posts_batch = list(self.reddit.subreddit(sub).hot(limit=limit_per_sub))
                for post in posts_batch:
                    self.rate_limit()
                    if post.url not in seen_urls and post.selftext and post.selftext.strip() != "":
                        post_data = self.get_post_data(post, num_comments, num_subcomments)
                        if post_data:  # Only append if post_data is not None
                            posts.append(post_data)
                            seen_urls.add(post.url)
            except Exception as e:
                logger.error(f"Could not fetch posts from subreddit {sub}: {str(e)}")
        return posts

    def extract_topics(self, posts, top_n=15): # This method might not be directly 
        try:
            words = []
            for post in posts:
                text = post.get('title', '') + " " + post.get('selftext', '')
                tokens = re.findall(r'\b(?!https?://)\w{4,}\b', text.lower())
                words.extend(tokens)
            freq = Counter(words)
            return [word for word, count in freq.most_common(top_n)]
        except Exception as e:
            logger.error(f"Error extracting topics: {str(e)}")
            return []

    def gather_posts_for_topic(self, topic, subreddits, limit=15, num_comments=10, num_subcomments=5): # This method might not be directly used but kept
        posts = []
        seen_urls = set()  # For deduplication
        for sub in subreddits:
            try:
                self.rate_limit()
                posts_batch = list(self.reddit.subreddit(sub).search(
                    query=topic,
                    sort='hot',
                    limit=limit,
                    time_filter='month'
                ))
                for post in posts_batch:
                    self.rate_limit()
                    if post.url not in seen_urls and post.selftext and post.selftext.strip() != "":
                        post_data = self.get_post_data(post, num_comments, num_subcomments)
                        if post_data:  # Only append if post_data is not None
                            posts.append(post_data)
                            seen_urls.add(post.url)
                    if len(posts) >= limit:
                        break
            except Exception as e:
                logger.error(f"Error fetching posts for topic '{topic}' in '{sub}': {str(e)}")
        return posts[:limit]

    def search_and_fetch_top_posts(self, query, limit=5, num_comments=10, num_subcomments=5):
        """
        Searches Reddit globally for a query and fetches the top N posts that have selftext.
        """
        if not self.reddit:
            logger.error("Reddit instance not available. Cannot search posts.")
            return []

        posts_data = []
        seen_urls = set()
        try:
            logger.info(f"Searching Reddit globally for query: '{query}' with a goal of {limit} posts with selftext, sorting by relevance.")
            
            # --- MODIFICATION START ---
            # Increase the PRAW search limit to ensure we fetch enough raw results
            # to find 'limit' posts that actually have selftext. A common heuristic is limit * 2 or 3.
            praw_search_limit = limit * 2 # Fetch double the requested limit from PRAW
            search_results = self.reddit.subreddit("all").search(query, limit=praw_search_limit, sort='relevance')
            # --- MODIFICATION END ---

            for post in search_results:
                self.rate_limit()

                # --- MODIFICATION START ---
                # This check ensures we stop processing once we have collected the desired 'limit' posts.
                if len(posts_data) >= limit:
                    logger.info(f"Successfully collected {limit} posts with selftext. Stopping further processing of search results.")
                    break
                # --- MODIFICATION END ---

                # Ensure post has selftext and is not a duplicate
                if post.url not in seen_urls and hasattr(post, 'selftext') and post.selftext and post.selftext.strip() != "":
                    logger.info(f"Processing post: {post.title[:50]}... (ID: {post.id})")
                    post_data_item = self.get_post_data(post, num_comments, num_subcomments)
                    if post_data_item:
                        posts_data.append(post_data_item)
                        seen_urls.add(post.url)
                        # The counter (implied by len(posts_data)) now only increments for valid posts
                    else:
                        logger.warning(f"Failed to get data for post {post.id}, it might have been skipped (e.g. empty selftext or other error in get_post_data).")
                elif not hasattr(post, 'selftext') or not post.selftext or post.selftext.strip() == "":
                    logger.info(f"Skipping post {post.id} (URL: {post.url}): No selftext or empty selftext.")
                elif post.url in seen_urls:
                    logger.info(f"Skipping duplicate post {post.id} (URL: {post.url}).")
                else:
                    logger.info(f"Skipping post {post.id} (URL: {post.url}) for other reasons (e.g. no selftext attribute).")


            if not posts_data:
                logger.warning(f"No posts with selftext found for query '{query}' within the search limit.")
            else:
                logger.info(f"Successfully fetched {len(posts_data)} posts with selftext for query '{query}'.")
            return posts_data
        except praw.exceptions.PRAWException as pe:
            logger.error(f"PRAW API error during search/fetch for query '{query}': {str(pe)}")
            if "401" in str(pe):
                logger.error("This might be an authentication issue. Please check your Reddit credentials and API access.")
            return []
        except Exception as e:
            logger.error(f"Generic error searching and fetching posts for query '{query}': {str(e)}")
            return []
# Replace simple_query_refiner with advanced_query_refiner in the main execution block
if __name__ == "__main__":
    raw_prompt = input("Enter your search prompt for Reddit: ")
    if not raw_prompt.strip():
        print("Search prompt cannot be empty.")
    else:
        # Step 1: Use Gemini API to reduce/refine the query
        final_query = gemini_reduce_query(raw_prompt)
        print(f"Gemini-generated search query: \"{final_query}\"")
        feedback = None
        while True:
            approval = input("\nDo you want to search Reddit with this query? (yes/no/f): ").strip().lower()
            if approval in ['yes', 'y']:
                break
            elif approval == 'no':
                print("Search cancelled by user.")
                exit(0)
            elif approval == 'f':
                feedback = input("Enter your feedback to improve the query: ")
                final_query = gemini_reduce_query(raw_prompt, feedback)
                print(f"Updated Gemini-generated query: \"{final_query}\"")
            else:
                print("Please enter 'yes', 'no', or 'feedback'.")

        scraper = RedditScraper()
        if scraper.reddit: # Check if Reddit instance was successfully created
            print(f"Searching Reddit for: \"{final_query}\"...")
            # Fetch top 5 posts, with 5 comments each, and 2 subcomments for each comment
            scraped_data = scraper.search_and_fetch_top_posts(final_query, limit=5, num_comments=5, num_subcomments=2)
            if scraped_data:
                output_filename = "reddit_search_output.json"
                try:
                    # Ensure the data directory exists
                    #os.makedirs(os.path.dirname(output_filename), exist_ok=True)
                    with open(output_filename, "w") as f:
                        json.dump(scraped_data, f, indent=4)
                    print(f"Successfully saved {len(scraped_data)} posts to {output_filename}")
                    # Display titles of scraped posts
                    print("\n--- Scraped Post Titles ---")
                    for i, post_info in enumerate(scraped_data):
                        print(f"{i+1}. {post_info.get('title', 'N/A')}")
                    print("---------------------------\n")
                except IOError as e:
                    print(f"Error saving data to JSON file: {e}")
            else:
                print("No data was scraped from Reddit, or an error occurred during scraping.")
        else:
            print("Failed to initialize Reddit scraper. Please check logs for errors (e.g., authentication).")
