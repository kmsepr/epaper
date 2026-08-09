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
from firebase_admin import credentials, firestore

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
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not configured in Koyeb")

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
        text = re.sub(r"[\U0001F300-\U0001FAFF]", " ", text)
        text = re.sub(r"[\U0001F600-\U0001F64F]", " ", text)
        text = re.sub(r"[\u2600-\u27BF]", " ", text)
        text = re.sub(r"[\uFE0F\u200D]", " ", text)
        text = re.sub(r"#\w+", "", text)
        text = re.sub(r"http\S+", "", text)
        text = re.sub(r"(join\s*@\w+.*)$", "", text, flags=re.IGNORECASE)
        text = re.sub(r"@\w+", "", text)
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
        posts += "<p>" + entry.get("description", "") + "</p><hr>"

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:system-ui;padding:10px}}
.btn{{background:#00695c;color:white;padding:8px 12px;border-radius:6px;text-decoration:none}}
</style>
</head>
<body>
<h2>{channel_name}</h2>
<a class="btn" href="?refresh=1">🔄 Refresh</a>
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
    months = sorted(os.listdir(ARCHIVE_FOLDER), reverse=True) if os.path.exists(ARCHIVE_FOLDER) else []

    html = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui;padding:10px;background:#f5f5f5}
.card{background:white;padding:12px;border-radius:10px;margin-bottom:15px}
.file{display:block;padding:9px;margin-top:5px;background:#e3f2fd;border-radius:6px;text-decoration:none;color:#1565c0}
</style>
</head>
<body>
<h2>📦 Feed Archives</h2>
"""

    if not months:
        html += "<p>No archives found.</p>"

    for month in months:
        month_path = os.path.join(ARCHIVE_FOLDER, month)
        if not os.path.isdir(month_path):
            continue
        html += f"<div class='card'><h3>{month}</h3>"
        for filename in os.listdir(month_path):
            html += f"<a class='file' href='/archive/{month}/{filename}'>{filename}</a>"
        html += "</div>"

    html += "</body></html>"
    return html

@app.route("/archive/<month>/<filename>")
def archive_file(month, filename):
    archive_path = os.path.join(ARCHIVE_FOLDER, month, filename)
    if not os.path.exists(archive_path):
        return "Archive not found", 404

    feed = feedparser.parse(archive_path)
    posts = ""

    for entry in list(feed.entries)[::-1][:100]:
        posts += f"""
<div class="post">
<h3>{entry.get('title','')}</h3>
<p>{entry.get('description','')}</p>
<a href="{entry.get('link','#')}" target="_blank">Open Source</a>
</div>
"""

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:system-ui;padding:10px;background:#f5f5f5}}
.post{{background:white;padding:12px;border-radius:10px;margin-bottom:15px}}
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
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:system-ui;background:#f0f2f5;margin:0;padding:10px;text-align:center}
h1{color:#d32f2f}
.section{font-weight:bold;margin-top:18px}
.btn{display:block;width:90%;margin:10px auto;padding:15px 5px;font-size:18px;font-weight:bold;text-decoration:none;border-radius:10px}
.audio{background:#e3f2fd;color:#1565c0}
.feed{background:#f1f8e9;color:#2e7d32}
.archive{background:#fff3e0;color:#ef6c00}
</style>
</head>
<body>
<h1>📰 വാർത്തകൾ</h1>
<div class="section">🎧 AUDIO CONTENT</div>
<a class="btn audio" href="/static/audio/Pathravarthakal.mp3">1️⃣ Pathravarthakal</a>
<a class="btn audio" href="/static/audio/DailyCa.mp3">2️⃣ Daily CA</a>
<div class="section">📰 NEWS FEEDS</div>
<a class="btn feed" href="/telegram/Pathravarthakal">3️⃣ Pathravarthakal Feed</a>
<a class="btn feed" href="/telegram/DailyCa">4️⃣ Daily CA Feed</a>
<div class="section">📦 ARCHIVES</div>
<a class="btn archive" href="/archives">5️⃣ Feed Archives</a>
</body>
</html>
"""

# ============================================================
# QUIZ PAGE
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
body{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f5f7fb;margin:0;color:#222}
.container{max-width:900px;margin:auto;padding:14px}
.hidden{display:none!important}
.header{text-align:center;padding:12px}
.header h1{color:#1565c0;margin:0}
button{border:0;border-radius:9px;padding:11px 16px;background:#1565c0;color:white;font-size:15px}
.status{padding:12px;background:#fff3cd;border-radius:9px;margin:10px 0;font-size:13px}
.error{background:#ffebee;color:#b71c1c}
#categories,#testList{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.category,.test{background:white;padding:18px;border-radius:14px;border:1px solid #e4e7ec;cursor:pointer}
.category{text-align:center;min-height:120px}
.icon{font-size:32px}
.title{font-weight:bold;font-size:17px}
.meta{font-size:13px;color:#777;margin-top:7px}
.option{background:white;border:2px solid #d9dee7;padding:14px;margin:10px 0;border-radius:10px;cursor:pointer}
.option.correct{background:#d8f3dc;border-color:#2e7d32}
.option.wrong{background:#ffd8d8;border-color:#c62828}
.card{background:white;padding:16px;border-radius:14px;margin:12px 0}
.question{font-size:20px;font-weight:600;line-height:1.5}
.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.back{background:#555}
.timer{font-weight:bold;color:#d32f2f}
.score{font-size:42px;font-weight:bold;text-align:center;color:#1565c0}
.center{text-align:center}
.leader{display:flex;align-items:center;gap:10px;background:white;padding:12px;border-radius:12px;margin:8px 0}
.points{margin-left:auto;font-weight:bold;color:#1565c0}
@media(max-width:500px){#categories,#testList{grid-template-columns:repeat(2,1fr)}.question{font-size:18px}}
@media(max-width:360px){#categories,#testList{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="container">
<section id="home">
<div class="header"><h1>🎯 CA Blockbuster</h1><p>Daily CA Revision</p></div>
<h2>Categories</h2>
<div id="categories"><div class="status">Loading...</div></div>
<br>
<button id="leaderboardButton">🏆 View Leaderboard</button>
</section>

<section id="tests" class="hidden">
<div class="topbar"><button id="backHomeButton" class="back">← Back</button></div>
<h2 id="topicTitle"></h2>
<div id="testList"></div>
</section>

<section id="quiz" class="hidden">
<div class="topbar"><button id="backTestsButton" class="back">← Tests</button><span id="timer" class="timer">00:00</span></div>
<h2 id="testTitle"></h2>
<div id="questionNumber"></div>
<div class="card"><div id="questionText" class="question"></div></div>
<div id="options"></div>
<div id="explanationCard" class="card hidden"><b>Explanation</b><div id="explanation"></div></div>
<div style="text-align:right"><button id="nextButton">Next →</button></div>
</section>

<section id="result" class="hidden">
<div class="header"><h1>🎉 Result</h1></div>
<div class="card center"><div id="scoreText" class="score"></div><p id="resultDetails"></p></div>
<button id="resultHomeButton">Back to Categories</button>
</section>

<section id="leaderboard" class="hidden">
<div class="topbar"><button id="leaderboardBackButton" class="back">← Back</button></div>
<div class="header"><h1>🏆 Leaderboard</h1></div>
<div id="leaderboardList"><div class="status">Loading...</div></div>
</section>
</div>

<script>
"use strict";
let allTests = [];let currentTests = [];let currentQuestions = [];let selectedTopic = "";let selectedTest = null;let currentQuestion = 0;let score = 0;let answered = false;let timerSeconds = 0;let timerInterval = null;
function esc(value){return String(value?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#039;");}
async function apiGet(url){const response = await fetch(url,{method:"GET",headers:{Accept:"application/json"}});let data;try{data = await response.json();}catch(error){throw new Error("Server returned invalid JSON (" + response.status + ")");}if(!response.ok){throw new Error(data.error || "Server error: " + response.status);}return data;}
async function loadData(){const container = document.getElementById("categories");try{container.innerHTML = '<div class="status">Loading from Firestore...</div>';allTests = await apiGet("/quiz/api/tests");if(!Array.isArray(allTests)){throw new Error("Invalid test data received.");}displayCategories();}catch(error){console.error("[Quiz]",error);container.innerHTML = '<div class="status error">' + esc(error.message) + '</div>';}}
function displayCategories(){const container = document.getElementById("categories");container.innerHTML = "";const topicIds = [...new Set(allTests.map(test => test.topicId).filter(Boolean))];if(!topicIds.length){container.innerHTML = '<div class="status">No categories found.</div>';return;}topicIds.sort((a,b) => String(a).localeCompare(String(b)));const icons = ["📚","🌍","📰","🔬","🏛️","💡","🇮🇳","🎯"];topicIds.forEach((topicId,index) => {const tests = allTests.filter(test => test.topicId === topicId);const card = document.createElement("div");card.className = "category";card.innerHTML = '<div class="icon">' + icons[index % icons.length] + '</div><div class="title">' + esc(topicId) + '</div><div class="meta">' + tests.length + ' Tests</div>';card.addEventListener("click",() => showTestsForTopic(topicId));container.appendChild(card);});}
function showTestsForTopic(topicId){selectedTopic = topicId;currentTests = allTests.filter(test => test.topicId === topicId);hideAll();document.getElementById("tests").classList.remove("hidden");document.getElementById("topicTitle").textContent = topicId;const container = document.getElementById("testList");container.innerHTML = "";currentTests.forEach(test => {const card = document.createElement("div");card.className = "test";card.innerHTML = '<div class="title">' + esc(test.title || test.id) + '</div><div class="meta">' + (test.questionCount || 0) + ' Questions • ' + (test.durationMinutes || 0) + ' min • ' + esc(test.difficulty || "") + '</div>';card.addEventListener("click",() => startQuiz(test));container.appendChild(card);});}
async function startQuiz(test){selectedTest = test;hideAll();document.getElementById("quiz").classList.remove("hidden");document.getElementById("testTitle").textContent = test.title || test.id;document.getElementById("questionText").textContent = "Loading questions...";try{currentQuestions = await apiGet("/quiz/api/questions/" + encodeURIComponent(test.id));if(!Array.isArray(currentQuestions) ||!currentQuestions.length){throw new Error("No questions found.");}currentQuestion = 0;score = 0;answered = false;startTimer(Number(test.durationMinutes) || 0);displayQuestion();}catch(error){document.getElementById("options").innerHTML = '<div class="status error">' + esc(error.message) + '</div>';}}
function displayQuestion(){const q = currentQuestions[currentQuestion];if(!q){finishQuiz();return;}answered = false;document.getElementById("questionNumber").textContent = "Question " + (currentQuestion + 1) + " / " + currentQuestions.length;document.getElementById("questionText").textContent = q.questionText || "";document.getElementById("explanationCard").classList.add("hidden");document.getElementById("nextButton").textContent = currentQuestion === currentQuestions.length - 1? "Finish ✓" : "Next →";const options = document.getElementById("options");options.innerHTML = "";[q.option0 || "",q.option1 || "",q.option2 || "",q.option3 || ""].forEach((option,index) => {const div = document.createElement("div");div.className = "option";div.textContent = option;div.addEventListener("click",() => selectAnswer(index,div));options.appendChild(div);});}
function selectAnswer(index,element){if(answered)return;answered = true;const q = currentQuestions[currentQuestion];const correct = Number(q.correctOptionIndex);const options = document.querySelectorAll(".option");if(index === correct){element.classList.add("correct");score++;}else{element.classList.add("wrong");if(options[correct]){options[correct].classList.add("correct");}}if(q.explanation){document.getElementById("explanation").textContent = q.explanation;document.getElementById("explanationCard").classList.remove("hidden");}}
function nextQuestion(){if(!answered)return;if(currentQuestion >= currentQuestions.length - 1){finishQuiz();return;}currentQuestion++;displayQuestion();}
function startTimer(minutes){clearInterval(timerInterval);const limit = Number(minutes) > 0;timerSeconds = limit? Number(minutes) * 60 : 0;updateTimer();timerInterval = setInterval(function(){if(limit){timerSeconds--;updateTimer();if(timerSeconds <= 0){clearInterval(timerInterval);finishQuiz();}}else{timerSeconds++;updateTimer();}},1000);}
function updateTimer(){const min = Math.floor(timerSeconds / 60);const sec = timerSeconds % 60;document.getElementById("timer").textContent = "⏱ " + String(min).padStart(2,"0") + ":" + String(sec).padStart(2,"0");}
function finishQuiz(){clearInterval(timerInterval);hideAll();document.getElementById("result").classList.remove("hidden");const total = currentQuestions.length;document.getElementById("scoreText").textContent = score + " / " + total;document.getElementById("resultDetails").textContent = (total? Math.round(score / total * 100) : 0) + "% correct";}
function hideAll(){["home","tests","quiz","result","leaderboard"].forEach(id => document.getElementById(id).classList.add("hidden"));}
function showHome(){clearInterval(timerInterval);hideAll();document.getElementById("home").classList.remove("hidden");}
function showTests(){clearInterval(timerInterval);hideAll();document.getElementById("tests").classList.remove("hidden");}
async function showLeaderboard(){hideAll();document.getElementById("leaderboard").classList.remove("hidden");const container = document.getElementById("leaderboardList");container.innerHTML = '<div class="status">Loading leaderboard...</div>';try{const users = await apiGet("/quiz/api/leaderboard");if(!Array.isArray(users) ||!users.length){container.innerHTML = '<div class="status">No leaderboard data.</div>';return;}container.innerHTML = "";users.forEach((user,index) => {const row = document.createElement("div");row.className = "leader";row.innerHTML = '<b>' + (index + 1) + '.</b><div><b>' + esc(user.name || "User") + '</b><div class="meta">' + esc(user.badgeTitle || "") + '</div></div><div class="points">' + Number(user.points || 0) + ' pts</div>';container.appendChild(row);});}catch(error){container.innerHTML = '<div class="status error">' + esc(error.message) + '</div>';}}
document.getElementById("backHomeButton").addEventListener("click",showHome);
document.getElementById("backTestsButton").addEventListener("click",showTests);
document.getElementById("resultHomeButton").addEventListener("click",showHome);
document.getElementById("leaderboardBackButton").addEventListener("click",showHome);
document.getElementById("leaderboardButton").addEventListener("click",showLeaderboard);
document.getElementById("nextButton").addEventListener("click",nextQuestion);
loadData();
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

# ============================================================
# QUIZ QUESTIONS
# ============================================================

@app.route("/quiz/api/questions/<path:test_id>")
def quiz_questions(test_id):
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

# ============================================================
# LEADERBOARD
# ============================================================

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
                "profilePhotoUri": data.get("profilePhotoUri") or "",
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