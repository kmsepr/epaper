import os
import time
import json
import feedparser
import threading
import datetime
import requests
import brotli
import re
from flask import Flask, render_template_string, Response, request, abort
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

app = Flask(__name__)

# -------------------- Config --------------------
UPLOAD_FOLDER = "static"
EPAPER_TXT = "epaper.txt"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

LOCATIONS = [
    "Kozhikode", "Malappuram", "Kannur", "Thrissur",
    "Kochi", "Thiruvananthapuram", "Palakkal", "Gulf"
]
RGB_COLORS = [
    "#FF6B6B", "#6BCB77", "#4D96FF", "#FFD93D",
    "#FF6EC7", "#00C2CB", "#FFA41B", "#845EC2"
]

TELEGRAM_CHANNELS = {
    "Pathravarthakal": "https://t.me/s/Pathravarthakal",
    "DailyCa": "https://t.me/s/DailyCAMalayalam"
}
XML_FOLDER = "telegram_xml"
os.makedirs(XML_FOLDER, exist_ok=True)

# ------------------ Utility ------------------
def get_url_for_location(location, dt_obj=None):
    if dt_obj is None:
        dt_obj = datetime.datetime.now()
    date_str = dt_obj.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

# ------------------ Threads ------------------
def update_epaper_json():
    url = "https://api2.suprabhaatham.com/api/ePaper"
    headers = {"Content-Type": "application/json", "Accept-Encoding": "br"}
    while True:
        try:
            r = requests.post(url, json={}, headers=headers, timeout=10)
            if r.headers.get('Content-Encoding') == 'br':
                data = brotli.decompress(r.content).decode('utf-8')
            else:
                data = r.text
            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(data)
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")
        time.sleep(8640)

def fetch_telegram_xml(name, url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        rss_root = ET.Element("rss", version="2.0")
        ch = ET.SubElement(rss_root, "channel")
        ET.SubElement(ch, "title").text = f"{name} Telegram Feed"

        for msg in soup.select(".tgme_widget_message_wrap")[:40]:
            date_tag = msg.select_one("a.tgme_widget_message_date")
            link = date_tag["href"] if date_tag and "href" in date_tag.attrs else url
            text_tag = msg.select_one(".tgme_widget_message_text")
            desc_html = text_tag.decode_contents() if text_tag else ""

            item = ET.SubElement(ch, "item")
            title_text = BeautifulSoup(desc_html, "html.parser").get_text(strip=True)
            ET.SubElement(item, "title").text = title_text[:80] + ("..." if len(title_text) > 80 else "")
            ET.SubElement(item, "link").text = link
            ET.SubElement(item, "description").text = desc_html

        ET.ElementTree(rss_root).write(
            os.path.join(XML_FOLDER, f"{name}.xml"),
            encoding="utf-8",
            xml_declaration=True
        )
    except Exception as e:
        print(f"[Error fetching {name}] {e}")

def telegram_updater():
    while True:
        for name, url in TELEGRAM_CHANNELS.items():
            fetch_telegram_xml(name, url)
        time.sleep(600)

# ------------------ Browser ------------------
@app.route("/browse")
def browse():
    url = request.args.get("url", "")
    if not url:
        return "<p>No URL provided.</p>", 400
    if not re.match(r"^https?://", url):
        url = "https://" + url
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width,initial-scale=1.0">
        <title>Browser - {url}</title>
    </head>
    <body style="margin:0">
        <iframe src="{url}" style="border:none;width:100%;height:100vh;"></iframe>
    </body>
    </html>
    """

# ------------------ Telegram HTML ------------------
@app.route("/telegram/<channel_name>")
def telegram_html(channel_name):
    if channel_name not in TELEGRAM_CHANNELS:
        return f"<p>Error: Channel '{channel_name}' not found.</p>", 404

    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")

    refresh_now = request.args.get("refresh") == "1"
    if refresh_now or not os.path.exists(path) or (time.time() - os.path.getmtime(path) > 120):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])

    try:
        feed = feedparser.parse(path)

        # ✅ NEWEST FIRST (without modifying feed structure)
        entries = list(feed.entries)[::-1]

        posts = ""
        for e in entries[:50]:
            link = e.get("link", TELEGRAM_CHANNELS[channel_name])
            desc_html = e.get("description", "").strip()
            soup = BeautifulSoup(desc_html, "html.parser")

            for tag in soup.find_all([
                "video", "iframe", "source", "audio",
                "svg", "poll", "button", "script", "style"
            ]):
                tag.decompose()

            img_tag = soup.find("img")
            text_only = soup.get_text(strip=True)

            if not text_only and not img_tag:
                continue

            content_html = ""
            if img_tag:
                content_html += f"<img src='{img_tag['src']}' loading='lazy'>"
            if text_only:
                content_html += f"<p>{text_only}</p>"

            posts += f"""
            <div class='post'>
                <a href='{link}' target='_blank'>{content_html}</a>
            </div>
            """

        last_updated = datetime.datetime.fromtimestamp(
            os.path.getmtime(path)
        ).strftime("%Y-%m-%d %H:%M:%S")

        return f"""
        <html><head>
        <meta name='viewport' content='width=device-width,initial-scale=1.0'>
        <title>{channel_name} Posts</title>
        </head><body>
        <h2>Telegram: {channel_name}
            <a href='?refresh=1'>🔄 Refresh</a>
        </h2>
        <div>Last updated: {last_updated}</div>
        {posts or "<p>No text or image posts found.</p>"}
        <p><a href='/'>🏠 Home</a></p>
        </body></html>
        """
    except Exception as e:
        return f"<p>Error loading feed: {e}</p>"

# ------------------ ePaper Routes ------------------
@app.route("/today")
def today_links():
    # ✅ Directly open Malappuram
    url = get_url_for_location("Malappuram")
    return f"""
    <script>
        window.location = "/browse?url=" + encodeURIComponent("{url}");
    </script>
    """

# ------------------ Home ------------------
@app.route("/")
def homepage():
    return """
    <h1>Lite Browser</h1>
    <p><a href="/today">📰 Today's ePaper</a></p>
    <p><a href="/telegram/Pathravarthakal">📣 Pathravarthakal</a></p>
    <p><a href="/telegram/DailyCa">🗞️ DailyCa</a></p>
    """

# ------------------ Run ------------------
if __name__ == "__main__":
    os.makedirs(XML_FOLDER, exist_ok=True)
    threading.Thread(target=update_epaper_json, daemon=True).start()
    threading.Thread(target=telegram_updater, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
