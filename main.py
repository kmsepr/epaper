import asyncio
from aiohttp import web
from playwright.async_api import async_playwright

EPAPER_URL = "https://epaper.suprabhaatham.com/details/Kozhikode/2025-05-17/1"
scraped_data = []

async def scrape():
    global scraped_data
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(EPAPER_URL, wait_until="networkidle")
        data = await page.evaluate("window.magazineData")
        pages = data.get("pages", [])
        scraped_data = [page.get("src") for page in pages if "src" in page]
        print("Scraped URLs:", scraped_data)
        await browser.close()

async def handle_root(request):
    return web.Response(text="Scraper is running!")

async def handle_data(request):
    return web.json_response({"image_urls": scraped_data})

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
    await asyncio.gather(
        scrape(),
        start_web_server()
    )

if __name__ == "__main__":
    asyncio.run(main())