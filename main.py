# main.py
import os
import random
import time
import json
import threading
import datetime
import requests
import brotli
import feedparser
import openai
from flask import Flask, render_template_string

# -------------------- Config --------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # change to "gpt-4-turbo" if available
openai.api_key = OPENAI_API_KEY

# Flask app
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
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            body {{font-family: 'Segoe UI', sans-serif;background:#f0f2f5;margin:0;padding:40px 20px;color:#333;text-align:center;}}
            h1 {{font-size:2em;margin-bottom:30px;}}
            .grid {{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:20px;max-width:1000px;margin:auto;}}
            .card {{padding:25px 15px;border-radius:16px;box-shadow:0 2px 8px rgba(0,0,0,0.1);transition:transform .2s;}}
            .card:hover {{transform:translateY(-4px);}}
            .card a {{text-decoration:none;font-size:1.1em;color:#fff;font-weight:bold;display:block;}}
            a.back {{display:inline-block;margin-top:40px;font-size:1em;color:#555;text-decoration:underline;}}
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
            print("✅ epaper.txt updated successfully.")
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")
        time.sleep(86400)

# ------------------ News & Quiz Helpers ------------------

RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms",
    "https://www.thehindu.com/news/national/feeder/default.rss"
]

def fetch_latest_headlines(max_per_feed=5, total_max=30):
    """Fetch headlines from configured RSS feeds. Return up to total_max headlines."""
    headlines = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:max_per_feed]:
                title = entry.get("title") or entry.get("summary") or ""
                if title:
                    headlines.append(title.strip())
        except Exception as e:
            print(f"[Error fetching {feed_url}] {e}")
    # Deduplicate and trim
    unique = []
    for h in headlines:
        if h not in unique:
            unique.append(h)
        if len(unique) >= total_max:
            break
    if not unique:
        # fallback headlines (will be used to generate questions when feeds fail)
        unique = [
            "India wins a major cricket tournament",
            "ISRO launches a new satellite",
            "Government announces a new education policy",
            "Nobel Prize ceremony announces winners"
        ]
    return unique

def ask_openai_for_mcq(headline, model=OPENAI_MODEL, max_retries=2):
    """
    Ask OpenAI to convert a headline into a specific MCQ with 4 options.
    Returns dict {question, options, answer} or None on failure.
    """
    if not OPENAI_API_KEY:
        print("[OpenAI] API key not set — skipping AI generation.")
        return None

    prompt = (
        "Turn the following news headline into a single, specific multiple-choice question (one correct answer) "
        "suitable for current affairs quizzes. Avoid vague 'which field' questions. Produce exactly 4 options. "
        "Return only valid JSON with keys: question, options (list of 4 strings), answer (exact option text that is correct).\n\n"
        f"Headline: {headline}\n\n"
        "Example output:\n"
        '{\"question\": \"Who won the Nobel Peace Prize in 2023?\", \"options\": [\"A\",\"B\",\"C\",\"D\"], \"answer\": \"C\"}\n\n"
        "Now produce the JSON for the headline above."
    )

    for attempt in range(max_retries + 1):
        try:
            resp = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=400
            )
            text = resp.choices[0].message.get("content", "").strip()
            # Attempt to find JSON inside text (some models may return surrounding text)
            # Try direct load; if fails, try to extract first {...}
            try:
                data = json.loads(text)
            except Exception:
                # extract the first JSON object in the response
                start = text.find("{")
                end = text.rfind("}") + 1
                if start != -1 and end != -1:
                    snippet = text[start:end]
                    data = json.loads(snippet)
                else:
                    raise
            # Validate structure
            if isinstance(data, dict) and "question" in data and "options" in data and "answer" in data:
                if isinstance(data["options"], list) and len(data["options"]) == 4:
                    return {
                        "question": data["question"].strip(),
                        "options": [opt.strip() for opt in data["options"]],
                        "answer": data["answer"].strip()
                    }
            print("[OpenAI] Response did not contain valid MCQ JSON — retrying.")
        except Exception as e:
            print(f"[OpenAI] attempt {attempt} error: {e}")
            time.sleep(1 + attempt * 2)
    return None

def local_mcq_fallback(headline, idx):
    """If OpenAI isn't available or fails, produce a template MCQ so quiz still works."""
    # Very simple heuristic-based fallback
    lower = headline.lower()
    year = datetime.datetime.now().year
    if "nobel" in lower:
        q = f"Who won the Nobel Peace Prize in {year}?"
        opts = ["Médecins Sans Frontières", "Greta Thunberg", "WHO", "UNICEF"]
        correct = opts[0]
    elif "launch" in lower or "satellite" in lower or "mission" in lower:
        q = f"Which organization launched the mission described in the news?"
        opts = ["ISRO", "NASA", "ESA", "Roscosmos"]
        correct = random.choice(opts)
    elif "tournament" in lower or "cup" in lower or "match" in lower:
        q = "Which team won the event mentioned in news?"
        opts = ["India", "Australia", "England", "South Africa"]
        correct = random.choice(opts)
    elif "appointed" in lower or "resigned" in lower or "elected" in lower:
        q = "Who was mentioned in the leadership change reported?"
        opts = ["Narendra Modi", "Joe Biden", "Rishi Sunak", "Emmanuel Macron"]
        correct = random.choice(opts)
    else:
        q = f"What is a key fact from this headline: \"{headline}\"?"
        opts = ["Politics", "Sports", "Science", "Economy"]
        correct = random.choice(opts)

    random.shuffle(opts)
    return {"question": q, "options": opts, "answer": correct}

# ------------------ AI-driven Quiz Generation ------------------

def generate_quiz(num_questions=8, use_openai=True):
    """
    Generate quiz.json using live headlines + OpenAI (if available).
    Ensures num_questions MCQs (4 options each).
    """
    print("🧠 Generating current-affairs quiz...")
    headlines = fetch_latest_headlines()
    # Prefer randomness: sample headlines so daily variety is higher
    sampled = random.sample(headlines, min(len(headlines), max(num_questions * 2, 12)))
    quiz = []
    for i, headline in enumerate(sampled, start=1):
        if len(quiz) >= num_questions:
            break
        mcq = None
        if use_openai and OPENAI_API_KEY:
            mcq = ask_openai_for_mcq(headline)
        if not mcq:
            mcq = local_mcq_fallback(headline, i)
        # Sanity check: ensure 4 options and non-empty answer
        if mcq and isinstance(mcq.get("options"), list) and len(mcq["options"]) == 4 and mcq.get("answer"):
            # dedupe options and ensure answer in options
            opts = []
            for o in mcq["options"]:
                o = o.strip()
                if o not in opts and o != "":
                    opts.append(o)
            # if dedupe reduced to <4, pad with generic distractors
            while len(opts) < 4:
                filler = f"Option {len(opts)+1}"
                if filler not in opts:
                    opts.append(filler)
            # if answer not present, set first option as answer (fallback)
            answer = mcq["answer"].strip()
            if answer not in opts:
                opts[0] = answer
            random.shuffle(opts)
            quiz.append({
                "q": f"Q{len(quiz)+1}. {mcq['question']}",
                "options": opts,
                "answer": answer
            })
        else:
            # skip malformed and continue
            continue
        time.sleep(1)  # gentle pacing to avoid rate spikes

    # Ensure at least 5 questions exist
    if len(quiz) < 5:
        while len(quiz) < 5:
            fallback = local_mcq_fallback("Fallback headline", len(quiz)+1)
            quiz.append({
                "q": f"Q{len(quiz)+1}. {fallback['question']}",
                "options": fallback['options'],
                "answer": fallback['answer']
            })

    # Persist
    with open(QUIZ_JSON, "w", encoding="utf-8") as f:
        json.dump(quiz, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {len(quiz)} questions to {QUIZ_JSON}")
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
        cards += f'<div class="card" style="background-color:{color};"><a href="{url}" target="_blank">{date_str}</a></div>'
    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

@app.route('/quiz')
def show_quiz():
    # If quiz json missing or empty, generate now
    if not os.path.exists(QUIZ_JSON):
        quiz = generate_quiz()
    else:
        try:
            with open(QUIZ_JSON, "r", encoding="utf-8") as f:
                quiz = json.load(f)
            if not quiz:
                quiz = generate_quiz()
        except Exception:
            quiz = generate_quiz()

    quiz_json = json.dumps(quiz)
    # Same UI you had, but title updated
    return render_template_string(f"""
    <!DOCTYPE html><html lang="en"><head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Current Affairs Quiz</title>
    <style>
        body {{font-family:'Segoe UI',sans-serif;background:#f0f2f5;margin:0;padding:30px 10px;text-align:center;color:#333}}
        h1{{font-size:1.8em;margin-bottom:20px}}
        .quiz-box{{background:white;padding:20px;border-radius:12px;box-shadow:0 2px 10px rgba(0,0,0,0.1);max-width:600px;margin:0 auto}}
        .options button{{display:block;width:100%;margin:8px 0;padding:10px;border:none;border-radius:8px;background:#e4e4e4;cursor:pointer;font-size:1em}}
        .options button:hover{{background:#d0d0d0}}
        .correct{{background:#6BCB77!important;color:white}}
        .wrong{{background:#FF6B6B!important;color:white}}
        .next-btn{{margin-top:15px;background:#4D96FF;color:white;border:none;border-radius:8px;padding:10px 20px;display:none}}
        a.back{{display:inline-block;margin-top:30px;font-size:1em;color:#555;text-decoration:underline}}
    </style></head><body>
    <h1>📰 AI Current Affairs Quiz</h1>
    <div class="quiz-box" id="quiz-box"><div class="question" id="question"></div><div class="options" id="options"></div><button class="next-btn" id="next-btn">Next</button></div>
    <div class="score-box" id="score-box" style="display:none"><h2>Your Score</h2><p id="score-text"></p><a class="back" href="/">Back to Home</a></div>
    <script>
        const quizData = {quiz_json};
        let current=0,score=0;
        const questionEl=document.getElementById('question'),optionsEl=document.getElementById('options'),nextBtn=document.getElementById('next-btn'),quizBox=document.getElementById('quiz-box'),scoreBox=document.getElementById('score-box'),scoreText=document.getElementById('score-text');
        function showQuestion(){const q=quizData[current];questionEl.textContent=q.q;optionsEl.innerHTML='';q.options.forEach(opt=>{const btn=document.createElement('button');btn.textContent=opt;btn.onclick=()=>selectAnswer(btn,q.answer);optionsEl.appendChild(btn);});}
        function selectAnswer(btn,correct){const buttons=optionsEl.querySelectorAll('button');buttons.forEach(b=>{b.disabled=true;if(b.textContent===correct)b.classList.add('correct');});if(btn.textContent===correct)score++;else btn.classList.add('wrong');nextBtn.style.display='block'}
        nextBtn.onclick=()=>{current++;nextBtn.style.display='none';if(current<quizData.length)showQuestion();else{quizBox.style.display='none';scoreBox.style.display='block';scoreText.textContent=`You scored ${score} / ${quizData.length}`}};showQuestion();
    </script></body></html>
    """)

# ------------------ Background threads ------------------

def auto_update_quiz():
    while True:
        try:
            print("🔄 Auto updating daily quiz...")
            generate_quiz(num_questions=8, use_openai=True)
            print(f"✅ Quiz updated at {datetime.datetime.now()}")
        except Exception as e:
            print(f"[Error updating quiz] {e}")
        time.sleep(86400)

# ------------------ Main ------------------

if __name__ == '__main__':
    # start background threads
    threading.Thread(target=update_epaper_json, daemon=True).start()
    threading.Thread(target=auto_update_quiz, daemon=True).start()
    # run app
    app.run(host='0.0.0.0', port=8000)