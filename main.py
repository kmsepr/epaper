from fastapi import FastAPI
from fastapi.responses import FileResponse
import fitz  # PyMuPDF
from PIL import Image
import requests
import io
from bs4 import BeautifulSoup
from datetime import datetime

app = FastAPI()

CROP_BOX = (0, 2300, 1200, 2650)  # Adjust to fit your needs


def get_page6_pdf_url():
    today = datetime.now().strftime("%Y-%m-%d")
    page_url = f"https://epaper.suprabhaatham.com/details/Kozhikode/{today}/1"

    try:
        res = requests.get(page_url)
        soup = BeautifulSoup(res.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Page 6 PDF usually has "Page-6" or similar in the URL
            if (
                href.endswith(".pdf")
                and "epaperpdf" in href
                and "Kozhikode" in href
                and "Page-6" in href
            ):
                return "https://epaper.suprabhaatham.com" + href

    except Exception as e:
        print("Error fetching PDF URL:", e)

    return None


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