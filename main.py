import os
import time
import feedparser
import threading
import requests
import re
import shutil
from datetime import datetime
from flask import Flask, request, send_from_directory
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import json
from gtts import gTTS

import firebase_admin
from firebase_admin import credentials, firestore, auth

app = Flask(__name__)

# ------------------ FIRESTORE ------------------
# Firebase service-account JSON is kept in the Koyeb
# environment variable FIREBASE_SERVICE_ACCOUNT_JSON.
_firestore_db = None

def get_firestore():
    global _firestore_db

    if _firestore_db is not None:
        return _firestore_db

    firebase_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")

    if not firebase_json:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON is not configured in Koyeb"
        )

    try:
        service_account_info = json.loads(firebase_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON"
        ) from e

    if not firebase_admin._apps:
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred)

    _firestore_db = firestore.client()
    return _firestore_db


# ------------------ FIREBASE WEB AUTH CONFIG ------------------
# These values are for the browser Firebase Authentication client.
# Set them in Koyeb environment variables, or replace the placeholders.
FIREBASE_WEB_CONFIG = {
    "apiKey": os.environ.get("FIREBASE_WEB_API_KEY", "YOUR_FIREBASE_WEB_API_KEY"),
    "authDomain": os.environ.get("FIREBASE_WEB_AUTH_DOMAIN", "YOUR_PROJECT_ID.firebaseapp.com"),
    "projectId": os.environ.get("FIREBASE_PROJECT_ID", "YOUR_PROJECT_ID"),
    "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", "YOUR_PROJECT_ID.firebasestorage.app"),
    "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID", "YOUR_MESSAGING_SENDER_ID"),
    "appId": os.environ.get("FIREBASE_WEB_APP_ID", "YOUR_FIREBASE_WEB_APP_ID")
}



# -------------------- Config --------------------
AUDIO_FOLDER = "static/audio"
XML_FOLDER = "telegram_xml"
ARCHIVE_FOLDER = "archive"

TELEGRAM_CHANNELS = {
    "Pathravarthakal": "https://t.me/s/Pathravarthakal",
    "DailyCa": "https://t.me/s/DailyCAMalayalam"
}

os.makedirs(XML_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)
os.makedirs(ARCHIVE_FOLDER, exist_ok=True)

# ------------------ Feed Archive ------------------
def archive_feed(xml_path):
    try:
        if not os.path.exists(xml_path):
            return

        month_folder = datetime.now().strftime("%Y-%m")

        archive_dir = os.path.join(
            ARCHIVE_FOLDER,
            month_folder
        )

        os.makedirs(archive_dir, exist_ok=True)

        filename = os.path.basename(xml_path)

        archive_path = os.path.join(
            archive_dir,
            filename
        )

        shutil.copy2(xml_path, archive_path)

        print(f"[Feed Archived] {archive_path}")

    except Exception as e:
        print(f"[Archive Error] {e}")

# ------------------ Telegram Fetch ------------------
def fetch_telegram_xml(name, url):
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )

        soup = BeautifulSoup(r.text, "html.parser")

        rss_root = ET.Element("rss", version="2.0")
        ch = ET.SubElement(rss_root, "channel")

        ET.SubElement(ch, "title").text = f"{name} Telegram Feed"

        for msg in soup.select(".tgme_widget_message_wrap")[:80]:

            date_tag = msg.select_one("a.tgme_widget_message_date")

            link = (
                date_tag["href"]
                if date_tag and "href" in date_tag.attrs
                else url
            )

            text_tag = msg.select_one(".tgme_widget_message_text")

            desc_html = (
                text_tag.decode_contents()
                if text_tag else ""
            )

            clean_text = BeautifulSoup(
                desc_html,
                "html.parser"
            ).get_text(" ", strip=True)

            item = ET.SubElement(ch, "item")

            ET.SubElement(item, "title").text = clean_text[:100]
            ET.SubElement(item, "link").text = link
            ET.SubElement(item, "description").text = clean_text

        # Save XML
        xml_path = os.path.join(
            XML_FOLDER,
            f"{name}.xml"
        )

        ET.ElementTree(rss_root).write(
            xml_path,
            encoding="utf-8",
            xml_declaration=True
        )

        # Archive copy
        archive_feed(xml_path)

        print(f"[Feed Updated] {name}")

    except Exception as e:
        print(f"[Error fetching {name}] {e}")

def telegram_updater():
    while True:
        for name, url in TELEGRAM_CHANNELS.items():
            fetch_telegram_xml(name, url)

        time.sleep(600)

# ------------------ 🔊 AUDIO ------------------
def generate_audio_from_feed(channel_name):

    path = os.path.join(
        XML_FOLDER,
        f"{channel_name}.xml"
    )

    if not os.path.exists(path):
        fetch_telegram_xml(
            channel_name,
            TELEGRAM_CHANNELS[channel_name]
        )

    feed = feedparser.parse(path)

    entries = list(feed.entries)[-25:]

    full_text = "ഇന്നത്തെ പ്രധാന വാർത്തകൾ.\n\n"

    for e in entries:

        desc_text = e.get("description", "")

        desc_text = re.sub(
            r"[\U0001F300-\U0001FAFF]",
            " ",
            desc_text
        )

        desc_text = re.sub(
            r"[\U0001F600-\U0001F64F]",
            " ",
            desc_text
        )

        desc_text = re.sub(
            r"[\u2600-\u27BF]",
            " ",
            desc_text
        )

        desc_text = re.sub(
            r"[\uFE0F\u200D]",
            " ",
            desc_text
        )

        desc_text = re.sub(
            r"#\w+",
            "",
            desc_text
        )

        desc_text = re.sub(
            r"http\S+",
            "",
            desc_text
        )

        desc_text = re.sub(
            r"(join\s*@\w+.*)$",
            "",
            desc_text,
            flags=re.IGNORECASE
        )

        desc_text = re.sub(
            r"@\w+",
            "",
            desc_text
        )

        desc_text = re.sub(
            r"[!?:;]+",
            ". ",
            desc_text
        )

        desc_text = re.sub(
            r"[\"'(){}\[\]<>]",
            " ",
            desc_text
        )

        desc_text = re.sub(
            r"\s+",
            " ",
            desc_text
        ).strip()

        if not desc_text or len(desc_text) < 5:
            desc_text = e.get("title", "")

        if not desc_text:
            continue

        full_text += f"{desc_text}.\n\n"

    if len(full_text.strip()) < 10:
        full_text = "ഇന്ന് വാർത്തകൾ ലഭ്യമല്ല."

    try:
        tts = gTTS(full_text, lang='ml')

        output_path = os.path.join(
            AUDIO_FOLDER,
            f"{channel_name}.mp3"
        )

        tts.save(output_path)

        print(f"[Audio Updated] {channel_name}")

    except Exception as e:
        print(f"[TTS Error] {e}")

