# pip install transformers torch spacy
# python -m spacy download en_core_web_sm


import json
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
import requests
from bs4 import BeautifulSoup
from transformers import pipeline

class FakeNewsDetector:
    def __init__(self, file_path):
        self.file_path = file_path
        self.llm = pipeline("text-generation", model="mistralai/Mistral-7B-v0.1")
        self.current_time = datetime.utcnow().timestamp()
    
    def load_json(self):
        with open(self.file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def extract_claims(self, text):
        """Extract claims using an LLM."""
        prompt = f"Extract the main verifiable claim from this text: '{text}'"
        response = self.llm(prompt, max_length=100, do_sample=True)
        return response[0]['generated_text'] if response else None
    
    def normalize(self, value, max_value=100):
        return min(value / max_value, 1.0)  # Scale to 0-1 range
    
    def compute_score(self, likes, comments, created_utc):
        """Calculate a credibility score based only on subreddit age."""
        subreddit_age = (self.current_time - created_utc) / (30 * 24 * 60 * 60)  # Convert seconds to months
        norm_likes = self.normalize(likes, 1000)
        norm_comments = self.normalize(comments, 500)
        norm_age = self.normalize(subreddit_age, 120)  # Normalize to 10 years (120 months)
        return (0.4 * norm_likes) + (0.3 * norm_comments) + (0.3 * norm_age)
    
    def categorize_claim(self, score):
        if score > 0.7:
            return "True"
        elif score < 0.3:
            return "False"
        return "Neutral"
    
    def generate_search_query(self, claim):
        return f"Is it true that {claim}?"
    
    async def google_search(self, query):
        """Use Playwright to fetch Google search results."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(f"https://www.google.com/search?q={query}")
            links = await page.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.href)")
            await browser.close()
            return links[:5]  # Return top 5 links
    
    def scrape_text(self, url):
        """Scrape and clean text from the webpage."""
        try:
            response = requests.get(url, timeout=5)
            soup = BeautifulSoup(response.text, "html.parser")
            paragraphs = soup.find_all("p")
            return " ".join([p.get_text() for p in paragraphs])[:2000]
        except Exception:
            return ""
    
    def verify_claim(self, claim, text):
        """Use LLM to determine if the scraped content supports or refutes the claim."""
        prompt = f"Claim: '{claim}'\nEvidence: '{text}'\nDoes this evidence support, refute, or remain neutral about the claim?"
        response = self.llm(prompt, max_length=50, do_sample=True)
        return response[0]['generated_text'] if response else "neutral"
    
    async def process_json(self):
        data = self.load_json()
        result = []
        
        for topic in data:
            for post in topic.get("reddit_posts", []):
                claim = self.extract_claims(post["title"])
                if not claim:
                    continue
                
                score = self.compute_score(post["score"], post["comments_count"], post["created_utc"])
                category = self.categorize_claim(score)
                
                if category in ["Neutral", "False"]:
                    query = self.generate_search_query(claim)
                    urls = await self.google_search(query)
                    texts = [self.scrape_text(url) for url in urls]
                    verdicts = [self.verify_claim(claim, text) for text in texts if text]
                    
                    if verdicts.count("support") > verdicts.count("refute"):
                        category = "True"
                    elif verdicts.count("refute") > verdicts.count("support"):
                        category = "False"
                    else:
                        category = "Unverified"
                
                result.append({"claim": claim, "verdict": category})
        
        return result

# Run the pipeline
file_path = "trending_topics_info.json"
detector = FakeNewsDetector(file_path)
asyncio.run(detector.process_json())
