from playwright.sync_api import sync_playwright
import requests
from urllib.parse import urljoin, urlparse, parse_qs

# Function to send prompts to your local Mistral model via Ollama
def query_mistral(prompt):
    url = "http://localhost:11434/api/generate"  # Ollama API endpoint
    data = {
        "model": "mistral",  # Your Mistral model with 275M parameters
        "prompt": prompt
    }
    response = requests.post(url, json=data)
    return response.json()["response"].strip()

# Function to capture the current webpage state (focused on search params and inputs)
def capture_page_state(page):
    # Extract URL query parameters
    parsed_url = urlparse(page.url)
    query_params = parse_qs(parsed_url.query)
    query_param_description = "Query Parameters:\n" + "\n".join(
        f"{key}: {value}" for key, value in query_params.items()
    ) if query_params else "No query parameters found."

    # Extract input fields
    inputs = page.query_selector_all("input")
    input_descriptions = []
    for input_elem in inputs:
        input_type = input_elem.get_attribute("type") or "text"
        name = input_elem.get_attribute("name") or ""
        id = input_elem.get_attribute("id") or ""
        placeholder = input_elem.get_attribute("placeholder") or ""
        if input_type in ["text", "search"]:  # Focus on search-related inputs
            input_descriptions.append(
                f"Input (type='{input_type}', name='{name}', id='{id}', placeholder='{placeholder}')"
            )

    # Extract links for crawling
    links = page.query_selector_all("a")
    link_descriptions = [link.get_attribute("href") for link in links if link.get_attribute("href")]

    page_state = (
        f"Current URL: {page.url}\n"
        f"{query_param_description}\n"
        f"Input Fields:\n" + ("\n".join(input_descriptions) if input_descriptions else "No input fields found.") + "\n"
        f"Links:\n" + ("\n".join(link_descriptions) if link_descriptions else "No links found.")
    )
    return page_state

# Function to create a prompt for Mistral (focused on crawling and finding search params/inputs)
def create_prompt(page_state, target_url):
    return (
        f"I want you to crawl the website '{target_url}' to find potential search parameters (e.g., URL query params like ?q=) "
        f"and input fields (e.g., <input type='text'> or <input type='search'>). Here is the current webpage state:\n\n"
        f"{page_state}\n\n"
        "Suggest the next action to explore the site and locate more search parameters or input fields. Respond with one of the following commands:\n"
        "- 'click: <selector>' to click an element (e.g., 'click: button#submit')\n"
        "- 'fill: <selector>, value: <value>' to fill an input field (e.g., 'fill: input[name='search'], value: \"test\"')\n"
        "- 'navigate: <url>' to navigate to a URL (e.g., 'navigate: /search')\n"
        "- 'scroll' to scroll down\n"
        "- 'done' if there are no more actions to take\n"
        "Ensure <selector> is a valid CSS selector."
    )

# Function to execute Mistral's commands using Playwright
def execute_command(page, command):
    try:
        if command.startswith("click: "):
            selector = command.split("click: ")[1].strip()
            page.click(selector)
        elif command.startswith("fill: "):
            parts = command.split("fill: ")[1].split(", value: ")
            selector = parts[0].strip()
            value = parts[1].strip()
            page.fill(selector, value)
            # Simulate form submission if applicable
            form = page.query_selector(selector).closest("form")
            if form:
                submit_button = form.query_selector("button[type='submit'], input[type='submit']")
                if submit_button:
                    submit_button.click()
        elif command.startswith("navigate: "):
            url = command.split("navigate: ")[1].strip()
            absolute_url = urljoin(page.url, url)
            page.goto(absolute_url)
        elif command == "scroll":
            page.evaluate("window.scrollBy(0, window.innerHeight)")
        elif command == "done":
            return "done"
        page.wait_for_load_state("networkidle")
    except Exception as e:
        print(f"Failed to execute command '{command}': {e}")
        return "error"
    return "success"

# Main function to crawl the site and find search parameters and input fields
def automated_crawl_with_mistral(target_url, max_steps=10):
    with sync_playwright() as p:
        # Launch the browser using Playwright
        browser = p.chromium.launch(headless=True)  # Set headless=False to see the browser
        page = browser.new_page()
        page.goto(target_url)
        visited_urls = set([target_url])
        steps = 0
        findings = []

        print(f"Starting crawl on {target_url}...")

        while steps < max_steps:
            # Capture the current page state
            page_state = capture_page_state(page)
            print(f"\nStep {steps} - Page State:\n{page_state}")

            # Record findings
            parsed_url = urlparse(page.url)
            query_params = parse_qs(parsed_url.query)
            if query_params:
                findings.append(f"URL: {page.url}\nQuery Parameters: {query_params}")
            inputs = page.query_selector_all("input[type='text'], input[type='search']")
            if inputs:
                input_details = [f"Input: type='{i.get_attribute('type')}', name='{i.get_attribute('name') or ''}', id='{i.get_attribute('id') or ''}'" for i in inputs]
                findings.append(f"URL: {page.url}\nInput Fields:\n" + "\n".join(input_details))

            # Create a prompt and query Mistral
            prompt = create_prompt(page_state, target_url)
            command = query_mistral(prompt)
            print(f"Mistral command: {command}")

            # Execute the command
            result = execute_command(page, command)
            if result == "done":
                print("Mistral indicated crawling is complete.")
                break
            elif result == "error":
                print("Error occurred, skipping to next step.")
                steps += 1
                continue

            # Track visited URLs
            if page.url not in visited_urls:
                visited_urls.add(page.url)

            steps += 1

        browser.close()

        # Print all findings
        print("\n=== Findings ===")
        if findings:
            for finding in findings:
                print(finding)
        else:
            print("No search parameters or input fields found.")
        print(f"Visited URLs: {visited_urls}")

# Example usage
target_url = "http://example.com"  # Replace with the site you want to crawl
automated_crawl_with_mistral(target_url)
