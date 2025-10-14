import os
import time
import json
import threading
import datetime
import requests
import brotli
import re
from flask import Flask, render_template_string, Response
from bs4 import BeautifulSoup

# -------------------- Config --------------------
app = Flask(__name__)
UPLOAD_FOLDER = "static"
EPAPER_TXT = "epaper.txt"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

LOCATIONS = [
    "Kozhikode", "Malappuram", "Kannur", "Thrissur",
    "Kochi", "Thiruvananthapuram", "Palakkal", "Gulf"
]
RGB_COLORS = [
    "#FF6B6B", "#6BCB77", "#4D96FF", "#FFD93D",
    "#FF6EC7", "#00C2CB", "#FFA41B", "#845EC2"
]

telegram_cache = {"rss": None, "time": 0}

# ------------------ Utility ------------------
def wrap_grid_page(title, items_html, show_back=True):
    back_html = '<p><a class="back" href="/">Back</a></p>' if show_back else ''
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

# ------------------ ePaper ------------------
def get_url_for_location(location, dt_obj=None):
    if dt_obj is None:
        dt_obj = datetime.datetime.now()
    date_str = dt_obj.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

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

# ------------------ Telegram Feed (HTML + RSS optional) ------------------
@app.route("/telegram")
def telegram_feed_view():
    """Visual viewer for the Pathravarthakal Telegram feed (default HTML view)."""
    channel_url = "https://t.me/s/Pathravarthakal"
    now = time.time()

    if telegram_cache.get("html") and now - telegram_cache["time"] < 600:
        return telegram_cache["html"]

    try:
        html = requests.get(channel_url, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")

        posts_html = ""
        for post in soup.select(".tgme_widget_message_wrap"):
            text_el = post.select_one(".tgme_widget_message_text")
            imgs = []

            # Try both <img> tags and background-image style
            for img in post.select("a.tgme_widget_message_photo_wrap img"):
                imgs.append(img["src"])
            for bg in post.select(".tgme_widget_message_photo_wrap"):
                if "style" in bg.attrs:
                    match = re.search(r"url\\('(.*?)'\\)", bg["style"])
                    if match:
                        imgs.append(match.group(1))

            date_el = post.select_one("time")
            link_el = post.select_one("a.tgme_widget_message_date")

            text = text_el.get_text("\n", strip=True) if text_el else ""
            date = date_el["datetime"] if date_el else ""
            link = link_el["href"] if link_el else channel_url

            # Build image grid
            img_tags = "".join(
                f'<img src="{src}" alt="Post image">' for src in imgs
            )

            if text or imgs:
                posts_html += f"""
                <div class="post">
                    <div class="text">{text}</div>
                    <div class="images">{img_tags}</div>
                    <div class="time">{date}</div>
                    <a href="{link}" target="_blank" class="button">🔗 Open in Telegram</a>
                </div>
                """

        html_page = f"""
        <!DOCTYPE html>
        <html lang="ml">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta http-equiv="refresh" content="300">
            <title>Pathravarthakal Telegram Feed</title>
            <style>
                body {{
                    font-family: system-ui, sans-serif;
                    background: #fafafa;
                    margin: 0;
                    padding: 15px;
                }}
                h1 {{
                    text-align: center;
                    color: #0088cc;
                }}
                .post {{
                    background: #fff;
                    border-radius: 10px;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
                    padding: 12px 15px;
                    margin-bottom: 16px;
                }}
                .text {{
                    font-size: 1em;
                    white-space: pre-wrap;
                }}
                .images {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                    gap: 6px;
                    margin-top: 8px;
                }}
                .images img {{
                    width: 100%;
                    border-radius: 6px;
                }}
                .time {{
                    font-size: 0.8em;
                    color: #777;
                    margin-top: 6px;
                }}
                .button {{
                    display: inline-block;
                    background: #0088cc;
                    color: white;
                    padding: 6px 10px;
                    border-radius: 6px;
                    text-decoration: none;
                    margin-top: 10px;
                    font-size: 0.9em;
                }}
                a.back {{
                    display:block;
                    text-align:center;
                    margin-top:30px;
                    text-decoration:underline;
                    color:#555;
                }}
            </style>
        </head>
        <body>
            <h1>📰 Pathravarthakal Telegram</h1>
            {posts_html if posts_html else "<p style='text-align:center;color:#777;'>No posts found.</p>"}
            <a class="back" href="/">← Back to Home</a>
        </body>
        </html>
        """

        telegram_cache["html"] = html_page
        telegram_cache["time"] = now
        return html_page

    except Exception as e:
        return f"<p>Error loading Telegram feed: {e}</p>", 500

# ------------------ Routes ------------------
@app.route('/')
def homepage():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("Pathravarthakal", "/telegram"),
    ]
    cards = ""
    for i, (label, link) in enumerate(links):
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{link}">{label}</a></div>'
    return render_template_string(wrap_grid_page("Suprabhaatham ePaper", cards, show_back=False))

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

# ------------------ Main ------------------
if __name__ == '__main__':
    threading.Thread(target=update_epaper_json, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)