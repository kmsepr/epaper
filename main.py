import os
import io
import threading
import time
import requests
from flask import Flask, send_file, jsonify
from PIL import Image
import pytesseract

app = Flask(__name__)

EPAPER_API = "https://epaper.suprabhaatham.com/api/editions"
CURRENT_LINK_FILE = "epaper.txt"

# Background task to fetch latest epaper links daily
def update_epaper():
    while True:
        try:
            r = requests.get(EPAPER_API, timeout=20)
            r.raise_for_status()
            data = r.json()
            today = data["editions"][0]["pages"]  # first edition pages
            with open(CURRENT_LINK_FILE, "w") as f:
                for page in today:
                    f.write(page["image"] + "\n")
        except Exception as e:
            print("Update error:", e)
        time.sleep(60 * 60 * 6)  # refresh every 6 hours

threading.Thread(target=update_epaper, daemon=True).start()

def get_today_pages():
    if not os.path.exists(CURRENT_LINK_FILE):
        return []
    with open(CURRENT_LINK_FILE) as f:
        return [x.strip() for x in f if x.strip()]

@app.route("/")
def home():
    pages = get_today_pages()
    if not pages:
        return "No epaper found. Please wait for update."
    return f'<h2>Suprabhaatham ePaper</h2><a href="{pages[0]}" target="_blank">Open Today\'s Front Page</a>'

@app.route("/prayer")
def prayer():
    pages = get_today_pages()
    if len(pages) < 6:
        return "Prayer page not available yet."

    try:
        img_url = pages[5]  # page 6 (index 5)
        r = requests.get(img_url, timeout=20)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))

        # Crop prayer section (adjust coords if needed)
        w, h = img.size
        crop_box = (int(0.05 * w), int(0.65 * h), int(0.95 * w), int(0.95 * h))
        cropped = img.crop(crop_box)

        # OCR to extract text
        text = pytesseract.image_to_string(cropped, lang="eng+mal")

        # Return both image + extracted text
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")

    except Exception as e:
        return f"Error extracting prayer times: {e}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)