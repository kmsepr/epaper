import os
import time
import json
import threading
import datetime
import requests
import re
import feedparser
from flask import Flask, Response, render_template_string, request
from bs4 import BeautifulSoup

# -------------------- Config --------------------
app = Flask(__name__)
UPLOAD_FOLDER = "static"
EPAPER_TXT = "epaper.txt"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# -------------------- Telegram RSS --------------------
def fetch_telegram_feed(channel="suprabhathamdaily"):
    """Fetch and parse Telegram channel feed"""
    url = f"https://t.me/s/{channel}"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")
    items = []

    for msg in soup.select(".tgme_widget_message_wrap"):
        text_el = msg.select_one(".tgme_widget_message_text")
        if not text_el:
            continue
        title = text_el.get_text(strip=True)[:100]
        link_el = msg.select_one("a.tgme_widget_message_date")
        if not link_el:
            continue
        link = link_el["href"]

        # --- Get proper post image (not channel logo) ---
        img_url = None
        photo_wrap = msg.select_one("a.tgme_widget_message_photo_wrap")
        if photo_wrap and "style" in photo_wrap.attrs:
            m = re.search(r'url\(["\']?(.*?)["\']?\)', photo_wrap["style"])
            if m:
                img_url = m.group(1)
        elif msg.select_one(".tgme_widget_message_photo_wrap img"):
            img_url = msg.select_one(".tgme_widget_message_photo_wrap img")["src"]

        desc = f"<p>{text_el.decode_contents()}</p>"
        if img_url:
            desc += f'<p><img src="{img_url}" style="max-width:100%"></p>'

        items.append({
            "title": title,
            "link": link,
            "description": desc,
            "pubDate": datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        })

    return items

@app.route("/feed/Pathravarthakal")
def telegram_rss():
    channel = request.args.get("ch", "suprabhathamdaily")
    items = fetch_telegram_feed(channel)
    rss = '<?xml version="1.0" encoding="UTF-8"?>\n'
    rss += '<rss version="2.0"><channel>'
    rss += f"<title>{channel} Telegram Feed</title>"
    rss += f"<link>https://t.me/{channel}</link>"
    rss += f"<description>Latest posts from @{channel}</description>"

    for i in items:
        rss += "<item>"
        rss += f"<title><![CDATA[{i['title']}]]></title>"
        rss += f"<link>{i['link']}</link>"
        rss += f"<description><![CDATA[{i['description']}]]></description>"
        rss += f"<pubDate>{i['pubDate']}</pubDate>"
        rss += "</item>"

    rss += "</channel></rss>"
    return Response(rss, mimetype="application/rss+xml")

# -------------------- Other Routes --------------------
@app.route("/")
def home():
    return render_template_string("""
        <h2>Suprabhaatham Server</h2>
        <ul>
            <li><a href="/njayar">Njayar Prabhadham</a></li>
            <li><a href="/today">Today's Epaper</a></li>
            <li><a href="/feed/Pathravarthakal">RSS Feed (Telegram)</a></li>
        </ul>
    """)

@app.route("/njayar")
def njayar():
    return "Njayar Prabhadham archive route working."

@app.route("/today")
def today():
    return "Today's ePaper route working."

# -------------------- Run --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)