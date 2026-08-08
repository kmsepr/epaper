import os
import time
import feedparser
import threading
import requests
import re
import shutil
from datetime import datetime
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import json
from gtts import gTTS

import firebase_admin
from firebase_admin import credentials, firestore, auth

app = Flask(__name__)

# ============================================================
# FIRESTORE
# ============================================================

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
        firebase_admin.initialize_app(
            credentials.Certificate(service_account_info)
        )

    _firestore_db = firestore.client()

    return _firestore_db


# ============================================================
# FIREBASE WEB AUTH CONFIG
# ============================================================

FIREBASE_PROJECT_ID = os.environ.get(
    "FIREBASE_PROJECT_ID",
    "YOUR_PROJECT_ID"
)

FIREBASE_WEB_CONFIG = {
    "apiKey": os.environ.get(
        "FIREBASE_WEB_API_KEY",
        "YOUR_FIREBASE_WEB_API_KEY"
    ),

    "authDomain": os.environ.get(
        "FIREBASE_WEB_AUTH_DOMAIN",
        f"{FIREBASE_PROJECT_ID}.firebaseapp.com"
    ),

    "projectId": FIREBASE_PROJECT_ID,

    "storageBucket": os.environ.get(
        "FIREBASE_STORAGE_BUCKET",
        f"{FIREBASE_PROJECT_ID}.firebasestorage.app"
    ),

    "messagingSenderId": os.environ.get(
        "FIREBASE_MESSAGING_SENDER_ID",
        "YOUR_MESSAGING_SENDER_ID"
    ),

    "appId": os.environ.get(
        "FIREBASE_WEB_APP_ID",
        "YOUR_FIREBASE_WEB_APP_ID"
    )
}


# ============================================================
# CONFIG
# ============================================================

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


# ============================================================
# FIREBASE AUTH HELPERS
# ============================================================

def get_authenticated_user():
    """
    Verify Firebase ID token sent from the browser.

    Browser sends:

        Authorization: Bearer FIREBASE_ID_TOKEN

    Returns decoded Firebase token or None.
    """

    header = request.headers.get("Authorization", "")

    if not header.startswith("Bearer "):
        return None

    token = header.split("Bearer ", 1)[1].strip()

    if not token:
        return None

    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        print("[Firebase Auth] Token verification failed:", e)
        return None


def require_authenticated_user():
    """
    Used by APIs that require Google/Firebase login.
    """

    user = get_authenticated_user()

    if not user:
        return None, (
            jsonify({
                "error": "Authentication required",
                "message": "Please sign in with Google first."
            }),
            401
        )

    return user, None


# ============================================================
# STAR CALCULATION
# ============================================================

def calculate_stars(correct, total):
    """
    Star calculation.

    Current thresholds:
        80% or more = 3 stars
        60% or more = 2 stars
        40% or more = 1 star
        below 40%   = 0 stars

    Keep this function isolated so the Android rules can be
    changed here without changing the leaderboard system.
    """

    try:
        correct = int(correct)
        total = int(total)
    except (TypeError, ValueError):
        return 0

    if total <= 0:
        return 0

    percentage = (correct / total) * 100

    if percentage >= 80:
        return 3

    if percentage >= 60:
        return 2

    if percentage >= 40:
        return 1

    return 0


def calculate_points(correct, stars):
    """
    Required formula:

        420 + correct × 10 + stars × 40
    """

    return 420 + (int(correct) * 10) + (int(stars) * 40)


# ============================================================
# FEED ARCHIVE
# ============================================================

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

        archive_path = os.path.join(
            archive_dir,
            os.path.basename(xml_path)
        )

        shutil.copy2(
            xml_path,
            archive_path
        )

        print(f"[Feed Archived] {archive_path}")

    except Exception as e:
        print(f"[Archive Error] {e}")


# ============================================================
# TELEGRAM FETCH
# ============================================================

def fetch_telegram_xml(name, url):

    try:

        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=10
        )

        soup = BeautifulSoup(
            r.text,
            "html.parser"
        )

        rss_root = ET.Element(
            "rss",
            version="2.0"
        )

        ch = ET.SubElement(
            rss_root,
            "channel"
        )

        ET.SubElement(
            ch,
            "title"
        ).text = f"{name} Telegram Feed"

        for msg in soup.select(
            ".tgme_widget_message_wrap"
        )[:80]:

            date_tag = msg.select_one(
                "a.tgme_widget_message_date"
            )

            link = (
                date_tag["href"]
                if date_tag and "href" in date_tag.attrs
                else url
            )

            text_tag = msg.select_one(
                ".tgme_widget_message_text"
            )

            desc_html = (
                text_tag.decode_contents()
                if text_tag
                else ""
            )

            clean_text = BeautifulSoup(
                desc_html,
                "html.parser"
            ).get_text(
                " ",
                strip=True
            )

            item = ET.SubElement(
                ch,
                "item"
            )

            ET.SubElement(
                item,
                "title"
            ).text = clean_text[:100]

            ET.SubElement(
                item,
                "link"
            ).text = link

            ET.SubElement(
                item,
                "description"
            ).text = clean_text

        xml_path = os.path.join(
            XML_FOLDER,
            f"{name}.xml"
        )

        ET.ElementTree(
            rss_root
        ).write(
            xml_path,
            encoding="utf-8",
            xml_declaration=True
        )

        archive_feed(xml_path)

        print(f"[Feed Updated] {name}")

    except Exception as e:
        print(
            f"[Error fetching {name}] {e}"
        )


def telegram_updater():

    while True:

        for name, url in TELEGRAM_CHANNELS.items():

            fetch_telegram_xml(
                name,
                url
            )

        time.sleep(600)


# ============================================================
# AUDIO
# ============================================================

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

    full_text = (
        "ഇന്നത്തെ പ്രധാന വാർത്തകൾ.\n\n"
    )

    for e in entries:

        desc_text = e.get(
            "description",
            ""
        )

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
            desc_text = e.get(
                "title",
                ""
            )

        if desc_text:

            full_text += (
                f"{desc_text}.\n\n"
            )

    if len(full_text.strip()) < 10:

        full_text = (
            "ഇന്ന് വാർത്തകൾ ലഭ്യമല്ല."
        )

    try:

        output_path = os.path.join(
            AUDIO_FOLDER,
            f"{channel_name}.mp3"
        )

        gTTS(
            full_text,
            lang="ml"
        ).save(output_path)

        print(
            f"[Audio Updated] {channel_name}"
        )

    except Exception as e:

        print(
            f"[TTS Error] {e}"
        )


def audio_updater():

    while True:

        for name in TELEGRAM_CHANNELS:

            generate_audio_from_feed(
                name
            )

        time.sleep(600)


