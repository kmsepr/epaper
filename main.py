import os
import time
import feedparser
import threading
import datetime
import requests
import re
from flask import Flask
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

            # Remove links, usernames, telegram junk
            clean_text = re.sub(r"http\S+", "", clean_text)
            clean_text = re.sub(r"@\w+", "", clean_text)
            clean_text = re.sub(r"(View in Telegram|Join Channel|Telegram|Open App)", "", clean_text, flags=re.IGNORECASE)

            clean_text = re.sub(r"\s+", " ", clean_text).strip()

            short_title = clean_text[:100] + ("..." if len(clean_text) > 100 else "")

            item = ET.SubElement(ch, "item")
            ET.SubElement(item, "title").text = short_title
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

    if not os.path.exists(path):
        return

    feed = feedparser.parse(path)
    entries = list(feed.entries)[-60:]

    full_text = "ഇന്നത്തെ പ്രധാന വാർത്തകൾ. "

    for e in entries:
        title = e.get("title", "")
        desc_text = e.get("description", "")

        # Remove links, usernames, junk
        desc_text = re.sub(r"http\S+", "", desc_text)
        desc_text = re.sub(r"@\w+", "", desc_text)
        desc_text = re.sub(r"(View in Telegram|Join Channel|Telegram|Open App)", "", desc_text, flags=re.IGNORECASE)

        # 🔥 Remove emojis (MAIN FIX)
        desc_text = re.sub(r"[\U00010000-\U0010ffff]", " ", desc_text)

        # Keep Malayalam + English + numbers + punctuation
        desc_text = re.sub(r"[^\u0D00-\u0D7Fa-zA-Z0-9\s.,!?]", " ", desc_text)

        # Clean spaces
        desc_text = re.sub(r"\s+", " ", desc_text).strip()

        # Skip useless
        if len(desc_text) < 20:
            continue

        full_text += f"വാർത്ത. {title}. വിശദാംശങ്ങൾ. {desc_text}. . . "

    if not full_text.strip():
        return

    # Limit size (gTTS safe)
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
    # Run immediately
    for name in TELEGRAM_CHANNELS.keys():
        generate_audio_from_feed(name)

    while True:
        for name in TELEGRAM_CHANNELS.keys():
            generate_audio_from_feed(name)
        time.sleep(3600)

# ------------------ Home ------------------
@app.route("/")
def home():
    return """
    <h2>പത്രവാർത്തകൾ</h2>

    <h3>🎧 Audio News</h3>
    <a href="/static/audio/Pathravarthakal.mp3">Pathravarthakal Audio</a><br><br>
    <a href="/static/audio/DailyCa.mp3">DailyCa Audio</a><br><br>

    <h3>📰 Feeds</h3>
    <a href="/telegram/Pathravarthakal">Pathravarthakal Feed</a><br><br>
    <a href="/telegram/DailyCa">DailyCa Feed</a>
    """

# ------------------ Feed View ------------------
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
    threading.Thread(target=telegram_updater, daemon=True).start()
    threading.Thread(target=audio_updater, daemon=True).start()

    app.run(host="0.0.0.0", port=8000)