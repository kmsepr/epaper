import os
import time
import json
import threading
import datetime
import requests
import brotli
import re
from flask import Flask, Response, render_template_string
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
        dt_obj = datetime.date.today()
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
        time.sleep(86400)

# ------------------ Telegram RSS Feed ------------------
@app.route("/feed/Pathravarthakal")
def telegram_rss():
    url = "https://t.me/s/Pathravarthakal"
    html = requests.get(url, timeout=10).text
    soup = BeautifulSoup(html, "html.parser")

    items = []
    for post in soup.select(".tgme_widget_message_wrap"):
        try:
            text_tag = post.select_one(".tgme_widget_message_text")
            title = text_tag.get_text(strip=True)[:120] if text_tag else "Pathravarthakal update"
            link_tag = post.select_one("a.tgme_widget_message_date")
            link = link_tag["href"] if link_tag else ""
            img_tag = post.select_one("img")
            img_url = img_tag["src"] if img_tag else None

            desc = f"<![CDATA[{str(text_tag)}]]>" if text_tag else ""
            img_part = f"<enclosure url='{img_url}' type='image/jpeg' length='0'/><media:content url='{img_url}' type='image/jpeg' medium='image' width='384'/>" if img_url else ""

            items.append(f"""
                <item>
                    <title><![CDATA[{title}]]></title>
                    <link>{link}</link>
                    <guid>{link}</guid>
                    <description>{desc}</description>
                    {img_part}
                </item>
            """)
        except Exception:
            continue

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
    <channel>
        <title>Pathravarthakal Telegram Feed</title>
        <link>{url}</link>
        <description>Latest posts from @Pathravarthakal Telegram channel</description>
        <language>ml</language>
        {''.join(items)}
    </channel></rss>"""

    return Response(rss, mimetype="application/rss+xml")

# ------------------ Routes ------------------
@app.route('/')
def homepage():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
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

    current = today
    while current.weekday() != 6:
        current -= datetime.timedelta(days=1)
    while current >= start_date:
        if current >= cutoff:
            sundays.append(current)
        current -= datetime.timedelta(days=7)

    cards = ""
    for i, d in enumerate(sundays):
        url = get_url_for_location("Njayar Prabhadham", d)
        date_str = d.strftime('%Y-%m-%d')
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{url}" target="_blank">{date_str}</a></div>'

    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

# ------------------ Main ------------------
if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    threading.Thread(target=update_epaper_json, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)