# ============================================================
# TELEGRAM PAGE
# ============================================================

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

    posts = "".join(
        f"<p>{e.get('description','')}</p><hr>"
        for e in list(feed.entries)[::-1][:50]
    )

    return f"""
    <html>
    <head>
    <meta name='viewport'
          content='width=device-width,initial-scale=1.0'>

    <style>
    body{{font-family:system-ui;padding:10px}}
    .btn{{background:#00695c;color:#fff;
    padding:8px 12px;border-radius:6px;
    text-decoration:none}}
    </style>

    </head>

    <body>

    <h2>{channel_name}</h2>

    <a class='btn'
       href='?refresh=1'>
       🔄 Refresh
    </a>

    <br><br>

    {posts}

    </body>
    </html>
    """


# ============================================================
# ARCHIVES
# ============================================================

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
        background:#f5f5f5
    }

    h2{text-align:center}

    .card{
        background:#fff;
        padding:12px;
        border-radius:10px;
        margin-bottom:15px;
        box-shadow:0 2px 5px rgba(0,0,0,.1)
    }

    .file{
        display:block;
        padding:8px;
        margin-top:5px;
        background:#e3f2fd;
        border-radius:6px;
        text-decoration:none;
        color:#1565c0;
        font-weight:bold
    }
    </style>

    </head>

    <body>

    <h2>📦 Feed Archives</h2>
    """

    if not months:

        html += (
            "<p>No archives found.</p>"
        )

    for month in months:

        month_path = os.path.join(
            ARCHIVE_FOLDER,
            month
        )

        if not os.path.isdir(month_path):
            continue

        html += (
            f"<div class='card'>"
            f"<h3>{month}</h3>"
        )

        for file in os.listdir(
            month_path
        ):

            html += (
                f"<a class='file' "
                f"href='/archive/{month}/{file}'>"
                f"{file}</a>"
            )

        html += "</div>"

    return (
        html +
        "</body></html>"
    )


# ============================================================
# ARCHIVE FILE
# ============================================================

@app.route("/archive/<month>/<filename>")
def archive_file(month, filename):

    archive_path = os.path.join(
        ARCHIVE_FOLDER,
        month,
        filename
    )

    if not os.path.exists(archive_path):
        return "Archive not found"

    feed = feedparser.parse(
        archive_path
    )

    posts = ""

    for e in list(feed.entries)[::-1][:100]:

        posts += f"""
        <div class='post'>

        <h3>
        {e.get('title','')}
        </h3>

        <p>
        {e.get('description','')}
        </p>

        <a class='open-btn'
           href='{e.get('link','#')}'
           target='_blank'>
           Open Source
        </a>

        </div>
        """

    return f"""
    <html>

    <head>

    <meta name='viewport'
          content='width=device-width,initial-scale=1.0'>

    <style>

    body{{
        font-family:system-ui;
        padding:10px;
        background:#f5f5f5
    }}

    h2{{
        text-align:center;
        color:#d32f2f
    }}

    .post{{
        background:#fff;
        padding:12px;
        border-radius:10px;
        margin-bottom:15px;
        box-shadow:0 2px 5px rgba(0,0,0,.1)
    }}

    .post h3{{
        margin-top:0;
        color:#1565c0;
        font-size:18px
    }}

    .post p{{
        line-height:1.5;
        color:#333
    }}

    .open-btn{{
        display:inline-block;
        margin-top:10px;
        background:#00695c;
        color:#fff;
        padding:8px 12px;
        border-radius:6px;
        text-decoration:none;
        font-size:14px
    }}

    </style>

    </head>

    <body>

    <h2>📦 Archive Feed</h2>

    {posts}

    </body>
    </html>
    """


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return """
    <!DOCTYPE html>

    <html>

    <head>

    <meta name='viewport'
    content='width=device-width,initial-scale=1.0,
    maximum-scale=1.0,user-scalable=no'>

    <style>

    body{
        font-family:'Segoe UI',Roboto,sans-serif;
        background:#f0f2f5;
        margin:0;
        padding:10px;
        text-align:center;
        color:#333
    }

    h1{
        font-size:22px;
        color:#d32f2f;
        margin:10px 0;
        border-bottom:2px solid #d32f2f;
        padding-bottom:5px
    }

    .section-header{
        display:flex;
        align-items:center;
        justify-content:center;
        margin-top:15px;
        font-weight:bold;
        font-size:14px;
        text-transform:uppercase;
        color:#555
    }

    .btn{
        display:block;
        width:90%;
        margin:10px auto;
        padding:15px 5px;
        font-size:18px;
        font-weight:bold;
        text-decoration:none;
        border-radius:10px;
        border:2px solid transparent;
        box-shadow:0 4px 6px rgba(0,0,0,.1)
    }

    .audio-btn{
        background:#e3f2fd;
        color:#1565c0;
        border-color:#bbdefb
    }

    .feed-btn{
        background:#f1f8e9;
        color:#2e7d32;
        border-color:#c8e6c9
    }

    .archive-btn{
        background:#fff3e0;
        color:#ef6c00;
        border-color:#ffcc80
    }

    .key-hint{
        font-size:12px;
        background:rgba(0,0,0,.1);
        padding:2px 6px;
        border-radius:4px;
        margin-right:8px
    }

    </style>

    </head>

    <body>

    <h1>📰 വാർത്തകൾ</h1>

    <div class='section-header'>
    🎧 AUDIO CONTENT
    </div>

    <a class='btn audio-btn'
       href='/static/audio/Pathravarthakal.mp3'
       accesskey='1'>
       <span class='key-hint'>1</span>
       Pathravarthakal
    </a>

    <a class='btn audio-btn'
       href='/static/audio/DailyCa.mp3'
       accesskey='2'>
       <span class='key-hint'>2</span>
       Daily CA
    </a>

    <div class='section-header'>
    📰 NEWS FEEDS
    </div>

    <a class='btn feed-btn'
       href='/telegram/Pathravarthakal'
       accesskey='3'>
       <span class='key-hint'>3</span>
       Pathravarthakal Feed
    </a>

    <a class='btn feed-btn'
       href='/telegram/DailyCa'
       accesskey='4'>
       <span class='key-hint'>4</span>
       Daily CA Feed
    </a>

    <div class='section-header'>
    📦 ARCHIVES
    </div>

    <a class='btn archive-btn'
       href='/archives'
       accesskey='5'>
       <span class='key-hint'>5</span>
       Feed Archives
    </a>

    <p style='font-size:10px;color:#888;margin-top:20px'>
    Use Up/Down keys to navigate
    </p>

    </body>
    </html>
    """


# ============================================================
# QUIZ APP
# ============================================================

@app.route("/quiz")
def quiz_app():

    html = r'''<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
content="width=device-width, initial-scale=1.0">

<title>CA Blockbuster Quiz</title>

<script src="https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js"></script>

<script src="https://www.gstatic.com/firebasejs/10.14.1/firebase-auth-compat.js"></script>

<style>

*{box-sizing:border-box}

body{
font-family:system-ui,-apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,sans-serif;
background:#f5f7fb;
margin:0;
color:#222
}

.container{
width:min(900px,100%);
margin:auto;
padding:16px 16px 40px
}

.header{
text-align:center;
padding:12px 0 10px
}

.header h1{
margin:0;
color:#1565c0;
font-size:32px
}

.header p{
color:#666;
margin:8px 0 0
}

h2{margin-top:20px}

.card{
background:#fff;
padding:18px;
margin:12px 0;
border-radius:14px;
box-shadow:0 2px 8px rgba(0,0,0,.09);
border:1px solid #e7eaf0
}

.hidden{display:none!important}

.topbar{
display:flex;
align-items:center;
justify-content:space-between;
gap:10px;
margin-bottom:16px
}

button{
border:none;
background:#1565c0;
color:#fff;
padding:11px 18px;
border-radius:9px;
font-size:15px;
cursor:pointer
}

button:disabled{
opacity:.65;
cursor:not-allowed
}

.back{background:#555}

.timer{
font-weight:700;
color:#d32f2f;
font-size:17px
}

.question-number{
color:#666;
margin-bottom:8px
}

.question{
font-size:20px;
line-height:1.55;
font-weight:600
}

.option{
background:#fff;
border:2px solid #d9dee7;
padding:14px;
margin:10px 0;
border-radius:10px;
cursor:pointer;
line-height:1.45
}

.option.correct{
background:#d8f3dc!important;
border-color:#2e7d32
}

.option.wrong{
background:#ffd8d8!important;
border-color:#c62828
}

.explanation{
line-height:1.5
}

.actions{
display:flex;
justify-content:flex-end;
margin-top:15px
}

.status{
padding:12px;
border-radius:9px;
background:#fff3cd;
color:#664d03;
margin:12px 0
}

.error{
background:#ffebee;
color:#b71c1c
}

.empty{
color:#777;
padding:20px 0
}

.score{
font-size:42px;
font-weight:800;
color:#1565c0;
text-align:center
}

.center{text-align:center}

.account-bar{
display:flex;
align-items:center;
justify-content:space-between;
gap:10px;
background:#fff;
border:1px solid #e5e7eb;
border-radius:16px;
padding:10px 12px;
margin-bottom:12px;
box-shadow:0 2px 8px rgba(0,0,0,.06)
}

.user-info{
display:flex;
align-items:center;
gap:10px;
min-width:0
}

.user-photo,
.leader-photo,
.leader-avatar{
width:44px;
height:44px;
border-radius:50%;
object-fit:cover;
flex:0 0 44px
}

.leader-avatar{
display:flex;
align-items:center;
justify-content:center;
background:#e3f2fd;
font-size:22px
}

.user-name{
font-weight:700;
overflow:hidden;
text-overflow:ellipsis;
white-space:nowrap
}

.user-email{
color:#777;
font-size:12px;
overflow:hidden;
text-overflow:ellipsis;
white-space:nowrap
}

.google-btn{
background:#fff;
color:#333;
border:1px solid #dadce0;
font-weight:600;
white-space:nowrap;
box-shadow:0 1px 3px rgba(0,0,0,.08)
}

.login-status{
text-align:center;
font-size:12px;
min-height:18px;
margin:-4px 0 10px
}

.logout-btn{
background:#f1f3f4;
color:#444;
font-size:13px;
padding:8px 12px
}

.leaderboard-button{
width:100%;
margin-top:18px;
padding:15px;
border-radius:14px;
background:linear-gradient(135deg,#1565c0,#42a5f5);
font-size:17px;
font-weight:700;
box-shadow:0 4px 10px rgba(21,101,192,.22)
}

#categories{
display:grid;
grid-template-columns:repeat(2,minmax(0,1fr));
gap:14px;
margin-top:14px
}

.category-card{
min-height:128px;
padding:18px 12px;
background:#fff;
border:1px solid #e5eaf2;
border-radius:18px;
box-shadow:0 4px 12px rgba(0,0,0,.07);
display:flex;
flex-direction:column;
justify-content:center;
align-items:center;
text-align:center;
cursor:pointer
}

.category-icon{
font-size:34px;
line-height:1;
margin-bottom:10px
}

.category-name{
font-size:16px;
font-weight:750;
line-height:1.25
}

.category-tests{
font-size:12px;
color:#777;
margin-top:6px
}

#testList{
display:grid;
grid-template-columns:repeat(2,minmax(0,1fr));
gap:14px
}

#testList .card{margin:0}

.leader-row{
display:flex;
align-items:center;
gap:12px;
background:#fff;
padding:13px;
margin:10px 0;
border-radius:15px;
border:1px solid #e7eaf0;
box-shadow:0 3px 10px rgba(0,0,0,.06)
}

.rank{
width:34px;
flex:0 0 34px;
text-align:center;
font-size:17px;
font-weight:800
}

.leader-info{
flex:1;
min-width:0
}

.leader-name{
font-weight:750;
white-space:nowrap;
overflow:hidden;
text-overflow:ellipsis
}

.leader-badge{
color:#777;
font-size:12px;
margin-top:3px;
white-space:nowrap;
overflow:hidden;
text-overflow:ellipsis
}

.leader-points{
color:#1565c0;
font-weight:800;
text-align:right;
white-space:nowrap
}

.leader-points small{
display:block;
color:#777;
font-size:10px;
font-weight:500
}

@media(max-width:600px){

.container{
padding:12px 12px 30px
}

.header h1{
font-size:26px
}

.question{
font-size:18px
}

#categories,
#testList{
grid-template-columns:repeat(2,minmax(0,1fr))
}

.account-bar{
align-items:flex-start
}

.google-btn,
.logout-btn{
padding:9px 10px
}

}

@media(max-width:380px){

#categories,
#testList{
grid-template-columns:1fr
}

}

</style>

</head>

<body>

<div class="container">

<section id="home">

<div id="accountBar"
class="account-bar">

<div class="user-info">

<div id="accountAvatar"
class="leader-avatar">
👤
</div>

<div>

<div id="accountName"
class="user-name">
Not signed in
</div>

<div id="accountEmail"
class="user-email">
Sign in to your Google account
</div>

</div>

</div>

<button id="googleLoginButton"
type="button"
class="google-btn">
🔐 Google Login
</button>

</div>

<div id="loginStatus"
class="login-status">
Initializing Google Login...
</div>

<div class="header">

<h1>🎯 CA Blockbuster</h1>

<p>Daily CA Revision</p>

</div>

<h2>Categories</h2>

<div id="categories">

<div class="status">
Loading...
</div>

</div>

<button id="leaderboardButton"
class="leaderboard-button"
type="button">

🏆 View Leaderboard

</button>

</section>


<section id="tests"
class="hidden">

<div class="topbar">

<button id="backHomeButton"
class="back"
type="button">
← Back
</button>

</div>

<h2 id="topicTitle"></h2>

<div id="testList"></div>

</section>


<section id="quiz"
class="hidden">

<div class="topbar">

<button id="backTestsButton"
class="back"
type="button">
← Tests
</button>

<span id="timer"
class="timer">
00:00
</span>

</div>

<h2 id="testTitle"></h2>

<div class="question-number"
id="questionNumber"></div>

<div class="card">

<div id="questionText"
class="question">
</div>

</div>

<div id="options"></div>

<div id="explanationCard"
class="card hidden">

<strong>Explanation</strong>

<div id="explanation"
class="explanation">
</div>

</div>

<div class="actions">

<button id="nextButton"
type="button">
Next →
</button>

</div>

</section>


<section id="result"
class="hidden">

<div class="header">

<h1>🎉 Result</h1>

</div>

<div class="card center">

<div id="scoreText"
class="score">
</div>

<p id="resultDetails"></p>

<div id="submitStatus"
class="status hidden">
</div>

</div>

<div class="center">

<button id="resultHomeButton"
type="button">
Back to Categories
</button>

</div>

</section>


<section id="leaderboard"
class="hidden">

<div class="topbar">

<button id="leaderboardBackButton"
class="back"
type="button">
← Back
</button>

</div>

<div class="header">

<h1>🏆 Leaderboard</h1>

<p>Top performers</p>

</div>

<div id="leaderboardList">

<div class="status">
Loading leaderboard...
</div>

</div>

</section>

</div>


<script>

window.__FIREBASE_WEB_CONFIG__ =
__FIREBASE_WEB_CONFIG__;

</script>


<!-- ========================================================
     FIREBASE GOOGLE LOGIN
     ======================================================== -->

<script>

(function(){

"use strict";

let auth = null;
let initialized = false;


function status(message,error){

const el =
document.getElementById("loginStatus");

if(!el) return;

el.textContent = message || "";

el.style.color =
error ? "#b71c1c" : "#666";

}


function escapeHtml(value){

return String(value ?? "")
.replace(/&/g,"&amp;")
.replace(/</g,"&lt;")
.replace(/>/g,"&gt;")
.replace(/"/g,"&quot;")
.replace(/'/g,"&#039;");

}


function updateAccount(user){

const avatar =
document.getElementById("accountAvatar");

const name =
document.getElementById("accountName");

const email =
document.getElementById("accountEmail");

const button =
document.getElementById("googleLoginButton");


if(!avatar || !name || !email || !button)
return;


if(user){

if(user.photoURL){

avatar.outerHTML =
'<img id="accountAvatar" ' +
'class="user-photo" ' +
'src="' +
escapeHtml(user.photoURL) +
'" alt="">';

}else{

avatar.textContent = "👤";
avatar.className = "leader-avatar";

}


name.textContent =
user.displayName || "Google User";

email.textContent =
user.email || "";

button.textContent =
"Logout";

button.className =
"logout-btn";

button.disabled = false;

status(
"✓ Signed in with Google"
);

}else{

const a =
document.getElementById("accountAvatar");

if(a){

a.outerHTML =
'<div id="accountAvatar" ' +
'class="leader-avatar">👤</div>';

}

name.textContent =
"Not signed in";

email.textContent =
"Sign in to your Google account";

button.textContent =
"🔐 Google Login";

button.className =
"google-btn";

button.disabled = false;

status(
initialized
? "Sign in with Google to continue."
: "Initializing Google Login..."
);

}

}


async function loginWithGoogle(){

console.log(
"[Google Login] Button clicked"
);


if(!auth){

const msg =
"Google Login is not ready. " +
"Check Firebase Web configuration " +
"in Koyeb.";

console.error(msg);

status(msg,true);

alert(msg);

return;

}


const button =
document.getElementById(
"googleLoginButton"
);


try{

button.disabled = true;

button.textContent =
"Connecting...";

status(
"Opening Google sign-in..."
);


const provider =
new firebase.auth.GoogleAuthProvider();


provider.setCustomParameters({
prompt:"select_account"
});


console.log(
"[Google Login] signInWithPopup"
);


await auth.signInWithPopup(
provider
);


console.log(
"[Google Login] Popup completed"
);


}catch(error){

console.error(
"[Google Login] Error:",
error
);


if(

error.code ===
"auth/popup-blocked"

||

error.code ===
"auth/popup-cancelled"

||

error.code ===
"auth/cancelled-popup-request"

){

try{

status(
"Opening Google sign-in..."
);

const provider =
new firebase.auth.GoogleAuthProvider();

provider.setCustomParameters({
prompt:"select_account"
});

await auth.signInWithRedirect(
provider
);

return;

}catch(e){

console.error(e);

status(
"Google Login failed: " +
e.message,
true
);

}

}else{

status(
"Google Login failed: " +
(error.message ||
error.code ||
"Unknown error"),
true
);

alert(
"Google Login failed\n\n" +
"Code: " +
(error.code || "unknown") +
"\n\n" +
(error.message ||
"Unknown error")
);

}

}finally{

if(!window.currentFirebaseUser){

button.disabled = false;

button.textContent =
"🔐 Google Login";

}

}

}


async function logoutGoogle(){

if(!auth) return;

try{

await auth.signOut();

}catch(error){

console.error(
"Logout error:",
error
);

}

}


window.loginWithGoogle =
loginWithGoogle;

window.logoutGoogle =
logoutGoogle;


function initializeFirebaseLogin(){

const button =
document.getElementById(
"googleLoginButton"
);


if(!button){

console.error(
"[Google Login] Button missing"
);

return;

}


button.addEventListener(
"click",
function(){

if(window.currentFirebaseUser){

logoutGoogle();

}else{

loginWithGoogle();

}

}
);


try{

const config =
window.__FIREBASE_WEB_CONFIG__;


if(!window.firebase){

throw new Error(
"Firebase Web SDK did not load."
);

}


if(

!config ||

!config.apiKey ||

String(config.apiKey)
.startsWith("YOUR_") ||

!config.projectId ||

String(config.projectId)
.startsWith("YOUR_")

){

throw new Error(
"Firebase Web configuration is missing. " +
"Check FIREBASE_WEB_API_KEY, " +
"FIREBASE_WEB_AUTH_DOMAIN, " +
"FIREBASE_PROJECT_ID, " +
"FIREBASE_STORAGE_BUCKET, " +
"FIREBASE_MESSAGING_SENDER_ID and " +
"FIREBASE_WEB_APP_ID in Koyeb."
);

}


console.log(
"[Google Login] Firebase project:",
config.projectId
);


if(!firebase.apps.length){

firebase.initializeApp(config);

}


auth =
firebase.auth();


window.firebaseAuthInstance =
auth;

window.googleLoginReady =
true;

initialized =
true;


auth.getRedirectResult()
.then(function(result){

if(result && result.user){

console.log(
"[Google Login] Redirect login completed:",
result.user.email
);

}

})
.catch(function(error){

console.error(
"[Google Login] Redirect result:",
error
);

});


auth.onAuthStateChanged(
function(user){

window.currentFirebaseUser =
user || null;

console.log(
"[Google Login] Auth state:",
user
? user.email
: "signed out"
);

updateAccount(user);

}
);


}catch(error){

console.error(
"[Google Login] Initialization:",
error
);

status(
"Google Login unavailable: " +
error.message,
true
);

}

}


if(
document.readyState === "loading"
){

document.addEventListener(
"DOMContentLoaded",
initializeFirebaseLogin
);

}else{

initializeFirebaseLogin();

}

})();

</script>


<!-- ========================================================
     QUIZ
     ======================================================== -->

<script>

"use strict";


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

let submittingResult = false;


function escapeHtml(value){

return String(value ?? "")
.replace(/&/g,"&amp;")
.replace(/</g,"&lt;")
.replace(/>/g,"&gt;")
.replace(/"/g,"&quot;")
.replace(/'/g,"&#039;");

}


/* ==========================================================
   API GET
   ========================================================== */

async function apiGet(
url,
requireLogin = false
){

const headers = {
Accept:"application/json"
};


const authInstance =
window.firebaseAuthInstance;

const user =
window.currentFirebaseUser;


if(authInstance && user){

try{

headers.Authorization =
"Bearer " +
await user.getIdToken(
true
);

}catch(error){

console.warn(
"Could not get Firebase ID token:",
error
);

}

}else if(requireLogin){

throw new Error(
"Please sign in with Google first."
);

}


const response =
await fetch(
url,
{
method:"GET",
headers:headers
}
);


let data;


try{

data =
await response.json();

}catch(error){

throw new Error(
"Server returned an invalid response (" +
response.status +
")"
);

}


if(!response.ok){

throw new Error(
data.error ||
"Server error: " +
response.status
);

}


return data;

}


/* ==========================================================
   API POST
   ========================================================== */

async function apiPost(
url,
body,
requireLogin = true
){

const user =
window.currentFirebaseUser;

if(requireLogin && !user){

throw new Error(
"Please sign in with Google before submitting your score."
);

}


const token =
await user.getIdToken(true);


const response =
await fetch(
url,
{
method:"POST",

headers:{
"Content-Type":
"application/json",

"Accept":
"application/json",

"Authorization":
"Bearer " + token
},

body:
JSON.stringify(body)

}
);


let data;


try{

data =
await response.json();

}catch(error){

throw new Error(
"Server returned an invalid response (" +
response.status +
")"
);

}


if(!response.ok){

throw new Error(
data.error ||
data.message ||
"Server error: " +
response.status
);

}


return data;

}


/* ==========================================================
   LOAD TESTS
   ========================================================== */

async function loadData(){

const categories =
document.getElementById(
"categories"
);


try{

categories.innerHTML =
'<div class="status">' +
'Loading from Firestore...' +
'</div>';


allTests =
await apiGet(
"/quiz/api/tests"
);


if(!Array.isArray(allTests)){

throw new Error(
"Invalid test data received"
);

}


displayCategories();


}catch(error){

console.error(
"[Quiz] Load tests:",
error
);


categories.innerHTML =
'<div class="status error">' +
'<strong>Unable to load quiz.</strong>' +
'<br><br>' +
escapeHtml(error.message) +
'</div>';

}

}


/* ==========================================================
   CATEGORIES
   ========================================================== */

function displayCategories(){

const container =
document.getElementById(
"categories"
);

container.innerHTML = "";


const topicIds =
[
...new Set(
allTests
.map(t => t.topicId)
.filter(Boolean)
)
];


if(!topicIds.length){

container.innerHTML =
'<div class="empty">' +
'No categories found.' +
'</div>';

return;

}


topicIds.sort(
(a,b) =>
String(a).localeCompare(
String(b)
)
);


const icons = [
"📚",
"🌍",
"📰",
"🔬",
"🏛️",
"💡",
"🇮🇳",
"🎯"
];


topicIds.forEach(
(topicId,index)=>{

const topicTests =
allTests.filter(
t => t.topicId === topicId
);


const card =
document.createElement(
"div"
);

card.className =
"category-card";


card.innerHTML =
'<div class="category-icon">' +
icons[index % icons.length] +
'</div>' +

'<div class="category-name">' +
escapeHtml(topicId) +
'</div>' +

'<div class="category-tests">' +
topicTests.length +
" " +
(
topicTests.length === 1
? "Test"
: "Tests"
) +
'</div>';


card.addEventListener(
"click",
()=>showTestsForTopic(
topicId
)
);


container.appendChild(
card
);

}
);

}


/* ==========================================================
   TEST LIST
   ========================================================== */

function showTestsForTopic(
topicId
){

selectedTopic =
topicId;

currentTests =
allTests.filter(
t => t.topicId === topicId
);


document.getElementById(
"home"
).classList.add("hidden");


document.getElementById(
"tests"
).classList.remove("hidden");


document.getElementById(
"quiz"
).classList.add("hidden");


document.getElementById(
"result"
).classList.add("hidden");


document.getElementById(
"leaderboard"
).classList.add("hidden");


document.getElementById(
"topicTitle"
).textContent =
topicId;


const container =
document.getElementById(
"testList"
);

container.innerHTML = "";


if(!currentTests.length){

container.innerHTML =
'<div class="empty">' +
'No tests found.' +
'</div>';

return;

}


currentTests.forEach(
test => {

const card =
document.createElement(
"div"
);

card.className =
"card clickable";


card.innerHTML =
'<div class="title">' +
escapeHtml(
test.title || test.id
) +
'</div>' +

(
test.subtitle
?
'<div class="subtitle">' +
escapeHtml(
test.subtitle
) +
'</div>'
:
""
) +

'<div class="meta">' +
escapeHtml(
String(
test.questionCount || 0
)
) +
' Questions • ' +
escapeHtml(
String(
test.durationMinutes || 0
)
) +
' min • ' +
escapeHtml(
String(
test.difficulty || ""
)
) +
'</div>';


card.addEventListener(
"click",
()=>startQuiz(test)
);


container.appendChild(
card
);

}
);

}


/* ==========================================================
   START QUIZ
   ========================================================== */

async function startQuiz(test){

selectedTest =
test;


try{

document.getElementById(
"tests"
).classList.add("hidden");


document.getElementById(
"quiz"
).classList.remove("hidden");


document.getElementById(
"result"
).classList.add("hidden");


document.getElementById(
"leaderboard"
).classList.add("hidden");


document.getElementById(
"testTitle"
).textContent =
test.title || test.id;


document.getElementById(
"questionText"
).textContent =
"Loading questions...";


document.getElementById(
"options"
).innerHTML = "";


currentQuestions =
await apiGet(
"/quiz/api/questions/" +
encodeURIComponent(
test.id
)
);


if(
!Array.isArray(currentQuestions) ||
!currentQuestions.length
){

throw new Error(
"No questions found for this test."
);

}


currentQuestion = 0;

score = 0;

answered = false;

submittingResult = false;


startTimer(
Number(
test.durationMinutes
) || 0
);


displayQuestion();


}catch(error){

console.error(
"[Quiz] Start:",
error
);


document.getElementById(
"questionText"
).textContent =
"";


document.getElementById(
"options"
).innerHTML =
'<div class="status error">' +
escapeHtml(
error.message
) +
'</div>';

}

}


/* ==========================================================
   QUESTION
   ========================================================== */

function displayQuestion(){

const q =
currentQuestions[
currentQuestion
];


if(!q){

finishQuiz();

return;

}


answered = false;


document.getElementById(
"questionNumber"
).textContent =
"Question " +
(currentQuestion + 1) +
" / " +
currentQuestions.length;


document.getElementById(
"questionText"
).textContent =
q.questionText || "";


document.getElementById(
"explanationCard"
).classList.add(
"hidden"
);


document.getElementById(
"explanation"
).textContent = "";


document.getElementById(
"nextButton"
).textContent =
currentQuestion ===
currentQuestions.length - 1
? "Finish ✓"
: "Next →";


const options =
document.getElementById(
"options"
);


options.innerHTML = "";


[
q.option0 || "",
q.option1 || "",
q.option2 || "",
q.option3 || ""
]
.forEach(
(option,index)=>{

const div =
document.createElement(
"div"
);

div.className =
"option";

div.textContent =
option;


div.addEventListener(
"click",
()=>selectAnswer(
index,
div
)
);


options.appendChild(
div
);

}
);

}


/* ==========================================================
   ANSWER
   ========================================================== */

function selectAnswer(
index,
element
){

if(answered)
return;


answered = true;


const q =
currentQuestions[
currentQuestion
];


const correctIndex =
Number(
q.correctOptionIndex
);


const optionElements =
document.querySelectorAll(
".option"
);


if(index === correctIndex){

element.classList.add(
"correct"
);

score++;

}else{

element.classList.add(
"wrong"
);

if(
optionElements[
correctIndex
]
){

optionElements[
correctIndex
].classList.add(
"correct"
);

}

}


if(q.explanation){

document.getElementById(
"explanation"
).textContent =
q.explanation;


document.getElementById(
"explanationCard"
).classList.remove(
"hidden"
);

}

}


/* ==========================================================
   NEXT
   ========================================================== */

function nextQuestion(){

if(!answered)
return;


if(
currentQuestion >=
currentQuestions.length - 1
){

finishQuiz();

return;

}


currentQuestion++;

displayQuestion();

}


/* ==========================================================
   TIMER
   ========================================================== */

function startTimer(
durationMinutes
){

clearInterval(
timerInterval
);


const hasLimit =
Number(durationMinutes) > 0;


timerSeconds =
hasLimit
? Number(durationMinutes) * 60
: 0;


updateTimerDisplay();


timerInterval =
setInterval(
()=>{

if(hasLimit){

timerSeconds--;

updateTimerDisplay();


if(timerSeconds <= 0){

clearInterval(
timerInterval
);

finishQuiz();

}

}else{

timerSeconds++;

updateTimerDisplay();

}

},
1000
);

}


function updateTimerDisplay(){

const minutes =
Math.floor(
timerSeconds / 60
);


const seconds =
timerSeconds % 60;


document.getElementById(
"timer"
).textContent =
"⏱ " +
String(minutes).padStart(
2,
"0"
) +
":" +
String(seconds).padStart(
2,
"0"
);

}


/* ==========================================================
   FINISH QUIZ
   ========================================================== */

async function finishQuiz(){

clearInterval(
timerInterval
);


document.getElementById(
"quiz"
).classList.add(
"hidden"
);


document.getElementById(
"result"
).classList.remove(
"hidden"
);


const total =
currentQuestions.length;


const percentage =
total
? Math.round(
score / total * 100
)
: 0;


document.getElementById(
"scoreText"
).textContent =
score +
" / " +
total;


const stars =
calculateStars(
score,
total
);


const basePoints =
420;


const earnedPoints =
basePoints +
(score * 10) +
(stars * 40);


document.getElementById(
"resultDetails"
).innerHTML =
percentage +
"% correct<br><br>" +

"⭐ Stars: <strong>" +
stars +
"</strong><br>" +

"🏆 Points earned: <strong>" +
earnedPoints +
"</strong>";


await submitQuizResult(
score,
total,
stars,
earnedPoints
);

}


/* ==========================================================
   SAME STAR RULES USED BY SERVER
   ========================================================== */

function calculateStars(
correct,
total
){

if(!total)
return 0;


const percentage =
(correct / total) * 100;


if(percentage >= 80)
return 3;


if(percentage >= 60)
return 2;


if(percentage >= 40)
return 1;


return 0;

}


/* ==========================================================
   SUBMIT SCORE
   ========================================================== */

async function submitQuizResult(
correct,
total,
stars,
earnedPoints
){

const statusBox =
document.getElementById(
"submitStatus"
);


statusBox.classList.remove(
"hidden"
);


if(!window.currentFirebaseUser){

statusBox.className =
"status error";


statusBox.innerHTML =
"⚠️ You are not signed in. " +
"Your score was not added to the leaderboard.";


return;

}


if(submittingResult)
return;


submittingResult = true;


statusBox.className =
"status";


statusBox.textContent =
"Saving your score...";


try{

const result =
await apiPost(
"/quiz/api/submit-score",
{
testId:
selectedTest
? selectedTest.id
: "",

testTitle:
selectedTest
? selectedTest.title || ""
: "",

correct:
correct,

total:
total,

stars:
stars,

earnedPoints:
earnedPoints
},
true
);


console.log(
"[Leaderboard] Score saved:",
result
);


statusBox.className =
"status";


statusBox.innerHTML =
"✅ Score added to leaderboard<br>" +

"🏆 +" +
Number(
result.pointsAdded || earnedPoints
) +
" points";


}catch(error){

console.error(
"[Leaderboard] Submit error:",
error
);


statusBox.className =
"status error";


statusBox.innerHTML =
"⚠️ Could not save your score.<br><br>" +
escapeHtml(
error.message
);

}finally{

submittingResult = false;

}

}


/* ==========================================================
   NAVIGATION
   ========================================================== */

function showHome(){

clearInterval(
timerInterval
);


document.getElementById(
"home"
).classList.remove(
"hidden"
);


document.getElementById(
"tests"
).classList.add(
"hidden"
);


document.getElementById(
"quiz"
).classList.add(
"hidden"
);


document.getElementById(
"result"
).classList.add(
"hidden"
);


document.getElementById(
"leaderboard"
).classList.add(
"hidden"
);

}


function showTests(){

clearInterval(
timerInterval
);


document.getElementById(
"quiz"
).classList.add(
"hidden"
);


document.getElementById(
"result"
).classList.add(
"hidden"
);


document.getElementById(
"leaderboard"
).classList.add(
"hidden"
);


document.getElementById(
"tests"
).classList.remove(
"hidden"
);

}


/* ==========================================================
   LEADERBOARD
   ========================================================== */

async function showLeaderboard(){

clearInterval(
timerInterval
);


document.getElementById(
"home"
).classList.add(
"hidden"
);


document.getElementById(
"tests"
).classList.add(
"hidden"
);


document.getElementById(
"quiz"
).classList.add(
"hidden"
);


document.getElementById(
"result"
).classList.add(
"hidden"
);


document.getElementById(
"leaderboard"
).classList.remove(
"hidden"
);


const container =
document.getElementById(
"leaderboardList"
);


container.innerHTML =
'<div class="status">' +
'Loading leaderboard...' +
'</div>';


try{

const users =
await apiGet(
"/quiz/api/leaderboard"
);


if(
!Array.isArray(users) ||
!users.length
){

container.innerHTML =
'<div class="empty">' +
'No leaderboard data found.' +
'</div>';

return;

}


container.innerHTML = "";


users.forEach(
(user,index)=>{

const row =
document.createElement(
"div"
);


row.className =
"leader-row";


const medal =
index === 0
? "🥇"
: index === 1
? "🥈"
: index === 2
? "🥉"
: String(index + 1);


const photo =
user.profilePhotoUri
?

'<img class="leader-photo" ' +
'src="' +
escapeHtml(
user.profilePhotoUri
) +
'" alt="">'

:

'<div class="leader-avatar">' +
escapeHtml(
user.avatarEmoji || "👤"
) +
'</div>';


row.innerHTML =

'<div class="rank">' +
medal +
'</div>' +

photo +

'<div class="leader-info">' +

'<div class="leader-name">' +
escapeHtml(
user.name || "User"
) +
'</div>' +

'<div class="leader-badge">' +
escapeHtml(
user.badgeTitle || ""
) +
'</div>' +

'</div>' +

'<div class="leader-points">' +

Number(
user.points || 0
) +

'<small>points</small>' +

'</div>';


container.appendChild(
row
);

}
);


}catch(error){

console.error(
"[Leaderboard] Error:",
error
);


container.innerHTML =
'<div class="status error">' +

'<strong>' +
'Unable to load leaderboard.' +
'</strong>' +

'<br><br>' +

escapeHtml(
error.message
) +

'</div>';

}

}


/* ==========================================================
   BUTTONS
   ========================================================== */

document.getElementById(
"backHomeButton"
).addEventListener(
"click",
showHome
);


document.getElementById(
"backTestsButton"
).addEventListener(
"click",
showTests
);


document.getElementById(
"resultHomeButton"
).addEventListener(
"click",
showHome
);


document.getElementById(
"leaderboardBackButton"
).addEventListener(
"click",
showHome
);


document.getElementById(
"leaderboardButton"
).addEventListener(
"click",
showLeaderboard
);


document.getElementById(
"nextButton"
).addEventListener(
"click",
nextQuestion
);


/* ==========================================================
   START
   ========================================================== */

loadData();

</script>

</body>

</html>'''

    return html.replace(
        "__FIREBASE_WEB_CONFIG__",
        json.dumps(
            FIREBASE_WEB_CONFIG
        )
    )


# ============================================================
# QUIZ FIRESTORE API
# ============================================================

@app.route("/quiz/api/tests")
def quiz_tests():

    try:

        db = get_firestore()

        docs =
        db.collection(
            "custom_tests"
        ).stream()

        tests = []

        for doc in docs:

            data =
            doc.to_dict()

            tests.append({

                "id":
                data.get("id")
                or doc.id,

                "topicId":
                data.get("topicId")
                or "",

                "title":
                data.get("title")
                or "",

                "subtitle":
                data.get("subtitle")
                or "",

                "durationMinutes":
                data.get("durationMinutes")
                or 0,

                "difficulty":
                data.get("difficulty")
                or "",

                "dateMillis":
                data.get("dateMillis"),

                "questionCount":
                0

            })


        question_counts = {}


        for qdoc in db.collection(
            "custom_questions"
        ).stream():

            qdata =
            qdoc.to_dict()

            test_id =
            qdata.get("testId")


            if test_id:

                question_counts[test_id] =
                    question_counts.get(
                        test_id,
                        0
                    ) + 1


        for test in tests:

            test["questionCount"] =
                question_counts.get(
                    test["id"],
                    0
                )


        return jsonify(tests)


    except Exception as e:

        print(
            f"[Quiz Firestore tests error] {e}"
        )

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================
# QUESTIONS
# ============================================================

@app.route(
    "/quiz/api/questions/<path:test_id>"
)
def quiz_questions(test_id):

    try:

        db = get_firestore()

        docs =
        db.collection(
            "custom_questions"
        ).where(
            "testId",
            "==",
            test_id
        ).stream()


        questions = []


        for doc in docs:

            data =
            doc.to_dict()


            questions.append({

                "id":
                data.get("id")
                or doc.id,

                "testId":
                data.get("testId")
                or "",

                "topicId":
                data.get("topicId")
                or "",

                "questionText":
                data.get("questionText")
                or "",

                "option0":
                data.get("option0")
                or "",

                "option1":
                data.get("option1")
                or "",

                "option2":
                data.get("option2")
                or "",

                "option3":
                data.get("option3")
                or "",

                "correctOptionIndex":
                data.get(
                    "correctOptionIndex",
                    0
                ),

                "explanation":
                data.get("explanation")
                or "",

                "hint":
                data.get("hint")
                or ""

            })


        return jsonify(questions)


    except Exception as e:

        print(
            f"[Quiz Firestore questions error] {e}"
        )

        return jsonify({
            "error": str(e)
        }), 500


# ============================================================
# SUBMIT QUIZ SCORE
# ============================================================

@app.route(
    "/quiz/api/submit-score",
    methods=["POST"]
)
def submit_quiz_score():

    # --------------------------------------------------------
    # 1. VERIFY GOOGLE/FIREBASE LOGIN
    # --------------------------------------------------------

    user, error_response =
        require_authenticated_user()

    if error_response:

        return error_response


    # --------------------------------------------------------
    # 2. GET FIREBASE UID
    # --------------------------------------------------------

    uid =
    user.get("uid")


    if not uid:

        return jsonify({
            "error":
            "Firebase UID not found."
        }), 401


    # --------------------------------------------------------
    # 3. GET USER INFORMATION
    # --------------------------------------------------------

    email =
    user.get("email") or ""


    name =
    user.get("name") or \
    user.get("email") or \
    "User"


    picture =
    user.get("picture") or ""


    # --------------------------------------------------------
    # 4. READ SCORE
    # --------------------------------------------------------

    data =
    request.get_json(
        silent=True
    ) or {}


    test_id =
    str(
        data.get(
            "testId",
            ""
        )
    )


    test_title =
    str(
        data.get(
            "testTitle",
            ""
        )
    )


    try:

        correct =
        int(
            data.get(
                "correct",
                0
            )
        )


        total =
        int(
            data.get(
                "total",
                0
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return jsonify({
            "error":
            "Invalid score."
        }), 400


    # --------------------------------------------------------
    # 5. VALIDATE
    # --------------------------------------------------------

    if total <= 0:

        return jsonify({
            "error":
            "Invalid question count."
        }), 400


    if correct < 0:

        return jsonify({
            "error":
            "Invalid correct answer count."
        }), 400


    if correct > total:

        return jsonify({
            "error":
            "Correct answers cannot exceed total questions."
        }), 400


    # --------------------------------------------------------
    # 6. SERVER CALCULATES STARS
    # --------------------------------------------------------

    stars =
    calculate_stars(
        correct,
        total
    )


    # --------------------------------------------------------
    # 7. SERVER CALCULATES POINTS
    #
    # 420 + correct×10 + stars×40
    # --------------------------------------------------------

    points_added =
    calculate_points(
        correct,
        stars
    )


    accuracy =
    round(
        (correct / total) * 100,
        2
    )


    # --------------------------------------------------------
    # 8. SAVE TO FIRESTORE
    #
    # IMPORTANT:
    #
    # leaderboard/{Firebase UID}
    # --------------------------------------------------------

    try:

        db =
        get_firestore()


        leaderboard_ref =
        db.collection(
            "leaderboard"
        ).document(uid)


        snapshot =
        leaderboard_ref.get()


        # ----------------------------------------------------
        # EXISTING USER
        # ----------------------------------------------------

        if snapshot.exists:

            old =
            snapshot.to_dict() or {}


            try:

                old_points =
                int(
                    old.get(
                        "points",
                        0
                    ) or 0
                )

            except (
                TypeError,
                ValueError
            ):

                old_points = 0


            try:

                old_correct =
                int(
                    old.get(
                        "correct",
                        0
                    ) or 0
                )

            except (
                TypeError,
                ValueError
            ):

                old_correct = 0


            try:

                old_questions =
                int(
                    old.get(
                        "questionsAnswered",
                        0
                    ) or 0
                )

            except (
                TypeError,
                ValueError
            ):

                old_questions = 0


            try:

                old_stars =
                int(
                    old.get(
                        "stars",
                        0
                    ) or 0
                )

            except (
                TypeError,
                ValueError
            ):

                old_stars = 0


            new_points =
            old_points + points_added


            new_correct =
            old_correct + correct


            new_questions =
            old_questions + total


            new_stars =
            old_stars + stars


            new_accuracy =
            round(
                (
                    new_correct /
                    new_questions
                ) * 100,
                2
            ) if new_questions else 0


            leaderboard_ref.set({

                "uid":
                uid,

                "name":
                name,

                "email":
                email,

                "profilePhotoUri":
                picture,

                "points":
                new_points,

                "accuracy":
                new_accuracy,

                "stars":
                new_stars,

                "correct":
                new_correct,

                "questionsAnswered":
                new_questions,

                "lastTestId":
                test_id,

                "lastTestTitle":
                test_title,

                "lastCorrect":
                correct,

                "lastTotal":
                total,

                "lastStars":
                stars,

                "lastPoints":
                points_added,

                "lastPlayedAt":
                firestore.SERVER_TIMESTAMP

            }, merge=True)


            total_points =
            new_points


        # ----------------------------------------------------
        # NEW USER
        # ----------------------------------------------------

        else:

            leaderboard_ref.set({

                "uid":
                uid,

                "name":
                name,

                "email":
                email,

                "profilePhotoUri":
                picture,

                "points":
                points_added,

                "accuracy":
                accuracy,

                "stars":
                stars,

                "correct":
                correct,

                "questionsAnswered":
                total,

                "lastTestId":
                test_id,

                "lastTestTitle":
                test_title,

                "lastCorrect":
                correct,

                "lastTotal":
                total,

                "lastStars":
                stars,

                "lastPoints":
                points_added,

                "createdAt":
                firestore.SERVER_TIMESTAMP,

                "lastPlayedAt":
                firestore.SERVER_TIMESTAMP

            })


            total_points =
            points_added


        print(
            "[Leaderboard] Saved:",
            uid,
            name,
            points_added,
            "points"
        )


        return jsonify({

            "success":
            True,

            "uid":
            uid,

            "name":
            name,

            "correct":
            correct,

            "total":
            total,

            "accuracy":
            accuracy,

            "stars":
            stars,

            "pointsAdded":
            points_added,

            "totalPoints":
            total_points

        })


    except Exception as e:

        print(
            "[Leaderboard Save Error]",
            e
        )

        return jsonify({
            "error":
            "Could not save leaderboard score.",
            "details":
            str(e)
        }), 500


# ============================================================
# LEADERBOARD
# ============================================================

@app.route(
    "/quiz/api/leaderboard"
)
def quiz_leaderboard():

    try:

        db =
        get_firestore()


        entries = []


        for doc in db.collection(
            "leaderboard"
        ).stream():

            data =
            doc.to_dict()


            try:

                points =
                int(
                    data.get(
                        "points",
                        0
                    ) or 0
                )

            except (
                TypeError,
                ValueError
            ):

                points = 0


            entries.append({

                "uid":
                data.get(
                    "uid"
                ) or doc.id,

                "name":
                data.get(
                    "name"
                ) or "User",

                "points":
                points,

                "accuracy":
                data.get(
                    "accuracy",
                    0
                ),

                "stars":
                data.get(
                    "stars",
                    0
                ),

                "badgeTitle":
                data.get(
                    "badgeTitle"
                ) or "",

                "avatarEmoji":
                data.get(
                    "avatarEmoji"
                ) or "👤",

                "profilePhotoUri":
                data.get(
                    "profilePhotoUri"
                ) or ""

            })


        entries.sort(
            key=lambda item:
            item["points"],
            reverse=True
        )


        return jsonify(
            entries[:50]
        )


    except Exception as e:

        print(
            "[Quiz Firestore leaderboard error]",
            e
        )

        return jsonify({
            "error":
            str(e)
        }), 500


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    print("[Startup] CA Blockbuster server starting...")
    print("[Startup] Firebase Web project:", FIREBASE_WEB_CONFIG.get("projectId"))

    app.run(
        host="0.0.0.0",
        port=8000
    )