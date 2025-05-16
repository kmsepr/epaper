import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

def download_page_6_image(date_str, save_path):
    options = Options()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)

    try:
        url = f"https://epaper.suprabhaatham.com/details/Kozhikode/{date_str}/1"
        print(f"Loading page 1 URL: {url}")
        driver.get(url)
        time.sleep(5)  # Wait for page 1 to load completely

        # Flip to page 6 by executing JavaScript
        print("Flipping to page 6...")
        driver.execute_script("window.Book.goToPage(6);")
        time.sleep(5)  # Wait for page 6 to load

        # Attempt to locate page 6 image
        print("Locating page 6 image...")
        # Inspected page has div.page elements, each with an <img> for the page
        # Using nth-child(6) to get page 6
        img_element = driver.find_element(By.CSS_SELECTOR, "div.page:nth-child(6) img")
        img_url = img_element.get_attribute("src")
        print(f"Found image URL: {img_url}")

        # Download image
        print(f"Downloading image to {save_path}...")
        response = requests.get(img_url)
        response.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(response.content)

        print("Download completed!")

    except Exception as e:
        print(f"Error: {e}")
        print("Could not get page 6 image, saving screenshot instead.")
        driver.save_screenshot(save_path)

    finally:
        driver.quit()

if __name__ == "__main__":
    date = "2025-05-16"
    os.makedirs("downloads", exist_ok=True)
    save_file = f"downloads/suprabhaatham_kozhikode_{date}_page6.jpg"
    download_page_6_image(date, save_file)