flask_epaper_with_pathravarthakal.py

Single-file Flask app that:

- Serves homepage, /today (Suprabhaatham ePaper links), /njayar (Njayar Prabhadham archive)

- Generates a Telegram-based RSS feed at /telegram/<channel>

- Displays a simple frontend at /Pathravarthakal which reads that RSS

- Uses a small in-memory cache for telegram RSS generation

- Starts a background thread placeholder to update epaper.json regularly

import os import re import time import json import threading import datetime from typing import Optional

import requests import feedparser from bs4 import BeautifulSoup from flask import Flask, render_template_string, Response, request

app = Flask(name) UPLOAD_FOLDER = "static" EPAPER_TXT = "epaper.txt" app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

---------- Configuration (tweak these) ----------

RGB_COLORS = [ "#FFCDD2", "#F8BBD0", "#E1BEE7", "#D1C4E9", "#C5CAE9", "#BBDEFB", "#B3E5FC", "#B2EBF2", "#B2DFDB", "#C8E6C9", "#DCEDC8", "#F0F4C3", "#FFF9C4", "#FFECB3", "#FFE0B2", ]

Small set of example locations (user likely has a larger list)

LOCATIONS = [ "Thiruvananthapuram", "Kollam", "Alappuzha", "Pathanamthitta", "Kottayam", "Idukki", "Ernakulam", "Thrissur", "Palakkad", "Malappuram", "Kozhikode", "Wayanad", "Kannur", "Kasaragod" ]

Map channel to a reference link (used in the RSS channel link)

CHANNELS = { "Pathravarthakal": "https://t.me/Pathravarthakal", }

Telegram RSS cache to avoid hammering the site

telegram_cache = {} TELEGRAM_CACHE_TTL = 60 * 5  # 5 minutes

--------------- Helpers -----------------

def wrap_grid_page(title: str, cards_html: str, show_back: bool = True) -> str: """Simple page wrapper using a responsive CSS grid for cards.""" back_html = "" if not show_back else '<p style="text-align:center;margin:8px;"><a href="/">Back</a></p>' return f""" <!doctype html> <html> <head> <meta charset="utf-8"> <meta name="viewport" content="width=device-width,initial-scale=1"> <title>{title}</title> <style> body{{font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial; background:#f5f7fa;margin:0;padding:16px;}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;max-width:980px;margin:18px auto;}} .card{{padding:16px;border-radius:12px;color:#111;box-shadow:0 6px 18px rgba(0,0,0,0.06);text-align:center}} .card a{{display:block;color:inherit;text-decoration:none;font-weight:600}} header{{text-align:center;margin-top:8px}} </style> </head> <body> <header> <h1 style="margin:6px 0;color:#0078cc;">{title}</h1> {back_html} </header> <main class="grid">{cards_html}</main> </body> </html> """

def get_url_for_location(loc: str, date: Optional[datetime.date] = None) -> str: """Return a plausible external URL for the Suprabhaatham ePaper. This function should be adapted to the real URL scheme you use. For demo we return a placeholder Google search URL. """ if date: ds = date.strftime('%Y-%m-%d') return f"https://example.com/epaper/{loc.replace(' ', '')}/{ds}" return f"https://example.com/epaper/{loc.replace(' ', '')}"

Placeholder updater — adapt to your real epaper JSON update routine

def update_epaper_json(): while True: try: # Here you would fetch and write epaper metadata to EPAPER_TXT or similar # For demonstration, we'll write a timestamp into EPAPER_TXT so the file exists os.makedirs(UPLOAD_FOLDER, exist_ok=True) with open(EPAPER_TXT, 'w') as f: f.write(json.dumps({'last_update': datetime.datetime.utcnow().isoformat()})) except Exception as e: print("[update_epaper_json] error:", e) time.sleep(60 * 10)  # run every 10 minutes

---------------- Telegram -> RSS generator ----------------

@app.route('/telegram/<channel>') def telegram_rss(channel: str): """Scrape the Telegram web widget for the given channel and return RSS XML. NOTE: scraping third-party sites might be brittle. Adjust selectors if the structure of the widget changes. """ now = time.time() # Simple cache if channel in telegram_cache: data = telegram_cache[channel] if now - data.get('time', 0) < TELEGRAM_CACHE_TTL: return Response(data['xml'], mimetype='application/rss+xml')