def audio_updater():
    while True:
        for name in TELEGRAM_CHANNELS:
            generate_audio_from_feed(name)

        time.sleep(600)

# ------------------ Feed Page ------------------
@app.route("/telegram/<channel_name>")
def telegram_html(channel_name):

    if channel_name not in TELEGRAM_CHANNELS:
        return "Invalid channel"

    path = os.path.join(
        XML_FOLDER,
        f"{channel_name}.xml"
    )

    if request.args.get("refresh") == "1":
        fetch_telegram_xml(
            channel_name,
            TELEGRAM_CHANNELS[channel_name]
        )

    if not os.path.exists(path):
        fetch_telegram_xml(
            channel_name,
            TELEGRAM_CHANNELS[channel_name]
        )

    feed = feedparser.parse(path)

    entries = list(feed.entries)[::-1]

    posts = ""

    for e in entries[:50]:
        posts += f"<p>{e.get('description','')}</p><hr>"

    return f"""
    <html>
    <head>
    <meta name='viewport'
          content='width=device-width,initial-scale=1.0'>

    <style>
    body {{
        font-family: system-ui;
        padding: 10px;
    }}

    .btn {{
        background: #00695c;
        color: #fff;
        padding: 8px 12px;
        border-radius: 6px;
        text-decoration: none;
    }}
    </style>
    </head>

    <body>

    <h2>{channel_name}</h2>

    <a class="btn" href="?refresh=1">
        🔄 Refresh
    </a>

    <br><br>

    {posts}

    </body>
    </html>
    """

# ------------------ Archive Page ------------------
@app.route("/archives")
def archives():

    months = sorted(
        os.listdir(ARCHIVE_FOLDER),
        reverse=True
    )

    html = """
    <html>
    <head>
    <meta name='viewport'
          content='width=device-width,initial-scale=1.0'>

    <style>

    body{
        font-family:system-ui;
        padding:10px;
        background:#f5f5f5;
    }

    h2{
        text-align:center;
    }

    .card{
        background:#fff;
        padding:12px;
        border-radius:10px;
        margin-bottom:15px;
        box-shadow:0 2px 5px rgba(0,0,0,0.1);
    }

    .file{
        display:block;
        padding:8px;
        margin-top:5px;
        background:#e3f2fd;
        border-radius:6px;
        text-decoration:none;
        color:#1565c0;
        font-weight:bold;
    }

    </style>
    </head>
    <body>

    <h2>📦 Feed Archives</h2>
    """

    if not months:
        html += "<p>No archives found.</p>"

    for month in months:

        month_path = os.path.join(
            ARCHIVE_FOLDER,
            month
        )

        if not os.path.isdir(month_path):
            continue

        html += f"<div class='card'><h3>{month}</h3>"

        files = os.listdir(month_path)

        for file in files:

            html += f"""
            <a class='file'
               href='/archive/{month}/{file}'>

               {file}

            </a>
            """

        html += "</div>"

    html += "</body></html>"

    return html

