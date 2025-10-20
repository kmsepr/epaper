import os
import time
import threading
import datetime
import requests
import re
from flask import Flask, render_template_string, Response, request
from bs4 import BeautifulSoup
import feedparser

# -------------------- Config --------------------
app = Flask(__name__)
UPLOAD_FOLDER = "static"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

LOCATIONS = [
    "Kozhikode", "Malappuram", "Kannur", "Thrissur",
    "Kochi", "Thiruvananthapuram", "Palakkal", "Gulf"
]
RGB_COLORS = [
    "#FF6B6B", "#6BCB77", "#4D96FF", "#FFD93D",
    "#FF6EC7", "#00C2CB", "#FFA41B", "#845EC2"
]

telegram_cache = {}
feed_cache = {}

CHANNELS = {
    "Pathravarthakal": "https://t.me/s/Pathravarthakal",
}

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

# ------------------ Telegram RSS Fetcher ------------------
def fetch_telegram_rss(channel):
    """Fetch latest Telegram posts and cache them."""
    try:
        url = CHANNELS[channel]
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        items = []
        for i, msg in enumerate(soup.select(".tgme_widget_message_wrap")[:40]):
            date_tag = msg.select_one("a.tgme_widget_message_date")
            link = date_tag["href"] if date_tag else f"https://t.me/{channel}"
            text_tag = msg.select_one(".tgme_widget_message_text")
            full_text = text_tag.text.strip().replace('\n', ' ') if text_tag else ""
            title = (full_text[:80].rsplit(' ', 1)[0] + "...") if len(full_text) > 80 else full_text

            # Image
            img_url = None
            style_tag = msg.select_one("a.tgme_widget_message_photo_wrap")
            if style_tag and "style" in style_tag.attrs:
                m = re.search(r"url['\"]?(.*?)['\"]?", style_tag["style"])
                if m: img_url = m.group(1)
            if not img_url:
                img_tag = msg.select_one("img")
                if img_tag and img_tag.get("src"): img_url = img_tag["src"]

            desc_html = f"<p>{full_text}</p>"
            if img_url:
                desc_html = f'<img src="{img_url}" style="max-width:600px;width:100%;height:auto;margin-bottom:10px;"><br>{desc_html}'

            local_link = f"/post/{i}?channel={channel}"
            items.append({"title": title, "link": local_link, "guid": link, "description": desc_html, "image": img_url})

        items.reverse()  # Latest first

        rss_items = ""
        for item in items:
            rss_items += f"""
            <item>
                <title>{item['title']}</title>
                <link>{request.url_root.rstrip('/')}{item['link']}</link>
                <guid>{item['guid']}</guid>
                <description><![CDATA[{item['description']}]]></description>
                {'<media:content url="' + item['image'] + '" medium="image" />' if item['image'] else ''}
            </item>"""

        rss = f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
        <channel>
            <title>{channel} Telegram Feed</title>
            <link>{CHANNELS[channel]}</link>
            <description>Latest posts from @{channel}</description>
            {rss_items}
        </channel>
        </rss>"""

        telegram_cache[channel] = {"xml": rss, "items": items, "time": time.time()}
        print(f"✅ Cached RSS for {channel}")

    except Exception as e:
        print(f"[Error fetching {channel} RSS] {e}")

def background_fetch():
    """Continuously fetch RSS for all channels in background."""
    while True:
        for channel in CHANNELS:
            fetch_telegram_rss(channel)
        time.sleep(600)  # every 10 minutes

# ------------------ Routes ------------------
@app.route('/')
def homepage():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("Pathravarthakal Feed", "/Pathravarthakal"),
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
        if current >= cutoff: sundays.append(current)
        current -= datetime.timedelta(days=7)

    cards = ""
    for i, d in enumerate(sundays):
        url = get_url_for_location("Njayar Prabhadham", d)
        date_str = d.strftime('%Y-%m-%d')
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{url}" target="_blank">{date_str}</a></div>'
    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

@app.route("/telegram/<channel>")
def telegram_rss(channel):
    if channel not in CHANNELS:
        return Response(f"<error>Channel not configured</error>", mimetype="application/rss+xml")
    if channel not in telegram_cache:
        fetch_telegram_rss(channel)
    return Response(telegram_cache[channel]["xml"], mimetype="application/rss+xml")

@app.route("/<channel>")
def show_channel_feed(channel):
    if channel not in CHANNELS: return "<p>Channel not found.</p>"
    if channel not in telegram_cache: fetch_telegram_rss(channel)

    html_items = ""
    for i, entry in enumerate(telegram_cache[channel]["items"]):
        html_items += f"""
        <div style='margin:10px;padding:10px;background:#fff;border-radius:12px;
                    box-shadow:0 2px 6px rgba(0,0,0,0.1);text-align:left;'>
            <h3><a href="/post/{i}?channel={channel}" style="color:#0078cc;text-decoration:none;">{entry['title']}</a></h3>
            <div style="color:#444;font-size:15px;">{entry['description']}</div>
        </div>"""
    return f"""
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{channel} Feed</title></head>
    <body style="font-family:sans-serif;background:#f5f7fa;margin:0;padding:10px;">
        <h2 style="text-align:center;color:#0078cc;">📰 {channel} Telegram Feed</h2>
        <div style="max-width:600px;margin:auto;">{html_items}</div>
        <p style="text-align:center;">📡 RSS: <a href="/telegram/{channel}" target="_blank">Link</a></p>
        <p style="text-align:center;"><a href="/" style="color:#0078cc;">🏠 Back to Home</a></p>
    </body>
    </html>
    """

@app.route("/post/<int:index>")
def show_post(index):
    channel = request.args.get("channel")
    if not channel or channel not in telegram_cache or index >= len(telegram_cache[channel]["items"]):
        return f"<p>Post not found. <a href='/{channel}'>Reload feed</a></p>"

    entry = telegram_cache[channel]["items"][index]
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{entry['title']}</title>
        <style>
            body {{font-family: 'Segoe UI', sans-serif;background:#f5f7fa;margin:0;padding:15px;color:#333;}}
            .container {{max-width:700px;margin:auto;background:#fff;border-radius:12px;
                        box-shadow:0 2px 8px rgba(0,0,0,0.1);padding:20px;}}
            h2 {{color:#0078cc;margin-top:0;font-size:1.3em;line-height:1.4;}}
            img {{width:100%;border-radius:12px;margin:15px 0;}}
            a {{color:#0078cc;text-decoration:none;}}
            .desc {{font-size:16px;line-height:1.5;color:#444;}}
            .footer {{text-align:center;margin-top:25px;font-size:0.9em;}}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>{entry['title']}</h2>
            {f'<img src="{entry["image"]}">' if entry["image"] else ''}
            <div class="desc">{entry['description']}</div>
            <div class="footer">
                <p><a href="/{channel}">← Back to Feed</a> |
                   <a href="{entry['link']}" target="_blank">🔗 Open Original</a></p>
            </div>
        </div>
    </body>
    </html>
    """

# ------------------ Main ------------------
if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    threading.Thread(target=background_fetch, daemon=True).start()
    app.run