import os
import time
import json
import threading
import datetime
import requests
import brotli
from flask import Flask, render_template_string
import random

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

# ---------------- GRID WRAPPER ----------------
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
            h1 {{ font-size: 2em; margin-bottom: 30px; }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 20px; max-width: 1000px; margin: auto;
            }}
            .card {{
                padding: 25px 15px; border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                transition: transform 0.2s ease;
            }}
            .card:hover {{ transform: translateY(-4px); }}
            .card a {{
                text-decoration: none; font-size: 1.1em;
                color: #fff; font-weight: bold; display: block;
            }}
            a.back {{ display: inline-block; margin-top: 40px; font-size: 1em; color: #555; text-decoration: underline; }}
            .question {{ text-align: left; margin: 20px auto; max-width: 700px; background: #fff; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            .options p {{ margin: 8px 0; }}
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        {items_html}
        {back_html}
    </body>
    </html>
    """

# ---------------- HOMEPAGE ----------------
@app.route('/')
def homepage():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("Malappuram Pages", "/malappuram/pages"),
        ("Current Affairs Quiz", "/quiz")
    ]
    cards = ""
    for i, (label, link) in enumerate(links):
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{link}">{label}</a></div>'
    return render_template_string(wrap_grid_page("Suprabhaatham ePaper & Quiz", f'<div class="grid">{cards}</div>', show_back=False))

# ---------------- TODAY LINKS ----------------
def get_url_for_location(location, dt_obj=None):
    if dt_obj is None:
        dt_obj = datetime.datetime.now()
    date_str = dt_obj.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

@app.route('/today')
def show_today_links():
    cards = ""
    for i, loc in enumerate(LOCATIONS):
        url = get_url_for_location(loc)
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{url}" target="_blank">{loc}</a></div>'
    return render_template_string(wrap_grid_page("Today's Suprabhaatham ePaper Links", f'<div class="grid">{cards}</div>'))

# ---------------- NJAYAR ----------------
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
    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", f'<div class="grid">{cards}</div>'))

# ---------------- UPDATE EPAPER JSON ----------------
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
                try:
                    decompressed_data = brotli.decompress(response.content).decode('utf-8')
                except Exception as e:
                    print(f"Error during Brotli decompression: {e}")
                    decompressed_data = response.text
            else:
                decompressed_data = response.text

            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(decompressed_data)

            print("epaper.txt updated successfully.")
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")

        time.sleep(86400)  # Wait for 24 hours

# ---------------- MALAPPURAM ----------------
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

        return render_template_string(wrap_grid_page("Malappuram - All Pages", f'<div class="grid">{cards}</div>'))
    except Exception as e:
        return f"Error: {e}", 500

# ---------------- QUIZ ----------------
def fetch_latest_news():
    """Get headlines from NewsAPI (replace NEWS_API_KEY with env var)"""
    api_key = os.getenv("NEWS_API_KEY", "demo")
    try:
        url = f"https://newsapi.org/v2/top-headlines?country=in&apiKey={api_key}"
        r = requests.get(url, timeout=10)
        return [a["title"] for a in r.json().get("articles", []) if "title" in a]
    except:
        return ["Parliament passes new education bill", "India wins cricket test match", "ISRO launches new satellite"]

def generate_quiz():
    headlines = fetch_latest_news()
    quiz = []
    for i, headline in enumerate(headlines[:10]):
        quiz.append({
            "q": f"Q{i+1}. What is the news about: {headline}?",
            "options": [
                "A. Related to Politics",
                "B. Related to Sports",
                "C. Related to Science/Tech",
                "D. Related to Economy"
            ],
            "answer": "Depends on headline"
        })
    with open(QUIZ_JSON, "w", encoding="utf-8") as f:
        json.dump(quiz, f, indent=2)
    return quiz

@app.route('/quiz')
def show_quiz():
    if not os.path.exists(QUIZ_JSON):
        quiz = generate_quiz()
    else:
        with open(QUIZ_JSON, "r", encoding="utf-8") as f:
            quiz = json.load(f)
    html = ""
    for q in quiz:
        html += f'<div class="question"><p><b>{q["q"]}</b></p><div class="options">'
        for opt in q["options"]:
            html += f"<p>{opt}</p>"
        html += "</div></div>"
    return render_template_string(wrap_grid_page("Current Affairs Quiz", html))

# ---------------- MAIN ----------------
if __name__ == '__main__':
    threading.Thread(target=update_epaper_json, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)
