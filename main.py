import os
import time
import feedparser
import threading
import requests
import re
import shutil
from datetime import datetime
from flask import Flask, request
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import json
from gtts import gTTS

import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth

app = Flask(__name__)

# ------------------ FIRESTORE ------------------
_firestore_db = None

def get_firestore():
    global _firestore_db
    if _firestore_db is not None:
        return _firestore_db

    firebase_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not firebase_json:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not configured in Koyeb")

    try:
        service_account_info = json.loads(firebase_json)
    except json.JSONDecodeError as e:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON") from e

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(service_account_info))

    _firestore_db = firestore.client()
    return _firestore_db

# ------------------ FIREBASE WEB AUTH CONFIG ------------------
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "").strip()
FIREBASE_WEB_CONFIG = {
    "apiKey": os.environ.get("FIREBASE_WEB_API_KEY", "").strip(),
    "authDomain": os.environ.get(
        "FIREBASE_WEB_AUTH_DOMAIN",
        f"{FIREBASE_PROJECT_ID}.firebaseapp.com" if FIREBASE_PROJECT_ID else ""
    ).strip(),
    "projectId": FIREBASE_PROJECT_ID,
    "storageBucket": os.environ.get(
        "FIREBASE_STORAGE_BUCKET",
        f"{FIREBASE_PROJECT_ID}.firebasestorage.app" if FIREBASE_PROJECT_ID else ""
    ).strip(),
    "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID", "").strip(),
    "appId": os.environ.get("FIREBASE_WEB_APP_ID", "").strip()
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
        archive_dir = os.path.join(ARCHIVE_FOLDER, month_folder)
        os.makedirs(archive_dir, exist_ok=True)
        archive_path = os.path.join(archive_dir, os.path.basename(xml_path))
        shutil.copy2(xml_path, archive_path)
        print(f"[Feed Archived] {archive_path}")
    except Exception as e:
        print(f"[Archive Error] {e}")

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

        xml_path = os.path.join(XML_FOLDER, f"{name}.xml")
        ET.ElementTree(rss_root).write(xml_path, encoding="utf-8", xml_declaration=True)
        archive_feed(xml_path)
        print(f"[Feed Updated] {name}")
    except Exception as e:
        print(f"[Error fetching {name}] {e}")

def telegram_updater():
    while True:
        for name, url in TELEGRAM_CHANNELS.items():
            fetch_telegram_xml(name, url)
        time.sleep(600)

# ------------------ AUDIO ------------------
def generate_audio_from_feed(channel_name):
    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")
    if not os.path.exists(path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])
    feed = feedparser.parse(path)
    entries = list(feed.entries)[-25:]
    full_text = "ഇന്നത്തെ പ്രധാന വാർത്തകൾ.\n\n"

    for e in entries:
        desc_text = e.get("description", "")
        desc_text = re.sub(r"[\U0001F300-\U0001FAFF]", " ", desc_text)
        desc_text = re.sub(r"[\U0001F600-\U0001F64F]", " ", desc_text)
        desc_text = re.sub(r"[\u2600-\u27BF]", " ", desc_text)
        desc_text = re.sub(r"[\uFE0F\u200D]", " ", desc_text)
        desc_text = re.sub(r"#\w+", "", desc_text)
        desc_text = re.sub(r"http\S+", "", desc_text)
        desc_text = re.sub(r"(join\s*@\w+.*)$", "", desc_text, flags=re.IGNORECASE)
        desc_text = re.sub(r"@\w+", "", desc_text)
        desc_text = re.sub(r"[!?:;]+", ". ", desc_text)
        desc_text = re.sub(r"[\"'(){}\[\]<>]", " ", desc_text)
        desc_text = re.sub(r"\s+", " ", desc_text).strip()
        if not desc_text or len(desc_text) < 5:
            desc_text = e.get("title", "")
        if desc_text:
            full_text += f"{desc_text}.\n\n"

    if len(full_text.strip()) < 10:
        full_text = "ഇന്ന് വാർത്തകൾ ലഭ്യമല്ല."

    try:
        output_path = os.path.join(AUDIO_FOLDER, f"{channel_name}.mp3")
        gTTS(full_text, lang="ml").save(output_path)
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
    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")
    if request.args.get("refresh") == "1":
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])
    if not os.path.exists(path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])
    feed = feedparser.parse(path)
    posts = "".join(f"<p>{e.get('description','')}</p><hr>" for e in list(feed.entries)[::-1][:50])
    return f"""
    <html><head><meta name='viewport' content='width=device-width,initial-scale=1.0'>
    <style>body{{font-family:system-ui;padding:10px}}.btn{{background:#00695c;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none}}</style>
    </head><body><h2>{channel_name}</h2><a class='btn' href='?refresh=1'>🔄 Refresh</a><br><br>{posts}</body></html>
    """

