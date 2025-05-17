import asyncio
from playwright.async_api import async_playwright
import json

EPAPER_URL = "https://epaper.suprabhaatham.com/details/Kozhikode/2025-05-17/1"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(EPAPER_URL, wait_until="networkidle")

        # Get window.magazineData
        data = await page.evaluate("window.magazineData")

        # Optional: extract image URLs from all pages
        pages = data.get("pages", [])
        image_urls = [page.get("src") for page in pages if "src" in page]

        print("Page image URLs:")
        for url in image_urls:
            print(url)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())