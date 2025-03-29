# pip install transformers torch spacy
# python -m spacy download en_core_web_sm




import json
import re
import spacy
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import time

# Load spaCy for natural language processing
nlp = spacy.load("en_core_web_sm")

# Verify GPU availability
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU device: {torch.cuda.get_device_name(0)}")
else:
    print("Warning: GPU not detected. Running on CPU will be slow.")

# Load the Phi-3-mini-4k-instruct model and tokenizer
model_name = "microsoft/Phi-3-mini-4k-instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype=torch.float16)  # FP16 for efficiency
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
print(f"Model loaded on {device} with {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")

# Function to extract valid historical/economic claims from text
def extract_valid_claims(text):
    """Extract claims that are historically or economically significant from a block of text."""
    if not isinstance(text, str) or not text.strip():
        return []
    
    doc = nlp(text)
    return [sent.text.strip() for sent in doc.sents if len(sent.text) > 20 and not is_irrelevant_claim(sent.text)]

# Function to determine if a claim is irrelevant
def is_irrelevant_claim(claim):
    """Determine if a claim is irrelevant based on specific keywords or phrases."""
    irrelevant_keywords = [
        "welcome", "thread", "question", "ask", "simple", "silly", "rules", "guidelines", "discuss",
        "discussion", "community", "promote", "advertise", "opinion", "thoughts", "well", "good", "try", "dreams"
    ]
    claim_lower = claim.lower()
    return any(keyword in claim_lower for keyword in irrelevant_keywords)

def extract_and_validate_claims_with_phi3(text):
    """Use the LLM to extract and validate claims directly from the text."""
    validated_claims = []
    start_time = time.time()
    prompt = (
        f"You are an expert in history and economics. Analyze the following text and extract all historically or economically significant claims. "
        f"For each claim, evaluate its accuracy based on facts up to April 2024. Provide a brief explanation for each claim and conclude with "
        f"'Verdict: True' or 'Verdict: False'.\n\n"
        f"Text: {text}\n\n"
        f"Output the results in the format:\n"
        f"- Claim: <claim>\n  Status: <True/False>\n  Explanation: <explanation>\n"
    )
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024).to(device)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=500,  # Allow for longer responses
            temperature=0.7,
            do_sample=True
        )
    
    response = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
    end_time = time.time()
    print(f"Processed text in {end_time - start_time:.2f} seconds")
    
    # Parse the response into claims, statuses, and explanations
    for line in response.split("\n"):
        if line.startswith("- Claim:"):
            claim = line.replace("- Claim:", "").strip()
        elif line.startswith("  Status:"):
            status = line.replace("  Status:", "").strip()
        elif line.startswith("  Explanation:"):
            explanation = line.replace("  Explanation:", "").strip()
            validated_claims.append((claim, status, explanation))
    
    return validated_claims

# Update the analyze_json function to use the new approach
def analyze_json(file_path):
    """Analyze JSON data to extract and validate claims."""
    print(f"Attempting to load JSON file: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"Successfully loaded JSON with {len(data)} top-level entries")
    except Exception as e:
        print(f"Error loading JSON: {str(e)}")
        return

    for topic_data in data:
        reddit_posts = topic_data.get("reddit_posts", [])
        youtube_videos = topic_data.get("youtube_videos", [])

        for post in reddit_posts:
            selftext = post.get("selftext", "")
            print(f"Processing Reddit post '{post.get('title', 'Untitled')}'")
            validated_claims = extract_and_validate_claims_with_phi3(selftext)
            print(f"Validated claims from Reddit post '{post.get('title', 'Untitled')}':")
            for claim, status, explanation in validated_claims:
                print(f"- Claim: {claim}")
                print(f"  Status: {status}")
                print(f"  Explanation: {explanation}")
                print()

        for video in youtube_videos:
            transcript = video.get("transcript", "")
            print(f"Processing YouTube video '{video.get('title', 'Untitled')}'")
            validated_claims = extract_and_validate_claims_with_phi3(transcript)
            print(f"Validated claims from YouTube video '{video.get('title', 'Untitled')}':")
            for claim, status, explanation in validated_claims:
                print(f"- Claim: {claim}")
                print(f"  Status: {status}")
                print(f"  Explanation: {explanation}")
                print()

# Entry point
if __name__ == "__main__":
    
    analyze_json("trending_topics_info.json")
