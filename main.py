import os
import asyncio
import threading
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, abort
from playwright.async_api import async_playwright

app = Flask(__name__)
PDF_DIR = "./pdfs"

if not os.path.exists(PDF_DIR):
    os.makedirs(PDF_DIR)

async def save_page_as_pdf(url, output_path):
    print(f"[{datetime.now()}] Starting PDF generation: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        await page.pdf(path=output_path, format="A4")
        await browser.close()
    print(f"[{datetime.now()}] Saved PDF to {output_path}")

async def generate_pdf_for_date(date_str):
    url = f"https://epaper.suprabhaatham.com/details/Kozhikode/{date_str}/1"
    output_path = os.path.join(PDF_DIR, f"Suprabhaatham_{date_str}_page1.pdf")
    if not os.path.exists(output_path):
        try:
            await save_page_as_pdf(url, output_path)
        except Exception as e:
            print(f"[{datetime.now()}] Error generating PDF for {date_str}: {e}")

async def daily_pdf_scheduler():
    while True:
        today_str = datetime.now().strftime("%Y-%m-%d")
        await generate_pdf_for_date(today_str)

        # Calculate seconds until next day at 00:01 AM
        now = datetime.now()
        next_day = (now + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
        wait_seconds = (next_day - now).total_seconds()
        print(f"[{datetime.now()}] PDF generation complete, sleeping for {int(wait_seconds)} seconds until next run.")
        await asyncio.sleep(wait_seconds)

@app.route("/")
def index():
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"Suprabhaatham_{date_str}_page1.pdf"
    filepath = os.path.join(PDF_DIR, filename)
    if os.path.exists(filepath):
        return f'<h2>PDF for {date_str}</h2><a href="/pdf/{filename}">Download PDF</a>'
    else:
        return "<h2>No cached PDFs available yet. Please wait for generation.</h2>"

@app.route("/pdf/<path:filename>")
def serve_pdf(filename):
    if os.path.exists(os.path.join(PDF_DIR, filename)):
        return send_from_directory(PDF_DIR, filename)
    else:
        abort(404)

@app.route("/health")
def health():
    return "OK", 200

def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(daily_pdf_scheduler())

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_background_loop, args=(loop,), daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=8000)