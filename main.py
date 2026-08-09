import os
import time
import feedparser
import threading
import requests
import re
import shutil
from datetime import datetime
from flask import Flask, request, jsonify, session
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import json
from gtts import gTTS

import firebase_admin
from firebase_admin import credentials, firestore, auth

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-key")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

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
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not configured")

    try:
        service_account_info = json.loads(firebase_json)
    except json.JSONDecodeError as e:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON") from e

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(service_account_info))

    _firestore_db = firestore.client()
    return _firestore_db

# ============================================================
# CONFIG
# ============================================================

AUDIO_FOLDER = "static/audio"
XML_FOLDER = "telegram_xml"
ARCHIVE_FOLDER = "archive"

TELEGRAM_CHANNELS = {
    "Pathravarthakal": "https://t.me/s/Pathravarthakal",
    "DailyCa": "https://t.me/s/DailyCAMalayalam",
}

os.makedirs(AUDIO_FOLDER, exist_ok=True)
os.makedirs(XML_FOLDER, exist_ok=True)
os.makedirs(ARCHIVE_FOLDER, exist_ok=True)

# ============================================================
# QUIZ AUTHENTICATION
# ============================================================

def firebase_web_api_key():
    key = os.environ.get("FIREBASE_WEB_API_KEY")
    if not key:
        raise RuntimeError("FIREBASE_WEB_API_KEY is not configured")
    return key

def firebase_auth_request(endpoint, payload):
    url = f"https://identitytoolkit.googleapis.com/v1/{endpoint}?key={firebase_web_api_key()}"
    response = requests.post(url, json=payload, timeout=15)
    try:
        data = response.json()
    except Exception:
        data = {}
    if not response.ok:
        message = data.get("error", {}).get("message", "Authentication failed")
        messages = {
            "INVALID_LOGIN_CREDENTIALS": "Invalid email or password.",
            "EMAIL_EXISTS": "An account with this email already exists.",
            "INVALID_EMAIL": "Please enter a valid email address.",
            "WEAK_PASSWORD : Password should be at least 6 characters": "Password must be at least 6 characters.",
            "WEAK_PASSWORD": "Password must be at least 6 characters.",
            "EMAIL_NOT_FOUND": "No account was found with this email.",
            "USER_DISABLED": "This account has been disabled.",
        }
        raise RuntimeError(messages.get(message, message.replace("_", " ").title()))
    return data

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return {"uid": uid, "email": session.get("email", ""), "name": session.get("name", "")}

def require_quiz_login():
    user = current_user()
    if not user:
        return None, (jsonify({"error": "Authentication required"}), 401)
    return user, None

# ============================================================
# TELEGRAM FEED
# ============================================================

def archive_feed(xml_path):
    try:
        if not os.path.exists(xml_path):
            return
        month_folder = datetime.now().strftime("%Y-%m")
        archive_dir = os.path.join(ARCHIVE_FOLDER, month_folder)
        os.makedirs(archive_dir, exist_ok=True)
        archive_path = os.path.join(archive_dir, os.path.basename(xml_path))
        shutil.copy2(xml_path, archive_path)
        print("[Feed Archived]", archive_path)
    except Exception as e:
        print("[Archive Error]", e)

def fetch_telegram_xml(name, url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        rss_root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss_root, "channel")
        ET.SubElement(channel, "title").text = f"{name} Telegram Feed"

        for msg in soup.select(".tgme_widget_message_wrap")[:80]:
            date_tag = msg.select_one("a.tgme_widget_message_date")
            link = date_tag.get("href", url) if date_tag else url
            text_tag = msg.select_one(".tgme_widget_message_text")
            desc_html = text_tag.decode_contents() if text_tag else ""
            clean_text = BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)

            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = clean_text[:100]
            ET.SubElement(item, "link").text = link
            ET.SubElement(item, "description").text = clean_text

        xml_path = os.path.join(XML_FOLDER, f"{name}.xml")
        ET.ElementTree(rss_root).write(xml_path, encoding="utf-8", xml_declaration=True)
        archive_feed(xml_path)
        print("[Feed Updated]", name)
    except Exception as e:
        print("[Telegram Error]", name, e)

def telegram_updater():
    while True:
        for name, url in TELEGRAM_CHANNELS.items():
            fetch_telegram_xml(name, url)
        time.sleep(600)

# ============================================================
# AUDIO
# ============================================================

