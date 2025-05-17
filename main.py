import asyncio
import json
import os
from aiohttp import web
from playwright.async_api import async_playwright
from datetime import datetime

CACHE_DIR = "cache"

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def cache_file_path(date_str):
    return os.path.join(CACHE_DIR, f"cache_{date_str}.json")

async def scrape(date_str):
    EPAPER_URL = f"https://epaper.suprabhaatham.com/details/Kozhikode/{date_str}/1"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(EPAPER_URL, wait_until="networkidle")
        data = await page.evaluate("window.magazineData")
        pages = data.get("pages", [])
        scraped_data = [page.get("src") for page in pages if "src" in page]
        await browser.close()
        return scraped_data

def load_cache(date_str):
    path = cache_file_path(date_str)
    if os.path.exists(path):
        with open(path, "r") as f:
            print(f"Loading cache from {path}")
            return json.load(f)
    return None

def save_cache(date_str, data):
    path = cache_file_path(date_str)
    with open(path, "w") as f:
        json.dump(data, f)
    print(f"Saved cache to {path}")

async def handle_root(request):
    today_str = datetime.now().strftime("%Y-%m-%d")

    cached_data = load_cache(today_str)
    if cached_data is None:
        print(f"Cache miss for {today_str}, scraping...")
        cached_data = await scrape(today_str)
        save_cache(today_str, cached_data)
    else:
        print(f"Cache hit for {today_str}")

    # Build HTML from cached data
    html = "<html><body>"
    for img_url in cached_data:
        html += f'<img src="{img_url}" style="width:100%;margin-bottom:10px;"><br>'
    html += "</body></html>"

    return web.Response(text=html, content_type='text/html')

async def handle_data(request):
    today_str = datetime.now().strftime("%Y-%m-%d")
    cached_data = load_cache(today_str)
    if cached_data is None:
        print(f"Cache miss for {today_str}, scraping...")
        cached_data = await scrape(today_str)
        save_cache(today_str, cached_data)
    else:
        print(f"Cache hit for {today_str}")
    return web.json_response({"image_urls": cached_data})

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/data", handle_data)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=8000)
    await site.start()
    print("Web server running on port 8000...")
    while True:
        await asyncio.sleep(3600)

async def main():
    await start_web_server()

if __name__ == "__main__":
    asyncio.run(main())