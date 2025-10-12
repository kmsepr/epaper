import os
import time
import json
import threading
import datetime
import requests
import brotli
import feedparser
from flask import Flask, render_template_string, Response, request # 'request' added for /feeds
from bs4 import BeautifulSoup

# -------------------- Config --------------------
app = Flask(__name__)
UPLOAD_FOLDER = "static"
EPAPER_TXT = "epaper.txt"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

LOCATIONS = [
    "Kozhikode", "Malappuram", "Kannur", "Thrissur",
    "Kochi", "Thiruvananthapuram", "Palakkad", "Gulf"
]
RGB_COLORS = [
    "#FF6B6B", "#6BCB77", "#4D96FF", "#FFD93D",
    "#FF6EC7", "#00C2CB", "#FFA41B", "#845EC2"
]

RSS_FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Times of India", "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms"),
    ("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss")
]

telegram_cache = {"rss": None, "time": 0}

# ------------------ HTML Wrappers ------------------

def wrap_grid_page(title, items_html, show_back=True):
    back_html = '<p><a class="back" href="/">Back to Home</a></p>' if show_back else ''
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
    
def wrap_feeds_page(title, content_html, active_tab):
    base_style = """
        body {font-family: 'Segoe UI', sans-serif; background:#f0f2f5; margin:0; padding:20px; color:#333;}
        h1 {font-size:2em; margin-bottom:20px; text-align:center;}
        .tabs {display:flex; justify-content:center; margin-bottom:20px; border-bottom:2px solid #ccc; max-width:800px; margin:20px auto;}
        .tab-button {padding:10px 20px; cursor:pointer; font-size:1.1em; font-weight:bold; color:#555; text-decoration:none; transition:color 0.2s;}
        .tab-button.active {color:#4D96FF; border-bottom:3px solid #4D96FF; margin-bottom:-2px;}
        .tab-content {max-width:800px; margin:auto; padding:20px; background:white; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.08);}
        .grid {display:grid; grid-template-columns:repeat(auto-fit, minmax(250px, 1fr)); gap:15px;}
        .card {padding:15px; border-radius:10px; box-shadow:0 1px 4px rgba(0,0,0,0.1); transition:transform .2s; min-height: 100px;}
        .card:hover {transform:translateY(-2px);}
        .card a {text-decoration:none; font-size:1em; color:#fff; font-weight:bold; display:block;}
        .card p {font-size:0.85em; margin: 5px 0 0 0;}
        a.back {display:block; margin-top:20px; text-align:center; font-size:1em; color:#555; text-decoration:underline;}
        .placeholder {text-align:center; padding:50px; color:#999; font-style:italic;}
    """
    
    tabs_html = f"""
    <div class="tabs">
        <a class="tab-button {'active' if active_tab == 'news' else ''}" href="/feeds?tab=news">News Feeds</a>
        <a class="tab-button {'active' if active_tab == 'podcast' else ''}" href="/feeds?tab=podcast">Podcasts (Placeholder)</a>
        <a class="tab-button {'active' if active_tab == 'add' else ''}" href="/feeds?tab=add">Add RSS by URL</a>
    </div>
    <div class="tab-content">
        {content_html}
    </div>
    """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>{base_style}</style>
    </head>
    <body>
        <h1>{title}</h1>
        {tabs_html}
        <p><a class="back" href="/">Back to Home</a></p>
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
    payload = {}
    while True:
        try:
            print("Fetching latest ePaper data...")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            data = brotli.decompress(response.content).decode('utf-8') if response.headers.get('Content-Encoding') == 'br' else response.text
            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(data)
            print("✅ epaper.txt updated successfully.")
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")
        time.sleep(86400)

# ------------------ Telegram to RSS Endpoint ------------------

