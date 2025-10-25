import os
import time
import json
import feedparser
import threading
import datetime
import requests
import brotli
import re
from flask import Flask, render_template_string, Response, request, abort
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

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

# ------------------ Telegram Channels ------------------
TELEGRAM_CHANNELS = {
    "Pathravarthakal": "https://t.me/s/Pathravarthakal",
    "AnotherChannel": "https://t.me/s/AnotherChannel"
}
XML_FOLDER = "telegram_xml"
os.makedirs(XML_FOLDER, exist_ok=True)
telegram_cache = {}  # HTML cache per channel

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

            try:
                if response.headers.get('Content-Encoding') == 'br':
                    data = brotli.decompress(response.content).decode('utf-8')
                else:
                    data = response.text
            except Exception:
                data = response.text

            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(data)
            print("✅ epaper.txt updated successfully.")
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")
        time.sleep(8640)

# ------------------ Telegram XML & HTML ------------------
def fetch_telegram_xml(channel_name, url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        rss_root = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss_root, "channel")
        ET.SubElement(channel, "title").text = f"{channel_name} Telegram Feed"
        ET.SubElement(channel, "link").text = url
        ET.SubElement(channel, "description").text = f"Latest posts from @{channel_name}"

        for msg in soup.select(".tgme_widget_message_wrap")[:50]:
            date_tag = msg.select_one("a.tgme_widget_message_date")
            link = date_tag["href"] if date_tag else url
            text_tag = msg.select_one(".tgme_widget_message_text")
            desc_html = text_tag.decode_contents() if text_tag else ""
            pub_date = date_tag["datetime"] if date_tag and date_tag.has_attr("datetime") else ""

            item = ET.SubElement(channel, "item")
            ET.SubElement(item, "title").text = BeautifulSoup(desc_html, "html.parser").get_text(strip=True)[:80]
            ET.SubElement(item, "link").text = link
            ET.SubElement(item, "guid").text = link
            ET.SubElement(item, "description").text = desc_html
            ET.SubElement(item, "pubDate").text = pub_date

            image_url = None
            style_tag = msg.select_one("a.tgme_widget_message_photo_wrap")
            if style_tag and "style" in style_tag.attrs:
                m = re.search(r"url\(['\"]?(.*?)['\"]?\)", style_tag["style"])
                if m:
                    image_url = m.group(1)
            if not image_url:
                img_tag = msg.select_one("img")
                if img_tag:
                    image_url = img_tag.get("src") or img_tag.get("data-thumb")
            if image_url:
                ET.SubElement(item, "enclosure", url=image_url, type="image/jpeg")

        xml_path = os.path.join(XML_FOLDER, f"{channel_name}.xml")
        tree = ET.ElementTree(rss_root)
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)
        print(f"✅ {channel_name} XML updated")
    except Exception as e:
        print(f"[Error fetching {channel_name} XML] {e}")

def telegram_updater():
    while True:
        for name, url in TELEGRAM_CHANNELS.items():
            fetch_telegram_xml(name, url)
        time.sleep(600)  # every 10 minutes

@app.route("/telegram/<channel_name>")
def telegram_html_view(channel_name):
    if channel_name not in TELEGRAM_CHANNELS:
        return "<p>Channel not found</p>", 404

    rss_xml_path = os.path.join(XML_FOLDER, f"{channel_name}.xml")
    if not os.path.exists(rss_xml_path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS[channel_name])

    # Parse XML to display in HTML
    try:
        with open(rss_xml_path, "r", encoding="utf-8") as f:
            xml_content = f.read()
        feed = feedparser.parse(xml_content)
        posts_html = ""

        # Latest posts first
        entries = feed.entries[:30]

        for entry in reversed(entries):  # newest at top
            title = entry.get("title", "")
            link = entry.get("link", "#")
            pubDate = entry.get("published", "")
            img_tags = ""

            if hasattr(entry, "media_content"):
                for m in entry.media_content:
                    img_tags += f'<img src="{m.get("url","")}" alt="Post image">'
            if hasattr(entry, "media_thumbnail"):
                for m in entry.media_thumbnail:
                    img_tags += f'<img src="{m.get("url","")}" alt="Post image">'

            posts_html += f"""
            <div class="post">
                <a href="{link}" target="_blank" class="title">{title}</a>
                <div class="images">{img_tags}</div>
                <div class="time">{pubDate}</div>
            </div>
            """

        html_page = f"""
        <!DOCTYPE html>
        <html lang="ml">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{channel_name} News Feed</title>
            <style>
                body {{font-family: system-ui, sans-serif; background:#f5f7fa; margin:0; padding:15px; color:#333;}}
                h1 {{text-align:center; color:#0078cc; margin-bottom:12px;}}
                .topbar {{display:flex; justify-content:center; gap:10px; margin-bottom:20px;}}
                .refresh {{background:#0078cc; color:white; padding:8px 12px; border-radius:6px; text-decoration:none; font-size:0.9em;}}
                .post {{background:#fff; border-radius:10px; box-shadow:0 2px 6px rgba(0,0,0,0.1); padding:12px 15px; margin-bottom:16px;}}
                .title {{font-size:1.05em; font-weight:600; color:#0078cc; text-decoration:none; display:block; margin-bottom:6px; line-height:1.4;}}
                .title:hover {{text-decoration:underline;}}
                .images {{display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:6px; margin-top:8px;}}
                .images img {{width:100%; border-radius:6px;}}
                .time {{font-size:0.8em; color:#777; margin-top:6px;}}
                a.back {{display:block; text-align:center; margin-top:30px; text-decoration:underline; color:#555;}}
            </style>
        </head>
        <body>
            <h1>{channel_name} Latest Posts</h1>
            <div class="topbar">
                <a href="/telegram/{channel_name}?refresh=1" class="refresh">🔄 Refresh</a>
                <a href="/" class="refresh" style="background:#555;">🏠 Home</a>
                <a href="/telegram/{channel_name}.xml" class="refresh" style="background:#444;">XML</a>
            </div>
            {posts_html if posts_html else "<p style='text-align:center;color:#777;'>No posts found.</p>"}
        </body>
        </html>
        """
        return html_page

    except Exception as e:
        return f"<p>Error loading feed: {e}</p>", 500
# ------------------ Homepage ------------------
@app.route("/")
def homepage():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
    ]
    cards = ""
    for i, (label, link) in enumerate(links):
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{link}">{label}</a></div>'

    # Telegram channels
    for i, (name, _) in enumerate(TELEGRAM_CHANNELS.items()):
        color = RGB_COLORS[(i+len(links)) % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="/telegram/{name}">{name}</a></div>'

    return render_template_string(wrap_grid_page("Suprabhaatham ePaper", cards, show_back=False))

# ------------------ /today ------------------
@app.route('/today')
def show_today_links():
    cards = ""
    for i, loc in enumerate(LOCATIONS):
        url = get_url_for_location(loc)
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{url}" target="_blank">{loc}</a></div>'
    return render_template_string(wrap_grid_page("Today's Suprabhaatham ePaper Links", cards))

# ------------------ /njayar ------------------
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
    threading.Thread(target=telegram_updater, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)