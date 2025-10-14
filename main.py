import os
import time
import json
import feedparser
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
        time.sleep(8640)

@app.route("/telegram")
def telegram_feed_view():
    """Display Pathravarthakal news via RSS feed with images."""
    rss_url = "https://cdn.mysitemapgenerator.com/shareapi/rss/14101528987"
    now = time.time()

    # Cache for 10 minutes unless manually refreshed
    refresh = "refresh" in flask.request.args
    if not refresh and telegram_cache.get("html") and now - telegram_cache["time"] < 600:
        return telegram_cache["html"]

    try:
        feed = feedparser.parse(rss_url)
        posts_html = ""

        # Limit to latest 50 posts
        entries = feed.entries[:50]

        for entry in entries:
            title = entry.get("title", "")
            link = entry.get("link", "#")
            date = entry.get("published", "")
            imgs = []

            if "media_content" in entry:
                imgs.extend(m.get("url", "") for m in entry.media_content)
            if "media_thumbnail" in entry:
                imgs.extend(m.get("url", "") for m in entry.media_thumbnail)

            img_tags = "".join(f'<img src="{src}" alt="Post image">' for src in imgs)

            posts_html += f"""
            <div class="post">
                <a href="{link}" target="_blank" class="title">{title}</a>
                <div class="images">{img_tags}</div>
                <div class="time">{date}</div>
            </div>
            """

        html_page = f"""
        <!DOCTYPE html>
        <html lang="ml">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta http-equiv="refresh" content="600">
            <title>📰 Pathravarthakal RSS Feed</title>
            <style>
                body {{
                    font-family: system-ui, sans-serif;
                    background: #f5f7fa;
                    margin: 0;
                    padding: 15px;
                    color: #333;
                }}
                h1 {{
                    text-align: center;
                    color: #0078cc;
                    margin-bottom: 12px;
                }}
                .topbar {{
                    display: flex;
                    justify-content: center;
                    gap: 10px;
                    margin-bottom: 20px;
                }}
                .refresh {{
                    display: inline-block;
                    background: #0078cc;
                    color: white;
                    padding: 8px 12px;
                    border-radius: 6px;
                    text-decoration: none;
                    font-size: 0.9em;
                }}
                .post {{
                    background: #fff;
                    border-radius: 10px;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.1);
                    padding: 12px 15px;
                    margin-bottom: 16px;
                    text-align: left;
                }}
                .title {{
                    font-size: 1.05em;
                    font-weight: 600;
                    color: #0078cc;
                    text-decoration: none;
                    display: block;
                    margin-bottom: 6px;
                    line-height: 1.4;
                }}
                .title:hover {{
                    text-decoration: underline;
                }}
                .images {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
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
            <h1>📰 Pathravarthakal RSS Feed</h1>
            <div class="topbar">
                <a href="/telegram?refresh=1" class="refresh">🔄 Refresh</a>
                <a href="/" class="refresh" style="background:#555;">🏠 Home</a>
            </div>
            {posts_html if posts_html else "<p style='text-align:center;color:#777;'>No posts found.</p>"}
        </body>
        </html>
        """

        telegram_cache["html"] = html_page
        telegram_cache["time"] = now
        return html_page

    except Exception as e:
        return f"<p>Error loading RSS feed: {e}</p>", 500

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
