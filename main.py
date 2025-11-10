import os
import time
import json
import feedparser
import threading
import datetime
import requests
import brotli
import re
from flask import Flask, render_template_string, Response, request, abort, redirect
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

app = Flask(__name__)

# -------------------- Config --------------------
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

TELEGRAM_CHANNELS = {
    "Pathravarthakal": "https://t.me/s/Pathravarthakal",
    "DailyCa": "https://t.me/s/DailyCAMalayalam"
}
XML_FOLDER = "telegram_xml"
os.makedirs(XML_FOLDER, exist_ok=True)

# 🎧 YouTube Playlists
PLAYLISTS = {
    "std10": "https://youtube.com/playlist?list=PLFMb-2_G0bMZMOWz-RvR9dk2Sj0UUnQTZ",
    
}

# ------------------ Utility ------------------
def get_url_for_location(location, dt_obj=None):
    if dt_obj is None:
        dt_obj = datetime.datetime.now()
    date_str = dt_obj.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

# ------------------ Threads ------------------
def update_epaper_json():
    url = "https://api2.suprabhaatham.com/api/ePaper"
    headers = {"Content-Type": "application/json", "Accept-Encoding": "br"}
    while True:
        try:
            print("Fetching latest ePaper data...")
            r = requests.post(url, json={}, headers=headers, timeout=10)
            if r.headers.get('Content-Encoding') == 'br':
                data = brotli.decompress(r.content).decode('utf-8')
            else:
                data = r.text
            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(data)
            print("✅ epaper.txt updated successfully.")
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")
        time.sleep(8640)

def fetch_telegram_xml(name, url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        rss_root = ET.Element("rss", version="2.0")
        ch = ET.SubElement(rss_root, "channel")
        ET.SubElement(ch, "title").text = f"{name} Telegram Feed"
        for msg in soup.select(".tgme_widget_message_wrap")[:40]:
            date_tag = msg.select_one("a.tgme_widget_message_date")
            link = date_tag["href"] if date_tag and "href" in date_tag.attrs else url
            text_tag = msg.select_one(".tgme_widget_message_text")
            desc_html = text_tag.decode_contents() if text_tag else ""
            item = ET.SubElement(ch, "item")
            title_text = BeautifulSoup(desc_html, "html.parser").get_text(strip=True)
            ET.SubElement(item, "title").text = title_text[:80] + ("..." if len(title_text) > 80 else "")
            ET.SubElement(item, "link").text = link
            ET.SubElement(item, "description").text = desc_html
        ET.ElementTree(rss_root).write(os.path.join(XML_FOLDER, f"{name}.xml"), encoding="utf-8", xml_declaration=True)
    except Exception as e:
        print(f"[Error fetching {name}] {e}")

def telegram_updater():
    while True:
        for name, url in TELEGRAM_CHANNELS.items():
            fetch_telegram_xml(name, url)
        time.sleep(600)

# ------------------ Browser ------------------
@app.route("/browse")
def browse():
    url = request.args.get("url", "")
    if not url:
        return "<p>No URL provided.</p>", 400
    if not re.match(r"^https?://", url):
        url = "https://" + url
    return f"""
    <!DOCTYPE html><html><head>
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>{url}</title>
    <style>
        body{{margin:0;background:#000;height:100vh;display:flex;flex-direction:column;}}
        iframe{{border:none;flex:1;width:100%;}}
        .topbar{{background:#111;color:white;display:flex;align-items:center;padding:6px;gap:8px;font-family:sans-serif;}}
        input[type=text]{{flex:1;padding:6px;border-radius:4px;border:none;outline:none;}}
        button{{background:#0078cc;color:white;border:none;padding:6px 10px;border-radius:4px;}}
    </style></head>
    <body>
        <div class="topbar">
            <form style="display:flex;flex:1;" onsubmit="go(event)">
                <input type="text" id="addr" value="{url}" placeholder="Enter URL...">
                <button>Go</button>
            </form>
            <button onclick="home()">🏠</button>
        </div>
        <iframe src="{url}"></iframe>
        <script>
            function go(e){{e.preventDefault();window.location='/browse?url='+encodeURIComponent(document.getElementById('addr').value);}}
            function home(){{window.location='/';}}
        </script>
    </body></html>
    """

# ------------------ Telegram HTML ------------------
@app.route("/telegram/<channel_name>")
def telegram_html(channel_name):
    if channel_name not in TELEGRAM_CHANNELS:
        return f"<p>Error: Channel '{channel_name}' not found.</p>", 404
    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")
    refresh_now = request.args.get("refresh") == "1"
    if refresh_now or not os.path.exists(path) or (time.time() - os.path.getmtime(path) > 120):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])
    try:
        feed = feedparser.parse(path)
        feed.entries.reverse()
        posts = ""
        for e in feed.entries[:50]:
            link = e.get("link", TELEGRAM_CHANNELS[channel_name])
            desc_html = e.get("description", "").strip()
            soup = BeautifulSoup(desc_html, "html.parser")
            for tag in soup.find_all(["video","iframe","source","audio","svg","poll","button","script","style"]):
                tag.decompose()
            img_tag = soup.find("img")
            text_only = soup.get_text(strip=True)
            if not text_only and not img_tag: continue
            content_html = ""
            if img_tag: content_html += f"<img src='{img_tag['src']}' loading='lazy'>"
            if text_only: content_html += f"<p>{text_only}</p>"
            posts += f"<div class='post'><a href='{link}' target='_blank'>{content_html}</a></div>"
        last_updated = datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
        return f"""
        <html><head><meta name='viewport' content='width=device-width,initial-scale=1.0'>
        <title>{channel_name}</title>
        <style>
            body{{font-family:sans-serif;background:#f5f6f7;margin:0;padding:10px;}}
            .post{{background:#fff;margin:12px 0;padding:12px;border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,0.08);}}
            img{{width:100%;border-radius:10px;margin-bottom:8px;}}
            p{{color:#333;font-size:0.95em;}}
        </style></head>
        <body><h2>{channel_name}</h2><div>{posts or '<p>No posts</p>'}</div>
        <p><a href='/'>🏠 Home</a></p></body></html>
        """
    except Exception as e:
        return f"<p>Error loading feed: {e}</p>"

