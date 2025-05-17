import asyncio
import json
import os
from aiohttp import web
from playwright.async_api import async_playwright
from datetime import datetime

CACHE_DIR = "/app/cache"

# Ensure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)

def cache_file_path(date_str):
    return os.path.join(CACHE_DIR, f"cache_{date_str}.json")

async def scrape(date_str):
    EPAPER_URL = f"https://epaper.suprabhaatham.com/details/Kozhikode/{date_str}/1"
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/chromium",
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )
        page = await browser.new_page()
        print(f"Scraping: {EPAPER_URL}")
        await page.goto(EPAPER_URL, wait_until="networkidle")
        data = await page.evaluate("window.magazineData")
        await browser.close()
        pages = data.get("pages", [])
        return [page.get("src") for page in pages if "src" in page]

def load_cache(date_str):
    path = cache_file_path(date_str)
    if os.path.exists(path):
        print(f"Cache hit: {path}")
        with open(path, "r") as f:
            return json.load(f)
    return None

def save_cache(date_str, data):
    path = cache_file_path(date_str)
    with open(path, "w") as f:
        json.dump(data, f)
    print(f"Cache saved: {path}")

async def handle_root(request):
    today_str = datetime.now().strftime("%Y-%m-%d")
    cached_data = load_cache(today_str)
    if cached_data is None:
        print("No cache. Scraping fresh data...")
        try:
            cached_data = await scrape(today_str)
            save_cache(today_str, cached_data)
        except Exception as e:
            return web.Response(text=f"Error: {e}", content_type='text/plain')

    html = "<html><body><h1>Today's Suprabhaatham ePaper</h1>"
    for img in cached_data:
        html += f'<img src="{img}" style="width:100%;margin-bottom:10px;"><br>'
    html += "</body></html>"
    return web.Response(text=html, content_type='text/html')

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_root)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8000)
    await site.start()
    print("Server running at http://0.0.0.0:8000")

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(start_web_server())