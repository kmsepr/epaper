import os
import time
import json
import threading
import datetime
import requests
import brotli
import re
import random
import subprocess
from collections import deque
from flask import Flask, Response, render_template_string, request, redirect, url_for, stream_with_context, abort
from bs4 import BeautifulSoup
from email.utils import format_datetime
import logging
from logging.handlers import RotatingFileHandler

# -----------------------------
# DIRECTORIES & FILE PATHS
# -----------------------------
DATA_DIR = "data"
LOG_DIR = "logs"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

LOG_PATH = os.path.join(LOG_DIR, "app.log")
handler = RotatingFileHandler(LOG_PATH, maxBytes=5*1024*1024, backupCount=3)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), handler]
)

# -----------------------------
# FLASK APP
# -----------------------------
app = Flask(__name__)

# -----------------------------
# YOUTUBE RADIO FILES
# -----------------------------
COOKIES_PATH = os.path.join(DATA_DIR, "cookies.txt")
CACHE_FILE = os.path.join(DATA_DIR, "playlist_cache.json")
PLAYLISTS_FILE = os.path.join(DATA_DIR, "playlists.json")
MAX_QUEUE_SIZE = 100


# Default Playlists
def load_playlists():
    if os.path.exists(PLAYLISTS_FILE):
        try:
            with open(PLAYLISTS_FILE, "r") as f:
                data = json.load(f)
                return data.get("playlists", {}), set(data.get("shuffle", []))
        except Exception as e:
            logging.error(f"Failed to load playlists: {e}")
    return {
        "Malayalam": "https://youtube.com/playlist?list=PLs0evDzPiKwAyJDAbmMOg44iuNLPaI4nn",
        "Hindi": "https://youtube.com/playlist?list=PLlXSv-ic4-yJj2djMawc8XqqtCn1BVAc2",
    }, {"Malayalam", "Hindi"}

def save_playlists():
    try:
        with open(PLAYLISTS_FILE, "w") as f:
            json.dump({"playlists": PLAYLISTS, "shuffle": list(SHUFFLE_PLAYLISTS)}, f)
    except Exception as e:
        logging.error(f"Failed to save playlists: {e}")

PLAYLISTS, SHUFFLE_PLAYLISTS = load_playlists()
STREAMS = {}  # name -> {VIDEO_IDS, INDEX, QUEUE, LOCK, LAST_REFRESH}

# -------------------- ePaper & Telegram Config --------------------
UPLOAD_FOLDER = "static"
EPAPER_TXT = "epaper.txt"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

LOCATIONS = ["Kozhikode", "Malappuram", "Kannur", "Thrissur",
             "Kochi", "Thiruvananthapuram", "Palakkal", "Gulf"]
RGB_COLORS = ["#FF6B6B", "#6BCB77", "#4D96FF", "#FFD93D",
              "#FF6EC7", "#00C2CB", "#FFA41B", "#845EC2"]

CHANNELS = {
    "Pathravarthakal": "https://t.me/s/Pathravarthakal",
    "Dailyca": "https://t.me/s/DailyCAMalayalam",
    "Pyq": "https://t.me/Prayaanam_innalakalilude",
}

telegram_cache = {}
feed_cache = {}

