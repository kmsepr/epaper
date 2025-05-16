from fastapi import FastAPI, Response
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import os

app = FastAPI()

def get_today_url():
    # Put your actual URL here, e.g., today's epaper page
    return "https://epaper.suprabhaatham.com/"

def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")  # Use new headless mode
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    # Add user-agent if needed
    # chrome_options.add_argument("user-agent=Mozilla/5.0 ...")

    driver = webdriver.Chrome(options=chrome_options)
    return driver

def save_page6_screenshot(driver, filename="page6.png"):
    driver.get(get_today_url())

    time.sleep(5)  # wait for page load - increase if slow

    # The page uses a flipbook. Locate page 6 canvas or container
    # For example purposes, wait and scroll to page 6

    # You may need to interact with flipbook controls, e.g. clicking "Next" 5 times:
    for _ in range(5):  # page 1 -> 6
        next_btn = driver.find_element(By.CSS_SELECTOR, ".flipbook-next")  # Adjust selector
        next_btn.click()
        time.sleep(2)  # wait for page animation

    # Now capture screenshot of the visible page area
    screenshot = driver.get_screenshot_as_png()
    with open(filename, "wb") as f:
        f.write(screenshot)

    return filename

@app.get("/prayertime")
def serve_prayer_time_image():
    driver = get_driver()
    try:
        image_path = save_page6_screenshot(driver)
        with open(image_path, "rb") as f:
            img_data = f.read()
        return Response(content=img_data, media_type="image/png")
    finally:
        driver.quit()
        if os.path.exists(image_path):
            os.remove(image_path)