# ------------------ ePaper ------------------
@app.route("/today")
def today_links():
    cards = ""
    for i, loc in enumerate(LOCATIONS):
        url = get_url_for_location(loc)
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background:{color}"><a href="/browse?url={url}">{loc}</a></div>'
    return render_template_string(wrap_home("Today's Editions", cards))

@app.route("/njayar")
def njayar_archive():
    cutoff = datetime.date(2024, 6, 30)
    today = datetime.date.today()
    sundays = []
    d = cutoff
    while d.weekday() != 6:
        d += datetime.timedelta(days=1)
    while d <= today:
        sundays.append(d)
        d += datetime.timedelta(days=7)
    cards = ""
    for i, d in enumerate(reversed(sundays)):
        url = get_url_for_location("Njayar Prabhadham", d)
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background:{color}"><a href="/browse?url={url}">{d}</a></div>'
    return render_template_string(wrap_home("Njayar Prabhadham - Sundays", cards))

# ------------------ Home ------------------
def wrap_home(title, inner):
    return f"""<html><body><p><a href='/'>🏠 Home</a></p><h1>{title}</h1><div>{inner}</div></body></html>"""

@app.route("/")
def homepage():
    BUILTIN_LINKS = [
        {"name": "Today's ePaper", "url": "/today", "icon": "📰"},
        {"name": "Njayar ePaper", "url": "/njayar", "icon": "🗓️"},
        {"name": "Pathravarthakal", "url": "/telegram/Pathravarthakal", "icon": "📣"},
        {"name": "DailyCa", "url": "/telegram/DailyCa", "icon": "🗞️"},
        {"name": "GitHub", "url": "https://github.com/", "icon": "🐙"},
        {"name": "Mobile TV", "url": "https://capitalist-anthe-pscj-4a28f285.koyeb.app/", "icon": "📺"},
        {"name": "VRadio", "url": "https://likely-zelda-junction-66aa4be8.koyeb.app/", "icon": "📻"},
        {"name": "Koyeb", "url": "https://app.koyeb.com/", "icon": "💎"},
        {"name": "ChatGPT", "url": "https://chatgpt.com/auth/login", "icon": "🤖"},
    ]
    link_html = []
    for x in BUILTIN_LINKS:
        target_attr = 'target="_blank"' if x['url'].startswith('http') else 'target="_self"'
        final_url = f"/browse?url={x['url']}" if x['url'].startswith('http') and not any(r in x['url'] for r in ["koyeb.app", "koyeb.com"]) else x['url']
        link_html.append(f'<div class="card"><div class="icon">{x["icon"]}</div><a href="{final_url}" {target_attr}>{x["name"]}</a></div>')
    playlist_cards = "".join(f'<div class="card"><div class="icon">🎧</div><a href="/stream/{k}">{k.capitalize()}</a></div>' for k in PLAYLISTS)
    html = f"""
    <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>Lite Browser</title>
    <style>
        body{{font-family:sans-serif;background:#f7f8fa;padding:20px;}}
        .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:15px;}}
        .card{{background:white;border-radius:15px;box-shadow:0 2px 6px rgba(0,0,0,0.1);
               text-align:center;padding:15px;transition:.2s;}}
        .card:hover{{transform:scale(1.04);}}
        .icon{{font-size:2em;margin-bottom:8px;}}
        a{{text-decoration:none;color:#111;font-weight:600;}}
        h2{{margin:10px 0;}}
    </style></head><body>
        <h1>Lite Browser</h1>
        <h2>🎧 YouTube Playlists</h2>
        <div class="grid">{playlist_cards}</div>
        <h2>🌐 Shortcuts</h2>
        <div class="grid">{''.join(link_html)}</div>
    </body></html>
    """
    return html

@app.route("/stream/<name>")
def stream(name):
    if name not in PLAYLISTS:
        return redirect("/")
    url = PLAYLISTS[name]
    embed = url.replace("playlist?", "embed/videoseries?")
    return f"""
    <html><head><meta name='viewport' content='width=device-width,initial-scale=1.0'>
    <title>{name.capitalize()} Radio</title>
    <style>
        body{{margin:0;background:#000;color:#fff;text-align:center;}}
        iframe{{width:100%;height:90vh;border:none;}}
    </style></head>
    <body>
        <h2>🎧 {name.capitalize()} Playlist</h2>
        <iframe src="{embed}" allow="autoplay; encrypted-media"></iframe>
        <p><a href="/" style="color:#0af;">🏠 Back</a></p>
    </body></html>
    """

# ------------------ Run ------------------
if __name__ == "__main__":
    threading.Thread(target=update_epaper_json, daemon=True).start()
    threading.Thread(target=telegram_updater, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)