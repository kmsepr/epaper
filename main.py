import os
import random
import time
import json
import threading
import datetime
import requests
import brotli
import feedparser
from openai import OpenAI
from flask import Flask, render_template_string

app = Flask(__name__)

UPLOAD_FOLDER = "static"
EPAPER_TXT = "epaper.txt"
QUIZ_JSON = "quiz.json"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ------------------ Config ------------------

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # Set OPENAI_API_KEY in your env

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
    headers = {"Content-Type": "application/json", "Accept-Encoding": "br"}
    while True:
        try:
            print("Fetching latest ePaper data...")
            response = requests.post(url, json={}, headers=headers, timeout=10)
            response.raise_for_status()
            data = brotli.decompress(response.content).decode('utf-8') if response.headers.get('Content-Encoding') == 'br' else response.text
            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(data)
            print("✅ epaper.txt updated successfully.")
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")
        time.sleep(86400)

# ------------------ AI Quiz Generator ------------------

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    "https://www.thehindu.com/news/national/feeder/default.rss"
]

def fetch_latest_headlines():
    headlines = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:5]:
                headlines.append(entry.title)
        except Exception as e:
            print(f"[Error fetching {feed_url}] {e}")
    if not headlines:
        headlines = ["India wins a major cricket tournament", "NASA launches a new space telescope"]
    return headlines[:10]

def ai_generate_question(headline):
    """Generate a 4-option quiz question from a news headline."""
    prompt = f"""
    You are a quiz generator. Based on the following news headline, create a factual multiple-choice question
    with exactly 4 options (one correct). Avoid vague questions like 'What field...'; make them specific, e.g.
    'Who won the Nobel Peace Prize in 2025?' or 'Which country launched this mission?'.

    Return output strictly as JSON:
    {{
        "question": "...",
        "options": ["A", "B", "C", "D"],
        "answer": "exact correct option text"
    }}

    Headline: {headline}
    """
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8
        )
        text = res.choices[0].message.content.strip()
        data = json.loads(text)
        if "question" in data and "options" in data:
            return data
    except Exception as e:
        print(f"[AI error] {e}")
    return None

def generate_quiz():
    print("🧠 Generating AI-based quiz...")
    headlines = fetch_latest_headlines()
    quiz = []
    for i, h in enumerate(headlines, 1):
        q = ai_generate_question(h)
        if q:
            quiz.append({
                "q": f"Q{i}. {q['question']}",
                "options": q["options"],
                "answer": q["answer"]
            })
        time.sleep(2)  # small delay to avoid rate limits

    if not quiz:
        quiz = [{
            "q": "Q1. Who won the Nobel Peace Prize in 2025?",
            "options": ["Médecins Sans Frontières", "Greta Thunberg", "WHO", "UNICEF"],
            "answer": "Médecins Sans Frontières"
        }]

    with open(QUIZ_JSON, "w", encoding="utf-8") as f:
        json.dump(quiz, f, indent=2, ensure_ascii=False)

    print(f"✅ {len(quiz)} AI quiz questions saved.")
    return quiz

# ------------------ Routes ------------------

@app.route('/')
def homepage():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("Current Affairs Quiz", "/quiz")
    ]
    cards = "".join(
        f'<div class="card" style="background-color:{RGB_COLORS[i%len(RGB_COLORS)]};"><a href="{link}">{label}</a></div>'
        for i, (label, link) in enumerate(links)
    )
    return render_template_string(wrap_grid_page("Suprabhaatham ePaper & Quiz", cards, show_back=False))

@app.route('/today')
def show_today_links():
    cards = "".join(
        f'<div class="card" style="background-color:{RGB_COLORS[i%len(RGB_COLORS)]};"><a href="{get_url_for_location(loc)}" target="_blank">{loc}</a></div>'
        for i, loc in enumerate(LOCATIONS)
    )
    return render_template_string(wrap_grid_page("Today's Suprabhaatham ePaper Links", cards))

