
"""
module_websearch.py

Web Search Module for TARS-AI Application.

This module provides functionality for performing web searches using Selenium WebDriver. 
It supports multiple search engines and allows for extracting specific content, links, 
and structured data from search results.
"""

# === Standard Libraries ===
import os
import sys
from contextlib import contextmanager
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import atexit
from datetime import datetime

from modules.module_messageQue import queue_message

# === Helper Functions ===
# Silence logs to suppress unnecessary outputs
@contextmanager
def silence_log():
    """
    Context manager to suppress unnecessary console logs during driver initialization.
    """
    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        with open(os.devnull, "w") as devnull:
            sys.stdout, sys.stderr = devnull, devnull
            yield
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr


def initialize_driver():
    """
    Initialize the Selenium WebDriver using Chromium.

    Returns:
    - WebDriver: Configured Selenium WebDriver instance.
    """
    options = ChromeOptions()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--no-sandbox")  # Bypass OS security model
    options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
    options.add_argument("--disable-infobars")
    options.add_argument("--lang=en-GB")

    service = ChromeService(executable_path="/usr/bin/chromedriver")  # Path to the chromedriver
    return webdriver.Chrome(service=service, options=options)

def quit_driver():
    """
    Quit the WebDriver instance when the script ends.
    """
    if driver:
        driver.quit()

def save_debug():
    """
    Save the current page source for debugging purposes.
    """
    with open("engine/debug.html", "w", encoding='utf-8') as f:
        f.write(driver.page_source)

def wait_for_element(element_id: str, delay: int = 10):
    """Wait for an element with a specific ID to be present."""
    try:
        WebDriverWait(driver, delay).until(EC.presence_of_element_located((By.ID, element_id)))
    except Exception:
        queue_message(f"ERROR: Element with ID '{element_id}' not found.")
        
def extract_text(selector):
    """
    Extract text content from elements matching the specified CSS selector.

    Parameters:
    - selector (str): The CSS selector for the elements.

    Returns:
    - str: Concatenated text content of matched elements.
    """
    return '\n'.join(el.text for el in driver.find_elements(By.CSS_SELECTOR, selector) if el and el.text).strip()

def extract_links(selector):
    """
    Extract hyperlinks from elements matching the specified CSS selector.

    Parameters:
    - selector (str): The CSS selector for the elements.

    Returns:
    - list: List of extracted hyperlinks.
    """
    return [el.get_attribute('href') for el in driver.find_elements(By.CSS_SELECTOR, selector) if el and el.text]

# === Search Functions ===
def search_query(url, query, content_selector, link_selector=None):
    """
    Perform a web search and extract content and links.

    Parameters:
    - url (str): Base search URL.
    - query (str): Search query.
    - content_selector (str): CSS selector for text content.
    - link_selector (str, optional): CSS selector for links.

    Returns:
    - tuple: Extracted text content and links (if applicable).
    """
    driver.get(url + query)
    wait_for_element('res')  # Wait for page to load

    content = extract_text(content_selector)
    links = extract_links(link_selector) if link_selector else []
    return content, links

def search_google(query):
    """
    Perform a Google search and extract featured snippets, knowledge panels, and snippets.

    Parameters:
    - query (str): The search query.

    Returns:
    - tuple: Extracted content and links.
    """
    queue_message(f"INFO: Searching Google for: {query}")
    driver.get("https://google.com/search?hl=en&q=" + query)
    wait_for_element('res')
    save_debug()

    text = ""
    # Featured snippets
    text += extract_text('.wDYxhc')
    queue_message(f"INFO: Featured snippets: {text}")
    # Knowledge panels
    text += extract_text('.hgKElc')
    queue_message(f"INFO: Knowledge panels: {text}")
    # Page snippets
    text += extract_text('.r025kc.lVm3ye')
    queue_message(f"INFO: Page snippets: {text}")
    # Additional selectors for compatibility
    text += extract_text('.yDYNvb.lyLwlc')

    return text

def search_google_news(query):
    """
    Perform a search on Google News and extract news snippets.

    Parameters:
    - query (str): The search query.

    Returns:
    - tuple: Extracted content and links.
    """
    queue_message(f"INFO: Fetching Google News for: {query}")
    return search_query(
        "https://google.com/search?hl=en&gl=us&tbm=nws&q=",
        query,
        ".dURPMd"
    )

def search_duckduckgo(query):
    """
    Perform a search on DuckDuckGo and extract results.

    Parameters:
    - query (str): The search query.

    Returns:
    - tuple: Extracted content and links.
    """
    queue_message(f"INFO: Searching DuckDuckGo for: {query}")
    return search_query(
        "https://duckduckgo.com/?kp=-2&kl=wt-wt&q=",
        query,
        '[data-result="snippet"]'
    )

def search_mojeek(query):
    """
    Perform a search on Mojeek and extract results.

    Parameters:
    - query (str): The search query.

    Returns:
    - tuple: Extracted content and links.
    """
    queue_message(f"INFO: Searching Mojeek for: {query}")
    base_url = "https://www.mojeek.com/search?q="
    full_url = base_url + query

    # Load the page
    driver.get(full_url)
    wait_for_element("results")  # Wait for results container to load

    # Extract search result snippets
    content = extract_text(".result-title, .result-desc")  # Titles and descriptions
    links = extract_links(".result-title > a")  # Result links

    return content

def search_mojeek_summary(query):
    """
    Perform a search on Mojeek and extract the summary text. Includes debugging information.

    Parameters:
    - query (str): The search query.

    Returns:
    - str: The extracted summary text, or an error message if not found.
    """
    queue_message(f"INFO: Searching Mojeek for: {query}")
    base_url = "https://www.mojeek.com/search?q="
    full_url = base_url + query

    try:
        # Load the Mojeek search results page
        driver.get(full_url)

        # Save page source for debugging
        save_debug()

        # Print all elements with 'id=kalid' for verification
        elements = driver.find_elements(By.ID, "kalid")
        if not elements:
            queue_message("DEBUG: No elements with ID 'kalid' found.")
        else:
            for el in elements:
                queue_message("DEBUG: Found element with ID 'kalid':", el.get_attribute("outerHTML"))

        # Wait for the summary box to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div#kalid.infobox-right.llm-ib"))
        )

        # Extract the summary content
        summary = extract_text("div#kalid.infobox-right.llm-ib div.content")
        queue_message("INFO: Summary extracted successfully.")
        return summary

    except Exception as e:
        queue_message(f"ERROR: Unable to extract summary. {e}")
        return "Summary not found. Check debug.html for details."


# === Initialize and Cleanup ===
driver = initialize_driver()
atexit.register(quit_driver)
