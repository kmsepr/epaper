import os
import time
import datetime
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from pdf2image import convert_from_path
from PIL import Image

app = FastAPI()

CACHE_PDF = "cached_page6.pdf"
CROPPED_IMG = "cropped_prayer_times.png"
CACHE_DURATION = 12 * 60 * 60  # 12 hours


def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=chrome_options)


def get_today_url():
    today = datetime.date.today().strftime("%Y-%m-%d")
    return f"https://epaper.suprabhaatham.com/details/Kozhikode/{today}/1"


def download_page6_pdf():
    if os.path.exists(CACHE_PDF):
        if time.time() - os.path.getmtime(CACHE_PDF) < CACHE_DURATION:
            return CACHE_PDF

    driver = get_driver()
    driver.get(get_today_url())
    try:
        link = driver.find_element(By.XPATH, '//a[contains(@href, "page6.pdf")]').get_attribute("href")
        driver.quit()
        if not link:
            return None

        response = requests.get(link)
        with open(CACHE_PDF, "wb") as f:
            f.write(response.content)
        return CACHE_PDF
    except Exception as e:
        driver.quit()
        print(f"Error finding or downloading PDF: {e}")
        return None


def crop_prayer_time_from_pdf(pdf_path):
    if os.path.exists(CROPPED_IMG):
        if time.time() - os.path.getmtime(CROPPED_IMG) < CACHE_DURATION:
            return CROPPED_IMG

    pages = convert_from_path(pdf_path, dpi=300)
    if len(pages) < 1:
        return None

    page6 = pages[0]  # Assuming single-page page6.pdf
    # Define the cropping box: (left, upper, right, lower)
    crop_box = (1400, 2650, 1950, 2800)
    cropped = page6.crop(crop_box)
    cropped.save(CROPPED_IMG)
    return CROPPED_IMG


@app.get("/", response_class=FileResponse)
def serve_prayer_time_image():
    pdf_path = download_page6_pdf()
    if not pdf_path:
        raise HTTPException(status_code=404, detail="Today's Page 6 PDF not found.")

    img_path = crop_prayer_time_from_pdf(pdf_path)
    if not img_path:
        raise HTTPException(status_code=500, detail="Failed to process image.")

    return FileResponse(img_path, media_type="image/png")