# -------------------- HTML Templates --------------------
HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Main Dashboard</title>
<style>
body { background:#f0f2f5;color:#333;text-align:center;font-family:sans-serif; }
h2 { margin-top:30px; }
.section { margin:40px auto; max-width:800px; }
.card { padding:25px 15px;border-radius:16px;box-shadow:0 2px 8px rgba(0,0,0,0.1);margin:10px; display:inline-block; min-width:180px;}
.card a {text-decoration:none;font-size:1.1em;color:#fff;font-weight:bold;display:block;}
</style>
</head>
<body>
<h1>Main Dashboard</h1>
<div class="section">
<h2>🎧 YouTube Radio</h2>
<div class="card" style="background:#4D96FF;"><a href="/radio">Open Radio Player</a></div>
</div>
<div class="section">
<h2>📰 Suprabhaatham ePaper & Telegram</h2>
<div class="card" style="background:#FF6B6B;"><a href="/news">Open News / Feeds</a></div>
</div>
</body>
</html>
"""

# -------------------- Utility Functions --------------------
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load cache: {e}")
    return {}

def save_cache(data):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logging.error(f"Failed to save cache: {e}")

CACHE = load_cache()

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

# -------------------- YouTube Radio Functions --------------------
def load_playlist_ids(name, force=False):
    now = time.time()
    cached = CACHE.get(name, {})
    if not force and cached and now - cached.get("time", 0) < 1800:
        logging.info(f"[{name}] Using cached playlist IDs ({len(cached['ids'])} videos)")
        return cached["ids"]
    url = PLAYLISTS[name]
    try:
        logging.info(f"[{name}] Refreshing playlist IDs...")
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "-J", url, "--cookies", COOKIES_PATH],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        data = json.loads(result.stdout)
        video_ids = [
            e["id"] for e in data.get("entries", [])
            if not e.get("private") and e.get("age_limit", 0) == 0
        ]
        if name in SHUFFLE_PLAYLISTS:
            random.shuffle(video_ids)
        CACHE[name] = {"ids": video_ids, "time": now}
        save_cache(CACHE)
        logging.info(f"[{name}] Loaded {len(video_ids)} video IDs successfully")
        return video_ids
    except Exception as e:
        logging.error(f"[{name}] Playlist load failed: {e}")
        return cached.get("ids", [])

def stream_worker(name):
    stream = STREAMS[name]
    failed_videos = set()
    played_videos = set()
    shuffle_enabled = name in SHUFFLE_PLAYLISTS
    while True:
        try:
            if not stream["VIDEO_IDS"]:
                logging.info(f"[{name}] Playlist empty, reloading...")
                stream["VIDEO_IDS"] = load_playlist_ids(name, force=True)
                failed_videos.clear()
                played_videos.clear()
                stream["INDEX"] = 0
                if not stream["VIDEO_IDS"]:
                    time.sleep(10)
                    continue
            if time.time() - stream["LAST_REFRESH"] > 1800:
                stream["VIDEO_IDS"] = load_playlist_ids(name, force=True)
                failed_videos.clear()
                played_videos.clear()
                stream["INDEX"] = 0
                stream["LAST_REFRESH"] = time.time()
                if shuffle_enabled:
                    random.shuffle(stream["VIDEO_IDS"])
            if shuffle_enabled:
                available = [v for v in stream["VIDEO_IDS"] if v not in failed_videos and v not in played_videos]
                if not available:
                    played_videos.clear()
                    available = [v for v in stream["VIDEO_IDS"] if v not in failed_videos]
                if not available:
                    time.sleep(5)
                    continue
                vid = random.choice(available)
                played_videos.add(vid)
            else:
                for _ in range(len(stream["VIDEO_IDS"])):
                    vid = stream["VIDEO_IDS"][stream["INDEX"] % len(stream["VIDEO_IDS"])]
                    stream["INDEX"] += 1
                    if vid not in failed_videos:
                        break
                else:
                    time.sleep(5)
                    continue
            url = f"https://www.youtube.com/watch?v={vid}"
            if not os.path.exists(COOKIES_PATH) or os.path.getsize(COOKIES_PATH) == 0:
                failed_videos.add(vid)
                continue
            try:
                result = subprocess.run(
                    ["yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio", "--cookies", COOKIES_PATH, "-g", url],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
                )
                audio_url = result.stdout.strip()
            except subprocess.CalledProcessError:
                failed_videos.add(vid)
                continue
            cmd = f'ffmpeg -re -i "{audio_url}" -b:a 40k -ac 1 -f mp3 pipe:1 -loglevel quiet'
            proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                if len(stream["QUEUE"]) < MAX_QUEUE_SIZE:
                    stream["QUEUE"].append(chunk)
            proc.stdout.close()
            proc.stderr.close()
            proc.wait()
        except Exception as e:
            logging.error(f"[{name}] Worker error: {e}", exc_info=True)
            time.sleep(5)

# -------------------- ePaper Functions --------------------
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
            response = requests.post(url, json={}, headers=headers, timeout=10)
            response.raise_for_status()
            if response.headers.get('Content-Encoding') == 'br':
                data = brotli.decompress(response.content).decode('utf-8')
            else:
                data = response.text
            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(data)
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")
        time.sleep(86400)  # update daily

# -------------------- ROUTES --------------------
@app.route('/')
def main_home():
    return render_template_string(HOME_HTML)

# -------------------- Radio Routes --------------------
@app.route("/radio")
def radio_home():
    items_html = ""
    for name in PLAYLISTS:
        items_html += f'<div class="card" style="background:#4D96FF;"><a href="/listen/{name}">{name}</a></div>'
    return wrap_grid_page("YouTube Radio", items_html)

@app.route("/listen/<name>")
def listen(name):
    if name not in PLAYLISTS:
        abort(404)
    playlist_url = PLAYLISTS.get(name)
    return f"""
    <html><body>
    <h2>{name} Radio</h2>
    <audio controls autoplay>
      <source src="/stream/{name}" type="audio/mpeg">
    </audio>
    <p><a href="/">← Back</a></p>
    </body></html>
    """

@app.route("/stream/<name>")
def stream_audio(name):
    if name not in STREAMS:
        abort(404)
    stream = STREAMS[name]
    def generate():
        while True:
            if stream["QUEUE"]:
                yield stream["QUEUE"].popleft()
            else:
                time.sleep(0.1)
    headers = {"Content-Type": "audio/mpeg"}
    return Response(stream_with_context(generate()), headers=headers)

@app.route("/add_playlist", methods=["POST"])
def add_playlist():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    if not name or not url:
        abort(400)
    match = re.search(r"(?:list=)([A-Za-z0-9_-]+)", url)
    if match:
        url = f"https://www.youtube.com/playlist?list={match.group(1)}"
    else:
        abort(400)
    PLAYLISTS[name] = url
    if request.form.get("shuffle"):
        SHUFFLE_PLAYLISTS.add(name)
    save_playlists()
    video_ids = load_playlist_ids(name)
    if not video_ids:
        return redirect(url_for("main_home"))
    STREAMS[name] = {"VIDEO_IDS": video_ids, "INDEX":0, "QUEUE":deque(), "LOCK":threading.Lock(), "LAST_REFRESH":time.time()}
    threading.Thread(target=stream_worker, args=(name,), daemon=True).start()
    return redirect(url_for("radio_home"))

@app.route("/delete/<name>")
def delete_playlist(name):
    if name not in PLAYLISTS:
        abort(404)
    if name in STREAMS:
        del STREAMS[name]
    PLAYLISTS.pop(name, None)
    SHUFFLE_PLAYLISTS.discard(name)
    CACHE.pop(name, None)
    save_cache(CACHE)
    save_playlists()
    return redirect(url_for("radio_home"))

# -------------------- ePaper & Telegram Routes --------------------
@app.route('/news')
def news_home():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("Pathravarthakal Feed", "/Pathravarthakal"),
    ]
    cards = ""
    for i, (label, link) in enumerate(links):
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{link}">{label}</a></div>'
    return render_template_string(wrap_grid_page("Suprabhaatham ePaper", cards, show_back=True))

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
    start_date = datetime.date(2019,1,6)
    today = datetime.date.today()
    cutoff = datetime.date(2024,6,30)
    sundays = []
    current = today
    while current.weekday()!=6: current -= datetime.timedelta(days=1)
    while current>=start_date:
        if current>=cutoff: sundays.append(current)
        current -= datetime.timedelta(days=7)
    cards = ""
    for i,d in enumerate(sundays):
        url = get_url_for_location("Njayar Prabhadham",d)
        date_str = d.strftime('%Y-%m-%d')
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{url}" target="_blank">{date_str}</a></div>'
    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

@app.route("/feed/<channel>")
def telegram_rss(channel):
    if channel not in CHANNELS:
        return Response(f"<error>Channel not configured: {channel}</error>", mimetype="application/rss+xml")
    now = time.time()
    cache_life = 600
    if channel in telegram_cache and now - telegram_cache[channel]["time"] < cache_life and "refresh" not in request.args:
        return Response(telegram_cache[channel]["xml"], mimetype="application/rss+xml")
    try:
        url = CHANNELS[channel]
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text,"html.parser")
        items = []
        for i,msg in enumerate(soup.select(".tgme_widget_message_wrap")[:40]):
            date_tag = msg.select_one("a.tgme_widget_message_date")
            link = date_tag["href"] if date_tag else f"https://t.me/{channel}"
            time_tag = date_tag.select_one("time") if date_tag else None
            if time_tag and time_tag.has_attr("datetime"):
                pub_time = datetime.datetime.fromisoformat(time_tag["datetime"].replace("Z","+00:00"))
            else:
                pub_time = datetime.datetime.utcnow()
            pub_date = format_datetime(pub_time)
            text_tag = msg.select_one(".tgme_widget_message_text")
            if text_tag:
                full_text = text_tag.text.strip().replace('\n',' ')
                title = (full_text[:100].rsplit(' ',1)[0]+"...") if len(full_text)>100 else full_text
                description_text = text_tag.decode_contents()
            else:
                title="Telegram Post"; description_text=""
            img_url = None
            photo_wrap = msg.select_one("a.tgme_widget_message_photo_wrap")
            if photo_wrap and "style" in photo_wrap.attrs:
                m = re.search(r'url\(["\']?(.*?)["\']?\)', photo_wrap["style"])
                if m: img_url=m.group(1)
            elif photo_wrap and photo_wrap.select_one("img"):
                img_url = photo_wrap.select_one("img")["src"]
            desc_html = f"<p>{description_text}</p>"
            if img_url: desc_html = f'<p><img src="{img_url}" style="max-width:100%;border-radius:8px;"></p>{desc_html}'
            items.append(f"""
            <item>
                <title><![CDATA[{title}]]></title>
                <link>{link}</link>
                <guid isPermaLink="true">{link}</guid>
                <author>@{channel}</author>
                <pubDate>{pub_date}</pubDate>
                <description><![CDATA[{desc_html}]]></description>
                {'<media:content url="'+img_url+'" medium="image" />' if img_url else ''}
            </item>
            """)
        items.reverse()
        last_build = format_datetime(datetime.datetime.utcnow())
        rss = f"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
        <channel>
            <title>{channel} Telegram Feed</title>
            <link>{CHANNELS[channel]}</link>
            <description>Latest posts from @{channel}</description>
            <language>en</language>
            <lastBuildDate>{last_build}</lastBuildDate>
            <generator>Suprabhaatham RSS Generator</generator>
            {''.join(items)}
        </channel>
        </rss>"""
        telegram_cache[channel] = {"xml": rss, "time": now}
        return Response(rss, mimetype="application/rss+xml")
    except Exception as e:
        return Response(f"<error>{e}</error>", mimetype="application/rss+xml")

@app.route("/<channel>")
def show_channel_feed(channel):
    if channel not in CHANNELS:
        return "<p>Channel not found or not configured.</p>"
    rss_url = request.url_root.rstrip("/") + f"/feed/{channel}"
    try:
        r = requests.get(rss_url)
        feed = feedparser.parse(r.text)
        feed_cache[channel] = feed.entries[:40]
    except Exception as e:
        return f"<p>Failed to load feed: {e}</p>"
    html_items = ""
    for i, entry in enumerate(feed_cache[channel]):
        title = entry.get("title","")
        desc = entry.get("summary","")
        pub = entry.get("published","")
        html_items += f"""
        <div style='margin:10px;padding:10px;background:#fff;border-radius:12px;
                     box-shadow:0 2px 6px rgba(0,0,0,0.1);text-align:left;'>
            <h3><a href="/post/{i}?channel={channel}" style="color:#0078cc;text-decoration:none;">{title}</a></h3>
            <small style="color:#888;">{pub}</small>
            <div style="color:#444;font-size:15px;">{desc}</div>
        </div>
        """
    return f"""
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{channel} Feed</title></head>
    <body style="font-family:sans-serif;background:#f5f7fa;margin:0;padding:10px;">
        <h2 style="text-align:center;color:#0078cc;">📰 {channel} Telegram Feed</h2>
        <div style="max-width:600px;margin:auto;">{html_items}</div>
        <p style="text-align:center;">📡 RSS: <a href="{rss_url}" target="_blank">{rss_url}</a></p>
        <p style="text-align:center;"><a href="/news" style="color:#0078cc;">🏠 Back to News Home</a></p>
    </body>
    </html>
    """

# -------------------- MAIN --------------------
if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    for name in PLAYLISTS:
        STREAMS[name] = {
            "VIDEO_IDS": load_playlist_ids(name),
            "INDEX": 0,
            "QUEUE": deque(),
            "LOCK": threading.Lock(),
            "LAST_REFRESH": time.time(),
        }
        threading.Thread(target=stream_worker, args=(name,), daemon=True).start()
    threading.Thread(target=update_epaper_json, daemon=True).start()
    logging.info("🎧 Multi-Playlist YouTube Radio + 📰 ePaper Telegram Feed started!")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",8000)))
