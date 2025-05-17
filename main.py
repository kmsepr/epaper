import asyncio
from aiohttp import web
from playwright.async_api import async_playwright
from datetime import datetime

scraped_data = []

async def scrape(date_str):
    global scraped_data
    EPAPER_URL = f"https://epaper.suprabhaatham.com/details/Kozhikode/{date_str}/1"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(EPAPER_URL, wait_until="networkidle")
        data = await page.evaluate("window.magazineData")
        pages = data.get("pages", [])
        scraped_data = [page.get("src") for page in pages if "src" in page]
        await browser.close()

async def handle_root(request):
    # get today's date as yyyy-mm-dd
    today_str = datetime.now().strftime("%Y-%m-%d")
    await scrape(today_str)

    # Build HTML with all images
    html = "<html><body>"
    for img_url in scraped_data:
        html += f'<img src="{img_url}" style="width:100%;margin-bottom:10px;"><br>'
    html += "</body></html>"
    return web.Response(text=html, content_type='text/html')

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_root)
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