# ------------------ Archive Page ------------------
@app.route("/archives")
def archives():
    months = sorted(os.listdir(ARCHIVE_FOLDER), reverse=True)
    html = """
    <html><head><meta name='viewport' content='width=device-width,initial-scale=1.0'>
    <style>
    body{font-family:system-ui;padding:10px;background:#f5f5f5}h2{text-align:center}
    .card{background:#fff;padding:12px;border-radius:10px;margin-bottom:15px;box-shadow:0 2px 5px rgba(0,0,0,.1)}
    .file{display:block;padding:8px;margin-top:5px;background:#e3f2fd;border-radius:6px;text-decoration:none;color:#1565c0;font-weight:bold}
    </style></head><body><h2>📦 Feed Archives</h2>
    """
    if not months:
        html += "<p>No archives found.</p>"
    for month in months:
        month_path = os.path.join(ARCHIVE_FOLDER, month)
        if not os.path.isdir(month_path):
            continue
        html += f"<div class='card'><h3>{month}</h3>"
        for file in os.listdir(month_path):
            html += f"<a class='file' href='/archive/{month}/{file}'>{file}</a>"
        html += "</div>"
    return html + "</body></html>"

# ------------------ Archive Files ------------------
@app.route("/archive/<month>/<filename>")
def archive_file(month, filename):
    archive_path = os.path.join(ARCHIVE_FOLDER, month, filename)
    if not os.path.exists(archive_path):
        return "Archive not found"
    feed = feedparser.parse(archive_path)
    posts = ""
    for e in list(feed.entries)[::-1][:100]:
        posts += f"""
        <div class='post'><h3>{e.get('title','')}</h3><p>{e.get('description','')}</p>
        <a class='open-btn' href='{e.get('link','#')}' target='_blank'>Open Source</a></div>
        """
    return f"""
    <html><head><meta name='viewport' content='width=device-width,initial-scale=1.0'>
    <style>
    body{{font-family:system-ui;padding:10px;background:#f5f5f5}}h2{{text-align:center;color:#d32f2f}}
    .post{{background:#fff;padding:12px;border-radius:10px;margin-bottom:15px;box-shadow:0 2px 5px rgba(0,0,0,.1)}}
    .post h3{{margin-top:0;color:#1565c0;font-size:18px}}.post p{{line-height:1.5;color:#333}}
    .open-btn{{display:inline-block;margin-top:10px;background:#00695c;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;font-size:14px}}
    </style></head><body><h2>📦 Archive Feed</h2>{posts}</body></html>
    """

# ------------------ Home ------------------
@app.route("/")
def home():
    return """
    <!DOCTYPE html><html><head>
    <meta name='viewport' content='width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no'>
    <style>
    body{font-family:'Segoe UI',Roboto,sans-serif;background:#f0f2f5;margin:0;padding:10px;text-align:center;color:#333}
    h1{font-size:22px;color:#d32f2f;margin:10px 0;border-bottom:2px solid #d32f2f;padding-bottom:5px}
    .section-header{display:flex;align-items:center;justify-content:center;margin-top:15px;font-weight:bold;font-size:14px;text-transform:uppercase;color:#555}
    .btn{display:block;width:90%;margin:10px auto;padding:15px 5px;font-size:18px;font-weight:bold;text-decoration:none;border-radius:10px;border:2px solid transparent;box-shadow:0 4px 6px rgba(0,0,0,.1)}
    .audio-btn{background:#e3f2fd;color:#1565c0;border-color:#bbdefb}.feed-btn{background:#f1f8e9;color:#2e7d32;border-color:#c8e6c9}.archive-btn{background:#fff3e0;color:#ef6c00;border-color:#ffcc80}
    .btn:focus,.btn:active{background:#ffeb3b!important;color:#000!important;border:3px solid #000!important;outline:none;transform:scale(1.02)}
    .key-hint{font-size:12px;background:rgba(0,0,0,.1);padding:2px 6px;border-radius:4px;margin-right:8px}
    </style></head><body>
    <h1>📰 വാർത്തകൾ</h1><div class='section-header'>🎧 AUDIO CONTENT</div>
    <a class='btn audio-btn' href='/static/audio/Pathravarthakal.mp3' accesskey='1'><span class='key-hint'>1</span>Pathravarthakal</a>
    <a class='btn audio-btn' href='/static/audio/DailyCa.mp3' accesskey='2'><span class='key-hint'>2</span>Daily CA</a>
    <div class='section-header'>📰 NEWS FEEDS</div>
    <a class='btn feed-btn' href='/telegram/Pathravarthakal' accesskey='3'><span class='key-hint'>3</span>Pathravarthakal Feed</a>
    <a class='btn feed-btn' href='/telegram/DailyCa' accesskey='4'><span class='key-hint'>4</span>Daily CA Feed</a>
    <div class='section-header'>📦 ARCHIVES</div>
    <a class='btn archive-btn' href='/archives' accesskey='5'><span class='key-hint'>5</span>Feed Archives</a>
    <p style='font-size:10px;color:#888;margin-top:20px'>Use Up/Down keys to navigate</p>
    </body></html>
    """

# ============================================================
# QUIZ APP
# ============================================================
@app.route("/quiz")
def quiz_app():
    html = r'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CA Blockbuster Quiz</title>
