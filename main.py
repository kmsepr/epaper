import os
import time
import json
import feedparser
import threading
import datetime
import requests
import brotli
import re
from flask import Flask, render_template_string, Response, request
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

            if response.headers.get('Content-Encoding') == 'br':
                data = brotli.decompress(response.content).decode('utf-8')
            else:
                data = response.text

            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(data)
            print("✅ epaper.txt updated successfully.")
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")
        time.sleep(8640)

# ------------------ Telegram RSS (self-hosted) ------------------
@app.route("/Pathravarthakal/rss")
def telegram_rss():
    """Generate RSS feed directly from Telegram channel with images."""
    channel = "Pathravarthakal"
    cache_life = 600  # 10 minutes cache
    now = time.time()

    # Serve cached feed
    if telegram_cache["rss"] and now - telegram_cache["time"] < cache_life and "refresh" not in request.args:
        return Response(telegram_cache["rss"], mimetype="application/rss+xml")

    try:
        url = f"https://t.me/s/{channel}"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        items = []
        for msg in soup.select(".tgme_widget_message_wrap")[:25]:
            date_tag = msg.select_one("a.tgme_widget_message_date")
            link = date_tag["href"] if date_tag else f"https://t.me/{channel}"
            text_tag = msg.select_one(".tgme_widget_message_text")
            title = (text_tag.text.strip()[:80] + "...") if text_tag else "Telegram Post"
            desc = str(text_tag) if text_tag else ""

            # Extract image or video thumbnail
            img_url = None
            style_tag = msg.select_one("a.tgme_widget_message_photo_wrap")
            if style_tag and "style" in style_tag.attrs:
                m = re.search(r"url\\(['\"]?(.*?)['\"]?\\)", style_tag["style"])
                if m:
                    img_url = m.group(1)

            # Fallback: img tag
            if not img_url:
                img_tag = msg.select_one("img")
                if img_tag and img_tag.get("src"):
                    img_url = img_tag["src"]

            # Add image to description
            if img_url:
                desc = f'<img src="{img_url}" width="100%"><br>{desc}'

            item = f"""
            <item>
                <title><![CDATA[{title}]]></title>
                <link>{link}</link>
                <guid>{link}</guid>
                <description><![CDATA[{desc}]]></description>
                {"<enclosure url='"+img_url+"' type='image/jpeg' />" if img_url else ""}
            </item>
            """
            items.append(item)

        rss = f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
        <channel>
            <title>Pathravarthakal Telegram Feed</title>
            <link>https://t.me/{channel}</link>
            <description>Latest posts from @{channel}</description>
            {''.join(items)}
        </channel>
        </rss>"""

        telegram_cache["rss"] = rss
        telegram_cache["time"] = now
        return Response(rss, mimetype="application/rss+xml")

    except Exception as e:
        return f"<p>Error generating Telegram RSS: {e}</p>", 500

# ------------------ Telegram Web View ------------------
@app.route("/telegram")
def telegram_feed_view():
    """Visual web page for Pathravarthakal feed (uses /Pathravarthakal/rss)."""
    feed_url = request.url_root.rstrip("/") + "/Pathravarthakal/rss"
    html = f"""
    <!DOCTYPE html>
    <html lang="ml">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>📰 Pathravarthakal Feed</title>
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
            .btn {{
                background: #0078cc;
                color: white;
                padding: 8px 12px;
                border-radius: 6px;
                text-decoration: none;
                font-size: 0.9em;
            }}
            iframe {{
                width: 100%;
                height: 85vh;
                border: none;
                background: white;
                border-radius: 8px;
            }}
        </style>
    </head>
    <body>
        <h1>📰 Pathravarthakal Feed</h1>
        <div class="topbar">
            <a href="/Pathravarthakal/rss?refresh=1" class="btn">🔄 Refresh RSS</a>
            <a href="/" class="btn" style="background:#555;">🏠 Home</a>
        </div>
        <iframe src="{feed_url}"></iframe>
    </body>
    </html>
    """
    return html

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