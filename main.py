from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
import fitz  # PyMuPDF
from PIL import Image
import requests
import io
from bs4 import BeautifulSoup

app = FastAPI()

CROP_BOX = (0, 2300, 1200, 2650)  # Adjust as needed
EPAPER_URL = "https://epaper.suprabhaatham.com/details/Kozhikode"

def get_latest_pdf_url():
    res = requests.get(EPAPER_URL)
    soup = BeautifulSoup(res.text, "html.parser")
    # Find the PDF URL for Page 6
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/media/" in href and href.endswith(".pdf") and "epaperpdf" in href:
            if "Kozhikode" in href:
                return "https://epaper.suprabhaatham.com" + href
    return None

@app.get("/")
def show_latest_prayer_times():
    pdf_url = get_latest_pdf_url()
    if not pdf_url:
        return {"error": "PDF not found"}

    # Download PDF
    response = requests.get(pdf_url)
    doc = fitz.open("pdf", response.content)

    # Page 6 is index 5
    try:
        page6 = doc.load_page(5)
    except IndexError:
        return {"error": "Page 6 not available"}

    pix = page6.get_pixmap(dpi=200)
    img = Image.open(io.BytesIO(pix.tobytes("png")))

    # Crop
    cropped = img.crop(CROP_BOX)
    output_path = "/tmp/prayer_times.png"
    cropped.save(output_path)

    return FileResponse(output_path, media_type="image/png")
