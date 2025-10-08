import json
import asyncio
import re
import os
from datetime import datetime
from urllib.parse import quote
import random # Import random for randomized delays
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError # Import TimeoutError

try:
    import pyautogui
    screen_width, screen_height = pyautogui.size()
except:
    screen_width, screen_height = 1920, 1080  # fallback

class TwitterScraper:
    def __init__(self,
                cookies_path="twitter_cookies.json",
                search_query="ISRO Future space missions",
                start_date=None,   # e.g. "2025-07-10"
                end_date=None, 
                json_output="tweets_output.json",
                output_dir="outputs", # ADDED THIS LINE
                max_concurrency=1,
                max_search_scroll_attempts=3, # New: Max scrolls for search results page
                max_comment_scroll_attempts=2, # New: Max scrolls for comments section of a post
                max_comments_per_post=5): # New: Limit for comments per post
        self.cookies_path = cookies_path
        self.search_query = search_query
        self.json_output = json_output
        self.output_dir = output_dir # ADDED THIS LINE
        self.start_date = start_date  # e.g. "2025-07-10"
        self.end_date = end_date 
        self.max_concurrency = max_concurrency
        self.all_tweets = []
        self.seen_urls = set() # To track unique tweets collected globally
        self.max_search_scroll_attempts = max_search_scroll_attempts
        self.max_comment_scroll_attempts = max_comment_scroll_attempts
        self.max_comments_per_post = max_comments_per_post


    async def extract_tweet_data(self, tweet_element):
        try:
            # User handle
            user_name_elem = await tweet_element.query_selector('[data-testid="User-Name"]')
            user_name_text = await user_name_elem.inner_text() if user_name_elem else ""
            handle_match = re.search(r'@(\w+)', user_name_text)
            user_handle = f"@{handle_match.group(1)}" if handle_match else ""

            # Tweet date
            time_elem = await tweet_element.query_selector('time')
            datetime_str = await time_elem.get_attribute('datetime') if time_elem else ""
            tweet_date = ""
            if datetime_str:
                dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                tweet_date = dt.strftime("%b %d, %Y")

            # Content
            content_elem = await tweet_element.query_selector('[data-testid="tweetText"]')
            content = await content_elem.inner_text() if content_elem else ""

            # Hashtags
            hashtags = re.findall(r"#\w+", content)

            # Engagements - Check if elements exist before getting text
            # Use specific data-testid for better targeting
            replies_elem = await tweet_element.query_selector('div[data-testid="reply"] span')
            replies = await replies_elem.inner_text() if replies_elem else "0"

            retweet_elem = await tweet_element.query_selector('div[data-testid="retweet"] span')
            retweets = await retweet_elem.inner_text() if retweet_elem else "0"

            like_elem = await tweet_element.query_selector('div[data-testid="like"] span')
            likes = await like_elem.inner_text() if like_elem else "0"

            view_elem = await tweet_element.query_selector('div[data-testid="app-text-transition-container"] span') # Common selector for views
            views_text = await view_elem.inner_text() if view_elem and "Views" in (await view_elem.inner_text()) else "N/A"
            views = views_text.replace(" Views", "").strip() if "Views" in views_text else "N/A" # Clean up "N.N K Views"

            # Tweet URL
            url_elem = await tweet_element.query_selector('a[dir="ltr"][role="link"]') # This link usually wraps the whole tweet
            href = await url_elem.get_attribute('href') if url_elem else ""
            tweet_url = f"https://x.com{href}" if href else ""

            return {
                "user_handle": user_handle,
                "tweet_date": tweet_date,
                "content": content,
                "replies": replies,
                "retweets": retweets,
                "likes": likes,
                "views": views,
                "tweet_url": tweet_url,
                "hashtags": hashtags
            }
        except Exception as e:
            # print(f"Error extracting tweet: {e}") # Uncomment for detailed debugging
            return None

    async def _check_login_status(self, page):
        """Checks if the user is successfully logged in by looking for logged-in specific elements."""
        home_button = await page.query_selector('a[aria-label="Home"]')
        if home_button:
            print("✅ Login status confirmed via 'Home' button.")
            return True
        else:
            print("⚠️ Login status NOT confirmed. May need manual intervention or fresh cookies.")
            return False

    async def scrape_search_tweets(self, page):
        # if self.end_date is None:
        #     self.end_date = datetime.now().strftime("%Y-%m-%d")

        query_string = self.search_query
        if self.start_date:
            query_string += f" since:{self.start_date} until:{self.end_date}"

        encoded_query = quote(query_string)
        search_url = f"https://x.com/search?q={encoded_query}" # Added f=live for real-time results

        print(f"🌐 Navigating to search URL: {search_url}")
        try:
            await page.goto(search_url, timeout=120000, wait_until="domcontentloaded")
            await asyncio.sleep(5) # Initial wait for content to load
            await page.wait_for_selector('article[data-testid="tweet"]', timeout=30000, state='visible') # Wait for first tweet to appear
        except PlaywrightTimeoutError:
            print(f"❌ Timed out navigating to search page or waiting for initial tweets. URL: {search_url}")
            return # Exit if initial load fails
        except Exception as e:
            print(f"❌ Error during initial search page navigation: {e}")
            return


        last_height = await page.evaluate("document.body.scrollHeight")
        scroll_attempts = 0
        
        print("Starting adaptive scroll and post collection on search page...")
        while scroll_attempts < self.max_search_scroll_attempts:
            # Scroll to the bottom
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(random.uniform(4, 8)) # Random wait time for dynamic content to load

            # Wait for more tweets to be visible after scrolling
            try:
                await page.wait_for_selector('article[data-testid="tweet"]', state='visible', timeout=10000)
            except PlaywrightTimeoutError:
                print("  Timed out waiting for new tweets after scroll on search page. Proceeding with current loaded posts.")
                # This could indicate the end of content or a temporary loading issue
            
            tweet_elements = await page.query_selector_all('[data-testid="tweet"]')
            newly_found_count = 0
            current_urls_on_page = set()
            for te in tweet_elements:
                tweet_data = await self.extract_tweet_data(te)
                if tweet_data and tweet_data["tweet_url"] not in self.seen_urls:
                    self.seen_urls.add(tweet_data["tweet_url"])
                    self.all_tweets.append(tweet_data)
                    newly_found_count += 1
                if tweet_data and tweet_data["tweet_url"]:
                    current_urls_on_page.add(tweet_data["tweet_url"])
            
            new_height = await page.evaluate("document.body.scrollHeight")
            
            print(f"  Scrolled {scroll_attempts + 1}/{self.max_search_scroll_attempts} times. Collected {len(self.all_tweets)} unique posts (new in this scroll: {newly_found_count}).")

            # Check if no new content loaded AND no new tweets found
            if new_height == last_height and newly_found_count == 0:
                print("  No new content or posts loaded on search page after scrolling. Breaking scroll loop.")
                break # No more content loading
            
            last_height = new_height
            scroll_attempts += 1
        
        print(f"✅ Finished initial post collection on search page. Total posts for comment scraping: {len(self.all_tweets)}")


    async def process_comments(self, tweet, context):
        """
        Navigates to an individual tweet page, scrolls to load comments,
        and scrapes comments data. Applies comment limit.
        """
        page = await context.new_page()
        await page.set_viewport_size({"width": screen_width, "height": screen_height})
        
        tweet_url = tweet.get('tweet_url')
        if not tweet_url:
            print(f"⚠️ Skipping comment scraping for a tweet with no URL.")
            await page.close()
            return

        print(f"➡️ Navigating to post: {tweet_url} to scrape comments...")
        
        max_retries = 3 # New: Number of retries for navigation/main tweet load
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"  Retrying navigation/main tweet load for {tweet_url} (Attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(random.uniform(5, 15)) # Longer random sleep before retry

                await page.goto(tweet_url, timeout=120000, wait_until="domcontentloaded")
                await asyncio.sleep(5) # Initial wait for content to load
                # Increased timeout for waiting for the main tweet
                await page.wait_for_selector('article[data-testid="tweet"]', state='visible', timeout=30000) # Increased to 30s
                break # If successful, break retry loop
            except PlaywrightTimeoutError as e:
                print(f"❌ Timed out (1st stage) navigating to {tweet_url} or waiting for main tweet (Attempt {attempt + 1}/{max_retries}). Error: {e}")
                if attempt == max_retries - 1:
                    print(f"  Max retries reached for {tweet_url}. Skipping comments for this post.")
                    await page.close()
                    return
            except Exception as e:
                print(f"❌ Error during initial post page navigation (1st stage) for {tweet_url} (Attempt {attempt + 1}/{max_retries}): {e}. Skipping comments.")
                if attempt == max_retries - 1:
                    print(f"  Max retries reached for {tweet_url}. Skipping comments for this post.")
                    await page.close()
                    return

        comments = []
        seen_comment_urls = set() # To prevent duplicate comments if they load multiple times
        
        last_height = await page.evaluate("document.body.scrollHeight")
        scroll_attempts = 0

        # Start adaptive scrolling for comments
        while scroll_attempts < self.max_comment_scroll_attempts:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)") # Scroll to bottom
            await asyncio.sleep(random.uniform(3, 6)) # Random wait time for new comments to load

            # Wait for new comment elements to appear
            try:
                # Comments are also tweets, but appear in the reply thread.
                # Increased timeout for waiting for comments after scroll
                await page.wait_for_selector('div[data-testid="cellInnerDiv"] article[data-testid="tweet"]', state='visible', timeout=15000) # Increased to 15s
            except PlaywrightTimeoutError:
                print(f"  Timed out (2nd stage) waiting for new comments after scroll for {tweet_url}. Proceeding with current loaded comments.")
                # This could indicate the end of content or a temporary loading issue
            
            tweet_elements = await page.query_selector_all('div[data-testid="cellInnerDiv"] article[data-testid="tweet"]')
            newly_found_comments_count = 0
            
            # Filter by checking for "Replying to" to ensure it's a comment, and skip the main tweet.
            for te in tweet_elements:
                try:
                    reply_indicator = await te.query_selector('div[data-testid="tweetText"] + div div[data-testid="User-Names"] a')
                    if not reply_indicator: # This is likely the main tweet or a non-reply element
                        continue

                    comment_data = await self.extract_tweet_data(te)
                    # Check for comment_data and if it's a new comment (not already seen)
                    if comment_data and comment_data["tweet_url"] not in seen_comment_urls:
                        comments.append(comment_data)
                        seen_comment_urls.add(comment_data["tweet_url"])
                        newly_found_comments_count += 1
                except Exception as e:
                    # print(f"  ⚠️ Error extracting individual comment: {e}") # Uncomment for detailed debugging
                    pass # Continue to next comment if one fails
            
            new_height = await page.evaluate("document.body.scrollHeight")
            
            # If no new content loaded AND no new comments found, break
            if new_height == last_height and newly_found_comments_count == 0:
                print(f"  No new content or comments loaded after scroll for {tweet_url}. Breaking comment scroll loop.")
                break
            
            last_height = new_height
            scroll_attempts += 1
            # print(f"  Scrolled {scroll_attempts}/{self.max_comment_scroll_attempts} times. Collected {len(comments)} unique comments for {tweet_url}.") # Uncomment for detailed debugging

        # Apply the comment limit after all available comments have been collected via scrolling
        if len(comments) > self.max_comments_per_post:
            print(f"  Limiting comments for {tweet_url} from {len(comments)} to {self.max_comments_per_post}.")
            comments = comments[:self.max_comments_per_post]
        else:
            print(f"  Collected {len(comments)} comments for {tweet_url} (less than or equal to limit).")

        tweet['comments'] = comments
        print(f"✅ Extracted {len(comments)} comments for {tweet_url}")
        await page.close()


    async def scrape_comments_concurrent(self, context):
        """
        Processes comments for all collected tweets concurrently using a semaphore.
        """
        sem = asyncio.Semaphore(self.max_concurrency)

        async def wrapped_process(tweet_item):
            async with sem:
                await self.process_comments(tweet_item, context)
        
        # Create tasks for all tweets, ensuring only unique ones are processed
        tasks = [wrapped_process(tweet) for tweet in self.all_tweets if tweet.get('tweet_url')]
        
        await asyncio.gather(*tasks)


    async def scrape_all(self):
        print("🚀 Running full Twitter scrape for posts and comments...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False, args=['--start-maximized'])
            context = await browser.new_context(viewport=None, user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/118.0.5993.89 Safari/537.36"
            ))
            
            # Load cookies
            try:
                with open(self.cookies_path, "r") as f:
                    cookies = json.load(f)
                    for cookie in cookies:
                        if "expirationDate" in cookie:
                            cookie["expires"] = cookie.pop("expirationDate")
                        ss = cookie.get("sameSite")
                        if isinstance(ss, str):
                            ss_lower = ss.lower()
                            if ss_lower == "lax":
                                cookie["sameSite"] = "Lax"
                            elif ss_lower == "strict":
                                cookie["sameSite"] = "Strict"
                            elif ss_lower in ["none", "no_restriction"]:
                                cookie["sameSite"] = "None"
                            else: # Default to Lax if unrecognizable for Playwright
                                cookie["sameSite"] = "Lax" 
                        else:
                            cookie["sameSite"] = "Lax" # Default
                        
                        # Remove potentially problematic fields
                        cookie.pop("partitionKey", None)
                        cookie.pop("firstPartyDomain", None)
                        cookie.pop("storeId", None)

                await context.add_cookies(cookies)
                print(f"✅ Loaded cookies from {self.cookies_path}")
            except FileNotFoundError:
                print(f"❌ Cookies file not found at {self.cookies_path}. Please ensure it exists.")
                await browser.close()
                return
            except json.JSONDecodeError:
                print(f"❌ Error decoding JSON from {self.cookies_path}. Ensure it's valid JSON.")
                await browser.close()
                return
            except Exception as e:
                print(f"❌ An error occurred loading or processing cookies: {e}")
                await browser.close()
                return

            page = await context.new_page()
            await page.set_viewport_size({"width": screen_width, "height": screen_height})
            
            # Go to home and check login status
            await page.goto("https://x.com/home", timeout=120000, wait_until="domcontentloaded")
            await asyncio.sleep(5) # Give time to load
            if not await self._check_login_status(page):
                print("🚨 Login failed or cookies are invalid. Please update 'twitter_cookies.json'.")
                await browser.close()
                return

            await self.scrape_search_tweets(page)
            
            # Now, scrape comments concurrently for all collected tweets
            print(f"\n💬 Starting concurrent comment scraping for {len(self.all_tweets)} posts...")
            await self.scrape_comments_concurrent(context)
            
            await browser.close()
        
        # Save all scraped data to a JSON file
        output_filepath = os.path.join(self.output_dir, self.json_output)
        with open(output_filepath, "w", encoding="utf-8") as f:
            json.dump(self.all_tweets, f, indent=4, ensure_ascii=False)
        print(f"✅ Extracted {len(self.all_tweets)} tweets with comments into {self.json_output}")
        print("🎉 All Twitter scraping done!")

    def run_pipeline(self):
        print("🚀 Running full Twitter scrape → extract → json pipeline...")
        # You can set start_date and end_date here if you want to override __init__ defaults
        # self.start_date = "2024-06-01"
        # self.end_date = "2025-08-28"
        asyncio.run(self.scrape_all())
        print("🎉 All done!")

if __name__ == "__main__":
    # Ensure 'outputs' directory exists for JSON output
    output_dir = "outputs"
    os.makedirs(output_dir, exist_ok=True)

    scraper = TwitterScraper(
        search_query="India China relations", # Your search query
        cookies_path=os.path.join("twitter_cookies.json"), # Assuming cookies are in outputs folder
        json_output="tweets_output.json", # Output file for scraped data
        #start_date="2025-06-01", # Optional: Specify start date (YYYY-MM-DD)
        #end_date="2025-08-28", # Optional: Specify end date (YYYY-MM-DD)
        #max_search_scroll_attempts=20, # Increased for potentially more posts
        #max_comment_scroll_attempts=15, # Increased for potentially more comments
        #max_comments_per_post=100 # Adjust this limit as needed
    )
    scraper.run_pipeline()


