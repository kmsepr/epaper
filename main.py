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
from gtts import gTTS   # ✅ NEW

app = Flask(__name__)

# -------------------- Config --------------------
UPLOAD_FOLDER = "static"
EPAPER_TXT = "epaper.txt"
AUDIO_FOLDER = "static/audio"   # ✅ NEW
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

TELEGRAM_CHANNELS = {
    "Pathravarthakal": "https://t.me/s/Pathravarthakal",
    "DailyCa": "https://t.me/s/DailyCAMalayalam"
}

XML_FOLDER = "telegram_xml"
os.makedirs(XML_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)   # ✅ NEW

LAST_AUDIO_DATE = {}   # ✅ NEW

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

# ------------------ Telegram Fetch ------------------
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

# ------------------ 🔊 AUDIO GENERATION ------------------
def generate_audio_from_feed(channel_name):
    today = datetime.date.today().isoformat()

    # Skip if already generated today
    if LAST_AUDIO_DATE.get(channel_name) == today:
        return

    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")
    if not os.path.exists(path):
        return

    feed = feedparser.parse(path)
    entries = list(feed.entries)[-30:]

    full_text = ""

    for e in entries:
        text = BeautifulSoup(e.get("description", ""), "html.parser").get_text(" ", strip=True)

        # Remove links
        text = re.sub(r"http\S+", "", text)

        if text:
            full_text += text + ". "

    if not full_text.strip():
        return

    full_text = full_text[:4000]
    full_text = "ഇന്നത്തെ പ്രധാന വാർത്തകൾ. " + full_text

    try:
        tts = gTTS(full_text, lang='ml')
        output_path = os.path.join(AUDIO_FOLDER, f"{channel_name}.mp3")
        tts.save(output_path)

        LAST_AUDIO_DATE[channel_name] = today
        print(f"[Daily Audio Generated] {channel_name}")

    except Exception as e:
        print(f"[TTS Error] {e}")

def audio_updater():
    while True:
        for name in TELEGRAM_CHANNELS.keys():
            generate_audio_from_feed(name)
        time.sleep(3600)

# ------------------ Browser ------------------
@app.route("/browse")
def browse():
    url = request.args.get("url", "")
    if not url:
        return "<p>No URL provided.</p>", 400
    if not re.match(r"^https?://", url):
        url = "https://" + url
    return f"""
    <html>
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

    if not os.path.exists(path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])

    feed = feedparser.parse(path)
    entries = list(feed.entries)[::-1]

    posts = ""
    count = 0

    for e in entries:
        title = e.get("title", "").lower()
        if "pinned" in title:
            continue

        link = e.get("link", TELEGRAM_CHANNELS[channel_name])
        desc_html = e.get("description", "").strip()
        soup = BeautifulSoup(desc_html, "html.parser")

        for tag in soup.find_all(["video","iframe","audio","script","style"]):
            tag.decompose()

        img_tag = soup.find("img")
        text_only = soup.get_text(strip=True)

        if not text_only and not img_tag:
            continue

        content_html = ""
        if img_tag:
            content_html += f"<img src='{img_tag['src']}'>"
        if text_only:
            content_html += f"<p>{text_only}</p>"

        posts += f"<div class='post'><a href='{link}'>{content_html}</a></div>"

        count += 1
        if count >= 50:
            break

    return f"<html><body>{posts}</body></html>"

# ------------------ ePaper ------------------
@app.route("/today")
def today_links():
    url = get_url_for_location("Malappuram")
    return f"<script>window.location='/browse?url='+encodeURIComponent('{url}');</script>"

# ------------------ Home ------------------
@app.route("/")
def homepage():
    return """
    <html>
    <body style="text-align:center">
        <h2>പത്രവാർത്തകൾ</h2>
        <a href="/today">ePaper</a><br><br>
        <a href="/telegram/Pathravarthakal">News</a><br><br>
        <a href="/telegram/DailyCa">DailyCa</a>
    </body>
    </html>
    """

# ------------------ Run ------------------
if __name__ == "__main__":
    threading.Thread(target=update_epaper_json, daemon=True).start()
    threading.Thread(target=telegram_updater, daemon=True).start()
    threading.Thread(target=audio_updater, daemon=True).start()   # ✅ NEW
    app.run(host="0.0.0.0", port=8000)