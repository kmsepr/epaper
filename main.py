import os
import time
import json
import threading
import datetime
import requests
import brotli
import feedparser
from flask import Flask, render_template_string, Response, request, redirect, url_for, abort
from bs4 import BeautifulSoup
import urllib.parse
import re # Added for clean_html function

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

RSS_FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Times of India", "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms"),
    ("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss")
]

telegram_cache = {"rss": None, "time": 0}

# Global list to store custom feeds in memory (Index is crucial for /feed_items)
CUSTOM_FEEDS = []

# ------------------ Utility Functions ------------------

def clean_html(raw_html):
    """Strips HTML tags and removes common entities for cleaner descriptions."""
    if not raw_html:
        return ""
    # Remove HTML tags
    clean_text = re.sub(r'<[^>]+>', '', str(raw_html))
    # Decode common HTML entities (e.g., &amp;)
    clean_text = clean_text.replace('&amp;', '&').replace('&nbsp;', ' ')
    return clean_text.strip()

# ------------------ HTML Wrappers ------------------

def wrap_grid_page(title, items_html, show_back=True):
    # FIXED: Escaping CSS braces by doubling them for Jinja compatibility.
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
    
def wrap_feeds_page(title, content_html, active_tab, message=None):
    # FIXED: Replaced f-string with standard quotes for base_style to solve the persistent Jinja2 parsing error.
    base_style = """
        body {font-family: 'Segoe UI', sans-serif; background:#f0f2f5; margin:0; padding:20px; color:#333;}
        h1 {font-size:2em; margin-bottom:20px; text-align:center;}
        .message.success {color:#38761d; background:#e6ffe6; border:1px solid #c6e6c6; padding:10px; border-radius:8px; margin-bottom:20px;}
        .tabs {display:flex; justify-content:center; margin-bottom:20px; border-bottom:2px solid #ccc; max-width:800px; margin:20px auto;}
        .tab-button {padding:10px 20px; cursor:pointer; font-size:1.1em; font-weight:bold; color:#555; text-decoration:none; transition:color 0.2s;}
        .tab-button.active {color:#4D96FF; border-bottom:3px solid #4D96FF; margin-bottom:-2px;}
        .tab-content {max-width:800px; margin:auto; padding:20px; background:white; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.08);}
        .grid {display:grid; grid-template-columns:repeat(auto-fit, minmax(250px, 1fr)); gap:15px;}
        .card {padding:15px; border-radius:10px; box-shadow:0 1px 4px rgba(0,0,0,0.1); transition:transform .2s; min-height: 100px; display: flex; flex-direction: column; justify-content: space-between;}
        .card:hover {transform:translateY(-2px);}
        .card a {text-decoration:none; font-size:1em; color:#fff; font-weight:bold; display:block;}
        .card p {font-size:0.85em; margin: 5px 0 0 0;}
        .feed-card {cursor: pointer;}
        .podcast-card {background-color:#4D96FF;}
        .podcast-thumb {width: 100%; height: 150px; background-size: cover; background-position: center; border-radius: 8px; margin-bottom: 10px;}
        .feed-list-item {border-bottom: 1px solid #eee; padding: 10px 0; text-align: left;}
        .feed-list-item h4 {margin: 0; font-size: 1.1em;}
        .feed-list-item a {text-decoration: none; color: #333; display: block;}
        .feed-list-item a:hover {color: #4D96FF;}
        .feed-list-item small {color: #777;}
        .audio-player {width: 100%; margin-top: 15px;}
        a.back {display:block; margin-top:20px; text-align:center; font-size:1em; color:#555; text-decoration:underline;}
        .placeholder {text-align:center; padding:50px; color:#999; font-style:italic;}
    """
    
    tabs_html = f"""
    <div class="tabs">
        <a class="tab-button {'active' if active_tab == 'news' else ''}" href="/feeds?tab=news">News Feeds</a>
        <a class="tab-button {'active' if active_tab == 'podcast' else ''}" href="/feeds?tab=podcast">Podcasts</a>
        <a class="tab-button {'active' if active_tab == 'add' else ''}" href="/feeds?tab=add">Add RSS by URL</a>
    </div>
    <div class="tab-content">
        {f'<div class="message success">{message}</div>' if message else ''}
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

# ------------------ Process Custom Feed ------------------

@app.route("/add_custom_feed", methods=['POST'])
def add_custom_feed():
    url = request.form.get('rss_url')
    category = request.form.get('category')
    
    if not url or not category:
        return redirect(url_for('show_feeds', tab='add', message='Error: URL and Category are required!'))

    try:
        feed = feedparser.parse(url, agent="Custom-Feed-Reader")
        if not feed.feed.get('title'):
            raise ValueError("Could not parse a title from the feed.")
            
        feed_title = feed.feed.get('title', 'Untitled Feed')
        feed_image = feed.feed.get('image', {}).get('href', None)
        if not feed_image and 'itunes_image' in feed.feed:
            feed_image = feed.feed.itunes_image
            
        CUSTOM_FEEDS.append({
            'url': url,
            'category': category.lower(),
            'title': feed_title,
            'image': feed_image,
            # Adding an index for easy retrieval later
            'index': len(CUSTOM_FEEDS) 
        })

        msg = f"✅ Successfully added '{feed_title}' as a {category.title()} feed!"
        return redirect(url_for('show_feeds', tab=category.lower(), message=msg))

    except Exception as e:
        # URL encode the error message for safe passing in the redirect URL
        error_msg = urllib.parse.quote(f'Error adding feed: {e}')
        return redirect(url_for('show_feeds', tab='add', message=error_msg))

# ------------------ Feeds Route - Main Display ------------------

@app.route("/feeds")
def show_feeds():
    active_tab = request.args.get('tab', 'news')
    message = request.args.get('message', None)
    content_html = ""
    
    # Filter feeds based on the active tab (only custom feeds are displayed)
    display_feeds = [f for f in CUSTOM_FEEDS if f['category'] == active_tab]
    
    if active_tab in ['news', 'podcast']:
        if not display_feeds:
             content_html = f'''
                <div class="placeholder">
                    <p>No {active_tab.title()} feeds added yet. Use the "Add RSS by URL" tab to add a feed.</p>
                    <p>Suggested feeds (for manual addition):</p>
                    <ul>
                        {''.join(f'<li>{name} - <code style="font-size:0.9em;">{url}</code></li>' for name, url in RSS_FEEDS)}
                    </ul>
                </div>
            '''
        else:
            # Build the grid of feed titles/cards
            cards = ""
            for i, feed_info in enumerate(display_feeds):
                color = RGB_COLORS[feed_info['index'] % len(RGB_COLORS)]
                
                # Check for image and link to the item list page
                thumb_style = f'background-image: url("{feed_info["image"]}");' if feed_info.get("image") else 'background-color: #555; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; font-size: 1.5em;'
                thumb_content = '' if feed_info.get("image") else feed_info['title'][:1]

                # Link goes to the new feed item viewer route
                link_url = url_for('show_feed_items', feed_index=feed_info['index'])
                
                cards += f'''
                <div class="card feed-card" style="background:{color}; color:white; text-align:left; cursor: pointer;" 
                     onclick="window.location.href='{link_url}'">
                    
                    <div class="podcast-thumb" style="{thumb_style}">{thumb_content}</div>
                    <div style="flex-grow: 1;">
                        <h3 style="margin-top: 0; font-size: 1.1em; color: white; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;" title="{feed_info['title']}">{feed_info['title']}</h3>
                        <p style="font-size: 0.9em; margin-bottom: 0;">Category: {feed_info['category'].title()}</p>
                    </div>
                </div>
                '''
            content_html = f'<div class="grid">{cards}</div>'

    elif active_tab == 'add':
        # --- Add RSS by URL Form ---
        content_html = f'''
            <div style="padding: 20px;">
                <p style="margin-bottom: 20px; font-weight: bold;">Add a new RSS feed to the collection:</p>
                <form action="{url_for('add_custom_feed')}" method="POST" style="display:flex; flex-direction: column; gap:15px;">
                    <div style="display:flex; flex-direction: column;">
                        <label for="rss_url" style="font-weight: bold; margin-bottom: 5px;">Feed URL:</label>
                        <input type="url" id="rss_url" name="rss_url" placeholder="e.g., https://example.com/feed.xml" required 
                               style="padding:10px; border-radius:5px; border:1px solid #ccc;">
                    </div>
                    <div style="display:flex; flex-direction: column;">
                        <label for="category" style="font-weight: bold; margin-bottom: 5px;">Category:</label>
                        <select id="category" name="category" required 
                                style="padding:10px; border-radius:5px; border:1px solid #ccc; background: white;">
                            <option value="news">News</option>
                            <option value="podcast">Podcast</option>
                        </select>
                    </div>
                    <button type="submit" style="padding:12px; border:none; border-radius:5px; background:#6BCB77; color:white; font-weight:bold; cursor: pointer;">Add Feed</button>
                </form>
                <p style="margin-top:20px; font-size: 0.9em; color: #777;">Tip: The Pathravarthakal Telegram RSS URL is available at: <code>{url_for('telegram_feed', _external=True)}</code></p>
                
                <h3 style="margin-top:30px;">Current Custom Feeds:</h3>
                <ul>
                {"".join(f"<li>{f['title']} ({f['category'].title()}) - <code style='font-size:0.9em;'>{f['url']}</code></li>" for f in CUSTOM_FEEDS) if CUSTOM_FEEDS else '<li>No custom feeds currently loaded.</li>'}
                </ul>
            </div>
        '''
        
    return render_template_string(wrap_feeds_page("📰 News & Feeds Center", content_html, active_tab, message))

# ------------------ Feed Item Viewer (New) ------------------

@app.route("/feed_items/<int:feed_index>")
def show_feed_items(feed_index):
    try:
        feed_info = CUSTOM_FEEDS[feed_index]
    except IndexError:
        abort(404, description="Feed not found.")

    feed_url = feed_info['url']
    category = feed_info['category']
    
    # Parse the feed to get the latest items
    try:
        feed = feedparser.parse(feed_url, agent="Custom-Feed-Reader")
        items = feed.entries
        feed_title = feed.feed.get('title', feed_info['title'])
    except Exception as e:
        return wrap_grid_page(f"Error Loading Feed", f"<p>Could not load feed from {feed_url}. Error: {e}</p>", show_back=True)

    
    # Render the items list
    items_html = ""
    for entry in items[:20]: # Show up to 20 items
        title = clean_html(entry.get('title', '(No Title)'))
        link = entry.get('link', '#')
        published = entry.get('published', entry.get('updated', ''))
        
        # Use content/summary/description fields for the body text
        content = entry.get('content', [{}])[0].get('value')
        summary_or_desc = entry.get('summary', entry.get('description', ''))
        
        body_text = clean_html(content) if content else clean_html(summary_or_desc)
        
        item_content = f"<h4>{title}</h4>" # Title is not an external link anymore
        item_content += f"<small>{published}</small>"
        
        # Add audio player for podcasts
        if category == 'podcast':
            audio_url = None
            if 'enclosures' in entry and entry['enclosures']:
                for enclosure in entry['enclosures']:
                    if enclosure.get('type', '').startswith('audio/'):
                        audio_url = enclosure['href']
                        break
            
            if audio_url:
                item_content += f'<audio controls class="audio-player" src="{audio_url}">Your browser does not support the audio element.</audio>'
        
        item_content += f"<p style='font-size: 0.9em; margin-top: 5px;'>{body_text[:300]}...</p>"
        
        # Provide a link to the original source if needed
        item_content += f"<p><a href='{link}' target='_blank'>Read/Listen to full item...</a></p>"

        items_html += f'<div class="feed-list-item">{item_content}</div>'

    # The wrap_grid_page is reused but with custom HTML structure for list view
    return render_template_string(wrap_grid_page(f"Items from: {feed_title}", items_html))

# ------------------ Routes ------------------

@app.route('/')
def homepage():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("News & Feeds Center", "/feeds")
    ]
    cards = ""
    for i, (label, link) in enumerate(links):
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{link}">{label}</a></div>'
    return render_template_string(wrap_grid_page("Suprabhaatham ePaper & RSS News", cards, show_back=False))

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
