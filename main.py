import os
import asyncio
import threading
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, abort
from playwright.async_api import async_playwright

app = Flask(__name__)
IMG_DIR = "./pdfs"  # still using /pdf path for convenience

if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)

async def save_page_as_image(url, output_path):
    print(f"[{datetime.now()}] Starting screenshot-based image generation: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        await page.goto(url)
        try:
            await page.wait_for_selector("img", timeout=15000)  # Adjust selector as needed
        except Exception as e:
            print(f"[{datetime.now()}] Warning: Image selector not found: {e}")
        await page.screenshot(path=output_path, full_page=True)
        await browser.close()
    print(f"[{datetime.now()}] Saved screenshot to {output_path}")

async def generate_image_for_date(date_str):
    url = f"https://epaper.suprabhaatham.com/details/Kozhikode/{date_str}/1"
    output_path = os.path.join(IMG_DIR, f"Suprabhaatham_{date_str}_page1.png")
    if not os.path.exists(output_path):
        try:
            await save_page_as_image(url, output_path)
        except Exception as e:
            print(f"[{datetime.now()}] Error generating screenshot for {date_str}: {e}")

async def daily_scheduler():
    while True:
        today_str = datetime.now().strftime("%Y-%m-%d")
        await generate_image_for_date(today_str)

        now = datetime.now()
        next_day = (now + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
        wait_seconds = (next_day - now).total_seconds()
        print(f"[{datetime.now()}] Screenshot complete. Sleeping {int(wait_seconds)}s until next run.")
        await asyncio.sleep(wait_seconds)

@app.route("/")
def index():
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"Suprabhaatham_{date_str}_page1.png"
    filepath = os.path.join(IMG_DIR, filename)
    if os.path.exists(filepath):
        return f'<h2>Front Page for {date_str}</h2><a href="/pdf/{filename}">Download Image</a><br><img src="/pdf/{filename}" width="600">'
    else:
        return "<h2>No cached image available yet. Please wait for generation.</h2>"

@app.route("/pdf/<path:filename>")
def serve_file(filename):
    if os.path.exists(os.path.join(IMG_DIR, filename)):
        return send_from_directory(IMG_DIR, filename)
    else:
        abort(404)

@app.route("/health")
def health():
    return "OK", 200

def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(daily_scheduler())

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_background_loop, args=(loop,), daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=8000)