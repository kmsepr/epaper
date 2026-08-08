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
from firebase_admin import credentials, firestore

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
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <title>CA Blockbuster Quiz</title>

    <style>
        * {
            box-sizing: border-box;
        }

        body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont,
                         "Segoe UI", Roboto, sans-serif;
            background: #f5f7fb;
            margin: 0;
            color: #222;
        }

        .container {
            width: min(760px, 100%);
            margin: auto;
            padding: 20px 16px 40px;
        }

        .header {
            text-align: center;
            padding: 18px 0 10px;
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

        h2 {
            margin-top: 20px;
        }

        .card {
            background: #fff;
            padding: 18px;
            margin: 12px 0;
            border-radius: 14px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.09);
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

        .hidden {
            display: none !important;
        }

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

        button:hover {
            opacity: .92;
        }

        .back {
            background: #555;
        }

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

        .option:hover {
            background: #f5f9ff;
        }

        .option.correct {
            background: #d8f3dc !important;
            border-color: #2e7d32;
        }

        .option.wrong {
            background: #ffd8d8 !important;
            border-color: #c62828;
        }

        .explanation {
            line-height: 1.5;
        }

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

        .center {
            text-align: center;
        }

        @media (max-width: 600px) {
            .header h1 {
                font-size: 26px;
            }

            .question {
                font-size: 18px;
            }
        }
    </style>
</head>

<body>

<div class="container">

    <!-- HOME / CATEGORIES -->
    <section id="home">
        <div class="header">
            <h1>🎯 CA Blockbuster</h1>
            <p>Practice tests from Firestore</p>
        </div>

        <h2>Categories</h2>

        <div id="categories">
            <div class="status">Loading...</div>
        </div>
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

</div>


<script>
"use strict";

/*
    The browser does NOT connect directly to Firestore.

    Browser
       ↓
    Flask /quiz/api/...
       ↓
    Firebase Admin SDK
       ↓
    Firestore
*/

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

async function apiGet(url) {

    const response = await fetch(url, {
        method: "GET",
        headers: {
            "Accept": "application/json"
        }
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

        card.className = "card clickable";

        card.innerHTML = `
            <div class="title">
                📚 ${escapeHtml(topicId)}
            </div>

            <div class="subtitle">
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
};


window.showTests = function() {

    clearInterval(timerInterval);

    document.getElementById("quiz")
        .classList.add("hidden");

    document.getElementById("result")
        .classList.add("hidden");

    document.getElementById("tests")
        .classList.remove("hidden");
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


# ------------------ Run ------------------
if __name__ == "__main__":

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
