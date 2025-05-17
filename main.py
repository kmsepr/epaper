import asyncio
from playwright.async_api import async_playwright
from aiohttp import web

EPAPER_URL = "https://epaper.suprabhaatham.com/details/Kozhikode/2025-05-17/1"

async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(EPAPER_URL, wait_until="networkidle")

        data = await page.evaluate("window.magazineData")
        pages = data.get("pages", [])
        image_urls = [page.get("src") for page in pages if "src" in page]
        print("Page image URLs:")
        for url in image_urls:
            print(url)

        await browser.close()

# Dummy HTTP server to pass health check
async def handle(request):
    return web.Response(text="OK")

app = web.Application()
app.router.add_get("/", handle)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(run_scraper())  # Run scraper in background
    web.run_app(app, port=8000)      # Run dummy web server