try:
    channel = channel.strip()
    widget_url = f"https://t.me/s/{channel}"
    r = requests.get(widget_url, timeout=12)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')

    items = []
    for msg in soup.select('.tgme_widget_message_wrap')[:40]:
        date_tag = msg.select_one('a.tgme_widget_message_date')
        link = date_tag['href'] if date_tag and date_tag.get('href') else f"https://t.me/{channel}"
        text_tag = msg.select_one('.tgme_widget_message_text')

        if text_tag:
            full_text = text_tag.get_text(' ', strip=True).replace('\n', ' ')
            title = (full_text[:80].rsplit(' ', 1)[0] + '...') if len(full_text) > 80 else full_text
        else:
            title = 'Telegram Post'

        # description: use the original HTML so images and formatting stay
        desc = str(text_tag) if text_tag else ''

        img_url = None
        style_tag = msg.select_one('a.tgme_widget_message_photo_wrap')
        if style_tag and 'style' in style_tag.attrs:
            # Extract url(...) from the CSS style safely
            m = re.search(r"url['\"]?(.*?)['\"]?", style_tag['style'])
            if m:
                img_url = m.group(1)

        if not img_url:
            img_tag = msg.select_one('img')
            if img_tag and img_tag.get('src'):
                img_url = img_tag['src']

        image_enclosure = ''
        if img_url:
            # media:content (mrss) element for RSS readers
            image_enclosure = f"<media:content url='{img_url}' medium='image' />"
            # prepend image to description
            desc = f'<img src="{img_url}" width="100%"><br>' + desc

        items.append(f"""
        <item>
            <title><![CDATA[{title}]]></title>
            <link>{link}</link>
            <guid isPermaLink="false">{link}</guid>
            <description><![CDATA[{desc}]]></description>
            {image_enclosure}
        </item>
        """)

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
    <channel>
        <title>{channel} Telegram Feed</title>
        <link>{CHANNELS.get(channel, 'https://t.me/' + channel)}</link>
        <description>Latest posts from @{channel}</description>
        {''.join(items)}
    </channel>
    </rss>"""

    telegram_cache[channel] = {'xml': rss, 'time': now}
    return Response(rss, mimetype='application/rss+xml')

except Exception as e:
    print(f"[Error fetching Telegram RSS] {e}")
    return Response(f"<error>{e}</error>", mimetype='application/rss+xml')

------------------ Telegram HTML Frontend ------------------

@app.route('/Pathravarthakal') def pathravarthakal_html(): """Frontend display for Pathravarthakal feed.""" channel = 'Pathravarthakal' url = f"/telegram/{channel}" rss_url = request.url_root.rstrip('/') + url try: r = requests.get(rss_url, timeout=8) r.raise_for_status() feed = feedparser.parse(r.text) except Exception as e: return f"<p>Failed to load feed: {e}</p>"

html_items = ''
for entry in feed.entries[:40]:
    title = entry.get('title', '')
    link = entry.get('link', '')
    desc = entry.get('summary', '')
    image = None

    # Check for media_content from feedparser
    if 'media_content' in entry:
        for m in entry.media_content:
            if 'url' in m:
                image = m['url']
                break
    elif 'media_thumbnail' in entry:
        for m in entry.media_thumbnail:
            if 'url' in m:
                image = m['url']
                break

    # Fallback: look inside description for img tag
    if not image:
        match = re.search(r'<img\s+src="([^"]+)"', desc)
        if match:
            image = match.group(1)

    html_items += f"""
    <div style='margin:10px;padding:10px;background:#fff;border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,0.1);text-align:left;'>
        {('<img src="'+image+'" style="width:100%;border-radius:12px;">' if image else '')}
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
    <p style="text-align:center;">📡 RSS: <a href="{url}" target="_blank">{rss_url}</a></p>
</body>
</html>
"""

------------------ Home ------------------

@app.route('/') def homepage(): links = [ ("Today's Editions", "/today"), ("Njayar Prabhadham Archive", "/njayar"), ("Pathravarthakal Feed", "/Pathravarthakal"), ] cards = '' for i, (label, link) in enumerate(links): color = RGB_COLORS[i % len(RGB_COLORS)] cards += f"<div class="card" style="background-color:{color};"><a href="{link}">{label}</a></div>" return render_template_string(wrap_grid_page("Suprabhaatham ePaper", cards, show_back=False))

@app.route('/today') def show_today_links(): cards = '' for i, loc in enumerate(LOCATIONS): url = get_url_for_location(loc) color = RGB_COLORS[i % len(RGB_COLORS)] cards += f"<div class="card" style="background-color:{color};"><a href="{url}" target="_blank">{loc}</a></div>" return render_template_string(wrap_grid_page("Today's Suprabhaatham ePaper Links", cards))

@app.route('/njayar') def show_njayar_archive(): start_date = datetime.date(2019, 1, 6) today = datetime.date.today() cutoff = datetime.date(2024, 6, 30)

# Build list of Sundays on or before today that are >= cutoff
sundays = []
current = today
while current.weekday() != 6:  # 6 is Sunday
    current -= datetime.timedelta(days=1)

while current >= start_date:
    if current >= cutoff:
        sundays.append(current)
    current -= datetime.timedelta(days=7)

# Render newest first
cards = ''
for i, d in enumerate(sorted(sundays, reverse=True)):
    url = get_url_for_location('Njayar Prabhadham', d)
    date_str = d.strftime('%Y-%m-%d')
    color = RGB_COLORS[i % len(RGB_COLORS)]
    cards += f"<div class=\"card\" style=\"background-color:{color};\"><a href=\"{url}\" target=\"_blank\">{date_str}</a></div>"

return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

------------------ Main ------------------

if name == 'main': os.makedirs(UPLOAD_FOLDER, exist_ok=True) # Start background updater thread threading.Thread(target=update_epaper_json, daemon=True).start() app.run(host='0.0.0.0', port=8000)

