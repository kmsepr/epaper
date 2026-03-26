import os
import time
import feedparser
import threading
import datetime
import requests
import brotli
import re
from flask import Flask, request
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from gtts import gTTS

app = Flask(__name__)

# -------------------- Config --------------------
UPLOAD_FOLDER = "static"
EPAPER_TXT = "epaper.txt"
AUDIO_FOLDER = "static/audio"

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

TELEGRAM_CHANNELS = {
    "Pathravarthakal": "https://t.me/s/Pathravarthakal",
    "DailyCa": "https://t.me/s/DailyCAMalayalam"
}

XML_FOLDER = "telegram_xml"

os.makedirs(XML_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

LAST_AUDIO_DATE = {}

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

            try:
                if r.headers.get('Content-Encoding') == 'br':
                    data = brotli.decompress(r.content).decode('utf-8')
                else:
                    data = r.text
            except:
                data = r.text

            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(data)

        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")

        time.sleep(8640)

# ------------------ Telegram Fetch (FIXED) ------------------
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

            # ✅ FULL CLEAN TEXT
            clean_text = BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)

            # Remove links
            clean_text = re.sub(r"http\S+", "", clean_text)

            # Short title
            short_title = clean_text[:100] + ("..." if len(clean_text) > 100 else "")

            item = ET.SubElement(ch, "item")
            ET.SubElement(item, "title").text = short_title
            ET.SubElement(item, "link").text = link

            # ✅ FULL TEXT STORED HERE
            ET.SubElement(item, "description").text = clean_text

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

# ------------------ 🔊 AUDIO ------------------
def generate_audio_from_feed(channel_name):
    today = datetime.date.today().isoformat()

    if LAST_AUDIO_DATE.get(channel_name) == today:
        return

    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")

    # Ensure XML exists
    if not os.path.exists(path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])

    if not os.path.exists(path):
        print("[Audio] XML missing:", channel_name)
        return

    feed = feedparser.parse(path)
    entries = list(feed.entries)[-30:]

    full_text = "ഇന്നത്തെ പ്രധാന വാർത്തകൾ. "

    for e in entries:
        title = e.get("title", "")
        desc_text = e.get("description", "")

        # Clean Malayalam text
        desc_text = re.sub(r"[A-Za-z]+", "", desc_text)

        combined = f"{title}. {desc_text}"

        if combined.strip():
            full_text += combined + " . . "

    if not full_text.strip():
        print("[Audio] Empty text")
        return

    full_text = full_text[:3500]

    try:
        tts = gTTS(full_text, lang='ml')
        output_path = os.path.join(AUDIO_FOLDER, f"{channel_name}.mp3")
        tts.save(output_path)

        LAST_AUDIO_DATE[channel_name] = today
        print(f"[Audio Generated] {channel_name}")

    except Exception as e:
        print(f"[TTS Error] {e}")

def audio_updater():
    # Run immediately
    for name in TELEGRAM_CHANNELS.keys():
        generate_audio_from_feed(name)

    while True:
        for name in TELEGRAM_CHANNELS.keys():
            generate_audio_from_feed(name)
        time.sleep(3600)

# ------------------ Routes ------------------
@app.route("/")
def home():
    return """
    <h2>പത്രവാർത്തകൾ</h2>
    <a href="/telegram/Pathravarthakal">News</a><br><br>
    <a href="/telegram/DailyCa">DailyCa</a><br><br>
    <a href="/static/audio/Pathravarthakal.mp3">🎧 Play News Audio</a>
    """

@app.route("/telegram/<channel_name>")
def telegram_html(channel_name):
    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")

    if not os.path.exists(path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])

    feed = feedparser.parse(path)
    entries = list(feed.entries)[::-1]

    posts = ""

    for e in entries[:50]:
        desc = e.get("description", "")
        posts += f"<p>{desc}</p><hr>"

    return posts or "No posts"

# ------------------ Run ------------------
if __name__ == "__main__":
    threading.Thread(target=update_epaper_json, daemon=True).start()
    threading.Thread(target=telegram_updater, daemon=True).start()
    threading.Thread(target=audio_updater, daemon=True).start()

    app.run(host="0.0.0.0", port=8000)