def generate_audio_from_feed(channel_name):
    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")
    if not os.path.exists(path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])

    feed = feedparser.parse(path)
    entries = list(feed.entries)[-25:]
    full_text = "ഇന്നത്തെ പ്രധാന വാർത്തകൾ.\n\n"

    for entry in entries:
        text = entry.get("description", "")
        text = re.sub(r"[\U0001F300-\U0001FAFF\U0001F600-\U0001F64F\u2600-\u27BF\uFE0F\u200D]", " ", text)
        text = re.sub(r"#\w+|http\S+|@\w+", "", text)
        text = re.sub(r"(join\s*@\w+.*)$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"[!?:;]+", ". ", text)
        text = re.sub(r"[\"'(){}\[\]<>]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 5:
            text = entry.get("title", "")
        if text:
            full_text += text + ".\n\n"

    if len(full_text.strip()) < 10:
        full_text = "ഇന്ന് വാർത്തകൾ ലഭ്യമല്ല."

    try:
        output_path = os.path.join(AUDIO_FOLDER, f"{channel_name}.mp3")
        gTTS(full_text, lang="ml").save(output_path)
        print("[Audio Updated]", channel_name)
    except Exception as e:
        print("[TTS Error]", e)

def audio_updater():
    while True:
        for name in TELEGRAM_CHANNELS:
            generate_audio_from_feed(name)
        time.sleep(600)

# ============================================================
# TELEGRAM PAGES
# ============================================================

@app.route("/telegram/<channel_name>")
def telegram_html(channel_name):
    if channel_name not in TELEGRAM_CHANNELS:
        return "Invalid channel", 404

    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")
    if request.args.get("refresh") == "1":
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])
    if not os.path.exists(path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])

    feed = feedparser.parse(path)
    posts = ""
    for entry in list(feed.entries)[::-1][:50]:
        posts += f"<div class='post-card'><p>{entry.get('description','')}</p></div>"

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:system-ui;background:#f5f7fb;margin:0;padding:16px}}
.header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}}
.btn{{background:linear-gradient(135deg,#00695c,#004d40);color:white;padding:10px 14px;border-radius:12px;text-decoration:none;font-weight:600;box-shadow:0 4px 10px rgba(0,105,92,.3)}}
.post-card{{background:white;padding:14px;border-radius:14px;margin-bottom:12px;box-shadow:0 2px 8px rgba(0,0,0,.05)}}
</style>
</head>
<body>
<div class="header"><h2>{channel_name}</h2><a class="btn" href="?refresh=1">🔄 Refresh</a></div>
{posts}
</body>
</html>
"""

# ============================================================
# ARCHIVES
# ============================================================

@app.route("/archives")
def archives():
    months = sorted(os.listdir(ARCHIVE_FOLDER), reverse=True) if os.path.exists(ARCHIVE_FOLDER) else []
    html = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>body{font-family:system-ui;padding:16px;background:#f5f7fb}.card{background:white;padding:16px;border-radius:16px;margin-bottom:16px;box-shadow:0 4px 12px rgba(0,0,0,.05)}.file{display:block;padding:10px;margin-top:8px;background:#e3f2fd;border-radius:10px;text-decoration:none;color:#1565c0;font-weight:500}</style></head><body><h2>📦 Feed Archives</h2>"""
    if not months: html += "<p>No archives found.</p>"
    for month in months:
        month_path = os.path.join(ARCHIVE_FOLDER, month)
        if not os.path.isdir(month_path): continue
        html += f"<div class='card'><h3>{month}</h3>"
        for filename in os.listdir(month_path):
            html += f"<a class='file' href='/archive/{month}/{filename}'>{filename}</a>"
        html += "</div>"
    html += "</body></html>"
    return html

@app.route("/archive/<month>/<filename>")
def archive_file(month, filename):
    archive_path = os.path.join(ARCHIVE_FOLDER, month, filename)
    if not os.path.exists(archive_path): return "Archive not found", 404
    feed = feedparser.parse(archive_path)
    posts = ""
    for entry in list(feed.entries)[::-1][:100]:
        posts += f"<div class='post'><h3>{entry.get('title','')}</h3><p>{entry.get('description','')}</p><a href='{entry.get('link','#')}' target='_blank'>Open Source</a></div>"
    return f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>body{{font-family:system-ui;padding:16px;background:#f5f7fb}}.post{{background:white;padding:16px;border-radius:16px;margin-bottom:16px;box-shadow:0 4px 12px rgba(0,0,0,.05)}}</style></head><body><h2>📦 Archive Feed</h2>{posts}</body></html>"""

# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    return """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui;background:linear-gradient(135deg,#667eea,#764ba2);margin:0;padding:20px;color:#333;text-align:center}
h1{color:white;font-size:28px;margin-bottom:20px}
.section{color:white;font-weight:700;margin:20px 0 10px;font-size:14px;letter-spacing:.5px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
.btn{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px;font-size:16px;font-weight:700;text-decoration:none;border-radius:18px;background:white;box-shadow:0 8px 20px rgba(0,0,0,.15);transition:.2s}
.btn:active{transform:scale(.97)}
.icon{font-size:28px;margin-bottom:6px}
.audio{color:#1565c0}
.feed{color:#2e7d32}
.archive{color:#ef6c00}
</style>
</head>
<body>
<h1>📰 വാർത്തകൾ</h1>
<div class="section">🎧 AUDIO</div>
<div class="grid">
<a class="btn audio" href="/static/audio/Pathravarthakal.mp3"><div class="icon">🎙️</div>Pathravarthakal</a>
<a class="btn audio" href="/static/audio/DailyCa.mp3"><div class="icon">🎙️</div>Daily CA</a>
</div>
<div class="section">📰 NEWS FEEDS</div>
<div class="grid">
<a class="btn feed" href="/telegram/Pathravarthakal"><div class="icon">📰</div>Pathravarthakal</a>
<a class="btn feed" href="/telegram/DailyCa"><div class="icon">📰</div>Daily CA</a>
</div>
<div class="section">📦 ARCHIVES</div>
<a class="btn archive" href="/archives"><div class="icon">📦</div>Feed Archives</a>
</body>
</html>
"""

# ============================================================
# QUIZ AUTH API
# ============================================================

@app.route("/quiz/api/auth/me")
def quiz_auth_me():
    user = current_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({"authenticated": True, **user})

@app.route("/quiz/api/auth/login", methods=["POST"])
def quiz_auth_login():
    try:
        data = request.get_json(silent=True) or {}
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if not email or not password:
            return jsonify({"error": "Email and password are required."}), 400
        result = firebase_auth_request("accounts:signInWithPassword", {
            "email": email, "password": password, "returnSecureToken": True
        })
        decoded = auth.verify_id_token(result["idToken"])
        session.clear()
        session.permanent = True
        session["uid"] = decoded["uid"]
        session["email"] = decoded.get("email", email)
        session["name"] = decoded.get("name", "")
        return jsonify({"authenticated": True, "uid": session["uid"], "email": session["email"]})
    except Exception as e:
        print("[Quiz Login Error]", e)
        return jsonify({"error": str(e)}), 401

@app.route("/quiz/api/auth/signup", methods=["POST"])
def quiz_auth_signup():
    try:
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if not name or not email or not password:
            return jsonify({"error": "Name, email and password are required."}), 400
        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters."}), 400
        result = firebase_auth_request("accounts:signUp", {
            "email": email, "password": password, "returnSecureToken": True
        })
        uid = result["localId"]
        try:
            auth.update_user(uid, display_name=name)
        except Exception as e:
            print("[Quiz Auth profile update warning]", e)
        db = get_firestore()
        db.collection("leaderboard").document(uid).set({
            "uid": uid, "email": email, "name": name, "points": 0,
            "accuracy": 0, "stars": 0, "badgeTitle": "New Aspirant",
            "avatarEmoji": "👤", "profilePhotoUri": "", "testsCompleted": 0,
            "totalQuestions": 0, "totalCorrect": 0, "bestStreak": 0,
            "createdAt": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        decoded = auth.verify_id_token(result["idToken"])
        session.clear(); session.permanent = True
        session["uid"] = uid; session["email"] = decoded.get("email", email); session["name"] = name
        return jsonify({"authenticated": True, "uid": uid, "email": email, "name": name})
    except Exception as e:
        print("[Quiz Signup Error]", e)
        return jsonify({"error": str(e)}), 400

@app.route("/quiz/api/auth/forgot", methods=["POST"])
def quiz_auth_forgot():
    try:
        data = request.get_json(silent=True) or {}
        email = str(data.get("email", "")).strip().lower()
        if not email:
            return jsonify({"error": "Email is required."}), 400
        firebase_auth_request("accounts:sendOobCode", {"requestType": "PASSWORD_RESET", "email": email})
        return jsonify({"success": True, "message": "Password reset link sent. Check your email."})
    except Exception as e:
        print("[Quiz Forgot Password Error]", e)
        return jsonify({"error": str(e)}), 400

@app.route("/quiz/api/auth/logout", methods=["POST"])
def quiz_auth_logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/quiz/api/result", methods=["POST"])
def quiz_save_result():
    user, error = require_quiz_login()
    if error:
        return error
    try:
        data = request.get_json(silent=True) or {}
        test_id = str(data.get("testId", ""))
        correct = max(0, int(data.get("correct", 0) or 0))
        wrong = max(0, int(data.get("wrong", 0) or 0))
        unanswered = max(0, int(data.get("unanswered", 0) or 0))
        gained_points = max(0, int(data.get("points", 0) or 0))
        accuracy = float(data.get("accuracy", 0) or 0)
        best_streak = max(0, int(data.get("bestStreak", 0) or 0))
        total = correct + wrong + unanswered
        db = get_firestore()
        ref = db.collection("leaderboard").document(user["uid"])
        snap = ref.get()
        old = snap.to_dict() if snap.exists else {}
        old_total_q = int(old.get("totalQuestions", 0) or 0)
        old_correct = int(old.get("totalCorrect", 0) or 0)
        total_q = old_total_q + total
        total_correct = old_correct + correct
        cumulative_accuracy = (total_correct / total_q * 100) if total_q else 0
        old_stars = int(old.get("stars", 0) or 0)
        stars_earned = 3 if accuracy >= 90 else 2 if accuracy >= 75 else 1 if accuracy >= 50 else 0
        new_stars = old_stars + stars_earned
        old_points = int(old.get("points", 0) or 0)
        new_points = old_points + gained_points
        old_tests = int(old.get("testsCompleted", 0) or 0)
        old_best = int(old.get("bestStreak", 0) or 0)
        badge = "Rising Scholar 🎯" if new_points >= 250 else "Active Aspirant" if old_tests >= 5 else "New Aspirant"
        ref.set({
            "uid": user["uid"], "email": user["email"], "name": user.get("name") or old.get("name") or "Aspirant",
            "points": new_points, "accuracy": round(cumulative_accuracy, 2), "stars": new_stars,
            "badgeTitle": badge, "testsCompleted": old_tests + 1, "totalQuestions": total_q,
            "totalCorrect": total_correct, "bestStreak": max(old_best, best_streak),
            "lastTestId": test_id, "lastScore": correct, "lastWrong": wrong,
            "lastUnanswered": unanswered, "lastAccuracy": round(accuracy, 2),
            "updatedAt": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        return jsonify({"success": True, "points": new_points, "stars": new_stars, "accuracy": round(cumulative_accuracy, 2), "rank": None})
    except Exception as e:
        print("[Quiz Result Save Error]", e)
        return jsonify({"error": str(e)}), 400

# ============================================================
# QUIZ PAGE - ATTRACTIVE UI
# ============================================================
@app.route("/quiz")
def quiz_app():
    html = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CA Blockbuster Quiz</title>
<style>
*{box-sizing:border-box}
:root{--bg:#0b1328;--panel:#18233a;--panel2:#202b43;--primary:#4b3cc4;--primary2:#7378f5;--text:#f7f7fb;--muted:#aeb6cb;--gold:#ffd21c}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);margin:0;color:var(--text);min-height:100vh}
.container{max-width:900px;margin:auto;padding:12px}.hidden{display:none!important}
.header{display:flex;justify-content:space-between;align-items:center;padding:12px 0 18px;color:white}.header h1{margin:0;font-size:21px;line-height:1.2}.header p{margin:7px 0 0;color:#b9bfd0;font-size:12px}
.headerBrand{display:flex;align-items:center;gap:10px}.brandIcon{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#4134b9;font-size:20px}
.leaderboard-icon-btn{background:transparent;border:0;box-shadow:none;padding:7px;cursor:pointer;color:#aeb6cb;font-size:23px}.leaderboard-icon{font-size:22px}
.globalRankCard{display:flex;align-items:center;gap:15px;background:linear-gradient(105deg,#11213c,#302681);border-radius:28px;padding:18px 20px;margin:4px 0 14px;cursor:pointer;box-shadow:0 12px 30px rgba(0,0,0,.18)}
.rankTrophy{width:52px;height:52px;border-radius:50%;background:rgba(255,205,45,.17);display:flex;align-items:center;justify-content:center;font-size:28px;flex:0 0 auto}.globalRankCard h2{margin:0;font-size:19px}.globalRankCard p{margin:5px 0 0;color:#aeb6cb;font-size:12px}.rankArrow{margin-left:auto;font-size:28px;color:#9ca6c2}
.sectionTitle{font-size:18px;margin:20px 0 12px}
.card{background:var(--panel2);color:var(--text);padding:18px;border-radius:20px;border:1px solid rgba(255,255,255,.04);box-shadow:0 8px 24px rgba(0,0,0,.16)}
#categories,#testList{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.category,.test{background:var(--panel);padding:18px;border-radius:17px;box-shadow:0 4px 12px rgba(0,0,0,.12);cursor:pointer;transition:.2s;text-align:center;color:white}.category:active,.test:active{transform:scale(.97)}
.icon{font-size:32px;margin-bottom:8px}.title{font-weight:700;font-size:16px;color:#f6f7fb}.meta{font-size:12px;color:#9ea8bd;margin-top:6px}
button{border:0;border-radius:13px;padding:12px 18px;background:linear-gradient(135deg,#5141ce,#3830a8);color:white;font-size:15px;font-weight:700;cursor:pointer;box-shadow:0 4px 12px rgba(54,48,168,.25)}button:active{transform:scale(.97)}.back{background:#3a3c4b;box-shadow:none}
.option{background:#1c2940;border:2px solid #2d3951;color:#f4f5fa;padding:15px;margin:11px 0;border-radius:14px;cursor:pointer;font-weight:500;transition:.2s}.option:active{transform:scale(.99)}.option.correct{background:#183b2b;border-color:#39a66a}.option.wrong{background:#48272d;border-color:#d75b68}
.question{font-size:19px;font-weight:700;line-height:1.5;color:#fff}.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}.timer{font-weight:700;color:#ff8793;font-size:16px}
.score{font-size:48px;font-weight:800;text-align:center;color:#7d83ff}.resultHero{text-align:center;padding:8px 4px 18px}.resultHero .score{font-size:56px;margin:4px 0}.grade{display:inline-block;padding:7px 14px;border-radius:999px;background:#302c76;color:#d6d5ff;font-weight:800;font-size:17px}
.resultGrid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:16px 0}.resultStat{background:#18243b;border-radius:14px;padding:14px;text-align:center}.resultStat .value{font-size:23px;font-weight:800}.resultStat .label{font-size:11px;color:#9fa8bd;margin-top:3px}.resultStat.good .value{color:#55d486}.resultStat.bad .value{color:#ff7180}.resultStat.neutral .value{color:#9298ff}
.progressWrap{height:10px;background:#303951;border-radius:999px;overflow:hidden;margin:14px 0}.progressBar{height:100%;width:0;background:linear-gradient(90deg,#6255e7,#8b91ff);border-radius:999px;transition:.5s}.performance{font-size:13px;line-height:1.6;color:#b9bfd0;text-align:center}
.review{margin-top:14px}.reviewItem{background:#18243b;color:#fff;padding:12px;border-radius:14px;margin:9px 0;border-left:5px solid #777}.reviewItem.correct{border-left-color:#3bc477}.reviewItem.wrong{border-left-color:#ef6372}.reviewItem.unanswered{border-left-color:#eebc35}.reviewQ{font-weight:700;font-size:14px}.reviewA{font-size:13px;color:#aeb6cb;margin-top:5px}
.status{padding:14px;background:#2b2b21;color:#e8dfad;border-radius:14px;margin:12px 0;font-size:14px}.error{background:#402329;color:#ffb5bd}
.rankPage{padding-bottom:30px}.rankHeader{display:flex;align-items:flex-start;gap:12px;padding:5px 0 18px}.rankBack{background:transparent;border:0;box-shadow:none;padding:0;font-size:30px;line-height:1;color:#fff}.rankHeader h1{margin:0;font-size:21px}.rankHeader p{margin:6px 0 0;color:#aeb6cb;font-size:12px}
.myRankCard{background:linear-gradient(135deg,#7075ef,#8a8ef9);border-radius:24px;padding:18px;margin-bottom:18px}.myRankTop{display:flex;align-items:center;gap:11px}.avatar{width:48px;height:48px;border-radius:50%;object-fit:cover;display:flex;align-items:center;justify-content:center;background:#536072;color:#fff;font-size:20px;font-weight:800;flex:0 0 auto;overflow:hidden}.avatar img{width:100%;height:100%;object-fit:cover}
.myRankName{font-size:17px;font-weight:800;display:flex;align-items:center;gap:7px;min-width:0}.badge{font-size:10px;background:rgba(255,255,255,.2);padding:6px 8px;border-radius:8px;white-space:nowrap}.myRankRole{font-size:12px;color:#e2e3ff;margin-top:4px}
.rankNumber{margin-left:auto;background:#fff;color:#6b70e9;border-radius:15px;padding:9px 14px;text-align:center;min-width:62px}.rankNumber small{display:block;font-size:9px;font-weight:700;color:#74789a}.rankNumber strong{font-size:22px}
.rankStats{display:grid;grid-template-columns:repeat(3,1fr);background:rgba(255,255,255,.12);border-radius:14px;margin-top:16px;padding:11px 4px}.rankStat{text-align:center;border-right:1px solid rgba(255,255,255,.18)}.rankStat:last-child{border-right:0}.rankStat .rsLabel{font-size:9px;color:#e0e1ff;font-weight:700;letter-spacing:.4px}.rankStat .rsValue{font-size:17px;font-weight:800;margin-top:7px}
.rankSectionTitle{font-size:18px;font-weight:800;margin:18px 0 12px}.topThree{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;align-items:end}.podium{background:#4b4754;border-radius:16px 16px 12px 12px;padding:10px 6px 9px;text-align:center;min-width:0}.podium.first{padding-top:14px;background:#4e4a58}.podium .medal{font-size:22px}.podium .podiumAvatar{margin:4px auto 6px}.podiumName{font-size:12px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.podiumRole{font-size:9px;color:#bcb9c6;margin-top:5px}.podiumPoints{display:inline-block;margin-top:8px;padding:6px 9px;background:#d8d6d9;color:#222;border-radius:12px;font-size:11px;font-weight:800}.podium.first .podiumPoints{background:#ffe329}
.stateHeader{display:flex;align-items:center;justify-content:space-between;margin:30px 0 10px}.stateHeader h2{margin:0;font-size:18px}.aspirantCount{background:#9a4d16;padding:7px 11px;border-radius:13px;font-size:11px;font-weight:800}
.rankRows{display:flex;flex-direction:column;gap:8px}.rankRow{display:flex;align-items:center;gap:10px;background:#18243b;padding:11px;border-radius:14px}.rankPos{width:28px;text-align:center;font-weight:800;color:#9fa8bd}.rankRow .avatar{width:38px;height:38px;font-size:16px}.rankRowMain{min-width:0}.rankRowName{font-size:13px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.rankRowSub{font-size:10px;color:#9fa8bd;margin-top:3px}.rankRowPoints{margin-left:auto;font-size:12px;font-weight:800;color:#9298ff;white-space:nowrap}
/* Login */
.loginScreen{min-height:calc(100vh - 24px);display:flex;align-items:flex-start;justify-content:center;padding:24px 12px 40px;background:#fff;color:#18304d;margin:0 -12px}.loginBox{width:100%;max-width:330px;margin-top:0}.loginBox h1,.loginBox .loginSubtitle{display:none}.formGroup{margin-bottom:22px}.formGroup label{display:block;color:#1d3654;font-weight:700;font-size:14px;margin-bottom:10px}.formGroup label .required{color:#e53935}.inputWrap{position:relative}.formInput{width:100%;height:41px;border:1px solid #c9d0d9;border-radius:0;padding:0 12px;font-size:14px;color:#18304d;outline:none;background:#fff}.formInput:focus{border-color:#278bd1;box-shadow:0 0 0 2px rgba(39,139,209,.08)}.passwordInput{padding-right:42px}.togglePassword{position:absolute;right:7px;top:50%;transform:translateY(-50%);border:0;background:transparent;box-shadow:none;color:#7d8792;padding:4px;font-size:15px;cursor:pointer}.loginButton{width:100%;height:48px;border-radius:0;background:linear-gradient(100deg,#0e86bd,#4a92df);font-size:16px;box-shadow:0 8px 16px rgba(28,130,194,.2);margin-top:1px}.loginLinks{margin-top:24px;padding-top:22px;border-top:1px solid #eee;text-align:center}.loginLinks p{margin:0 0 12px;color:#68788b;font-size:14px}.loginLinks a{color:#0072b8;text-decoration:none;font-weight:700;cursor:pointer}.loginError{display:none;background:#fff0f0;color:#c62828;border:1px solid #ffcdd2;padding:10px 12px;margin:0 0 15px;font-size:13px;border-radius:3px}.loginSuccess{display:none;background:#eef8f1;color:#267342;border:1px solid #c9e8d2;padding:10px 12px;margin:0 0 15px;font-size:13px;border-radius:3px}.loginLoading{opacity:.65;pointer-events:none}.logoutButton{background:#303449;box-shadow:none;padding:8px 12px;font-size:12px}
@media(max-width:500px){#categories,#testList{grid-template-columns:repeat(2,1fr)}.question{font-size:18px}.container{padding:10px 12px}}
@media(max-width:360px){#categories,#testList{grid-template-columns:1fr}.rankStat .rsLabel{font-size:8px}.rankStat .rsValue{font-size:15px}}
</style>
</head>
<body>
<div class="container">

<section id="login" class="loginScreen">
  <div class="loginBox">

    <div id="loginError" class="loginError"></div>
    <div id="loginSuccess" class="loginSuccess"></div>
    <form id="loginForm" autocomplete="on">
      <div class="formGroup">
        <label for="loginEmail"><span class="required">*</span> Email</label>
        <div class="inputWrap"><input id="loginEmail" class="formInput" type="email" autocomplete="email" placeholder="Enter your email" required></div>
      </div>
      <div class="formGroup">
        <label for="loginPassword"><span class="required">*</span> Password</label>
        <div class="inputWrap"><input id="loginPassword" class="formInput passwordInput" type="password" autocomplete="current-password" placeholder="Enter your password" required><button type="button" id="togglePassword" class="togglePassword" aria-label="Show password">◉</button></div>
      </div>
      <button id="loginButton" class="loginButton" type="submit">Sign In</button>
    </form>
    <div class="loginLinks">
      <p>Don't have an account? <a id="signupLink">Sign Up</a></p>
      <p><a id="forgotLink">Forgot your password?</a></p>
    </div>
  </div>
</section>

<section id="signup" class="loginScreen hidden">
  <div class="loginBox">
    <h1>Create Account</h1>
    <p class="loginSubtitle">Create your CA Blockbuster aspirant account</p>
    <div id="signupError" class="loginError"></div>
    <form id="signupForm" autocomplete="on">
      <div class="formGroup"><label for="signupName"><span class="required">*</span> Name</label><div class="inputWrap"><input id="signupName" class="formInput" type="text" autocomplete="name" placeholder="Enter your name" required></div></div>
      <div class="formGroup"><label for="signupEmail"><span class="required">*</span> Email</label><div class="inputWrap"><input id="signupEmail" class="formInput" type="email" autocomplete="email" placeholder="Enter your email" required></div></div>
      <div class="formGroup"><label for="signupPassword"><span class="required">*</span> Password</label><div class="inputWrap"><input id="signupPassword" class="formInput passwordInput" type="password" autocomplete="new-password" placeholder="Minimum 6 characters" minlength="6" required></div></div>
      <button class="loginButton" type="submit">Sign Up</button>
    </form>
    <div class="loginLinks"><p>Already have an account? <a id="backToLoginLink">Sign In</a></p></div>
  </div>
</section>

<section id="forgot" class="loginScreen hidden">
  <div class="loginBox">
    <h1>Reset Password</h1>
    <p class="loginSubtitle">We'll send a password reset link to your email</p>
    <div id="forgotError" class="loginError"></div><div id="forgotSuccess" class="loginSuccess"></div>
    <form id="forgotForm"><div class="formGroup"><label for="forgotEmail"><span class="required">*</span> Email</label><div class="inputWrap"><input id="forgotEmail" class="formInput" type="email" placeholder="Enter your email" required></div></div><button class="loginButton" type="submit">Send Reset Link</button></form>
    <div class="loginLinks"><p><a id="forgotBackLink">← Back to Sign In</a></p></div>
  </div>
</section>

<section id="home" class="hidden">
<div class="header">
  <div class="headerBrand"><div class="brandIcon">✦</div><div><h1>CA Blockbuster</h1><p>CA Revision</p></div></div>
  <div style="display:flex;align-items:center;gap:5px"><button class="leaderboard-icon-btn" id="leaderboardButton" aria-label="Global Rank List">⇥</button><button class="logoutButton" id="logoutButton">Logout</button></div>
</div>
<div class="globalRankCard" id="globalRankCard">
  <div class="rankTrophy">🏆</div><div><h2>Global Rank List</h2><p>See your standing in the community</p></div><div class="rankArrow">›</div>
</div>
<h2 class="sectionTitle">Categories</h2>
<div id="categories"><div class="status">Loading...</div></div>
</section>

<section id="tests" class="hidden">
<div class="topbar"><button id="backHomeButton" class="back">← Back</button></div>
<h2 id="topicTitle" style="color:white"></h2>
<div id="testList"></div>
</section>

<section id="quiz" class="hidden">
<div class="topbar"><button id="backTestsButton" class="back">← Tests</button><span id="timer" class="timer">00:00</span></div>
<h2 id="testTitle" style="color:white"></h2>
<div id="questionNumber" style="color:white;opacity:.9"></div>
<div class="card"><div id="questionText" class="question"></div></div>
<div id="options"></div>
<div id="explanationCard" class="card hidden"><b>Explanation</b><div id="explanation"></div></div>
<div style="text-align:right"><button id="nextButton">Next →</button></div>
</section>

<section id="result" class="hidden">
<div class="header"><h1>🎉 Result</h1></div>
<div class="card">
  <div class="resultHero">
    <div id="scoreText" class="score"></div>
    <div id="gradeText" class="grade"></div>
    <div id="resultDetails" class="performance"></div>
    <div class="progressWrap"><div id="resultProgress" class="progressBar"></div></div>
  </div>
  <div class="resultGrid">
    <div class="resultStat good"><div id="correctStat" class="value">0</div><div class="label">Correct</div></div>
    <div class="resultStat bad"><div id="wrongStat" class="value">0</div><div class="label">Wrong</div></div>
    <div class="resultStat neutral"><div id="unansweredStat" class="value">0</div><div class="label">Unanswered</div></div>
    <div class="resultStat neutral"><div id="pointsStat" class="value">0</div><div class="label">Points</div></div>
    <div class="resultStat neutral"><div id="accuracyStat" class="value">0%</div><div class="label">Accuracy</div></div>
    <div class="resultStat neutral"><div id="timeStat" class="value">00:00</div><div class="label">Time Used</div></div>
    <div class="resultStat neutral"><div id="avgTimeStat" class="value">0s</div><div class="label">Avg / Question</div></div>
    <div class="resultStat neutral"><div id="streakStat" class="value">0</div><div class="label">Best Streak</div></div>
  </div>
  <div id="performanceText" class="performance"></div>
  <div id="review" class="review"></div>
</div>
<div style="display:flex;gap:10px;margin-top:12px">
  <button id="resultHomeButton" style="flex:1">Back to Categories</button>
  <button id="resultTestsButton" class="back" style="flex:1">More Tests</button>
</div>
</section>

<section id="leaderboard" class="hidden">
<div class="rankPage">
  <div class="rankHeader"><button id="leaderboardBackButton" class="rankBack">‹</button><div><h1>Rank Board 🏆</h1><p>Aspirant Rankings &amp; Standings</p></div></div>
  <div id="myRankCard"></div>
  <div class="rankSectionTitle">Top 3 Rankers</div>
  <div id="topThree" class="topThree"></div>
  <div class="stateHeader"><h2>Global Rank List</h2><span id="aspirantCount" class="aspirantCount">0 Aspirants</span></div>
  <div id="rankRows" class="rankRows"></div>
</div>
</section>
</div>

<script>
"use strict";
let allTests = [];
let currentTests = [];
let currentQuestions = [];
let selectedTopic = "";
let selectedTest = null;
let currentQuestion = 0;
let score = 0;
let correctCount = 0;
let wrongCount = 0;
let unansweredCount = 0;
let questionResults = [];
let answered = false;
let timerSeconds = 0;
let elapsedSeconds = 0;
let timerInterval = null;
let quizStartTime = 0;
let points = 0;
let streak = 0;
let maxStreak = 0;
function esc(value){return String(value?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");}
async function apiGet(url){const response = await fetch(url,{method:"GET",headers:{Accept:"application/json"}});let data;try{data = await response.json();}catch(error){throw new Error("Server returned invalid JSON (" + response.status + ")");}if(!response.ok){throw new Error(data.error || "Server error: " + response.status);}return data;}
async function loadData(){const container = document.getElementById("categories");try{container.innerHTML = '<div class="status">Loading from Firestore...</div>';allTests = await apiGet("/quiz/api/tests");if(!Array.isArray(allTests)){throw new Error("Invalid test data received.");}displayCategories();}catch(error){console.error("[Quiz]",error);container.innerHTML = '<div class="status error">' + esc(error.message) + '</div>';}}
function displayCategories(){const container = document.getElementById("categories");container.innerHTML = "";const topicIds = [...new Set(allTests.map(test => test.topicId).filter(Boolean))];if(!topicIds.length){container.innerHTML = '<div class="status">No categories found.</div>';return;}topicIds.sort((a,b) => String(a).localeCompare(String(b)));const icons = ["📚","🌍","📰","🔬","🏛️","💡","🇮🇳","🎯"];topicIds.forEach((topicId,index) => {const tests = allTests.filter(test => test.topicId === topicId);const prettyName = topicId.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());const card = document.createElement("div");card.className = "category";card.innerHTML = '<div class="icon">' + icons[index % icons.length] + '</div><div class="title">' + esc(prettyName) + '</div><div class="meta">' + tests.length + ' Tests</div>';card.addEventListener("click",() => showTestsForTopic(topicId));container.appendChild(card);});}
function showTestsForTopic(topicId){selectedTopic = topicId;currentTests = allTests.filter(test => test.topicId === topicId);hideAll();document.getElementById("tests").classList.remove("hidden");document.getElementById("topicTitle").textContent = topicId.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());const container = document.getElementById("testList");container.innerHTML = "";currentTests.forEach(test => {const card = document.createElement("div");card.className = "test";card.innerHTML = '<div class="title">' + esc(test.title || test.id) + '</div><div class="meta">' + (test.questionCount || 0) + ' Questions • ' + (test.durationMinutes || 0) + ' min • ' + esc(test.difficulty || "") + '</div>';card.addEventListener("click",() => startQuiz(test));container.appendChild(card);});}
async function startQuiz(test){
selectedTest = test;
hideAll();
document.getElementById("quiz").classList.remove("hidden");
document.getElementById("testTitle").textContent = test.title || test.id;
document.getElementById("questionText").textContent = "Loading questions...";
try{
  currentQuestions = await apiGet("/quiz/api/questions/" + encodeURIComponent(test.id));
  if(!Array.isArray(currentQuestions) || !currentQuestions.length){throw new Error("No questions found.");}
  currentQuestion = 0;
  score = 0;
  correctCount = 0;
  wrongCount = 0;
  unansweredCount = 0;
  questionResults = [];
  answered = false;
  points = 0;
  streak = 0;
  maxStreak = 0;
  quizStartTime = Date.now();
  startTimer(Number(test.durationMinutes) || 0);
  displayQuestion();
}catch(error){
  document.getElementById("options").innerHTML = '<div class="status error">' + esc(error.message) + '</div>';
}}
function displayQuestion(){const q = currentQuestions[currentQuestion];if(!q){finishQuiz();return;}answered = false;document.getElementById("questionNumber").textContent = "Question " + (currentQuestion + 1) + " / " + currentQuestions.length;document.getElementById("questionText").textContent = q.questionText || "";document.getElementById("explanationCard").classList.add("hidden");document.getElementById("nextButton").textContent = currentQuestion === currentQuestions.length - 1? "Finish ✓" : "Next →";const options = document.getElementById("options");options.innerHTML = "";[q.option0 || "",q.option1 || "",q.option2 || "",q.option3 || ""].forEach((option,index) => {const div = document.createElement("div");div.className = "option";div.textContent = option;div.addEventListener("click",() => selectAnswer(index,div));options.appendChild(div);});}
function selectAnswer(index,element){
if(answered)return;
answered = true;
const q = currentQuestions[currentQuestion];
const correct = Number(q.correctOptionIndex);
const options = document.querySelectorAll(".option");
const isCorrect = index === correct;

if(isCorrect){
  element.classList.add("correct");
  score++;
  correctCount++;
  streak++;
  maxStreak = Math.max(maxStreak, streak);
  const streakBonus = Math.min(5, Math.max(0, streak - 1));
  points += 10 + streakBonus;
}else{
  element.classList.add("wrong");
  wrongCount++;
  streak = 0;
  if(options[correct]) options[correct].classList.add("correct");
  points = Math.max(0, points - 2);
}

questionResults[currentQuestion] = {
  question: q.questionText || "",
  selected: index,
  correct: correct,
  isCorrect: isCorrect,
  explanation: q.explanation || "",
  selectedText: [q.option0,q.option1,q.option2,q.option3][index] || "",
  correctText: [q.option0,q.option1,q.option2,q.option3][correct] || ""
};

if(q.explanation){
  document.getElementById("explanation").textContent = q.explanation;
  document.getElementById("explanationCard").classList.remove("hidden");
}}
function nextQuestion(){
if(!answered){
  return;
}
if(currentQuestion >= currentQuestions.length - 1){
  finishQuiz();
  return;
}
currentQuestion++;
displayQuestion();
}
function startTimer(minutes){
clearInterval(timerInterval);
const limit = Number(minutes) > 0;
timerSeconds = limit ? Number(minutes) * 60 : 0;
elapsedSeconds = 0;
updateTimer();
timerInterval = setInterval(function(){
  elapsedSeconds++;
  if(limit){
    timerSeconds--;
    updateTimer();
    if(timerSeconds <= 0){
      clearInterval(timerInterval);
      finishQuiz(true);
    }
  }else{
    timerSeconds++;
    updateTimer();
  }
},1000);
}
function updateTimer(){
const min = Math.floor(timerSeconds / 60);
const sec = timerSeconds % 60;
document.getElementById("timer").textContent = "⏱ " + String(min).padStart(2,"0") + ":" + String(sec).padStart(2,"0");
}
function finishQuiz(timeExpired=false){
clearInterval(timerInterval);
const total = currentQuestions.length;
if(!total)return;

if(currentQuestion < total && !answered){
  unansweredCount++;
  const q = currentQuestions[currentQuestion];
  questionResults[currentQuestion] = {
    question:q.questionText || "",
    selected:null,
    correct:Number(q.correctOptionIndex),
    isCorrect:false,
    unanswered:true,
    explanation:q.explanation || "",
    selectedText:"Not answered",
    correctText:[q.option0,q.option1,q.option2,q.option3][Number(q.correctOptionIndex)] || ""
  };
}

const answeredTotal = correctCount + wrongCount;
const accuracy = answeredTotal ? (correctCount / answeredTotal) * 100 : 0;
const completion = (answeredTotal / total) * 100;
const percent = (correctCount / total) * 100;
const grade = percent >= 90 ? "A+" : percent >= 80 ? "A" : percent >= 70 ? "B" : percent >= 60 ? "C" : percent >= 50 ? "D" : "Needs Practice";

document.getElementById("scoreText").textContent = correctCount + " / " + total;
document.getElementById("gradeText").textContent = grade;
document.getElementById("correctStat").textContent = correctCount;
document.getElementById("wrongStat").textContent = wrongCount;
document.getElementById("unansweredStat").textContent = unansweredCount;
document.getElementById("pointsStat").textContent = points;
document.getElementById("accuracyStat").textContent = Math.round(accuracy) + "%";
document.getElementById("timeStat").textContent = formatTime(elapsedSeconds);
document.getElementById("avgTimeStat").textContent = Math.round(elapsedSeconds / total) + "s";
document.getElementById("streakStat").textContent = maxStreak;
document.getElementById("resultProgress").style.width = Math.round(percent) + "%";

let message = percent >= 90 ? "Excellent performance! 🔥" :
              percent >= 75 ? "Very good! Keep going. 💪" :
              percent >= 50 ? "Good attempt. Review the mistakes and improve. 📚" :
              "Keep practicing. Every attempt improves your score. 🎯";
document.getElementById("resultDetails").textContent =
  Math.round(percent) + "% score • " + Math.round(completion) + "% completed" +
  (timeExpired ? " • Time limit reached" : "");

document.getElementById("performanceText").innerHTML =
  "<b>" + message + "</b><br>Scoring: +10 for each correct answer, streak bonus up to +5, −2 for each wrong answer.";

renderReview();

hideAll();
document.getElementById("result").classList.remove("hidden");
}
function formatTime(seconds){
const m=Math.floor(seconds/60), s=seconds%60;
return String(m).padStart(2,"0")+":"+String(s).padStart(2,"0");
}
function renderReview(){
const container=document.getElementById("review");
container.innerHTML="<h3>📋 Answer Review</h3>";
questionResults.forEach((r,i)=>{
  if(!r)return;
  const cls=r.unanswered?"unanswered":(r.isCorrect?"correct":"wrong");
  const icon=r.unanswered?"🟡":(r.isCorrect?"✅":"❌");
  container.innerHTML +=
    '<div class="reviewItem '+cls+'">' +
    '<div class="reviewQ">'+icon+' Q'+(i+1)+'. '+esc(r.question)+'</div>' +
    '<div class="reviewA">Your answer: '+esc(r.selectedText)+'</div>' +
    '<div class="reviewA">Correct answer: '+esc(r.correctText)+'</div>' +
    (r.explanation?'<div class="reviewA">💡 '+esc(r.explanation)+'</div>':'') +
    '</div>';
});
}
function hideAll(){["home","tests","quiz","result","leaderboard"].forEach(id => document.getElementById(id).classList.add("hidden"));}
function showHome(){clearInterval(timerInterval);hideAll();document.getElementById("home").classList.remove("hidden");}
function showTests(){clearInterval(timerInterval);hideAll();document.getElementById("tests").classList.remove("hidden");}
async function showLeaderboard(){
hideAll();document.getElementById("leaderboard").classList.remove("hidden");
const myCard=document.getElementById("myRankCard"),top=document.getElementById("topThree"),rows=document.getElementById("rankRows");
myCard.innerHTML='<div class="status">Loading rank board...</div>';top.innerHTML='';rows.innerHTML='<div class="status">Loading...</div>';
try{
const users=await apiGet("/quiz/api/leaderboard");
if(!Array.isArray(users))throw new Error("Invalid leaderboard data.");
users.sort((a,b)=>Number(b.points||0)-Number(a.points||0));
document.getElementById("aspirantCount").textContent=users.length+" Aspirants";
if(!users.length){myCard.innerHTML='<div class="status">No leaderboard data.</div>';rows.innerHTML='';return;}
const me=users[0];
const av=me.profilePhotoUri?'<div class="avatar"><img src="'+esc(me.profilePhotoUri)+'" alt=""></div>':'<div class="avatar">'+esc(me.avatarEmoji||"👤")+'</div>';
myCard.innerHTML='<div class="myRankCard"><div class="myRankTop">'+av+'<div style="min-width:0"><div class="myRankName">'+esc(me.name||"Aspirant")+(me.badgeTitle?'<span class="badge">'+esc(me.badgeTitle)+'</span>':'')+'</div><div class="myRankRole">Aspirant Member</div></div><div class="rankNumber"><small>RANK</small><strong>#1</strong></div></div><div class="rankStats"><div class="rankStat"><div class="rsLabel">TOTAL POINTS</div><div class="rsValue">🏆 '+Number(me.points||0)+'</div></div><div class="rankStat"><div class="rsLabel">STARS EARNED</div><div class="rsValue">⭐ '+Number(me.stars||0)+'</div></div><div class="rankStat"><div class="rsLabel">ACCURACY</div><div class="rsValue">↗ '+Math.round(Number(me.accuracy||0))+'%</div></div></div></div>';
const medals=["🥇","🥈","🥉"];
users.slice(0,3).forEach((u,i)=>{const a=u.profilePhotoUri?'<div class="avatar podiumAvatar"><img src="'+esc(u.profilePhotoUri)+'" alt=""></div>':'<div class="avatar podiumAvatar">'+esc(u.avatarEmoji||"👤")+'</div>';top.innerHTML+='<div class="podium '+(i===0?'first':'')+'"><div class="medal">'+medals[i]+'</div>'+a+'<div class="podiumName">'+esc(u.name||"Aspirant")+'</div><div class="podiumRole">Aspirant</div><div class="podiumPoints">'+Number(u.points||0)+' pts</div></div>';});
rows.innerHTML='';
users.forEach((u,i)=>{const a=u.profilePhotoUri?'<div class="avatar"><img src="'+esc(u.profilePhotoUri)+'" alt=""></div>':'<div class="avatar">'+esc(u.avatarEmoji||"👤")+'</div>';rows.innerHTML+='<div class="rankRow"><div class="rankPos">#'+(i+1)+'</div>'+a+'<div class="rankRowMain"><div class="rankRowName">'+esc(u.name||"Aspirant")+'</div><div class="rankRowSub">'+esc(u.badgeTitle||"Aspirant")+' • '+Math.round(Number(u.accuracy||0))+'% accuracy</div></div><div class="rankRowPoints">'+Number(u.points||0)+' pts</div></div>';});
}catch(error){myCard.innerHTML='<div class="status error">'+esc(error.message)+'</div>';top.innerHTML='';rows.innerHTML='';}
}
document.getElementById("backHomeButton").addEventListener("click",showHome);
document.getElementById("backTestsButton").addEventListener("click",showTests);
document.getElementById("resultHomeButton").addEventListener("click",showHome);
document.getElementById("resultTestsButton").addEventListener("click",showTests);
document.getElementById("leaderboardBackButton").addEventListener("click",showHome);
document.getElementById("leaderboardButton").addEventListener("click",showLeaderboard);
document.getElementById("globalRankCard").addEventListener("click",showLeaderboard);
document.getElementById("nextButton").addEventListener("click",nextQuestion);

async function authPost(url,payload){
  const response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json",Accept:"application/json"},body:JSON.stringify(payload)});
  let data={};
  try{data=await response.json();}catch(e){throw new Error("Server returned invalid JSON ("+response.status+")");}
  if(!response.ok)throw new Error(data.error||"Authentication failed");
  return data;
}
function showOnlyAuth(id){
  ["login","signup","forgot","home","tests","quiz","result","leaderboard"].forEach(x=>document.getElementById(x).classList.add("hidden"));
  document.getElementById(id).classList.remove("hidden");
}
function setLoginMessage(id,message,type){
  const el=document.getElementById(id); if(!el)return;
  el.textContent=message||""; el.style.display=message?"block":"none";
  el.classList.toggle("error",type==="error");
}
function setLoginBusy(form,busy){form.classList.toggle("loginLoading",busy);form.querySelectorAll("button,input").forEach(x=>x.disabled=busy);}
async function checkQuizAuth(){
  try{
    const response=await fetch("/quiz/api/auth/me",{headers:{Accept:"application/json"}});
    if(response.ok){showOnlyAuth("home");loadData();return true;}
  }catch(e){console.error("[Auth]",e);}
  showOnlyAuth("login");
  return false;
}

document.getElementById("loginForm").addEventListener("submit",async function(e){
  e.preventDefault();
  setLoginMessage("loginError","");setLoginMessage("loginSuccess","");
  const form=e.currentTarget;const button=document.getElementById("loginButton");
  setLoginBusy(form,true);button.textContent="Signing In...";
  try{
    await authPost("/quiz/api/auth/login",{email:document.getElementById("loginEmail").value.trim(),password:document.getElementById("loginPassword").value});
    showOnlyAuth("home");
    loadData();
  }catch(err){setLoginMessage("loginError",err.message,"error");}
  finally{setLoginBusy(form,false);button.textContent="Sign In";}
});

document.getElementById("togglePassword").addEventListener("click",function(){
  const input=document.getElementById("loginPassword");
  input.type=input.type==="password"?"text":"password";
  this.textContent=input.type==="password"?"◉":"◉";
});

document.getElementById("signupLink").addEventListener("click",()=>{setLoginMessage("loginError","");showOnlyAuth("signup");});
document.getElementById("backToLoginLink").addEventListener("click",()=>showOnlyAuth("login"));
document.getElementById("forgotLink").addEventListener("click",()=>{setLoginMessage("forgotError","");setLoginMessage("forgotSuccess","");showOnlyAuth("forgot");});
document.getElementById("forgotBackLink").addEventListener("click",()=>showOnlyAuth("login"));

document.getElementById("signupForm").addEventListener("submit",async function(e){
  e.preventDefault();
  setLoginMessage("signupError","");const form=e.currentTarget;setLoginBusy(form,true);
  try{
    await authPost("/quiz/api/auth/signup",{name:document.getElementById("signupName").value.trim(),email:document.getElementById("signupEmail").value.trim(),password:document.getElementById("signupPassword").value});
    showOnlyAuth("home");loadData();
  }catch(err){setLoginMessage("signupError",err.message,"error");}
  finally{setLoginBusy(form,false);}
});

document.getElementById("forgotForm").addEventListener("submit",async function(e){
  e.preventDefault();setLoginMessage("forgotError","");setLoginMessage("forgotSuccess","");
  const form=e.currentTarget;setLoginBusy(form,true);
  try{
    await authPost("/quiz/api/auth/forgot",{email:document.getElementById("forgotEmail").value.trim()});
    setLoginMessage("forgotSuccess","Password reset email sent. Check your inbox.");
  }catch(err){setLoginMessage("forgotError",err.message,"error");}
  finally{setLoginBusy(form,false);}
});

document.getElementById("logoutButton").addEventListener("click",async function(){
  try{await fetch("/quiz/api/auth/logout",{method:"POST"});}catch(e){console.error(e);}
  clearInterval(timerInterval);showOnlyAuth("login");
  document.getElementById("loginPassword").value="";
  setLoginMessage("loginError","");
});

checkQuizAuth();
</script>
</body>
</html>
"""
    return html
# ============================================================
# QUIZ FIRESTORE API
# ============================================================

@app.route("/quiz/api/tests")
def quiz_tests():
    user, error = require_quiz_login()
    if error:
        return error

    try:
        db = get_firestore()
        tests = []
        for doc in db.collection("custom_tests").stream():
            data = doc.to_dict()
            tests.append({
                "id": data.get("id") or doc.id,
                "topicId": data.get("topicId") or "",
                "title": data.get("title") or "",
                "subtitle": data.get("subtitle") or "",
                "durationMinutes": data.get("durationMinutes") or 0,
                "difficulty": data.get("difficulty") or "",
                "dateMillis": data.get("dateMillis"),
                "questionCount": 0,
            })
        question_counts = {}
        for doc in db.collection("custom_questions").stream():
            data = doc.to_dict()
            test_id = data.get("testId")
            if test_id:
                question_counts[test_id] = question_counts.get(test_id, 0) + 1
        for test in tests:
            test["questionCount"] = question_counts.get(test["id"], 0)
        return jsonify(tests)
    except Exception as e:
        print("[Quiz Firestore tests error]", e)
        return jsonify({"error": str(e)}), 500

@app.route("/quiz/api/questions/<path:test_id>")
def quiz_questions(test_id):
    user, error = require_quiz_login()
    if error:
        return error

    try:
        db = get_firestore()
        questions = []
        docs = db.collection("custom_questions").where("testId", "==", test_id).stream()
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
                "hint": data.get("hint") or "",
            })
        return jsonify(questions)
    except Exception as e:
        print("[Quiz Firestore questions error]", e)
        return jsonify({"error": str(e)}), 500

@app.route("/quiz/api/leaderboard")
def quiz_leaderboard():
    user, error = require_quiz_login()
    if error:
        return error

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
                "profilePhotoUri": data.get("profilePhotoUri") or "",
                "state": data.get("state") or data.get("stateName") or "",
                "testsCompleted": data.get("testsCompleted", 0),
                "bestStreak": data.get("bestStreak", 0),
            })
        entries.sort(key=lambda item: item["points"], reverse=True)
        return jsonify(entries[:50])
    except Exception as e:
        print("[Leaderboard error]", e)
        return jsonify({"error": str(e)}), 500

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    print("[Startup] CA Blockbuster server starting...")
    print("[Startup] Firestore configured:", bool(os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")))
    threading.Thread(target=telegram_updater, daemon=True).start()
    threading.Thread(target=audio_updater, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