@app.route('/njayar')
def show_njayar_archive():
    start_date = datetime.date(2019, 1, 6)
    today = datetime.date.today()
    cutoff = datetime.date(2024, 6, 30)
    sundays = [start_date + datetime.timedelta(days=7*i) for i in range(((today-start_date).days)//7 + 1)]
    sundays = [d for d in sundays if d >= cutoff]
    cards = "".join(
        f'<div class="card" style="background-color:{RGB_COLORS[i%len(RGB_COLORS)]};"><a href="{get_url_for_location("Njayar Prabhadham", d)}" target="_blank">{d.strftime("%Y-%m-%d")}</a></div>'
        for i, d in enumerate(reversed(sundays))
    )
    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

@app.route('/quiz')
def show_quiz():
    if not os.path.exists(QUIZ_JSON):
        quiz = generate_quiz()
    else:
        try:
            with open(QUIZ_JSON, "r", encoding="utf-8") as f:
                quiz = json.load(f)
        except:
            quiz = generate_quiz()

    quiz_json = json.dumps(quiz)
    return render_template_string(f"""
    <!DOCTYPE html><html lang="en"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Current Affairs Quiz</title>
    <style>
        body {{font-family:'Segoe UI',sans-serif;background:#f0f2f5;margin:0;padding:30px 10px;text-align:center;}}
        .quiz-box, .score-box {{background:white;padding:20px;border-radius:12px;max-width:600px;margin:auto;box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
        .options button {{display:block;width:100%;margin:8px 0;padding:10px;font-size:1em;border:none;border-radius:8px;background:#e4e4e4;cursor:pointer;}}
        .options button:hover{{background:#d0d0d0;}}
        .correct{{background:#6BCB77!important;color:white;}}
        .wrong{{background:#FF6B6B!important;color:white;}}
        .next-btn{{margin-top:15px;background:#4D96FF;color:white;border:none;border-radius:8px;padding:10px 20px;display:none;}}
        .next-btn:hover{{background:#3c7de6;}}
        a.back{{display:inline-block;margin-top:30px;font-size:1em;color:#555;text-decoration:underline;}}
    </style></head><body>
    <h1>📰 AI Current Affairs Quiz</h1>
    <div class="quiz-box" id="quiz-box"><div class="question" id="question"></div><div class="options" id="options"></div><button class="next-btn" id="next-btn">Next</button></div>
    <div class="score-box" id="score-box" style="display:none;"><h2>Your Score</h2><p id="score-text"></p><a class="back" href="/">Back to Home</a></div>
    <script>
    const quizData={quiz_json};let current=0,score=0;
    const qEl=document.getElementById('question'),oEl=document.getElementById('options'),nBtn=document.getElementById('next-btn'),
    qBox=document.getElementById('quiz-box'),sBox=document.getElementById('score-box'),sText=document.getElementById('score-text');
    function showQ(){{const q=quizData[current];qEl.textContent=q.q;oEl.innerHTML='';q.options.forEach(opt=>{{const b=document.createElement('button');b.textContent=opt;
    b.onclick=()=>sel(b,q.answer);oEl.appendChild(b);}});}}
    function sel(btn,ans){{oEl.querySelectorAll('button').forEach(b=>{{b.disabled=true;if(b.textContent===ans)b.classList.add('correct');}});
    if(btn.textContent===ans)score++;else btn.classList.add('wrong');nBtn.style.display='block';}}
    nBtn.onclick=()=>{{current++;nBtn.style.display='none';if(current<quizData.length)showQ();else{{qBox.style.display='none';sBox.style.display='block';sText.textContent=`You scored ${{score}} / ${{quizData.length}}`;}}}};
    showQ();
    </script></body></html>
    """)

# ------------------ Background Threads ------------------

def auto_update_quiz():
    while True:
        try:
            print("🔄 Regenerating daily AI quiz...")
            generate_quiz()
            print(f"✅ Quiz updated at {datetime.datetime.now()}")
        except Exception as e:
            print(f"[Error updating quiz] {e}")
        time.sleep(86400)

# ------------------ Main ------------------

if __name__ == '__main__':
    threading.Thread(target=update_epaper_json, daemon=True).start()
    threading.Thread(target=auto_update_quiz, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)