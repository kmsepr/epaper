import os
import time
import json
import threading
import datetime
import requests
import brotli
import feedparser
from flask import Flask, render_template_string

app = Flask(__name__)

UPLOAD_FOLDER = "static"
EPAPER_TXT = "epaper.txt"
QUIZ_JSON = "quiz.json"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

LOCATIONS = [
    "Kozhikode", "Malappuram", "Kannur", "Thrissur",
    "Kochi", "Thiruvananthapuram", "Palakkad", "Gulf"
]
RGB_COLORS = [
    "#FF6B6B", "#6BCB77", "#4D96FF", "#FFD93D",
    "#FF6EC7", "#00C2CB", "#FFA41B", "#845EC2"
]

# ------------------ ePaper Functions ------------------

def get_url_for_location(location, dt_obj=None):
    if dt_obj is None:
        dt_obj = datetime.datetime.now()
    date_str = dt_obj.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

def wrap_grid_page(title, items_html, show_back=True):
    back_html = '<p><a class="back" href="/">Back to Home</a></p>' if show_back else ''
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            body {{
                font-family: 'Segoe UI', sans-serif;
                background: #f0f2f5;
                margin: 0;
                padding: 40px 20px;
                color: #333;
                text-align: center;
            }}
            h1 {{
                font-size: 2em;
                margin-bottom: 30px;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 20px;
                max-width: 1000px;
                margin: auto;
            }}
            .card {{
                padding: 25px 15px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                transition: transform 0.2s ease;
            }}
            .card:hover {{
                transform: translateY(-4px);
            }}
            .card a {{
                text-decoration: none;
                font-size: 1.1em;
                color: #fff;
                font-weight: bold;
                display: block;
            }}
            a.back {{
                display: inline-block;
                margin-top: 40px;
                font-size: 1em;
                color: #555;
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        <div class="grid">{items_html}</div>
        {back_html}
    </body>
    </html>
    """

def update_epaper_json():
    url = "https://api2.suprabhaatham.com/api/ePaper"
    headers = {
        "Content-Type": "application/json",
        "Accept-Encoding": "br"
    }
    payload = {}

    while True:
        try:
            print("Fetching latest ePaper data...")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()

            if response.headers.get('Content-Encoding') == 'br':
                decompressed_data = brotli.decompress(response.content).decode('utf-8')
            else:
                decompressed_data = response.text

            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(decompressed_data)

            print("epaper.txt updated successfully.")
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")

        time.sleep(86400)  # Wait for 24 hours

# ------------------ RSS Quiz Functions ------------------

RSS_FEED = "https://www.thehindu.com/news/national/feeder/default.rss"

CATEGORIES = {
    "Politics & Governance": ["parliament", "bill", "modi", "bjp", "congress", "minister", "election", "assembly"],
    "Sports & Games": ["cricket", "football", "hockey", "tennis", "olympic", "match", "tournament", "cup"],
    "Science & Technology": ["isro", "satellite", "ai", "space", "research", "nasa", "scientist", "technology"],
    "Business & Economy": ["market", "gdp", "inflation", "trade", "stock", "investment", "economy", "budget"],
    "International Affairs": ["china", "us", "pakistan", "war", "united nations", "ukraine", "world"]
}

def fetch_latest_news():
    try:
        feed = feedparser.parse(RSS_FEED)
        return [entry.title for entry in feed.entries[:10]]
    except:
        return ["Fallback: Parliament passes new education bill",
                "Fallback: India wins cricket test match",
                "Fallback: ISRO launches new satellite"]

def categorize_headline(headline: str) -> str:
    h = headline.lower()
    for category, keywords in CATEGORIES.items():
        if any(word in h for word in keywords):
            return category
    return "General Affairs"

def generate_quiz():
    headlines = fetch_latest_news()
    quiz = []
    for i, headline in enumerate(headlines[:10]):
        correct = categorize_headline(headline)
        options = list(CATEGORIES.keys()) + ["General Affairs"]
        quiz.append({
            "q": f"Q{i+1}. Which category best fits this news: \"{headline}\"?",
            "options": options,
            "answer": correct
        })
    with open(QUIZ_JSON, "w", encoding="utf-8") as f:
        json.dump(quiz, f, indent=2)
    return quiz

# ------------------ Routes ------------------

@app.route('/')
def homepage():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("Current Affairs Quiz", "/quiz")
    ]
    cards = ""
    for i, (label, link) in enumerate(links):
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{link}">{label}</a></div>'
    return render_template_string(wrap_grid_page("Suprabhaatham ePaper & Quiz", cards, show_back=False))

def auto_update_quiz():
    """Background task to regenerate quiz daily."""
    while True:
        try:
            print("Generating latest quiz from RSS feed...")
            quiz = generate_quiz()
            print(f"Quiz updated successfully at {datetime.datetime.now()}")
        except Exception as e:
            print(f"[Error updating quiz] {e}")
        time.sleep(86400)  # Wait 24 hours

@app.route('/today')
def show_today_links():
    cards = ""
    for i, loc in enumerate(LOCATIONS):
        url = get_url_for_location(loc)
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{url}" target="_blank">{loc}</a></div>'
    return render_template_string(wrap_grid_page("Today's Suprabhaatham ePaper Links", cards))

@app.route('/njayar')
def show_njayar_archive():
    start_date = datetime.date(2019, 1, 6)
    today = datetime.date.today()
    cutoff = datetime.date(2024, 6, 30)
    sundays = []
    current = start_date
    while current <= today:
        if current >= cutoff:
            sundays.append(current)
        current += datetime.timedelta(days=7)

    cards = ""
    for i, d in enumerate(reversed(sundays)):
        url = get_url_for_location("Njayar Prabhadham", d)
        date_str = d.strftime('%Y-%m-%d')
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{url}" target="_blank" rel="noopener noreferrer">{date_str}</a></div>'
    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

@app.route('/malappuram/pages')
def show_malappuram_pages():
    if not os.path.exists(EPAPER_TXT):
        return "epaper.txt not found", 404

    try:
        with open(EPAPER_TXT, "r", encoding="utf-8") as f:
            data = json.load(f)

        pages = [entry for entry in data.get("data", []) if entry.get("Location") == "Malappuram"]

        if not pages:
            return "No pages found for Malappuram.", 404

        cards = ""
        for i, page in enumerate(sorted(pages, key=lambda x: x.get("PageNo", 0))):
            img_url = page.get("Image")
            page_no = page.get("PageNo", "N/A")
            date = page.get("Date", "")
            cards += f'<div class="card" style="background-color:{RGB_COLORS[i % len(RGB_COLORS)]};"><a href="{img_url}" target="_blank">Page {page_no}<br><small>{date}</small></a></div>'

        return render_template_string(wrap_grid_page("Malappuram - All Pages", cards))
    except Exception as e:
        return f"Error: {e}", 500

def auto_update_quiz():
    """Background task to regenerate quiz daily."""
    while True:
        try:
            print("Generating latest quiz from RSS feed...")
            quiz = generate_quiz()
            print(f"Quiz updated successfully at {datetime.datetime.now()}")
        except Exception as e:
            print(f"[Error updating quiz] {e}")
        time.sleep(86400)  # Wait 24 hours


@app.route('/quiz')
def show_quiz():
    if not os.path.exists(QUIZ_JSON):
        quiz = generate_quiz()
    else:
        with open(QUIZ_JSON, "r", encoding="utf-8") as f:
            quiz = json.load(f)

    quiz_json = json.dumps(quiz)

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Current Affairs Quiz</title>
        <style>
            body {{
                font-family: 'Segoe UI', sans-serif;
                background: #f0f2f5;
                margin: 0;
                padding: 30px 10px;
                color: #333;
                text-align: center;
            }}
            h1 {{
                font-size: 1.8em;
                margin-bottom: 20px;
            }}
            .quiz-box {{
                background: white;
                padding: 20px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                max-width: 600px;
                margin: 0 auto;
            }}
            .question {{
                font-size: 1.1em;
                margin-bottom: 15px;
            }}
            .options button {{
                display: block;
                width: 100%;
                margin: 8px 0;
                padding: 10px;
                font-size: 1em;
                border: none;
                border-radius: 8px;
                background: #e4e4e4;
                cursor: pointer;
                transition: background 0.2s;
            }}
            .options button:hover {{
                background: #d0d0d0;
            }}
            .correct {{
                background: #6BCB77 !important;
                color: white;
            }}
            .wrong {{
                background: #FF6B6B !important;
                color: white;
            }}
            .next-btn {{
                margin-top: 15px;
                background: #4D96FF;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                cursor: pointer;
                display: none;
            }}
            .next-btn:hover {{
                background: #3c7de6;
            }}
            .score-box {{
                display: none;
                background: #fff;
                padding: 20px;
                border-radius: 12px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                max-width: 400px;
                margin: 0 auto;
            }}
            a.back {{
                display: inline-block;
                margin-top: 30px;
                font-size: 1em;
                color: #555;
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <h1>📰 Current Affairs Quiz</h1>
        <div class="quiz-box" id="quiz-box">
            <div class="question" id="question"></div>
            <div class="options" id="options"></div>
            <button class="next-btn" id="next-btn">Next</button>
        </div>

        <div class="score-box" id="score-box">
            <h2>Your Score</h2>
            <p id="score-text"></p>
            <a class="back" href="/">Back to Home</a>
        </div>

        <script>
            const quizData = {quiz_json};
            let current = 0;
            let score = 0;

            const questionEl = document.getElementById('question');
            const optionsEl = document.getElementById('options');
            const nextBtn = document.getElementById('next-btn');
            const quizBox = document.getElementById('quiz-box');
            const scoreBox = document.getElementById('score-box');
            const scoreText = document.getElementById('score-text');

            function showQuestion() {{
                const q = quizData[current];
                questionEl.textContent = q.q;
                optionsEl.innerHTML = '';
                q.options.forEach(opt => {{
                    const btn = document.createElement('button');
                    btn.textContent = opt;
                    btn.onclick = () => selectAnswer(btn, q.answer);
                    optionsEl.appendChild(btn);
                }});
            }}

            function selectAnswer(btn, correctAnswer) {{
                const buttons = optionsEl.querySelectorAll('button');
                buttons.forEach(b => {{
                    b.disabled = true;
                    if (b.textContent === correctAnswer) b.classList.add('correct');
                }});
                if (btn.textContent === correctAnswer) {{
                    score++;
                }} else {{
                    btn.classList.add('wrong');
                }}
                nextBtn.style.display = 'block';
            }}

            nextBtn.onclick = () => {{
                current++;
                nextBtn.style.display = 'none';
                if (current < quizData.length) {{
                    showQuestion();
                }} else {{
                    showScore();
                }}
            }};

            function showScore() {{
                quizBox.style.display = 'none';
                scoreBox.style.display = 'block';
                scoreText.textContent = `You scored ${{score}} / ${{quizData.length}}`;
            }}

            showQuestion();
        </script>
    </body>
    </html>
    """
    return html

# ------------------ Main ------------------

if __name__ == '__main__':
    threading.Thread(target=update_epaper_json, daemon=True).start()
    threading.Thread(target=auto_update_quiz, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)