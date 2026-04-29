import os
import time
import feedparser
import threading
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
        time.sleep(600)  # every 10 minutes

# ------------------ 🔊 AUDIO ------------------
def generate_audio_from_feed(channel_name):
    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")

    if not os.path.exists(path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])

    feed = feedparser.parse(path)
    entries = list(feed.entries)[-25:]

    full_text = "ഇന്നത്തെ പ്രധാന വാർത്തകൾ.\n\n"

    for e in entries:
        desc_text = e.get("description", "")

        # 🔥 Remove emojis (FULL FIX)
        desc_text = re.sub(r"[\U0001F300-\U0001FAFF]", " ", desc_text)
        desc_text = re.sub(r"[\U0001F600-\U0001F64F]", " ", desc_text)
        desc_text = re.sub(r"[\u2600-\u27BF]", " ", desc_text)   # ✅ ✔ ☑ etc
        desc_text = re.sub(r"[\uFE0F\u200D]", " ", desc_text)

        # 🔥 Remove hashtags
        desc_text = re.sub(r"#\w+", "", desc_text)

        # 🔥 Remove URLs
        desc_text = re.sub(r"http\S+", "", desc_text)

        # 🔥 Remove trailing join text
        desc_text = re.sub(r"(join\s*@\w+.*)$", "", desc_text, flags=re.IGNORECASE)

        # 🔥 Remove @mentions
        desc_text = re.sub(r"@\w+", "", desc_text)

        # 🔥 Replace punctuation (avoid "ആശ്ചര്യ ചിഹ്നം")
        desc_text = re.sub(r"[!?:;]+", ". ", desc_text)

        # 🔥 Remove other unwanted symbols
        desc_text = re.sub(r"[\"'(){}\[\]<>]", " ", desc_text)

        # Clean spaces
        desc_text = re.sub(r"\s+", " ", desc_text).strip()

        # 🔥 Fallback if empty
        if not desc_text or len(desc_text) < 5:
            desc_text = e.get("title", "")

        if not desc_text:
            continue

        full_text += f"{desc_text}.\n\n"

    if len(full_text.strip()) < 10:
        full_text = "ഇന്ന് വാർത്തകൾ ലഭ്യമല്ല."

    try:
        tts = gTTS(full_text, lang='ml')
        output_path = os.path.join(AUDIO_FOLDER, f"{channel_name}.mp3")
        tts.save(output_path)

        print(f"[Audio Updated] {channel_name}")

    except Exception as e:
        print(f"[TTS Error] {e}")

def audio_updater():
    while True:
        for name in TELEGRAM_CHANNELS:
            generate_audio_from_feed(name)
        time.sleep(600)  # every 10 minutes

# ------------------ Feed Page ------------------
@app.route("/telegram/<channel_name>")
def telegram_html(channel_name):
    if channel_name not in TELEGRAM_CHANNELS:
        return "Invalid channel"

    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")

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
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <style>
            body {
                font-family: 'Segoe UI', Roboto, sans-serif;
                background: #f0f2f5;
                margin: 0;
                padding: 10px;
                text-align: center;
                color: #333;
            }

            h1 {
                font-size: 22px;
                color: #d32f2f; /* Deep Red */
                margin: 10px 0;
                border-bottom: 2px solid #d32f2f;
                padding-bottom: 5px;
            }

            .section-header {
                display: flex;
                align-items: center;
                justify-content: center;
                margin-top: 15px;
                font-weight: bold;
                font-size: 14px;
                text-transform: uppercase;
                color: #555;
            }

            /* Keypad Friendly Buttons */
            .btn {
                display: block;
                width: 90%;
                margin: 10px auto;
                padding: 15px 5px;
                font-size: 18px;
                font-weight: bold;
                text-decoration: none;
                border-radius: 10px;
                border: 2px solid transparent;
                transition: all 0.2s;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }

            /* Specific Colors for clarity */
            .audio-btn { background: #e3f2fd; color: #1565c0; border-color: #bbdefb; }
            .feed-btn { background: #f1f8e9; color: #2e7d32; border-color: #c8e6c9; }

            /* Focus state is CRITICAL for keypad navigation */
            .btn:focus, .btn:active {
                background: #ffeb3b !important; /* Bright Yellow focus */
                color: #000 !important;
                border: 3px solid #000 !important;
                outline: none;
                transform: scale(1.02);
            }

            .key-hint {
                font-size: 12px;
                background: rgba(0,0,0,0.1);
                padding: 2px 6px;
                border-radius: 4px;
                margin-right: 8px;
            }
        </style>
    </head>
    <body>

    <h1>📰 വാർത്തകൾ</h1>

    <div class="section-header">🎧 AUDIO CONTENT</div>

    <a class="btn audio-btn" href="/static/audio/Pathravarthakal.mp3" accesskey="1">
        <span class="key-hint">1</span> Pathravarthakal
    </a>

    <a class="btn audio-btn" href="/static/audio/DailyCa.mp3" accesskey="2">
        <span class="key-hint">2</span> Daily CA
    </a>

    <div class="section-header">📰 NEWS FEEDS</div>

    <a class="btn feed-btn" href="/telegram/Pathravarthakal" accesskey="3">
        <span class="key-hint">3</span> Pathravarthakal Feed
    </a>

    <a class="btn feed-btn" href="/telegram/DailyCa" accesskey="4">
        <span class="key-hint">4</span> Daily CA Feed
    </a>

    <p style="font-size: 10px; color: #888; margin-top: 20px;">Use Up/Down keys to navigate</p>

    </body>
    </html>
    """
# ------------------ Run ------------------
if __name__ == "__main__":
    threading.Thread(target=telegram_updater, daemon=True).start()
    threading.Thread(target=audio_updater, daemon=True).start()

    app.run(host="0.0.0.0", port=8000)
