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
app = Flask(__name__) # FIX 1: Corrected 'name' to '__name__'
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

telegram_cache = {}
CHANNELS = {
    "Pathravarthakal": "https://t.me/s/Pathravarthakal",
    # Add more channels here later:
    # "AnotherChannel": "https://t.me/s/AnotherChannel"
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

# ------------------ Telegram RSS (XML backend) ------------------
@app.route("/telegram/<channel>")
def telegram_rss(channel):
    """Universal backend RSS feed with images for Telegram channels."""
    if channel not in CHANNELS:
        return Response(f"<error>Channel not configured: {channel}</error>", mimetype="application/rss+xml")

    now = time.time()
    cache_life = 600

    if (
        channel in telegram_cache
        and now - telegram_cache[channel]["time"] < cache_life
        and "refresh" not in request.args
    ):
        return Response(telegram_cache[channel]["xml"], mimetype="application/rss+xml")

    try:
        url = CHANNELS[channel]
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        items = []
        for post in soup.select(".tgme_widget_message_wrap"):
            try:
                text_tag = post.select_one(".tgme_widget_message_text")
                
                # Title: first 120 chars of text
                title = text_tag.get_text(strip=True)[:120] if text_tag else f"{channel} update"
                
                # Link: the permanent link to the post
                link_tag = post.select_one("a.tgme_widget_message_date")
                link = link_tag["href"] if link_tag else ""
                
                # Image: get source URL of any image in the post
                img_tag = post.select_one("img")
                img_url = img_tag["src"] if img_tag else None

                # Description: full HTML content wrapped in CDATA
                desc = f"<![CDATA[{str(text_tag)}]]>" if text_tag else ""
                
                # Media tags for RSS readers
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
            except Exception as e:
                # print(f"Error parsing post: {e}") # Debugging line
                continue
        
        rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
        <channel>
            <title>{channel} Telegram Feed</title>
            <link>{url}</link>
            <description>Latest posts from @{channel} Telegram channel</description>
            <language>ml</language>
            {''.join(items)}
        </channel></rss>"""

        # Cache the result
        telegram_cache[channel] = {"xml": rss_xml, "time": now}
        
        return Response(rss_xml, mimetype="application/rss+xml")

    except Exception as e:
        return Response(f"<error>Error fetching feed: {e}</error>", mimetype="application/rss+xml")


# ------------------ Telegram HTML Viewer ------------------
@app.route("/<channel>")
def telegram_html_feed(channel):
    """HTML viewer for a specific Telegram channel, relying on the RSS backend."""
    # Build the URL for the XML backend
    rss_url = request.url_root + f"telegram/{channel}"
    
    # Fetch the XML from the backend (or cache)
    r = requests.get(rss_url)
    if r.status_code != 200 or "<error>" in r.text:
        return f"<h1>Error loading feed for {channel}</h1><p>{r.text}</p>"
        
    # Use feedparser to easily parse the generated XML
    feed = feedparser.parse(r.text)
    
    html_items = ""
    for entry in feed.entries:
        # Extract data from the parsed entry
        title = entry.title
        link = entry.link
        # Use content[0].value (the CDATA content) as the main description
        desc = entry.description if hasattr(entry, 'description') else ''
        
        # Check for media content to get the image
        image = None
        if 'media_content' in entry and len(entry.media_content) > 0:
            image = entry.media_content[0].get('url')
        elif 'enclosures' in entry and len(entry.enclosures) > 0:
            image = entry.enclosures[0].get('href')

        # Build the HTML card for this post
        html_items += f"""
        <div style='background:white;padding:15px;margin-bottom:20px;border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,0.1);text-align:left;'>
            {'<img src="'+image+'" style="width:100%;border-radius:12px;">' if image else ''}
            <h3><a href="{link}" target="_blank" style="color:#0078cc;text-decoration:none;">{title}</a></h3>
            <div style="color:#444;font-size:14px;">{desc}</div>
        </div>
        """

    return f"""
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{channel} Feed</title>
    </head>
    <body style="font-family:sans-serif;background:#f5f7fa;margin:0;padding:10px;">
        <h2 style="text-align:center;color:#0078cc;">📰 {channel} Telegram Feed</h2>
        <div style="max-width:600px;margin:auto;">{html_items}</div>
        <p style="text-align:center;">📡 RSS: <a href="{rss_url}" target="_blank">{rss_url}</a></p>
    </body>
    </html>
    """

# ------------------ Home ------------------
@app.route('/')
def homepage():
    # Dynamically create the Telegram links based on the CHANNELS dict
    tele_links = [(f"{name} Feed", f"/{name}") for name in CHANNELS]
    
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
    ] + tele_links
    
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
    # The cutoff date is 2024-06-30
    cutoff = datetime.date(2024, 6, 30) 
    sundays = []
    
    # Start checking from the last Sunday on or before today
    current = today
    while current.weekday() != 6: # 6 is Sunday
        current -= datetime.timedelta(days=1)

    while current >= start_date:
        # Only include Sundays that are on or after the cutoff date
        if current >= cutoff: 
            sundays.append(current)
        current -= datetime.timedelta(days=7) # Go back one week

    # Reversing sundays ensures the newest date is first in the list
    sundays.reverse() 
    
    cards = ""
    for i, d in enumerate(sundays):
        url = get_url_for_location("Njayar Prabhadham", d)
        date_str = d.strftime('%Y-%m-%d')
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{url}" target="_blank">{date_str}</a></div>'
        
    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

# ------------------ Main ------------------
if __name__ == '__main__': # FIX 2: Corrected 'name' to '__main__'
    # Create the static directory if it doesn't exist
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    threading.Thread(target=update_epaper_json, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)
