import os
import time
import threading
import requests
import brotli
import logging
from flask import Flask, Response, render_template_string

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
app = Flask(__name__)

EPAPER_URL = "https://suprabhaatham.com/api/epaper"
EPAPER_FILE = "epaper.txt"

# ------------------------------
# Fetch Suprabhaatham ePaper data safely
# ------------------------------
def fetch_epaper_data():
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "User-Agent": "Mozilla/5.0 (compatible; ePaperBot/1.0)"
    }
    res = requests.get(EPAPER_URL, headers=headers, timeout=15)
    res.raise_for_status()

    # Handle Brotli compression safely
    encoding = res.headers.get("content-encoding", "")
    if "br" in encoding:
        data = brotli.decompress(res.content).decode("utf-8")
    else:
        data = res.text
    return data


# ------------------------------
# Background updater thread
# ------------------------------
def update_epaper_loop():
    while True:
        try:
            logging.info("Fetching latest ePaper data...")
            data = fetch_epaper_data()
            with open(EPAPER_FILE, "w", encoding="utf-8") as f:
                f.write(data)
            logging.info("✅ ePaper data updated successfully.")
        except Exception as e:
            logging.error("[Error updating epaper.txt] %s", e)
        time.sleep(24 * 60 * 60)  # Update once every 24 hours


# ------------------------------
# Flask Routes
# ------------------------------
@app.route("/")
def index():
    html = """
    <h2>Suprabhaatham ePaper Monitor</h2>
    <p>This server automatically fetches and updates Suprabhaatham ePaper data daily.</p>
    <p><a href="/epaper">View latest epaper.txt</a></p>
    """
    return render_template_string(html)


@app.route("/epaper")
def serve_epaper():
    if not os.path.exists(EPAPER_FILE):
        return Response("No data yet. Please wait for the first update.", mimetype="text/plain")
    with open(EPAPER_FILE, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/plain")


# ------------------------------
# Start background thread
# ------------------------------
def start_background_updater():
    thread = threading.Thread(target=update_epaper_loop, daemon=True)
    thread.start()

if __name__ == "__main__":
    start_background_updater()
    app.run(host="0.0.0.0", port=8000)