import os
import asyncio
import datetime
import glob
import threading
from flask import Flask, jsonify, send_from_directory, url_for
from playwright.async_api import async_playwright

app = Flask(__name__)

PDF_DIR = "./pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

def get_today_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")

async def save_page_as_pdf(url, output_path):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        await page.pdf(path=output_path, format="A4")
        await browser.close()
        print(f"Saved PDF to {output_path}")

async def generate_today_pdf():
    date_str = get_today_str()
    url = f"https://epaper.suprabhaatham.com/details/Kozhikode/{date_str}/1"
    filename = f"Suprabhaatham_{date_str}_page1.pdf"
    output_path = os.path.join(PDF_DIR, filename)

    if not os.path.exists(output_path):
        print(f"Generating PDF for {date_str}")
        await save_page_as_pdf(url, output_path)
    else:
        print(f"PDF for {date_str} already cached")

async def clear_old_pdfs():
    today_str = get_today_str()
    for f in glob.glob(os.path.join(PDF_DIR, "*.pdf")):
        if today_str not in f:
            try:
                os.remove(f)
                print(f"Removed old cached PDF: {f}")
            except Exception as e:
                print(f"Error removing file {f}: {e}")

async def daily_task():
    while True:
        await clear_old_pdfs()
        await generate_today_pdf()
        # Sleep 24 hours before next run
        await asyncio.sleep(24 * 3600)

def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(daily_task())

@app.route("/")
def index():
    files = os.listdir(PDF_DIR)
    if not files:
        return "<h1>No cached PDFs available yet. Please wait for generation.</h1>"
    html = "<h1>Cached PDFs</h1><ul>"
    for f in files:
        link = url_for('serve_pdf', filename=f)
        html += f'<li><a href="{link}">{f}</a></li>'
    html += "</ul>"
    return html

@app.route("/pdfs/<path:filename>")
def serve_pdf(filename):
    return send_from_directory(PDF_DIR, filename)

if __name__ == "__main__":
    # Start asyncio background loop in a separate thread
    new_loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_background_loop, args=(new_loop,), daemon=True)
    t.start()

    # Run Flask server
    app.run(host="0.0.0.0", port=8000)