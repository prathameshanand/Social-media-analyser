

# Social Media Analyser

This project integrates the Mistral AI model (275M parameters) running locally via Ollama with Playwright to crawl a website and identify potential search parameters (e.g., URL query parameters).

## Features

- Launches a browser using Playwright.
- Crawls a target website under the control of the Mistral AI model.
- Identifies and reports search-related URL query parameters and input fields.
- Note: This project does not include vulnerability detection logic; it focuses solely on crawling and element identification.

## Prerequisites

Before starting, ensure you have:

- **Windows 11**: The operating system you’re using.
- **Internet Connection**: Required for downloading dependencies.
- **Basic Command-Line Knowledge**: To run commands in Command Prompt or PowerShell.

## Installation

### Step 1: Install Python

1. **Check if Python is Installed**:
    ```sh
    python --version
    ```
    If Python 3.8 or higher is installed (e.g., Python 3.11.0), skip to Step 2. Otherwise, proceed.

2. **Download and Install Python**:
    - Visit [python.org/downloads](https://www.python.org/downloads).
    - Download the latest Python version (e.g., 3.11.x).
    - Run the installer:
        - Check "Add Python to PATH" during installation.
        - Click "Install Now".
    - Verify installation:
        ```sh
        python --version
        ```

### Step 2: Install Ollama

Ollama runs your Mistral AI model locally and provides an API for interaction.

1. **Download Ollama**:
    - Go to [ollama.com/download](https://ollama.com/download).
    - Download the Windows version (e.g., `ollama-windows-amd64.exe`).

2. **Install Ollama**:
    - Run the downloaded `.exe` file.
    - Follow the installer prompts to complete the installation.

3. **Pull the Mistral Model**:
    - Open Command Prompt or PowerShell.
    - Pull the Mistral model:
        ```sh
        ollama pull mistral
        ```
    This downloads the 275M parameter Mistral model (or a similar variant, depending on what’s available).

### Step 3: Run Ollama

1. **Start the Ollama server**:
    ```sh
    ollama run mistral
    ```
    This launches the model and exposes an API at `http://localhost:11434`. Keep this terminal open while running the script.

2. **Verify Ollama**:
    Test the API using a tool like `curl` (if installed) or a simple Python script:
    ```python
    import requests
    response = requests.post("http://localhost:11434/api/generate", json={"model": "mistral", "prompt": "Hello"})
    print(response.json()["response"])
    ```
    If it prints a response, Ollama is working.

### Step 4: Install Python Dependencies

The script requires `playwright` for browser automation and `requests` for API calls.

1. **Open Command Prompt or PowerShell**:
    Ensure you’re in your project directory (e.g., `cd C:\Users\YourName\Projects\SampurnaScan`).

2. **Install Playwright**:
    ```sh
    pip install playwright
    ```
    - Install the browser binaries:
        ```sh
        playwright install
        ```
    This downloads Chromium, Firefox, and WebKit. Chromium is used by default.

3. **Install Requests**:
    ```sh
    pip install requests
    ```

4. **Verify Installations**:
    Check versions:
    ```sh
    pip show playwright requests
    ```
    Ensure both are listed (e.g., `playwright version 1.x.x`, `requests version 2.x.x`).

## Running the Project

1. **Start Ollama**:
    ```sh
    ollama run mistral
    ```
    Keep this window open to keep the API running.

2. **Run the Script**:
    - Open another Command Prompt or PowerShell window.
    - Navigate to your project directory:
        ```sh
        cd C:\Users\YourName\Projects\SampurnaScan
        ```
    - Execute the script:
        ```sh
        python crawl_search.py
        ```
    Replace `target_url` in the script with the website you want to crawl (e.g., `http://testphp.vulnweb.com` for a test site).

---

This updated README should be clearer and more organized. Let me know if you need any further modifications!