@app.route("/telegram")
def telegram_feed():
    """Scrape Telegram public channel messages and output as RSS feed (cached 10 min)."""
    channel_url = "https://t.me/s/Pathravarthakal"
    now = time.time()

    if telegram_cache["rss"] and now - telegram_cache["time"] < 600:
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
            desc = title + (f'<br><img src="{img_url}" style="max-width:100%">' if img_url else "")

            items.append({
                "title": title,
                "link": link,
                "pubDate": pub_date,
                "description": desc
            })

        rss_items = "\n".join(
            f"""
            <item>
                <title><![CDATA[{i['title']}]]></title>
                <link>{i['link']}</link>
                <pubDate>{i['pubDate']}</pubDate>
                <description><![CDATA[{i['description']}]]></description>
            </item>
            """ for i in items[:20]
        )

        rss = f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Pathravarthakal Telegram Feed</title>
            <link>{channel_url}</link>
            <description>Latest updates from the Pathravarthakal Telegram channel.</description>
            <language>ml</language>
            {rss_items}
          </channel>
        </rss>"""

        telegram_cache["rss"] = rss
        telegram_cache["time"] = now
        return Response(rss, mimetype="application/rss+xml")

    except Exception as e:
        return f"Error fetching Telegram feed: {e}", 500

# ------------------ Feeds Route (New) ------------------

@app.route("/feeds")
def show_feeds():
    # Default to the 'news' tab
    active_tab = request.args.get('tab', 'news')
    content_html = ""
    
    if active_tab == 'news':
        # --- Aggregated News Feeds (Existing RSS + Telegram Scrape) ---
        items = []
        
        # 1. Existing Static RSS Feeds
        for name, url in RSS_FEEDS:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]: # Max 5 per source
                    items.append({
                        "source": name,
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "date": entry.get("published", "")
                    })
            except Exception as e:
                print(f"[RSS error] {url}: {e}")
                
        # 2. Pathravarthakal Telegram Scrape
        try:
            channel_url = "https://t.me/s/Pathravarthakal"
            html = requests.get(channel_url, timeout=5).text
            soup = BeautifulSoup(html, "html.parser")
            for post in soup.select(".tgme_widget_message_wrap")[:5]: # Max 5 posts
                title_el = post.select_one(".tgme_widget_message_text")
                link_el = post.select_one("a.tgme_widget_message_date")
                date_el = post.select_one("time")

                title = title_el.get_text(strip=True)[:100] + "..." if title_el else "(No text)"
                link = link_el["href"] if link_el else channel_url
                pub_date = date_el["datetime"] if date_el else ""
                
                items.append({
                    "source": "Pathravarthakal (Telegram)",
                    "title": title,
                    "link": link,
                    "date": pub_date
                })
        except Exception as e:
            print(f"[Telegram Scrape error] {e}")

        # --- Render Cards ---
        cards = ""
        for i, item in enumerate(items):
            color = RGB_COLORS[i % len(RGB_COLORS)]
            cards += f'''
            <div class="card" style="background:{color};color:white;text-align:left">
                <a href="{item['link']}" target="_blank">{item['title']}</a>
                <p style="font-size:0.9em;margin-top:8px;">🗞 {item['source']} — {item['date'].split('T')[0] if item['date'] else 'Date N/A'}</p>
            </div>
            '''
        content_html = f'<div class="grid">{cards}</div>'

    elif active_tab == 'podcast':
        # --- Podcast Placeholder ---
        content_html = '''
            <div class="placeholder">
                <p>This section is reserved for podcast feeds. Logic to fetch and display podcast episodes would go here.</p>
            </div>
        '''

    elif active_tab == 'add':
        # --- Add RSS by URL Form ---
        content_html = '''
            <div style="padding: 20px;">
                <p>Enter an RSS feed URL to read its content (requires server-side processing which is a placeholder here):</p>
                <form action="/process_custom_rss" method="POST" style="display:flex; gap:10px;">
                    <input type="url" name="rss_url" placeholder="e.g., https://example.com/feed.xml" required 
                           style="flex-grow:1; padding:10px; border-radius:5px; border:1px solid #ccc;">
                    <button type="submit" style="padding:10px 15px; border:none; border-radius:5px; background:#6BCB77; color:white; font-weight:bold;">Load Feed</button>
                </form>
                <p style="margin-top:20px;">For the Pathravarthakal Telegram RSS URL, use: <code>/telegram</code></p>
            </div>
        '''
        
    return render_template_string(wrap_feeds_page("📰 News & Feeds Center", content_html, active_tab))

# ------------------ Routes ------------------

@app.route('/')
def homepage():
    # UPDATED: Removed individual RSS/Telegram links from the homepage grid
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("News & Feeds Center", "/feeds") # NEW combined link
    ]
    cards = ""
    for i, (label, link) in enumerate(links):
        # We need a fallback color set if the number of links is less than the RGB_COLORS list length
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{link}">{label}</a></div>'
    return render_template_string(wrap_grid_page("Suprabhaatham ePaper & RSS News", cards, show_back=False))

# NOTE: The old /news route is now redundant and removed.

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
