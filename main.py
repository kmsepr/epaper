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
from gtts import gTTS

app = Flask(__name__)

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


# ------------------ QUIZ APP ------------------
@app.route("/quiz")
def quiz_app():
    return """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <title>CA Blockbuster Quiz</title>

    <style>
        body {
            font-family: system-ui, sans-serif;
            background: #f5f7fb;
            margin: 0;
            padding: 15px;
            color: #222;
        }

        .container {
            max-width: 700px;
            margin: auto;
        }

        h1 {
            text-align: center;
            color: #1565c0;
        }

        .card {
            background: white;
            padding: 18px;
            margin: 12px 0;
            border-radius: 14px;
            box-shadow: 0 2px 8px rgba(0,0,0,.1);
            cursor: pointer;
        }

        .card:hover {
            background: #e3f2fd;
        }

        .title {
            font-size: 18px;
            font-weight: bold;
        }

        .subtitle {
            color: #666;
            margin-top: 5px;
        }

        .hidden {
            display: none;
        }

        .option {
            background: white;
            border: 2px solid #ddd;
            padding: 14px;
            margin: 10px 0;
            border-radius: 10px;
            cursor: pointer;
        }

        .option:hover {
            background: #f0f7ff;
        }

        .correct {
            background: #c8e6c9 !important;
            border-color: #2e7d32;
        }

        .wrong {
            background: #ffcdd2 !important;
            border-color: #c62828;
        }

        button {
            border: none;
            background: #1565c0;
            color: white;
            padding: 12px 20px;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
        }

        .topbar {
            display: flex;
            justify-content: space-between;
            margin-bottom: 15px;
        }

        #timer {
            font-weight: bold;
            color: #d32f2f;
        }

        .back {
            background: #555;
        }
    </style>
</head>

<body>

<div class="container">

    <!-- HOME -->
    <div id="home">
        <h1>🎯 CA Blockbuster</h1>
        <h2>Categories</h2>
        <div id="categories">
            Loading...
        </div>
    </div>

    <!-- TEST LIST -->
    <div id="tests" class="hidden">
        <div class="topbar">
            <button class="back" onclick="showHome()">← Back</button>
        </div>

        <h2 id="topicTitle"></h2>

        <div id="testList">
            Loading...
        </div>
    </div>

    <!-- QUIZ -->
    <div id="quiz" class="hidden">

        <div class="topbar">
            <button class="back" onclick="showTests()">← Tests</button>
            <span id="timer">00:00</span>
        </div>

        <h2 id="testTitle"></h2>

        <p id="questionNumber"></p>

        <div class="card">
            <div id="questionText"></div>
        </div>

        <div id="options"></div>

        <div class="card">
            <b>Explanation</b>
            <p id="explanation"></p>
        </div>

        <button onclick="nextQuestion()">Next →</button>

    </div>

    <!-- RESULT -->
    <div id="result" class="hidden">
        <h1>🎉 Result</h1>

        <div class="card">
            <h2 id="scoreText"></h2>
        </div>

        <button onclick="showHome()">Back to Home</button>
    </div>

</div>


<script type="module">

import { initializeApp }
    from "https://www.gstatic.com/firebasejs/12.0.0/firebase-app.js";

import {
    getFirestore,
    collection,
    getDocs
} from "https://www.gstatic.com/firebasejs/12.0.0/firebase-firestore.js";


/*
==================================================
PUT YOUR FIREBASE WEB CONFIG HERE
==================================================
*/

const firebaseConfig = {

    apiKey: "YOUR_API_KEY",

    authDomain: "YOUR_PROJECT.firebaseapp.com",

    projectId: "YOUR_PROJECT_ID",

    storageBucket: "YOUR_PROJECT.firebasestorage.app",

    messagingSenderId: "YOUR_SENDER_ID",

    appId: "YOUR_APP_ID"

};


const app = initializeApp(firebaseConfig);
const db = getFirestore(app);


/*
==================================================
DATA
==================================================
*/

let tests = [];
let questions = [];

let selectedTopic = "";
let selectedTest = null;

let currentQuestion = 0;
let score = 0;
let answered = false;

let timerSeconds = 0;
let timerInterval;


/*
==================================================
LOAD FIRESTORE
==================================================
*/

async function loadData() {

    try {

        const testSnapshot =
            await getDocs(collection(db, "custom_tests"));

        tests = [];

        testSnapshot.forEach(doc => {

            const data = doc.data();

            tests.push({
                id: data.id || doc.id,
                topicId: data.topicId || "unknown",
                title: data.title || data.name || "",
                subtitle:
                    data.subtitle ||
                    data.description ||
                    "",
                durationMinutes:
                    data.durationMinutes || 10,
                difficulty:
                    data.difficulty || "Medium",
                dateMillis:
                    data.dateMillis || null
            });

        });


        const questionSnapshot =
            await getDocs(
                collection(db, "custom_questions")
            );

        questions = [];

        questionSnapshot.forEach(doc => {

            const data = doc.data();

            questions.push({
                id: data.id || doc.id,

                testId: data.testId,

                topicId: data.topicId || "",

                questionText:
                    data.questionText ||
                    data.question ||
                    "",

                options: [
                    data.option0 || "",
                    data.option1 || "",
                    data.option2 || "",
                    data.option3 || ""
                ],

                correctOptionIndex:
                    data.correctOptionIndex ?? 0,

                explanation:
                    data.explanation || "",

                hint:
                    data.hint || ""
            });

        });


        displayCategories();

    } catch (error) {

        console.error(error);

        document.getElementById("categories")
            .innerHTML =
            "<p>Unable to load quiz.</p>";

    }

}


/*
==================================================
CATEGORIES
==================================================
*/

function displayCategories() {

    const container =
        document.getElementById("categories");

    container.innerHTML = "";

    const topicIds =
        [...new Set(
            tests.map(test => test.topicId)
        )];


    topicIds.forEach(topicId => {

        const topicTests =
            tests.filter(
                test => test.topicId === topicId
            );


        const card =
            document.createElement("div");

        card.className = "card";

        card.innerHTML = `
            <div class="title">
                📚 ${topicId}
            </div>

            <div class="subtitle">
                ${topicTests.length} Tests
            </div>
        `;


        card.onclick = () =>
            showTestsForTopic(topicId);


        container.appendChild(card);

    });

}


/*
==================================================
TEST LIST
==================================================
*/

function showTestsForTopic(topicId) {

    selectedTopic = topicId;

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


    const topicTests =
        tests.filter(
            test => test.topicId === topicId
        );


    topicTests.forEach(test => {

        const questionCount =
            questions.filter(
                q => q.testId === test.id
            ).length;


        const card =
            document.createElement("div");

        card.className = "card";

        card.innerHTML = `
            <div class="title">
                ${test.title}
            </div>

            <div class="subtitle">
                ${test.subtitle}
            </div>

            <div class="subtitle">
                ${questionCount} Questions
                • ${test.durationMinutes} min
                • ${test.difficulty}
            </div>
        `;


        card.onclick = () =>
            startQuiz(test);


        container.appendChild(card);

    });

}


/*
==================================================
START QUIZ
==================================================
*/

function startQuiz(test) {

    selectedTest = test;

    currentQuestion = 0;
    score = 0;
    answered = false;


    questions =
        questions.filter(
            q => q.testId === test.id
        );


    document.getElementById("tests")
        .classList.add("hidden");

    document.getElementById("quiz")
        .classList.remove("hidden");


    document.getElementById("testTitle")
        .textContent = test.title;


    startTimer();

    displayQuestion();

}


/*
==================================================
QUESTION
==================================================
*/

function displayQuestion() {

    const q =
        questions[currentQuestion];


    if (!q) {

        finishQuiz();

        return;

    }


    answered = false;


    document.getElementById("questionNumber")
        .textContent =
        `Question ${currentQuestion + 1} / ${questions.length}`;


    document.getElementById("questionText")
        .textContent = q.questionText;


    document.getElementById("explanation")
        .textContent = "";


    const options =
        document.getElementById("options");

    options.innerHTML = "";


    q.options.forEach(
        (option, index) => {

            const div =
                document.createElement("div");

            div.className = "option";

            div.textContent = option;


            div.onclick = () =>
                selectAnswer(index, div);


            options.appendChild(div);

        }
    );

}


/*
==================================================
ANSWER
==================================================
*/

function selectAnswer(index, element) {

    if (answered)
        return;

    answered = true;


    const q =
        questions[currentQuestion];


    const optionElements =
        document.querySelectorAll(".option");


    if (index === q.correctOptionIndex) {

        element.classList.add("correct");

        score++;

    } else {

        element.classList.add("wrong");

        optionElements[
            q.correctOptionIndex
        ].classList.add("correct");

    }


    document.getElementById("explanation")
        .textContent =
        q.explanation || "";

}


/*
==================================================
NEXT
==================================================
*/

window.nextQuestion = function() {

    if (!answered)
        return;


    currentQuestion++;

    displayQuestion();

};


/*
==================================================
TIMER
==================================================
*/

function startTimer() {

    clearInterval(timerInterval);

    timerSeconds = 0;


    timerInterval =
        setInterval(() => {

            timerSeconds++;


            const minutes =
                Math.floor(timerSeconds / 60);

            const seconds =
                timerSeconds % 60;


            document.getElementById("timer")
                .textContent =
                String(minutes).padStart(2, "0")
                + ":" +
                String(seconds).padStart(2, "0");

        }, 1000);

}


/*
==================================================
RESULT
==================================================
*/

function finishQuiz() {

    clearInterval(timerInterval);


    document.getElementById("quiz")
        .classList.add("hidden");

    document.getElementById("result")
        .classList.remove("hidden");


    document.getElementById("scoreText")
        .textContent =
        `${score} / ${questions.length}`;

}


/*
==================================================
NAVIGATION
==================================================
*/

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

    document.getElementById("tests")
        .classList.remove("hidden");

};


loadData();

</script>

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
