from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import atexit
import os
from contextlib import contextmanager
import sys

# Silence logs to suppress unnecessary outputs
@contextmanager
def silence_log():
    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        with open(os.devnull, "w") as devnull:
            sys.stdout, sys.stderr = devnull, devnull
            yield
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr


def initialize_driver():
    """Initialize the Selenium WebDriver using Chromium."""
    options = ChromeOptions()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--no-sandbox")  # Bypass OS security model
    options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
    options.add_argument("--disable-infobars")
    options.add_argument("--lang=en-GB")
    
    service = ChromeService(executable_path="/usr/bin/chromedriver")  # Explicitly specify the chromedriver path
    return webdriver.Chrome(service=service, options=options)

def get_from_selector(selector: str):
    result = ''
    for el in driver.find_elements(By.CSS_SELECTOR, selector):
        if el and el.text:
            result += el.text + '\n'
    return result

def quit_driver():
    """Quit the WebDriver when the script ends."""
    if driver:
        driver.quit()


def search_query(url: str, query: str, content_selector: str, link_selector: str = None) -> (str, list[str]):
    """
    Perform a search on a specified URL and extract content and links.

    Args:
        url (str): Base search URL.
        query (str): Search query.
        content_selector (str): CSS selector for text content.
        link_selector (str): CSS selector for links (optional).

    Returns:
        tuple: Extracted text content and links.
    """
    driver.get(url + query)
    wait_for_element('res')  # Default wait for page to load

    content = extract_text(content_selector)
    links = extract_links(link_selector) if link_selector else []
    return content, links

def save_debug():
    with open("module_engine/debug.html", "w", encoding='utf-8') as f:
        f.write(driver.page_source)

def wait_for_id(id: str, delay: int = 5):
    try:
        WebDriverWait(driver, delay).until(EC.presence_of_element_located((By.ID, id)))
    except:
        print(f"Element with id {id} not found, proceeding without.")

def extract_text(selector: str) -> str:
    """Extract text from elements matching the CSS selector."""
    return '\n'.join(el.text for el in driver.find_elements(By.CSS_SELECTOR, selector) if el and el.text).strip()


def extract_links(selector: str) -> list[str]:
    """Extract links from elements matching the CSS selector."""
    return [el.get_attribute('href') for el in driver.find_elements(By.CSS_SELECTOR, selector) if el and el.text]


def wait_for_element(element_id: str, delay: int = 10):
    """Wait for an element with a specific ID to be present."""
    try:
        WebDriverWait(driver, delay).until(EC.presence_of_element_located((By.ID, element_id)))
    except Exception:
        print(f"Element with ID '{element_id}' not found.")


# Specific search functions
def search_google2(query: str) -> str:
    print(f"Searching Google for: {query}")
    return search_query(
        "https://google.com/search?hl=en&q=",
        query,
        ".wDYxhc"  # Featured snippets
    )


def search_google(query: str) -> (str, list[str]):
    global driver
    print(f"Searching Google for {query}...")
    driver.get("https://google.com/search?hl=en&q=" + query)
    wait_for_id('res')
    save_debug()
    text = ''
    # Answer box
    text += get_from_selector('.wDYxhc')
    print(f"Answer box: {text}")
    # Knowledge panel
    text += get_from_selector('.hgKElc')
    print(f"Knowledge panel: {text}")
    # Page snippets
    text += get_from_selector('.r025kc.lVm3ye')
    print(f"Page snippets: {text}")
    # Old selectors (for compatibility)
    text += get_from_selector('.yDYNvb.lyLwlc')
    # Links
    #links = get_links_from_selector('.yuRUbf a')
    print("Found: " + text)
    return (text)

def search_duckduckgo(query: str) -> str:
    print(f"Searching DuckDuckGo for: {query}")
    return search_query(
        "https://duckduckgo.com/?kp=-2&kl=wt-wt&q=",
        query,
        '[data-result="snippet"]'
    )


def get_google_news(query: str) -> str:
    """Fetch news content from Google News."""
    print(f"Fetching Google News for: {query}")
    return search_query(
        "https://google.com/search?hl=en&gl=us&tbm=nws&q=",
        query,
        ".dURPMd"
    )


# Initialize and register cleanup
driver = initialize_driver()
atexit.register(quit_driver)
