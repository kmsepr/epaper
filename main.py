import os
import time
import json
import threading
import datetime
import requests
import brotli
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

# ------------------ Telegram ------------------
@app.route("/telegram")
def telegram_feed():
    """RSS feed output from Telegram channel"""
    channel_url = "https://t.me/s/Pathravarthakal"
    now = time.time()

    # cache for 10 minutes
    if telegram_cache.get("rss") and now - telegram_cache.get("time", 0) < 600:
        return Response(telegram_cache["rss"], mimetype="application/rss+xml")

    try:
        html = requests.get(channel_url, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")

        items = []
        for post in soup.select(".tgme_widget_message_wrap"):
            title_el = post.select_one(".tgme_widget_message_text")
            img_el = post.select_one("a.tgme_widget_message_photo_wrap img")
            link_el = post.select_one("a.tgme_widget_message_date")
            date_el = post.select_one("time")

            title = title_el.get_text(strip=True) if title_el else "(No text)"
            link = link_el["href"] if link_el else channel_url
            pub_date = date_el["datetime"] if date_el else datetime.datetime.utcnow().isoformat()
            img_url = img_el["src"] if img_el else ""

            desc = title
            if img_url:
                desc += f'<br><img src="{img_url}" style="max-width:100%">'

            items.append({
                "title": title,
                "link": link,
                "pubDate": pub_date,
                "description": desc,
                "image": img_url
            })

        # Keep only the latest 30
        latest_items = items[:30]

        rss_items = "\n".join(
            f"""
            <item>
                <title><![CDATA[{i['title']}]]></title>
                <link>{i['link']}</link>
                <pubDate>{i['pubDate']}</pubDate>
                <description><![CDATA[{i['description']}]]></description>
                {f'<enclosure url="{i["image"]}" type="image/jpeg" />' if i["image"] else ""}
                {f'<media:content url="{i["image"]}" medium="image" />' if i["image"] else ""}
            </item>
            """ for i in latest_items
        )

        rss = f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"
             xmlns:media="http://search.yahoo.com/mrss/">
          <channel>
            <title>Pathravarthakal Telegram Feed</title>
            <link>{channel_url}</link>
            <description>Latest updates from the Pathravarthakal Telegram channel.</description>
            <language>ml</language>
            <lastBuildDate>{datetime.datetime.utcnow().isoformat()}</lastBuildDate>
            {rss_items}
          </channel>
        </rss>"""

        telegram_cache["rss"] = rss
        telegram_cache["time"] = now

        return Response(rss, mimetype="application/rss+xml")

    except Exception as e:
        return f"Error fetching Telegram feed: {e}", 500

# ------------------ Routes ------------------
@app.route('/')
def homepage():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("Telegram Feed", "/telegram")
    ]
    cards = ""
    for i, (label, link) in enumerate(links):
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{link}">{label}</a></div>'
    return render_template_string(wrap_grid_page("Suprabhaatham ePaper & Telegram", cards, show_back=False))

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