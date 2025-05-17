import os
import asyncio
import threading
from flask import Flask, send_from_directory, abort
from playwright.async_api import async_playwright

app = Flask(__name__)
IMG_DIR = "./pdfs"
IMG_NAME = "frontpage.png"
IMG_PATH = os.path.join(IMG_DIR, IMG_NAME)

if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)

async def save_frontpage_image():
    url = "https://epaper.suprabhaatham.com"
    print(f"Starting screenshot for: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1400, "height": 2000})
        await page.goto(url)
        await page.wait_for_timeout(8000)
        await page.screenshot(path=IMG_PATH, full_page=True)
        await browser.close()
    print(f"Screenshot saved to {IMG_PATH}")

@app.route("/")
def index():
    if os.path.exists(IMG_PATH):
        return f'<h2>Suprabhaatham Front Page</h2><a href="/pdf/{IMG_NAME}">Download Image</a><br><img src="/pdf/{IMG_NAME}" width="600">'
    else:
        return "<h2>No screenshot available yet. Please wait for generation.</h2>"

@app.route("/pdf/<path:filename>")
def serve_file(filename):
    if os.path.exists(os.path.join(IMG_DIR, filename)):
        return send_from_directory(IMG_DIR, filename)
    else:
        abort(404)

async def daily_scheduler():
    while True:
        try:
            await save_frontpage_image()
        except Exception as e:
            print(f"Error: {e}")
        await asyncio.sleep(24 * 60 * 60)

def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(daily_scheduler())

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_background_loop, args=(loop,), daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=8000)