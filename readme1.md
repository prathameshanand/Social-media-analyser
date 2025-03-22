

Running the Project
Start Ollama:
Open a Command Prompt or PowerShell window.
Integrating Mistral AI with Playwright for Web Crawling
This project integrates the Mistral AI model (275M parameters) running locally via Ollama with Playwright to crawl a website and identify potential search parameters (e.g., URL query parameters like ?q=) and input fields (e.g., <input type="text"> or <input type="search">). The script uses Python and is designed to run on Windows 11.

Features
Launches a browser using Playwright.
Crawls a target website under the control of the Mistral AI model.
Identifies and reports search-related URL query parameters and input fields.
No vulnerability detection logic (focused solely on crawling and element identification).
Prerequisites
Before starting, ensure you have:

Windows 11: The operating system you’re using.
Internet Connection: Required for downloading dependencies.
Basic Command-Line Knowledge: To run commands in Command Prompt or PowerShell.
Installation

Installation Steps
Step 1: Install Python
Check if Python is Installed:
Open Command Prompt (cmd) or PowerShell and run:
bash

Collapse

Wrap

Copy
python --version
If Python 3.8 or higher is installed (e.g., Python 3.11.0), skip to Step 2. Otherwise, proceed.
Download and Install Python:
Visit python.org/downloads.
Download the latest Python version (e.g., 3.11.x).
Run the installer:
Check "Add Python to PATH" during installation.
Click "Install Now".
Verify installation:
bash

Collapse

Wrap

Copy
python --version




Step 2: Install Ollama
Ollama runs your Mistral AI model locally and provides an API for interaction.

Download Ollama:
Go to ollama.com/download.
Download the Windows version (e.g., ollama-windows-amd64.exe).
Install Ollama:
Run the downloaded .exe file.
Follow the installer prompts to complete the installation.
Pull the Mistral Model:
Open Command Prompt or PowerShell.
Pull the Mistral model (assuming it’s available as mistral):
bash

Collapse

Wrap

Copy
ollama pull mistral
This downloads the 275M parameter Mistral model (or a similar variant, depending on what’s available).



Run Ollama:
Start the Ollama server:
bash

Collapse

Wrap

Copy
ollama run mistral
This launches the model and exposes an API at http://localhost:11434. Keep this terminal open while running the script.
Verify Ollama:
Test the API using a tool like curl (if installed) or a simple Python script:
python

Collapse

Wrap

Copy
import requests
response = requests.post("http://localhost:11434/api/generate", json={"model": "mistral", "prompt": "Hello"})
print(response.json()["response"])
If it prints a response, Ollama is working.
Step 3: Install Python Dependencies
The script requires playwright for browser automation and requests for API calls.

Open Command Prompt or PowerShell:
Ensure you’re in your project directory (e.g., cd C:\Users\YourName\Projects\SampurnaScan).



Install Playwright:
bash

Collapse

Wrap

Copy
pip install playwright
Install the browser binaries:
bash

Collapse

Wrap

Copy
playwright install
This downloads Chromium, Firefox, and WebKit. Chromium is used by default.
Install Requests:
bash

Collapse

Wrap

Copy
pip install requests
Verify Installations:
Check versions:
bash

Collapse

Wrap

Copy
pip show playwright requests
Ensure both are listed (e.g., playwright version 1.x.x, requests version 2.x.x).

Run:
bash

Collapse

Wrap

Copy
ollama run mistral
Keep this window open to keep the API running.
Run the Script:
Open another Command Prompt or PowerShell window.
Navigate to your project directory:
bash

Collapse

Wrap

Copy
cd C:\Users\YourName\Projects\SampurnaScan
Execute the script:
bash

Collapse

Wrap

Copy
python crawl_search.py
Replace target_url in the script with the website you want to crawl (e.g., http://testphp.vulnweb.com for a test site).