# ------------------ Archive Files ------------------
@app.route("/archive/<month>/<filename>")
def archive_file(month, filename):

    archive_path = os.path.join(
        ARCHIVE_FOLDER,
        month,
        filename
    )

    if not os.path.exists(archive_path):
        return "Archive not found"

    feed = feedparser.parse(archive_path)

    entries = list(feed.entries)[::-1]

    posts = ""

    for e in entries[:100]:

        title = e.get("title", "")

        desc = e.get("description", "")

        link = e.get("link", "#")

        posts += f"""
        <div class='post'>
            <h3>{title}</h3>

            <p>{desc}</p>

            <a class='open-btn'
               href='{link}'
               target='_blank'>

               Open Source

            </a>
        </div>
        """

    return f"""
    <html>

    <head>

    <meta name='viewport'
          content='width=device-width,
                   initial-scale=1.0'>

    <style>

    body{{
        font-family:system-ui;
        padding:10px;
        background:#f5f5f5;
    }}

    h2{{
        text-align:center;
        color:#d32f2f;
    }}

    .post{{
        background:#fff;
        padding:12px;
        border-radius:10px;
        margin-bottom:15px;
        box-shadow:0 2px 5px rgba(0,0,0,0.1);
    }}

    .post h3{{
        margin-top:0;
        color:#1565c0;
        font-size:18px;
    }}

    .post p{{
        line-height:1.5;
        color:#333;
    }}

    .open-btn{{
        display:inline-block;
        margin-top:10px;
        background:#00695c;
        color:#fff;
        padding:8px 12px;
        border-radius:6px;
        text-decoration:none;
        font-size:14px;
    }}

    </style>

    </head>

    <body>

    <h2>📦 Archive Feed</h2>

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

    <meta name="viewport"
          content="width=device-width,
                   initial-scale=1.0,
                   maximum-scale=1.0,
                   user-scalable=no">

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
        color: #d32f2f;
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

    .audio-btn {
        background: #e3f2fd;
        color: #1565c0;
        border-color: #bbdefb;
    }

    .feed-btn {
        background: #f1f8e9;
        color: #2e7d32;
        border-color: #c8e6c9;
    }

    .archive-btn {
        background: #fff3e0;
        color: #ef6c00;
        border-color: #ffcc80;
    }

    .btn:focus,
    .btn:active {
        background: #ffeb3b !important;
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

    <div class="section-header">
        🎧 AUDIO CONTENT
    </div>

    <a class="btn audio-btn"
       href="/static/audio/Pathravarthakal.mp3"
       accesskey="1">

       <span class="key-hint">1</span>
       Pathravarthakal
    </a>

    <a class="btn audio-btn"
       href="/static/audio/DailyCa.mp3"
       accesskey="2">

       <span class="key-hint">2</span>
       Daily CA
    </a>

    <div class="section-header">
        📰 NEWS FEEDS
    </div>

    <a class="btn feed-btn"
       href="/telegram/Pathravarthakal"
       accesskey="3">

       <span class="key-hint">3</span>
       Pathravarthakal Feed
    </a>

    <a class="btn feed-btn"
       href="/telegram/DailyCa"
       accesskey="4">

       <span class="key-hint">4</span>
       Daily CA Feed
    </a>

    <div class="section-header">
        📦 ARCHIVES
    </div>

    <a class="btn archive-btn"
       href="/archives"
       accesskey="5">

       <span class="key-hint">5</span>
       Feed Archives
    </a>

    <p style="font-size:10px;
              color:#888;
              margin-top:20px;">

       Use Up/Down keys to navigate

    </p>

    </body>
    </html>
    """


# ------------------ QUIZ APP ------------------

