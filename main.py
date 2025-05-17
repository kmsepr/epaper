import asyncio
from playwright.async_api import async_playwright

async def save_page_as_pdf(url, output_path):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        await page.pdf(path=output_path, format="A4")
        await browser.close()
        print(f"Saved PDF to {output_path}")

url = "https://epaper.suprabhaatham.com/details/Kozhikode/2025-05-17/1"
output_path = "Suprabhaatham_2025-05-17_page1.pdf"

asyncio.run(save_page_as_pdf(url, output_path))