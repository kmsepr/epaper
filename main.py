import os
import time
import feedparser
import threading
import datetime
import requests
import re
from flask import Flask, request
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from gtts import gTTS

app = Flask(__name__)

# -------------------- Config --------------------
AUDIO_FOLDER = "static/audio"
XML_FOLDER = "telegram_xml"

TELEGRAM_CHANNELS = {
    "Pathravarthakal": "https://t.me/s/Pathravarthakal",
    "DailyCa": "https://t.me/s/DailyCAMalayalam"
}

os.makedirs(XML_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

LAST_AUDIO_DATE = {}

# ------------------ Telegram Fetch ------------------
def fetch_telegram_xml(name, url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        rss_root = ET.Element("rss", version="2.0")
        ch = ET.SubElement(rss_root, "channel")
        ET.SubElement(ch, "title").text = f"{name} Telegram Feed"

        for msg in soup.select(".tgme_widget_message_wrap")[:80]:
            date_tag = msg.select_one("a.tgme_widget_message_date")
            link = date_tag["href"] if date_tag and "href" in date_tag.attrs else url

            text_tag = msg.select_one(".tgme_widget_message_text")
            desc_html = text_tag.decode_contents() if text_tag else ""

            clean_text = BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)

            item = ET.SubElement(ch, "item")
            ET.SubElement(item, "title").text = clean_text[:100]
            ET.SubElement(item, "link").text = link
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

    if not os.path.exists(path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])

    feed = feedparser.parse(path)
    entries = list(feed.entries)[-60:]

    full_text = "ഇന്നത്തെ പ്രധാന വാർത്തകൾ. "

    for e in entries:
        raw_text = e.get("description", "")

        # 🔥 SPLIT CONTENT (MAIN FIX)
        parts = re.split(r"[👉🔰•\n]+", raw_text)

        for part in parts:
            desc_text = part.strip()

            if not desc_text:
                continue

            # ---------------- CLEAN ----------------
            desc_text = re.sub(r"http\S+", "", desc_text)
            desc_text = re.sub(r"@\w+", "", desc_text)

            # Remove emojis fully
            desc_text = re.sub(r"[\U0001F000-\U0001FFFF]", " ", desc_text)
            desc_text = re.sub(r"[\u2600-\u27BF]", " ", desc_text)
            desc_text = re.sub(r"[\uFE0F\u200D]", " ", desc_text)

            # Remove hashtags
            desc_text = re.sub(r"#\w+", "", desc_text)

            # Keep Malayalam + English
            desc_text = re.sub(r"[^\u0D00-\u0D7Fa-zA-Z0-9\s.,!?:-]", " ", desc_text)

            desc_text = re.sub(r"\s+", " ", desc_text).strip()

            # ---------------- FILTER ----------------
            skip_words = [
                "join", "demo", "class", "batch", "pdf",
                "whatsapp", "വാട്സ്ആപ്പ്",
                "channel", "message", "click",
                "fee", "psc", "keralapsc", "dailycamalayalam"
            ]

            if any(word in desc_text.lower() for word in skip_words):
                continue

            if len(desc_text) < 20 or len(desc_text) > 250:
                continue

            # ---------------- ADD ----------------
            full_text += f"വാർത്ത. {desc_text}. . . "

    if len(full_text) < 50:
        return

    if len(full_text) > 3500:
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
    for name in TELEGRAM_CHANNELS:
        generate_audio_from_feed(name)

    while True:
        for name in TELEGRAM_CHANNELS:
            generate_audio_from_feed(name)
        time.sleep(600)

# ------------------ Feed Page ------------------
@app.route("/telegram/<channel_name>")
def telegram_html(channel_name):
    if channel_name not in TELEGRAM_CHANNELS:
        return "Invalid channel"

    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")

    # 🔥 Refresh button trigger
    if request.args.get("refresh") == "1":
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])

    if not os.path.exists(path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])

    feed = feedparser.parse(path)
    entries = list(feed.entries)[::-1]

    posts = ""
    for e in entries[:50]:
        posts += f"<p>{e.get('description','')}</p><hr>"

    return f"""
    <html>
    <head>
    <meta name='viewport' content='width=device-width,initial-scale=1.0'>
    <style>
    body {{font-family:system-ui;padding:10px;}}
    .btn {{background:#00695c;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;}}
    </style>
    </head>
    <body>

    <h2>{channel_name}</h2>
    <a class="btn" href="?refresh=1">🔄 Refresh</a><br><br>

    {posts}

    </body>
    </html>
    """

# ------------------ Home ------------------
@app.route("/")
def home():
    return """
    <h2>പത്രവാർത്തകൾ</h2>

    <h3>🎧 Audio</h3>
    <a href="/static/audio/Pathravarthakal.mp3">Pathravarthakal</a><br><br>
    <a href="/static/audio/DailyCa.mp3">DailyCa</a><br><br>

    <h3>📰 Feeds</h3>
    <a href="/telegram/Pathravarthakal">Pathravarthakal</a><br><br>
    <a href="/telegram/DailyCa">DailyCa</a>
    """

# ------------------ Run ------------------
if __name__ == "__main__":
    threading.Thread(target=telegram_updater, daemon=True).start()
    threading.Thread(target=audio_updater, daemon=True).start()

    app.run(host="0.0.0.0", port=8000)