@app.route("/quiz")
def quiz_app():
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <title>CA Blockbuster Quiz</title>

    <!-- Firebase Web SDK: required for Google Sign-In -->
    <script src="https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js"></script>
    <script src="https://www.gstatic.com/firebasejs/10.14.1/firebase-auth-compat.js"></script>

    <style>
        * { box-sizing: border-box; }

        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont,
                         "Segoe UI", Roboto, sans-serif;
            background: #f5f7fb;
            margin: 0;
            color: #222;
        }

        .container {
            width: min(900px, 100%);
            margin: auto;
            padding: 16px 16px 40px;
        }

        .header {
            text-align: center;
            padding: 12px 0 10px;
        }

        .header h1 {
            margin: 0;
            color: #1565c0;
            font-size: 32px;
        }

        .header p {
            color: #666;
            margin: 8px 0 0;
        }

        h2 { margin-top: 20px; }

        .card {
            background: #fff;
            padding: 18px;
            margin: 12px 0;
            border-radius: 14px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, .09);
            border: 1px solid #e7eaf0;
        }

        .clickable {
            cursor: pointer;
            transition: transform .12s, background .12s;
        }

        .clickable:hover {
            background: #eef6ff;
            transform: translateY(-1px);
        }

        .title {
            font-size: 18px;
            font-weight: 700;
        }

        .subtitle {
            color: #666;
            margin-top: 6px;
            line-height: 1.4;
        }

        .meta {
            color: #555;
            font-size: 14px;
            margin-top: 8px;
        }

        .hidden { display: none !important; }

        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 16px;
        }

        button {
            border: none;
            background: #1565c0;
            color: white;
            padding: 11px 18px;
            border-radius: 9px;
            font-size: 15px;
            cursor: pointer;
        }

        button:hover { opacity: .92; }

        .back { background: #555; }

        .timer {
            font-weight: 700;
            color: #d32f2f;
            font-size: 17px;
        }

        .question-number {
            color: #666;
            margin-bottom: 8px;
        }

        .question {
            font-size: 20px;
            line-height: 1.55;
            font-weight: 600;
        }

        .option {
            background: #fff;
            border: 2px solid #d9dee7;
            padding: 14px;
            margin: 10px 0;
            border-radius: 10px;
            cursor: pointer;
            line-height: 1.45;
        }

        .option:hover { background: #f5f9ff; }

        .option.correct {
            background: #d8f3dc !important;
            border-color: #2e7d32;
        }

        .option.wrong {
            background: #ffd8d8 !important;
            border-color: #c62828;
        }

        .explanation { line-height: 1.5; }

        .actions {
            display: flex;
            justify-content: flex-end;
            margin-top: 15px;
        }

        .status {
            padding: 12px;
            border-radius: 9px;
            background: #fff3cd;
            color: #664d03;
            margin: 12px 0;
        }

        .error {
            background: #ffebee;
            color: #b71c1c;
        }

        .empty {
            color: #777;
            padding: 20px 0;
        }

        .score {
            font-size: 42px;
            font-weight: 800;
            color: #1565c0;
            text-align: center;
        }

        .center { text-align: center; }

        /* Google login */
        .account-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            background: #fff;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 10px 12px;
            margin-bottom: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,.06);
        }

        .user-info {
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
        }

        .user-photo,
        .leader-photo,
        .leader-avatar {
            width: 44px;
            height: 44px;
            border-radius: 50%;
            object-fit: cover;
            flex: 0 0 44px;
        }

        .leader-avatar {
            display: flex;
            align-items: center;
            justify-content: center;
            background: #e3f2fd;
            font-size: 22px;
        }

        .user-name {
            font-weight: 700;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .user-email {
            color: #777;
            font-size: 12px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .google-btn {
            background: #fff;
            color: #333;
            border: 1px solid #dadce0;
            font-weight: 600;
            white-space: nowrap;
            box-shadow: 0 1px 3px rgba(0,0,0,.08);
        }

        .login-status {
            text-align: center;
            font-size: 12px;
            min-height: 18px;
            margin: -4px 0 10px;
        }

        .google-btn,
        .logout-btn {
            position: relative;
            z-index: 5;
            pointer-events: auto;
        }

        .logout-btn {
            background: #f1f3f4;
            color: #444;
            font-size: 13px;
            padding: 8px 12px;
        }

        .leaderboard-button {
            width: 100%;
            margin-top: 18px;
            padding: 15px;
            border-radius: 14px;
            background: linear-gradient(135deg, #1565c0, #42a5f5);
            font-size: 17px;
            font-weight: 700;
            box-shadow: 0 4px 10px rgba(21,101,192,.22);
        }

        /* Attractive category grid */
        #categories {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
            margin-top: 14px;
        }

        .category-card {
            min-height: 128px;
            padding: 18px 12px;
            background: #fff;
            border: 1px solid #e5eaf2;
            border-radius: 18px;
            box-shadow: 0 4px 12px rgba(0,0,0,.07);
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            text-align: center;
            cursor: pointer;
            transition: transform .15s, box-shadow .15s, background .15s;
        }

        .category-card:hover {
            transform: translateY(-3px);
            background: #f8fbff;
            box-shadow: 0 7px 18px rgba(0,0,0,.10);
        }

        .category-icon {
            font-size: 34px;
            line-height: 1;
            margin-bottom: 10px;
        }

        .category-name {
            font-size: 16px;
            font-weight: 750;
            line-height: 1.25;
        }

        .category-tests {
            font-size: 12px;
            color: #777;
            margin-top: 6px;
        }

        /* Test cards */
        #testList {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
        }

        #testList .card { margin: 0; }

        /* Leaderboard */
        .leader-row {
            display: flex;
            align-items: center;
            gap: 12px;
            background: #fff;
            padding: 13px;
            margin: 10px 0;
            border-radius: 15px;
            border: 1px solid #e7eaf0;
            box-shadow: 0 3px 10px rgba(0,0,0,.06);
        }

        .rank {
            width: 34px;
            flex: 0 0 34px;
            text-align: center;
            font-size: 17px;
            font-weight: 800;
        }

        .leader-info {
            flex: 1;
            min-width: 0;
        }

        .leader-name {
            font-weight: 750;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .leader-badge {
            color: #777;
            font-size: 12px;
            margin-top: 3px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .leader-points {
            color: #1565c0;
            font-weight: 800;
            text-align: right;
            white-space: nowrap;
        }

        .leader-points small {
            display: block;
            color: #777;
            font-size: 10px;
            font-weight: 500;
        }

        @media (max-width: 600px) {
            .container { padding: 12px 12px 30px; }
            .header h1 { font-size: 26px; }
            .question { font-size: 18px; }

            #categories,
            #testList {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .account-bar {
                align-items: flex-start;
            }

            .google-btn,
            .logout-btn {
                padding: 9px 10px;
            }
        }

        @media (max-width: 380px) {
            #categories,
            #testList {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>

<body>

<div class="container">

    <!-- HOME / CATEGORIES -->
    <section id="home">

        <div id="accountBar" class="account-bar">
            <div class="user-info">
                <div class="leader-avatar">👤</div>
                <div>
                    <div class="user-name">Not signed in</div>
                    <div class="user-email">Sign in to your Google account</div>
                </div>
            </div>

            <button id="googleLoginButton"
                    type="button"
                    class="google-btn"
                    onclick="loginWithGoogle()">
                🔐 Google Login
            </button>
        </div>

        <div id="loginStatus" class="login-status">
            Initializing Google Login...
        </div>

        <div class="header">
            <h1>🎯 CA Blockbuster</h1>
            <p>Daily CA Revision</p>
        </div>

        <h2>Categories</h2>

        <div id="categories">
            <div class="status">Loading...</div>
        </div>

        <button class="leaderboard-button"
                onclick="showLeaderboard()">
            🏆 View Leaderboard
        </button>

    </section>


    <!-- TEST LIST -->
    <section id="tests" class="hidden">

        <div class="topbar">
            <button class="back" onclick="showHome()">← Back</button>
        </div>

        <h2 id="topicTitle"></h2>

        <div id="testList"></div>

    </section>


    <!-- QUIZ -->
    <section id="quiz" class="hidden">

        <div class="topbar">
            <button class="back" onclick="showTests()">← Tests</button>
            <span id="timer" class="timer">00:00</span>
        </div>

        <h2 id="testTitle"></h2>

        <div class="question-number" id="questionNumber"></div>

        <div class="card">
            <div id="questionText" class="question"></div>
        </div>

        <div id="options"></div>

        <div id="explanationCard" class="card hidden">
            <strong>Explanation</strong>
            <div id="explanation" class="explanation"></div>
        </div>

        <div class="actions">
            <button id="nextButton" onclick="nextQuestion()">
                Next →
            </button>
        </div>

    </section>


    <!-- RESULT -->
    <section id="result" class="hidden">

        <div class="header">
            <h1>🎉 Result</h1>
        </div>

        <div class="card center">
            <div id="scoreText" class="score"></div>
            <p id="resultDetails"></p>
        </div>

        <div class="center">
            <button onclick="showHome()">Back to Categories</button>
        </div>

    </section>

    <!-- LEADERBOARD -->
    <section id="leaderboard" class="hidden">

        <div class="topbar">
            <button class="back" onclick="showHome()">← Back</button>
        </div>

        <div class="header">
            <h1>🏆 Leaderboard</h1>
            <p>Top performers</p>
        </div>

        <div id="leaderboardList">
            <div class="status">Loading leaderboard...</div>
        </div>

    </section>

</div>


<script>
"use strict";

/*
    Browser
       ↓
    Firebase Authentication (Google)
       ↓
    Firebase ID token
       ↓
    Flask /quiz/api/...
       ↓
    Firebase Admin SDK
       ↓
    Firestore
*/

const firebaseConfig = __FIREBASE_WEB_CONFIG__;

let firebaseApp = null;
let firebaseAuth = null;
let currentUser = null;
let firebaseAuthReady = false;

function setLoginStatus(message, isError = false) {
    const el = document.getElementById("loginStatus");
    if (!el) return;
    el.textContent = message || "";
    el.style.color = isError ? "#b71c1c" : "#666";
}

try {
    console.log("[Google Login] Starting Firebase Web Authentication...");
    console.log("[Google Login] Firebase project:", firebaseConfig.projectId || "missing");
    console.log("[Google Login] Auth domain:", firebaseConfig.authDomain || "missing");

    if (!window.firebase) {
        throw new Error(
            "Firebase Web SDK did not load. Check internet access/CSP and the Firebase SDK script URLs."
        );
    }

    if (
        firebaseConfig.apiKey &&
        !firebaseConfig.apiKey.startsWith("YOUR_") &&
        firebaseConfig.projectId &&
        !firebaseConfig.projectId.startsWith("YOUR_")
    ) {
        firebaseApp = firebase.initializeApp(firebaseConfig);
        firebaseAuth = firebase.auth();
        firebaseAuthReady = true;

        console.log("[Google Login] Firebase initialized successfully.");
        setLoginStatus("Google sign-in is ready.");

        firebaseAuth.onAuthStateChanged(function(user) {
            currentUser = user || null;

            if (currentUser) {
                console.log("[Google Login] Signed in:", currentUser.email);
                setLoginStatus("Signed in with Google.");
            } else {
                console.log("[Google Login] No user signed in.");
                setLoginStatus("Sign in with Google to continue.");
            }

            updateAccountUI();
        });
    } else {
        console.error("[Google Login] Firebase Web configuration is missing.", firebaseConfig);
        setLoginStatus(
            "Google Login is not configured. Add the Firebase Web variables in Koyeb.",
            true
        );
    }
} catch (e) {
    console.error("[Google Login] Firebase initialization failed:", e);
    setLoginStatus(
        "Google Login initialization failed: " + e.message,
        true
    );
}

let allTests = [];
let currentTests = [];
let currentQuestions = [];

let selectedTopic = "";
let selectedTest = null;

let currentQuestion = 0;
let score = 0;
let answered = false;

let timerSeconds = 0;
let timerInterval = null;


/* ------------------ API ------------------ */

async function apiGet(url, requireLogin = false) {

    const headers = {
        "Accept": "application/json"
    };

    if (firebaseAuth && currentUser) {
        try {
            headers["Authorization"] =
                "Bearer " + await currentUser.getIdToken();
        } catch (e) {
            console.warn("Could not get Firebase ID token:", e);
        }
    } else if (requireLogin) {
        throw new Error("Please sign in with Google first.");
    }

    const response = await fetch(url, {
        method: "GET",
        headers: headers
    });

    let data;

    try {
        data = await response.json();
    } catch (e) {
        throw new Error(
            "Server returned an invalid response (" +
            response.status + ")"
        );
    }

    if (!response.ok) {
        throw new Error(
            data.error || ("Server error: " + response.status)
        );
    }

    return data;
}


/* ------------------ LOAD TESTS ------------------ */

async function loadData() {

    const categories =
        document.getElementById("categories");

    try {

        categories.innerHTML =
            '<div class="status">Loading from Firestore...</div>';

        allTests = await apiGet("/quiz/api/tests");

        if (!Array.isArray(allTests)) {
            throw new Error("Invalid test data received");
        }

        displayCategories();

    } catch (error) {

        console.error(error);

        categories.innerHTML = `
            <div class="status error">
                <strong>Unable to load quiz.</strong>
                <br><br>
                ${escapeHtml(error.message)}
                <br><br>
                Check the Firebase service-account setting in Koyeb.
            </div>
        `;
    }
}


/* ------------------ CATEGORIES ------------------ */

function displayCategories() {

    const container =
        document.getElementById("categories");

    container.innerHTML = "";

    const topicIds = [
        ...new Set(
            allTests
                .map(test => test.topicId)
                .filter(topicId => topicId)
        )
    ];

    if (topicIds.length === 0) {
        container.innerHTML =
            '<div class="empty">No categories found.</div>';
        return;
    }

    topicIds.sort((a, b) =>
        String(a).localeCompare(String(b))
    );

    topicIds.forEach(topicId => {

        const topicTests =
            allTests.filter(
                test => test.topicId === topicId
            );

        const card =
            document.createElement("div");

        card.className = "category-card";

        const icons = [
            "📚", "🌍", "📰", "🔬",
            "🏛️", "💡", "🇮🇳", "🎯"
        ];

        const icon =
            icons[topicIds.indexOf(topicId) % icons.length];

        card.innerHTML = `
            <div class="category-icon">${icon}</div>

            <div class="category-name">
                ${escapeHtml(topicId)}
            </div>

            <div class="category-tests">
                ${topicTests.length}
                ${topicTests.length === 1 ? "Test" : "Tests"}
            </div>
        `;

        card.onclick = () =>
            showTestsForTopic(topicId);

        container.appendChild(card);
    });
}


/* ------------------ TEST LIST ------------------ */

function showTestsForTopic(topicId) {

    selectedTopic = topicId;

    currentTests =
        allTests.filter(
            test => test.topicId === topicId
        );

    document.getElementById("home")
        .classList.add("hidden");

    document.getElementById("tests")
        .classList.remove("hidden");

    document.getElementById("quiz")
        .classList.add("hidden");

    document.getElementById("result")
        .classList.add("hidden");

    document.getElementById("topicTitle")
        .textContent = topicId;

    const container =
        document.getElementById("testList");

    container.innerHTML = "";

    if (currentTests.length === 0) {
        container.innerHTML =
            '<div class="empty">No tests found.</div>';
        return;
    }

    currentTests.forEach(test => {

        const card =
            document.createElement("div");

        card.className = "card clickable";

        card.innerHTML = `
            <div class="title">
                ${escapeHtml(test.title || test.id)}
            </div>

            ${
                test.subtitle
                    ? `<div class="subtitle">
                           ${escapeHtml(test.subtitle)}
                       </div>`
                    : ""
            }

            <div class="meta">
                ${escapeHtml(
                    String(test.questionCount || 0)
                )} Questions
                •
                ${escapeHtml(
                    String(test.durationMinutes || 0)
                )} min
                •
                ${escapeHtml(
                    String(test.difficulty || "")
                )}
            </div>
        `;

        card.onclick = () =>
            startQuiz(test);

        container.appendChild(card);
    });
}


/* ------------------ START QUIZ ------------------ */

async function startQuiz(test) {

    selectedTest = test;

    try {

        document.getElementById("tests")
            .classList.add("hidden");

        document.getElementById("quiz")
            .classList.remove("hidden");

        document.getElementById("result")
            .classList.add("hidden");

        document.getElementById("testTitle")
            .textContent = test.title || test.id;

        document.getElementById("questionText")
            .textContent = "Loading questions...";

        document.getElementById("options")
            .innerHTML = "";

        currentQuestions =
            await apiGet(
                "/quiz/api/questions/" +
                encodeURIComponent(test.id)
            );

        if (!Array.isArray(currentQuestions) ||
            currentQuestions.length === 0) {

            throw new Error(
                "No questions found for this test."
            );
        }

        currentQuestion = 0;
        score = 0;
        answered = false;

        startTimer(
            Number(test.durationMinutes) || 0
        );

        displayQuestion();

    } catch (error) {

        console.error(error);

        document.getElementById("questionText")
            .textContent = "";

        document.getElementById("options")
            .innerHTML = `
                <div class="status error">
                    ${escapeHtml(error.message)}
                </div>
            `;
    }
}


/* ------------------ QUESTION ------------------ */

function displayQuestion() {

    const q =
        currentQuestions[currentQuestion];

    if (!q) {
        finishQuiz();
        return;
    }

    answered = false;

    document.getElementById("questionNumber")
        .textContent =
        "Question " +
        (currentQuestion + 1) +
        " / " +
        currentQuestions.length;

    document.getElementById("questionText")
        .textContent =
        q.questionText || "";

    document.getElementById("explanationCard")
        .classList.add("hidden");

    document.getElementById("explanation")
        .textContent = "";

    document.getElementById("nextButton")
        .textContent =
        currentQuestion === currentQuestions.length - 1
            ? "Finish ✓"
            : "Next →";

    const options =
        document.getElementById("options");

    options.innerHTML = "";

    const optionValues = [
        q.option0 || "",
        q.option1 || "",
        q.option2 || "",
        q.option3 || ""
    ];

    optionValues.forEach((option, index) => {

        const div =
            document.createElement("div");

        div.className = "option";

        div.textContent = option;

        div.onclick = () =>
            selectAnswer(index, div);

        options.appendChild(div);
    });
}


/* ------------------ ANSWER ------------------ */

function selectAnswer(index, element) {

    if (answered)
        return;

    answered = true;

    const q =
        currentQuestions[currentQuestion];

    const correctIndex =
        Number(q.correctOptionIndex);

    const optionElements =
        document.querySelectorAll(".option");

    if (index === correctIndex) {

        element.classList.add("correct");
        score++;

    } else {

        element.classList.add("wrong");

        if (optionElements[correctIndex]) {
            optionElements[correctIndex]
                .classList.add("correct");
        }
    }

    if (q.explanation) {

        document.getElementById("explanation")
            .textContent = q.explanation;

        document.getElementById("explanationCard")
            .classList.remove("hidden");
    }
}


/* ------------------ NEXT ------------------ */

window.nextQuestion = function() {

    if (!answered)
        return;

    if (
        currentQuestion >=
        currentQuestions.length - 1
    ) {

        finishQuiz();
        return;
    }

    currentQuestion++;

    displayQuestion();
};


/* ------------------ TIMER ------------------ */

function startTimer(durationMinutes) {

    clearInterval(timerInterval);

    /*
       Use the test duration when available.
       If duration is 0, count elapsed time instead.
    */

    const hasLimit =
        Number(durationMinutes) > 0;

    const totalSeconds =
        Number(durationMinutes) * 60;

    timerSeconds = hasLimit
        ? totalSeconds
        : 0;

    updateTimerDisplay(hasLimit);

    timerInterval =
        setInterval(() => {

            if (hasLimit) {

                timerSeconds--;

                updateTimerDisplay(true);

                if (timerSeconds <= 0) {
                    clearInterval(timerInterval);
                    finishQuiz();
                }

            } else {

                timerSeconds++;

                updateTimerDisplay(false);
            }

        }, 1000);
}


function updateTimerDisplay(hasLimit) {

    const minutes =
        Math.floor(timerSeconds / 60);

    const seconds =
        timerSeconds % 60;

    const display =
        String(minutes).padStart(2, "0") +
        ":" +
        String(seconds).padStart(2, "0");

    document.getElementById("timer")
        .textContent =
        hasLimit ? "⏱ " + display : "⏱ " + display;
}


/* ------------------ RESULT ------------------ */

function finishQuiz() {

    clearInterval(timerInterval);

    document.getElementById("quiz")
        .classList.add("hidden");

    document.getElementById("result")
        .classList.remove("hidden");

    const total =
        currentQuestions.length;

    document.getElementById("scoreText")
        .textContent =
        score + " / " + total;

    const percentage =
        total > 0
            ? Math.round((score / total) * 100)
            : 0;

    document.getElementById("resultDetails")
        .textContent =
        percentage + "% correct";
}


/* ------------------ NAVIGATION ------------------ */

window.showHome = function() {

    clearInterval(timerInterval);

    document.getElementById("home")
        .classList.remove("hidden");

    document.getElementById("tests")
        .classList.add("hidden");

    document.getElementById("quiz")
        .classList.add("hidden");

    document.getElementById("result")
        .classList.add("hidden");

    document.getElementById("leaderboard")
        .classList.add("hidden");
};


window.showTests = function() {

    clearInterval(timerInterval);

    document.getElementById("quiz")
        .classList.add("hidden");

    document.getElementById("result")
        .classList.add("hidden");

    document.getElementById("leaderboard")
        .classList.add("hidden");

    document.getElementById("tests")
        .classList.remove("hidden");
};


/* ------------------ GOOGLE LOGIN ------------------ */

window.loginWithGoogle = async function() {

    console.log("[Google Login] Button clicked.");

    const button = document.getElementById("googleLoginButton");

    if (!firebaseAuthReady || !firebaseAuth) {
        const message =
            "Google Login is not ready.\n\n" +
            "Open browser Developer Console (F12) for the exact error.\n" +
            "Also check the Firebase Web variables in Koyeb.";

        console.error("[Google Login]", message);
        setLoginStatus(message.replace(/\n/g, " "), true);
        alert(message);
        return;
    }

    try {
        if (button) {
            button.disabled = true;
            button.textContent = "Connecting...";
        }

        setLoginStatus("Opening Google sign-in...");

        const provider =
            new firebase.auth.GoogleAuthProvider();

        provider.setCustomParameters({
            prompt: "select_account"
        });

        console.log("[Google Login] Calling signInWithPopup...");

        await firebaseAuth.signInWithPopup(provider);

        console.log("[Google Login] Popup sign-in completed.");

    } catch (error) {

        console.error("[Google Login] Sign-in error:", error);
        console.error("[Google Login] Error code:", error.code);
        console.error("[Google Login] Error message:", error.message);

        if (error.code === "auth/popup-blocked" ||
            error.code === "auth/cancelled-popup-request") {

            try {
                console.log("[Google Login] Popup blocked. Switching to redirect...");
                setLoginStatus("Redirecting to Google sign-in...");
                await firebaseAuth.signInWithRedirect(provider);
                return;
            } catch (redirectError) {
                console.error("[Google Login] Redirect sign-in error:", redirectError);
                setLoginStatus(
                    "Google Login failed: " + redirectError.message,
                    true
                );
            }
        } else {
            setLoginStatus(
                "Google Login failed: " +
                (error.message || "Unknown error"),
                true
            );
            alert(
                "Google Login failed\n\n" +
                "Code: " + (error.code || "unknown") + "\n\n" +
                (error.message || "Unknown error")
            );
        }
    } finally {
        if (button && !currentUser) {
            button.disabled = false;
            button.textContent = "🔐 Google Login";
        }
    }
};


window.logoutGoogle = async function() {

    if (!firebaseAuth)
        return;

    try {
        await firebaseAuth.signOut();
    } catch (error) {
        console.error("Logout error:", error);
    }
};


function updateAccountUI() {

    const bar =
        document.getElementById("accountBar");

    if (!bar)
        return;

    const info =
        bar.querySelector(".user-info");

    const button =
        document.getElementById("googleLoginButton");

    if (currentUser) {

        const photo =
            currentUser.photoURL
                ? `<img class="user-photo"
                        src="${escapeHtml(currentUser.photoURL)}"
                        alt="">`
                : `<div class="leader-avatar">👤</div>`;

        info.innerHTML = `
            ${photo}

            <div>
                <div class="user-name">
                    ${escapeHtml(
                        currentUser.displayName || "Google User"
                    )}
                </div>

                <div class="user-email">
                    ${escapeHtml(currentUser.email || "")}
                </div>
            </div>
        `;

        button.type = "button";
        button.textContent = "Logout";
        button.className = "logout-btn";
        button.onclick = window.logoutGoogle;

    } else {

        info.innerHTML = `
            <div class="leader-avatar">👤</div>

            <div>
                <div class="user-name">
                    Not signed in
                </div>

                <div class="user-email">
                    Sign in to your Google account
                </div>
            </div>
        `;

        button.type = "button";
        button.textContent = "🔐 Google Login";
        button.className = "google-btn";
        button.onclick = window.loginWithGoogle;
    }
}


/* ------------------ LEADERBOARD ------------------ */

window.showLeaderboard = async function() {

    clearInterval(timerInterval);

    document.getElementById("home")
        .classList.add("hidden");

    document.getElementById("tests")
        .classList.add("hidden");

    document.getElementById("quiz")
        .classList.add("hidden");

    document.getElementById("result")
        .classList.add("hidden");

    document.getElementById("leaderboard")
        .classList.remove("hidden");

    const container =
        document.getElementById("leaderboardList");

    container.innerHTML =
        '<div class="status">Loading leaderboard...</div>';

    try {

        const users =
            await apiGet("/quiz/api/leaderboard");

        if (!Array.isArray(users) || users.length === 0) {
            container.innerHTML =
                '<div class="empty">No leaderboard data found.</div>';
            return;
        }

        container.innerHTML = "";

        users.forEach(function(user, index) {

            const row =
                document.createElement("div");

            row.className = "leader-row";

            const medal =
                index === 0 ? "🥇" :
                index === 1 ? "🥈" :
                index === 2 ? "🥉" :
                String(index + 1);

            const photo =
                user.profilePhotoUri
                    ? `<img class="leader-photo"
                            src="${escapeHtml(user.profilePhotoUri)}"
                            alt="">`
                    : `<div class="leader-avatar">
                            ${escapeHtml(
                                user.avatarEmoji || "👤"
                            )}
                       </div>`;

            row.innerHTML = `
                <div class="rank">${medal}</div>

                ${photo}

                <div class="leader-info">
                    <div class="leader-name">
                        ${escapeHtml(user.name || "User")}
                    </div>

                    <div class="leader-badge">
                        ${escapeHtml(
                            user.badgeTitle || ""
                        )}
                    </div>
                </div>

                <div class="leader-points">
                    ${Number(user.points || 0)}
                    <small>points</small>
                </div>
            `;

            container.appendChild(row);
        });

    } catch (error) {

        console.error(error);

        container.innerHTML = `
            <div class="status error">
                <strong>Unable to load leaderboard.</strong>
                <br><br>
                ${escapeHtml(error.message)}
            </div>
        `;
    }
};


/* ------------------ HTML SAFETY ------------------ */

function escapeHtml(value) {

    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


/* ------------------ START ------------------ */

loadData();

</script>

</body>
</html>
"""

    return html.replace(
        "__FIREBASE_WEB_CONFIG__",
        json.dumps(FIREBASE_WEB_CONFIG)
    )



# ------------------ QUIZ FIRESTORE API ------------------

@app.route("/quiz/api/tests")
def quiz_tests():
    try:
        db = get_firestore()

        docs = db.collection("custom_tests").stream()

        tests = []

        for doc in docs:
            data = doc.to_dict()

            tests.append({
                "id": data.get("id") or doc.id,
                "topicId": data.get("topicId") or "",
                "title": data.get("title") or "",
                "subtitle": data.get("subtitle") or "",
                "durationMinutes":
                    data.get("durationMinutes") or 0,
                "difficulty":
                    data.get("difficulty") or "",
                "dateMillis":
                    data.get("dateMillis"),
                "questionCount": 0
            })

        # Count questions for each test.
        # This keeps the category/test UI useful without
        # requiring the browser to access Firestore.
        question_counts = {}

        question_docs = (
            db.collection("custom_questions")
            .stream()
        )

        for qdoc in question_docs:
            qdata = qdoc.to_dict()
            test_id = qdata.get("testId")

            if test_id:
                question_counts[test_id] = (
                    question_counts.get(test_id, 0) + 1
                )

        for test in tests:
            test["questionCount"] = question_counts.get(
                test["id"], 0
            )

        return tests

    except Exception as e:
        print(f"[Quiz Firestore tests error] {e}")

        return {
            "error": str(e)
        }, 500


@app.route("/quiz/api/questions/<path:test_id>")
def quiz_questions(test_id):
    try:
        db = get_firestore()

        docs = (
            db.collection("custom_questions")
            .where("testId", "==", test_id)
            .stream()
        )

        questions = []

        for doc in docs:
            data = doc.to_dict()

            questions.append({
                "id": data.get("id") or doc.id,
                "testId": data.get("testId") or "",
                "topicId": data.get("topicId") or "",
                "questionText":
                    data.get("questionText") or "",
                "option0":
                    data.get("option0") or "",
                "option1":
                    data.get("option1") or "",
                "option2":
                    data.get("option2") or "",
                "option3":
                    data.get("option3") or "",
                "correctOptionIndex":
                    data.get("correctOptionIndex", 0),
                "explanation":
                    data.get("explanation") or "",
                "hint":
                    data.get("hint") or ""
            })

        return questions

    except Exception as e:
        print(f"[Quiz Firestore questions error] {e}")

        return {
            "error": str(e)
        }, 500



# ------------------ QUIZ LEADERBOARD API ------------------

@app.route("/quiz/api/leaderboard")
def quiz_leaderboard():
    try:
        db = get_firestore()

        docs = db.collection("leaderboard").stream()

        entries = []

        for doc in docs:
            data = doc.to_dict()

            try:
                points = int(data.get("points", 0) or 0)
            except (TypeError, ValueError):
                points = 0

            entries.append({
                "name": data.get("name") or "User",
                "points": points,
                "accuracy": data.get("accuracy", 0),
                "stars": data.get("stars", 0),
                "badgeTitle": data.get("badgeTitle") or "",
                "avatarEmoji": data.get("avatarEmoji") or "👤",
                "profilePhotoUri": data.get("profilePhotoUri") or ""
            })

        entries.sort(
            key=lambda item: item["points"],
            reverse=True
        )

        return entries[:50]

    except Exception as e:
        print(f"[Quiz Firestore leaderboard error] {e}")

        return {
            "error": str(e)
        }, 500


# ------------------ Run ------------------
if __name__ == "__main__":

    print("[Startup] CA Blockbuster server starting...")
    print("[Startup] Firebase Web project:", FIREBASE_WEB_CONFIG.get("projectId"))
    print("[Startup] Firebase Web authDomain:", FIREBASE_WEB_CONFIG.get("authDomain"))
    print("[Startup] Firebase Web API key configured:", bool(
        FIREBASE_WEB_CONFIG.get("apiKey") and
        not str(FIREBASE_WEB_CONFIG.get("apiKey")).startswith("YOUR_")
    ))
    print("[Startup] Firebase Web appId configured:", bool(
        FIREBASE_WEB_CONFIG.get("appId") and
        not str(FIREBASE_WEB_CONFIG.get("appId")).startswith("YOUR_")
    ))

    threading.Thread(
        target=telegram_updater,
        daemon=True
    ).start()

    threading.Thread(
        target=audio_updater,
        daemon=True
    ).start()

    app.run(
        host="0.0.0.0",
        port=8000
    )