<script src="https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.14.1/firebase-auth-compat.js"></script>
<style>
*{box-sizing:border-box}body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f5f7fb;margin:0;color:#222}.container{width:min(900px,100%);margin:auto;padding:16px 16px 40px}.header{text-align:center;padding:12px 0 10px}.header h1{margin:0;color:#1565c0;font-size:32px}.header p{color:#666;margin:8px 0 0}h2{margin-top:20px}.card{background:#fff;padding:18px;margin:12px 0;border-radius:14px;box-shadow:0 2px 8px rgba(0,0,0,.09);border:1px solid #e7eaf0}.clickable{cursor:pointer;transition:transform .12s,background .12s}.clickable:hover{background:#eef6ff;transform:translateY(-1px)}.title{font-size:18px;font-weight:700}.subtitle{color:#666;margin-top:6px;line-height:1.4}.meta{color:#555;font-size:14px;margin-top:8px}.hidden{display:none!important}.topbar{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:16px}button{border:none;background:#1565c0;color:#fff;padding:11px 18px;border-radius:9px;font-size:15px;cursor:pointer}button:hover{opacity:.92}button:disabled{opacity:.65;cursor:not-allowed}.back{background:#555}.timer{font-weight:700;color:#d32f2f;font-size:17px}.question-number{color:#666;margin-bottom:8px}.question{font-size:20px;line-height:1.55;font-weight:600}.option{background:#fff;border:2px solid #d9dee7;padding:14px;margin:10px 0;border-radius:10px;cursor:pointer;line-height:1.45}.option:hover{background:#f5f9ff}.option.correct{background:#d8f3dc!important;border-color:#2e7d32}.option.wrong{background:#ffd8d8!important;border-color:#c62828}.explanation{line-height:1.5}.actions{display:flex;justify-content:flex-end;margin-top:15px}.status{padding:12px;border-radius:9px;background:#fff3cd;color:#664d03;margin:12px 0}.error{background:#ffebee;color:#b71c1c}.empty{color:#777;padding:20px 0}.score{font-size:42px;font-weight:800;color:#1565c0;text-align:center}.center{text-align:center}
.account-bar{display:flex;align-items:center;justify-content:space-between;gap:10px;background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:10px 12px;margin-bottom:12px;box-shadow:0 2px 8px rgba(0,0,0,.06)}.user-info{display:flex;align-items:center;gap:10px;min-width:0}.user-photo,.leader-photo,.leader-avatar{width:44px;height:44px;border-radius:50%;object-fit:cover;flex:0 0 44px}.leader-avatar{display:flex;align-items:center;justify-content:center;background:#e3f2fd;font-size:22px}.user-name{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.user-email{color:#777;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.google-btn{background:#fff;color:#333;border:1px solid #dadce0;font-weight:600;white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.08)}.login-status{text-align:center;font-size:12px;min-height:18px;margin:-4px 0 10px}.logout-btn{background:#f1f3f4;color:#444;font-size:13px;padding:8px 12px}.leaderboard-button{width:100%;margin-top:18px;padding:15px;border-radius:14px;background:linear-gradient(135deg,#1565c0,#42a5f5);font-size:17px;font-weight:700;box-shadow:0 4px 10px rgba(21,101,192,.22)}
#categories{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:14px}.category-card{min-height:128px;padding:18px 12px;background:#fff;border:1px solid #e5eaf2;border-radius:18px;box-shadow:0 4px 12px rgba(0,0,0,.07);display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;cursor:pointer;transition:transform .15s,box-shadow .15s,background .15s}.category-card:hover{transform:translateY(-3px);background:#f8fbff;box-shadow:0 7px 18px rgba(0,0,0,.1)}.category-icon{font-size:34px;line-height:1;margin-bottom:10px}.category-name{font-size:16px;font-weight:750;line-height:1.25}.category-tests{font-size:12px;color:#777;margin-top:6px}#testList{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}#testList .card{margin:0}.leader-row{display:flex;align-items:center;gap:12px;background:#fff;padding:13px;margin:10px 0;border-radius:15px;border:1px solid #e7eaf0;box-shadow:0 3px 10px rgba(0,0,0,.06)}.rank{width:34px;flex:0 0 34px;text-align:center;font-size:17px;font-weight:800}.leader-info{flex:1;min-width:0}.leader-name{font-weight:750;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.leader-badge{color:#777;font-size:12px;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.leader-points{color:#1565c0;font-weight:800;text-align:right;white-space:nowrap}.leader-points small{display:block;color:#777;font-size:10px;font-weight:500}@media(max-width:600px){.container{padding:12px 12px 30px}.header h1{font-size:26px}.question{font-size:18px}#categories,#testList{grid-template-columns:repeat(2,minmax(0,1fr))}.account-bar{align-items:flex-start}.google-btn,.logout-btn{padding:9px 10px}}@media(max-width:380px){#categories,#testList{grid-template-columns:1fr}}
</style></head><body>
<div class="container">
<section id="home">
<div id="accountBar" class="account-bar"><div class="user-info"><div id="accountAvatar" class="leader-avatar">👤</div><div><div id="accountName" class="user-name">Not signed in</div><div id="accountEmail" class="user-email">Sign in to your Google account</div></div></div><button id="googleLoginButton" type="button" class="google-btn">🔐 Google Login</button></div>
<div id="loginStatus" class="login-status">Initializing Google Login...</div>
<div class="header"><h1>🎯 CA Blockbuster</h1><p>Daily CA Revision</p></div><h2>Categories</h2>
<div id="categories"><div class="status">Loading...</div></div>
<button id="leaderboardButton" class="leaderboard-button" type="button">🏆 View Leaderboard</button>
</section>
<section id="tests" class="hidden"><div class="topbar"><button id="backHomeButton" class="back" type="button">← Back</button></div><h2 id="topicTitle"></h2><div id="testList"></div></section>
<section id="quiz" class="hidden"><div class="topbar"><button id="backTestsButton" class="back" type="button">← Tests</button><span id="timer" class="timer">00:00</span></div><h2 id="testTitle"></h2><div class="question-number" id="questionNumber"></div><div class="card"><div id="questionText" class="question"></div></div><div id="options"></div><div id="explanationCard" class="card hidden"><strong>Explanation</strong><div id="explanation" class="explanation"></div></div><div class="actions"><button id="nextButton" type="button">Next →</button></div></section>
<section id="result" class="hidden"><div class="header"><h1>🎉 Result</h1></div><div class="card center"><div id="scoreText" class="score"></div><p id="resultDetails"></p></div><div class="center"><button id="resultHomeButton" type="button">Back to Categories</button></div></section>
<section id="leaderboard" class="hidden"><div class="topbar"><button id="leaderboardBackButton" class="back" type="button">← Back</button></div><div class="header"><h1>🏆 Leaderboard</h1><p>Top performers</p></div><div id="leaderboardList"><div class="status">Loading leaderboard...</div></div></section>
</div>

<!-- Firebase configuration is injected by Flask. -->
<script>window.__FIREBASE_WEB_CONFIG__=__FIREBASE_CONFIG_JSON__;</script>

<!-- Google/Firebase authentication.  Redirect flow is used deliberately for Android/mobile browsers. -->
<script>
(function () {
    "use strict";

    let auth = null;
    let initialized = false;
    let initStarted = false;

    function setStatus(message, isError) {
        const el = document.getElementById("loginStatus");
        if (!el) return;
        el.textContent = message || "";
        el.style.color = isError ? "#b71c1c" : "#666";
    }

    function esc(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function updateAccount(user) {
        const avatar = document.getElementById("accountAvatar");
        const name = document.getElementById("accountName");
        const email = document.getElementById("accountEmail");
        const button = document.getElementById("googleLoginButton");
        if (!avatar || !name || !email || !button) return;

        if (user) {
            if (user.photoURL) {
                avatar.outerHTML = '<img id="accountAvatar" class="user-photo" src="' +
                    esc(user.photoURL) + '" alt="">';
            } else {
                avatar.textContent = "👤";
                avatar.className = "leader-avatar";
            }
            name.textContent = user.displayName || "Google User";
            email.textContent = user.email || "";
            button.textContent = "Logout";
            button.className = "logout-btn";
            button.disabled = false;
            setStatus("Signed in with Google.");
        } else {
            const a = document.getElementById("accountAvatar");
            if (a) {
                a.outerHTML = '<div id="accountAvatar" class="leader-avatar">👤</div>';
            }
            name.textContent = "Not signed in";
            email.textContent = "Sign in to your Google account";
            button.textContent = "🔐 Google Login";
            button.className = "google-btn";
            button.disabled = false;
            setStatus(initialized ? "Sign in with Google to continue." : "Initializing Google Login...");
        }
    }

    async function loginWithGoogle() {
        const button = document.getElementById("googleLoginButton");
        if (!auth) {
            const msg = "Google Login is not ready. " +
                "Firebase Web configuration could not be initialized.";
            console.error(msg);
            setStatus(msg, true);
            alert(msg);
            return;
        }

        try {
            button.disabled = true;
            button.textContent = "Connecting...";
            setStatus("Opening Google sign-in...");

            const provider = new firebase.auth.GoogleAuthProvider();
            provider.setCustomParameters({ prompt: "select_account" });

            // Redirect is more reliable than popups on Android Chrome/Koyeb.
            await auth.signInWithRedirect(provider);
        } catch (error) {
            console.error("[Google Login] Redirect sign-in error:", error);
            button.disabled = false;
            button.textContent = "🔐 Google Login";
            setStatus("Google Login failed: " +
                (error.message || error.code || "Unknown error"), true);
            alert("Google Login failed\n\nCode: " +
                (error.code || "unknown") + "\n\n" +
                (error.message || "Unknown error"));
        }
    }

    async function logoutGoogle() {
        if (!auth) return;
        try {
            await auth.signOut();
        } catch (error) {
            console.error("[Google Login] Logout error:", error);
            setStatus("Logout failed: " + (error.message || "Unknown error"), true);
        }
    }

    window.loginWithGoogle = loginWithGoogle;
    window.logoutGoogle = logoutGoogle;

    async function initializeGoogleAuth() {
        if (initStarted) return;
        initStarted = true;

        const button = document.getElementById("googleLoginButton");
        if (!button) {
            console.error("[Google Login] Button not found.");
            return;
        }

        button.onclick = function () {
            if (window.currentFirebaseUser) {
                logoutGoogle();
            } else {
                loginWithGoogle();
            }
        };

        try {
            setStatus("Initializing Google Login...");

            if (!window.firebase) {
                throw new Error(
                    "Firebase Web SDK did not load. Check network access to www.gstatic.com."
                );
            }

            const config = window.__FIREBASE_WEB_CONFIG__;
            if (!config || !config.apiKey || !config.authDomain || !config.projectId || !config.appId) {
                throw new Error(
                    "Firebase Web configuration is incomplete. Set FIREBASE_WEB_API_KEY, " +
                    "FIREBASE_PROJECT_ID, FIREBASE_WEB_APP_ID and the other Firebase Web variables in Koyeb."
                );
            }

            console.log("[Google Login] Firebase project:", config.projectId);

            if (!firebase.apps.length) {
                firebase.initializeApp(config);
            }

            auth = firebase.auth();
            window.firebaseAuthInstance = auth;
            window.googleLoginReady = true;

            await auth.setPersistence(firebase.auth.Auth.Persistence.LOCAL);

            auth.onAuthStateChanged(function (user) {
                window.currentFirebaseUser = user || null;
                console.log(
                    "[Google Login] Auth state:",
                    user ? user.email : "signed out",
                    user ? user.uid : ""
                );
                updateAccount(user);
            });

            initialized = true;
            setStatus("Google sign-in is ready.");

            // Complete a previous signInWithRedirect() operation.
            try {
                const result = await auth.getRedirectResult();
                if (result && result.user) {
                    console.log("[Google Login] Redirect sign-in completed:", result.user.email);
                    setStatus("Signed in with Google.");
                }
            } catch (error) {
                console.error("[Google Login] Redirect result error:", error);
                setStatus("Google Login failed: " +
                    (error.message || error.code || "Unknown error"), true);
            }
        } catch (error) {
            console.error("[Google Login] Initialization failed:", error);
            setStatus("Google Login unavailable: " +
                (error.message || "Unknown error"), true);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initializeGoogleAuth);
    } else {
        initializeGoogleAuth();
    }
})();
</script>

<!-- Main quiz script: no inline onclick handlers are required. -->
<script>
"use strict";
let allTests=[],currentTests=[],currentQuestions=[],selectedTopic="",selectedTest=null,currentQuestion=0,score=0,answered=false,timerSeconds=0,timerInterval=null,answers={},quizFinished=false;
function escapeHtml(value){return String(value??"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");}
async function apiGet(url,requireLogin=false){
 const headers={Accept:"application/json"};
 const user=window.currentFirebaseUser;
 if(requireLogin&&!user)throw new Error("Please sign in with Google first.");
 if(user){
  try{headers.Authorization="Bearer "+await user.getIdToken(true);}
  catch(e){throw new Error("Could not obtain the Firebase login token. Please sign in again.");}
 }
 const response=await fetch(url,{method:"GET",headers});
 let data;
 try{data=await response.json();}catch(e){throw new Error("Server returned an invalid response ("+response.status+")");}
 if(!response.ok)throw new Error(data.error||("Server error: "+response.status));
 return data;
}
async function loadData(){const categories=document.getElementById("categories");try{categories.innerHTML='<div class="status">Loading from Firestore...</div>';allTests=await apiGet("/quiz/api/tests");if(!Array.isArray(allTests))throw new Error("Invalid test data received");displayCategories();}catch(error){console.error("[Quiz] Load tests error:",error);categories.innerHTML='<div class="status error"><strong>Unable to load quiz.</strong><br><br>'+escapeHtml(error.message)+'<br><br>Check the Firebase service-account setting in Koyeb.</div>';}}
function displayCategories(){const container=document.getElementById("categories");container.innerHTML="";const topicIds=[...new Set(allTests.map(t=>t.topicId).filter(Boolean))];if(!topicIds.length){container.innerHTML='<div class="empty">No categories found.</div>';return;}topicIds.sort((a,b)=>String(a).localeCompare(String(b)));const icons=["📚","🌍","📰","🔬","🏛️","💡","🇮🇳","🎯"];topicIds.forEach((topicId,index)=>{const topicTests=allTests.filter(t=>t.topicId===topicId),card=document.createElement("div");card.className="category-card";card.innerHTML='<div class="category-icon">'+icons[index%icons.length]+'</div><div class="category-name">'+escapeHtml(topicId)+'</div><div class="category-tests">'+topicTests.length+' '+(topicTests.length===1?"Test":"Tests")+'</div>';card.addEventListener("click",()=>showTestsForTopic(topicId));container.appendChild(card);});}
function showTestsForTopic(topicId){selectedTopic=topicId;currentTests=allTests.filter(t=>t.topicId===topicId);document.getElementById("home").classList.add("hidden");document.getElementById("tests").classList.remove("hidden");document.getElementById("quiz").classList.add("hidden");document.getElementById("result").classList.add("hidden");document.getElementById("leaderboard").classList.add("hidden");document.getElementById("topicTitle").textContent=topicId;const container=document.getElementById("testList");container.innerHTML="";if(!currentTests.length){container.innerHTML='<div class="empty">No tests found.</div>';return;}currentTests.forEach(test=>{const card=document.createElement("div");card.className="card clickable";card.innerHTML='<div class="title">'+escapeHtml(test.title||test.id)+'</div>'+(test.subtitle?'<div class="subtitle">'+escapeHtml(test.subtitle)+'</div>':"")+'<div class="meta">'+escapeHtml(String(test.questionCount||0))+' Questions • '+escapeHtml(String(test.durationMinutes||0))+' min • '+escapeHtml(String(test.difficulty||""))+'</div>';card.addEventListener("click",()=>startQuiz(test));container.appendChild(card);});}
async function startQuiz(test){
 selectedTest=test;
 if(!window.currentFirebaseUser){
  alert("Please sign in with Google before starting a quiz.");
  return;
 }
 try{
  document.getElementById("tests").classList.add("hidden");
  document.getElementById("quiz").classList.remove("hidden");
  document.getElementById("result").classList.add("hidden");
  document.getElementById("leaderboard").classList.add("hidden");
  document.getElementById("testTitle").textContent=test.title||test.id;
  document.getElementById("questionText").textContent="Loading questions...";
  document.getElementById("options").innerHTML="";
  currentQuestions=await apiGet("/quiz/api/questions/"+encodeURIComponent(test.id),true);
  if(!Array.isArray(currentQuestions)||!currentQuestions.length)throw new Error("No questions found for this test.");
  currentQuestion=0;score=0;answered=false;answers={};quizFinished=false;
  startTimer(Number(test.durationMinutes)||0);
  displayQuestion();
 }catch(error){
  console.error("[Quiz] Start error:",error);
  document.getElementById("questionText").textContent="";
  document.getElementById("options").innerHTML='<div class="status error">'+escapeHtml(error.message)+'</div>';
 }
}
function displayQuestion(){const q=currentQuestions[currentQuestion];if(!q){finishQuiz();return;}answered=false;document.getElementById("questionNumber").textContent="Question "+(currentQuestion+1)+" / "+currentQuestions.length;document.getElementById("questionText").textContent=q.questionText||"";document.getElementById("explanationCard").classList.add("hidden");document.getElementById("explanation").textContent="";document.getElementById("nextButton").textContent=currentQuestion===currentQuestions.length-1?"Finish ✓":"Next →";const options=document.getElementById("options");options.innerHTML="";[q.option0||"",q.option1||"",q.option2||"",q.option3||""].forEach((option,index)=>{const div=document.createElement("div");div.className="option";div.textContent=option;div.addEventListener("click",()=>selectAnswer(index,div));options.appendChild(div);});}
function selectAnswer(index,element){
 if(answered)return;
 answered=true;
 const q=currentQuestions[currentQuestion];
 answers[q.id]=index;
 const correctIndex=Number(q.correctOptionIndex);
 const optionElements=document.querySelectorAll(".option");
 if(index===correctIndex){element.classList.add("correct");score++;}
 else{element.classList.add("wrong");if(optionElements[correctIndex])optionElements[correctIndex].classList.add("correct");}
 if(q.explanation){document.getElementById("explanation").textContent=q.explanation;document.getElementById("explanationCard").classList.remove("hidden");}
}
function nextQuestion(){if(!answered)return;if(currentQuestion>=currentQuestions.length-1){finishQuiz();return;}currentQuestion++;displayQuestion();}
function startTimer(durationMinutes){clearInterval(timerInterval);const hasLimit=Number(durationMinutes)>0;timerSeconds=hasLimit?Number(durationMinutes)*60:0;updateTimerDisplay();timerInterval=setInterval(()=>{if(hasLimit){timerSeconds--;updateTimerDisplay();if(timerSeconds<=0){clearInterval(timerInterval);finishQuiz();}}else{timerSeconds++;updateTimerDisplay();}},1000);}
function updateTimerDisplay(){const minutes=Math.floor(timerSeconds/60),seconds=timerSeconds%60;document.getElementById("timer").textContent="⏱ "+String(minutes).padStart(2,"0")+":"+String(seconds).padStart(2,"0");}
async function finishQuiz(){
 if(quizFinished)return;
 quizFinished=true;
 clearInterval(timerInterval);

 const total=currentQuestions.length;
 const localPercentage=total?Math.round(score/total*100):0;
 document.getElementById("quiz").classList.add("hidden");
 document.getElementById("result").classList.remove("hidden");
 document.getElementById("scoreText").textContent=score+" / "+total;
 document.getElementById("resultDetails").textContent="Saving score...";

 try{
  const user=window.currentFirebaseUser;
  if(!user)throw new Error("Google login is required to save your score.");
  const token=await user.getIdToken(true);
  const response=await fetch("/quiz/api/submit",{
   method:"POST",
   headers:{"Content-Type":"application/json","Accept":"application/json","Authorization":"Bearer "+token},
   body:JSON.stringify({testId:selectedTest.id,answers:answers})
  });
  let data;
  try{data=await response.json();}catch(e){throw new Error("Server returned an invalid response ("+response.status+")");}
  if(!response.ok)throw new Error(data.error||("Server error: "+response.status));

  score=Number(data.correct||0);
  document.getElementById("scoreText").textContent=score+" / "+Number(data.total||total);
  document.getElementById("resultDetails").textContent=
   Number(data.percentage||localPercentage)+"% correct • "+
   "⭐ "+Number(data.starsEarned||0)+" stars • "+
   "+"+Number(data.attemptPoints||0)+" points this attempt";
 }catch(error){
  console.error("[Quiz] Score submission error:",error);
  document.getElementById("resultDetails").textContent=
   "Score not saved: "+(error.message||"Unknown error");
 }
}
function showHome(){clearInterval(timerInterval);document.getElementById("home").classList.remove("hidden");document.getElementById("tests").classList.add("hidden");document.getElementById("quiz").classList.add("hidden");document.getElementById("result").classList.add("hidden");document.getElementById("leaderboard").classList.add("hidden");}
function showTests(){clearInterval(timerInterval);document.getElementById("quiz").classList.add("hidden");document.getElementById("result").classList.add("hidden");document.getElementById("leaderboard").classList.add("hidden");document.getElementById("tests").classList.remove("hidden");}
async function showLeaderboard(){clearInterval(timerInterval);document.getElementById("home").classList.add("hidden");document.getElementById("tests").classList.add("hidden");document.getElementById("quiz").classList.add("hidden");document.getElementById("result").classList.add("hidden");document.getElementById("leaderboard").classList.remove("hidden");const container=document.getElementById("leaderboardList");container.innerHTML='<div class="status">Loading leaderboard...</div>';try{const users=await apiGet("/quiz/api/leaderboard");if(!Array.isArray(users)||!users.length){container.innerHTML='<div class="empty">No leaderboard data found.</div>';return;}container.innerHTML="";users.forEach((user,index)=>{const row=document.createElement("div");row.className="leader-row";const medal=index===0?"🥇":index===1?"🥈":index===2?"🥉":String(index+1);const photo=user.profilePhotoUri?'<img class="leader-photo" src="'+escapeHtml(user.profilePhotoUri)+'" alt="">':'<div class="leader-avatar">'+escapeHtml(user.avatarEmoji||"👤")+'</div>';row.innerHTML='<div class="rank">'+medal+'</div>'+photo+'<div class="leader-info"><div class="leader-name">'+escapeHtml(user.name||"User")+'</div><div class="leader-badge">'+escapeHtml(user.badgeTitle||"")+'</div></div><div class="leader-points">'+Number(user.points||0)+'<small>points</small></div>';container.appendChild(row);});}catch(error){console.error("[Leaderboard] Error:",error);container.innerHTML='<div class="status error"><strong>Unable to load leaderboard.</strong><br><br>'+escapeHtml(error.message)+'</div>';}}

document.getElementById("backHomeButton").addEventListener("click",showHome);
document.getElementById("backTestsButton").addEventListener("click",showTests);
document.getElementById("resultHomeButton").addEventListener("click",showHome);
document.getElementById("leaderboardBackButton").addEventListener("click",showHome);
document.getElementById("leaderboardButton").addEventListener("click",showLeaderboard);
document.getElementById("nextButton").addEventListener("click",nextQuestion);
loadData();
</script>
</body></html>'''
    return html.replace("__FIREBASE_CONFIG_JSON__", json.dumps(FIREBASE_WEB_CONFIG))

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
                "durationMinutes": data.get("durationMinutes") or 0,
                "difficulty": data.get("difficulty") or "",
                "dateMillis": data.get("dateMillis"),
                "questionCount": 0
            })

        question_counts = {}
        for qdoc in db.collection("custom_questions").stream():
            qdata = qdoc.to_dict()
            test_id = qdata.get("testId")
            if test_id:
                question_counts[test_id] = question_counts.get(test_id, 0) + 1

        for test in tests:
            test["questionCount"] = question_counts.get(test["id"], 0)
        return tests
    except Exception as e:
        print(f"[Quiz Firestore tests error] {e}")
        return {"error": str(e)}, 500

@app.route("/quiz/api/questions/<path:test_id>")
def quiz_questions(test_id):
    try:
        db = get_firestore()
        docs = db.collection("custom_questions").where("testId", "==", test_id).stream()
        questions = []
        for doc in docs:
            data = doc.to_dict()
            questions.append({
                "id": data.get("id") or doc.id,
                "testId": data.get("testId") or "",
                "topicId": data.get("topicId") or "",
                "questionText": data.get("questionText") or "",
                "option0": data.get("option0") or "",
                "option1": data.get("option1") or "",
                "option2": data.get("option2") or "",
                "option3": data.get("option3") or "",
                "correctOptionIndex": data.get("correctOptionIndex", 0),
                "explanation": data.get("explanation") or "",
                "hint": data.get("hint") or ""
            })
        return questions
    except Exception as e:
        print(f"[Quiz Firestore questions error] {e}")
        return {"error": str(e)}, 500

# ------------------ QUIZ SCORE SUBMISSION ------------------

def require_firebase_user():
    """Verify the Firebase ID token supplied by the browser."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise PermissionError("Missing Firebase login token")

    token = header[7:].strip()
    if not token:
        raise PermissionError("Missing Firebase login token")

    try:
        return firebase_auth.verify_id_token(token)
    except Exception as e:
        print(f"[Firebase Auth] Token verification failed: {e}")
        raise PermissionError("Invalid or expired Firebase login token")


def calculate_stars(percentage):
    """Same star thresholds used by the Android scoring design."""
    if percentage >= 90:
        return 3
    if percentage >= 60:
        return 2
    if percentage >= 40:
        return 1
    return 0


@app.route("/quiz/api/submit", methods=["POST"])
def quiz_submit():
    try:
        user = require_firebase_user()
        payload = request.get_json(silent=True) or {}
        test_id = str(payload.get("testId") or "").strip()
        raw_answers = payload.get("answers") or {}

        if not test_id:
            return {"error": "Missing testId"}, 400
        if not isinstance(raw_answers, dict):
            return {"error": "answers must be an object"}, 400

        db = get_firestore()

        # Read the authoritative questions from Firestore.
        docs = db.collection("custom_questions").where("testId", "==", test_id).stream()
        questions = []
        for doc in docs:
            data = doc.to_dict()
            qid = str(data.get("id") or doc.id)
            try:
                correct = int(data.get("correctOptionIndex", 0))
            except (TypeError, ValueError):
                correct = 0
            questions.append((qid, correct))

        if not questions:
            return {"error": "No questions found for this test"}, 404

        correct_count = 0
        for qid, correct_index in questions:
            if qid not in raw_answers:
                continue
            try:
                selected = int(raw_answers[qid])
            except (TypeError, ValueError):
                continue
            if selected == correct_index:
                correct_count += 1

        total = len(questions)
        percentage = round((correct_count / total) * 100) if total else 0
        stars_earned = calculate_stars(percentage)
        attempt_points = correct_count * 10

        uid = str(user.get("uid"))
        email = str(user.get("email") or "")
        name = str(user.get("name") or user.get("email") or "Google User")
        picture = str(user.get("picture") or "")

        leaderboard_ref = db.collection("leaderboard").document(uid)
        transaction = db.transaction()

        @firestore.transactional
        def update_leaderboard(transaction):
            snapshot = leaderboard_ref.get(transaction=transaction)
            old = snapshot.to_dict() if snapshot.exists else {}

            total_correct = int(old.get("totalCorrect", 0) or 0) + correct_count
            attempts_count = int(old.get("attemptsCount", 0) or 0) + 1
            percentage_sum = float(old.get("percentageSum", 0) or 0) + percentage

            best_stars = dict(old.get("bestStarsByTest", {}) or {})
            old_best = int(best_stars.get(test_id, 0) or 0)
            if stars_earned > old_best:
                best_stars[test_id] = stars_earned

            total_stars = sum(int(v or 0) for v in best_stars.values())
            total_points = 420 + (total_correct * 10) + (total_stars * 40)
            average_accuracy = int(round(percentage_sum / attempts_count)) if attempts_count else 0

            badge = (
                "Master 🏆" if total_points > 1000 else
                "CA Top Aspirant 🌟" if total_points > 600 else
                "Rising Scholar 🎯"
            )

            data = {
                "uid": uid,
                "name": name,
                "email": email,
                "profilePhotoUri": picture,
                "avatarEmoji": "🎯",
                "totalCorrect": total_correct,
                "attemptsCount": attempts_count,
                "percentageSum": percentage_sum,
                "bestStarsByTest": best_stars,
                "stars": total_stars,
                "points": total_points,
                "accuracy": average_accuracy,
                "badgeTitle": badge,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            }
            transaction.set(leaderboard_ref, data, merge=True)
            return data

        updated = update_leaderboard(transaction)

        return {
            "ok": True,
            "uid": uid,
            "correct": correct_count,
            "total": total,
            "percentage": percentage,
            "starsEarned": stars_earned,
            "attemptPoints": attempt_points,
            "totalStars": int(updated.get("stars", 0)),
            "totalPoints": int(updated.get("points", 420)),
        }

    except PermissionError as e:
        return {"error": str(e)}, 401
    except Exception as e:
        print(f"[Quiz Submit Error] {e}")
        return {"error": str(e)}, 500


# ------------------ QUIZ LEADERBOARD API ------------------
@app.route("/quiz/api/leaderboard")
def quiz_leaderboard():
    try:
        db = get_firestore()
        entries = []
        for doc in db.collection("leaderboard").stream():
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
        entries.sort(key=lambda item: item["points"], reverse=True)
        return entries[:50]
    except Exception as e:
        print(f"[Quiz Firestore leaderboard error] {e}")
        return {"error": str(e)}, 500

# ------------------ Run ------------------
if __name__ == "__main__":
    print("[Startup] CA Blockbuster server starting...")
    print("[Startup] Firebase Web project:", FIREBASE_WEB_CONFIG.get("projectId"))
    print("[Startup] Firebase Web authDomain:", FIREBASE_WEB_CONFIG.get("authDomain"))
    print("[Startup] Firebase Web API key configured:", bool(FIREBASE_WEB_CONFIG.get("apiKey") and not str(FIREBASE_WEB_CONFIG.get("apiKey")).startswith("YOUR_")))
    print("[Startup] Firebase Web appId configured:", bool(FIREBASE_WEB_CONFIG.get("appId") and not str(FIREBASE_WEB_CONFIG.get("appId")).startswith("YOUR_")))

    threading.Thread(target=telegram_updater, daemon=True).start()
    threading.Thread(target=audio_updater, daemon=True).start()

    app.run(host="0.0.0.0", port=8000)