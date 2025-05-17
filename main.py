from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import json
import time

def get_page_urls():
    # Set up headless Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options)

    try:
        # Navigate to the page
        url = "https://epaper.suprabhaatham.com/details/Kozhikode/2025-05-17/1"
        driver.get(url)

        # Wait for the page to load
        time.sleep(5)  # Adjust as necessary

        # Get page source and parse with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Find the script tag containing 'window.magazineData'
        script_tag = soup.find("script", string=lambda t: t and "window.magazineData" in t)
        if not script_tag:
            raise Exception("Could not find page data script.")

        # Extract JSON data from the script tag
        script_content = script_tag.string
        json_data = script_content.split("window.magazineData = ")[1].split(";\n")[0]
        data = json.loads(json_data)

        # Extract page URLs
        pages = data.get("pages", [])
        urls = [page.get("image") for page in pages if page.get("image")]

        return urls

    finally:
        driver.quit()

if __name__ == "__main__":
    urls = get_page_urls()
    for url in urls:
        print(url)