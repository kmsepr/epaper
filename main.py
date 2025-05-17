import os
import asyncio
from flask import Flask, request, jsonify, send_from_directory, url_for
from playwright.async_api import async_playwright

app = Flask(__name__)

PDF_DIR = "./pdfs"
os.makedirs(PDF_DIR, exist_ok=True)

async def save_page_as_pdf(url, output_path):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        await page.pdf(path=output_path, format="A4")
        await browser.close()
        print(f"Saved PDF to {output_path}")

@app.route("/")
def index():
    files = os.listdir(PDF_DIR)
    html = "<h1>Cached PDFs</h1><ul>"
    for f in files:
        link = url_for('serve_pdf', filename=f)
        html += f'<li><a href="{link}">{f}</a></li>'
    html += "</ul>"
    return html

@app.route("/generate_pdf")
def generate_pdf():
    url = request.args.get("url", "https://epaper.suprabhaatham.com/details/Kozhikode/2025-05-17/1")
    filename = request.args.get("filename", "page1.pdf")
    output_path = os.path.join(PDF_DIR, filename)

    if os.path.exists(output_path):
        return jsonify({"message": "PDF served from cache", "filename": filename})

    asyncio.run(save_page_as_pdf(url, output_path))
    return jsonify({"message": "PDF generated and saved", "filename": filename})

@app.route("/list_pdfs")
def list_pdfs():
    files = os.listdir(PDF_DIR)
    return jsonify({"pdf_files": files})

@app.route("/pdfs/<path:filename>")
def serve_pdf(filename):
    return send_from_directory(PDF_DIR, filename)

@app.route("/clear_cache", methods=["POST"])
def clear_cache():
    for f in os.listdir(PDF_DIR):
        try:
            os.remove(os.path.join(PDF_DIR, f))
        except Exception:
            pass
    return jsonify({"message": "Cache cleared"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)