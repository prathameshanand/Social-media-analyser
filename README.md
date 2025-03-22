# Fake News Detector

## Overview
This project is designed to analyze social media posts, extract claims, and classify them as **true** or **false** using engagement metrics and web verification. The pipeline processes a JSON file containing Reddit posts, extracts verifiable claims, and verifies them through web searches and LLM-based analysis.

## Features
- Extracts claims from Reddit posts using an **LLM (Mistral-7B)**
- Computes a credibility score based on **likes, comments, and subreddit age**
- Classifies claims as **true, false, or neutral**
- Searches the web for neutral and false claims using **Google search automation**
- Scrapes and processes relevant web pages for verification
- Uses an **LLM** to compare claims with evidence and finalize classification

## Installation
### 1. Clone the Repository
```bash
git clone https://github.com/prathameshanand/Social-media-analyser
cd Social-media-analyser
```

### 2. Create a Virtual Environment (Optional but Recommended)
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

## Running the Pipeline
### 1. Prepare Your Data
Ensure you have a JSON file named `trending_topics_info.json` in the project directory. This file should contain Reddit posts with metadata like likes, comments, and timestamps.

### 2. Run the Detector
```bash
python main.py
```

## Expected Output
The script processes the JSON file and outputs a list of claims with their final classification:
```json
[
    {"claim": "Bitcoin mining is banned in China", "verdict": "True"},
    {"claim": "Dogecoin will reach $1 soon", "verdict": "False"},
    {"claim": "Stock market will crash in 2025", "verdict": "Unverified"}
]
```

## Notes
- **Subreddit age** is the only age-related factor considered in credibility scoring.
- The **LLM model is not downloaded** in this script; ensure you have a running LLM service or modify the code to use an API.
- Web scraping is done via **Playwright**; ensure it's installed correctly.

## Contributing
Feel free to fork the repository and submit pull requests. Any improvements or bug fixes are welcome!

## License
MIT License. See `LICENSE` for more details.

---

Enjoy detecting fake news! 🚀

