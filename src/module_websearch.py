
"""
module_websearch.py

Web Search Module for GPTARS Application.

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
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: Element with ID '{element_id}' not found.")
        
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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Searching Google for: {query}")
    driver.get("https://google.com/search?hl=en&q=" + query)
    wait_for_element('res')
    save_debug()

    text = ""
    # Featured snippets
    text += extract_text('.wDYxhc')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Featured snippets: {text}")
    # Knowledge panels
    text += extract_text('.hgKElc')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Knowledge panels: {text}")
    # Page snippets
    text += extract_text('.r025kc.lVm3ye')
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Page snippets: {text}")
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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Fetching Google News for: {query}")
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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: Searching DuckDuckGo for: {query}")
    return search_query(
        "https://duckduckgo.com/?kp=-2&kl=wt-wt&q=",
        query,
        '[data-result="snippet"]'
    )

# === Initialize and Cleanup ===
driver = initialize_driver()
atexit.register(quit_driver)
