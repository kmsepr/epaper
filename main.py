from fastapi import FastAPI
from fastapi.responses import FileResponse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import fitz  # PyMuPDF
from PIL import Image
import io
import time
from datetime import datetime

app = FastAPI()

CROP_BOX = (0, 2300, 1200, 2650)  # Adjust as needed

def get_page6_pdf_url():
    today = datetime.now().strftime("%Y-%m-%d")
    url = f"https://epaper.suprabhaatham.com/details/Kozhikode/{today}/1"

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)
    time.sleep(5)  # Wait for JavaScript to load content

    # Find all anchor tags
    links = driver.find_elements_by_tag_name("a")
    pdf_url = None
    for link in links:
        href = link.get_attribute("href")
        if href and href.endswith(".pdf") and "Page-6" in href:
            pdf_url = href
            break

    driver.quit()
    return pdf_url

@app.get("/")
def serve_prayer_time_image():
    pdf_url = get_page6_pdf_url()
    if not pdf_url:
        return {"error": "Today's Page 6 PDF not found."}

    try:
        response = requests.get(pdf_url)
        doc = fitz.open("pdf", response.content)
        page6 = doc.load_page(0)  # Only one page (Page 6 PDF)

        pix = page6.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))

        cropped = img.crop(CROP_BOX)
        output_path = "/tmp/prayer_times.png"
        cropped.save(output_path)

        return FileResponse(output_path, media_type="image/png")

    except Exception as e:
        return {"error": f"Failed to process PDF: {e}"}