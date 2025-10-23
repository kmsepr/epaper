import os
import time
import json
import threading
import logging
import subprocess
import random
from collections import deque
from flask import Flask, Response, render_template_string, abort, stream_with_context, request, redirect, url_for
from logging.handlers import RotatingFileHandler

# -----------------------------
# CONFIG & LOGGING
# -----------------------------
LOG_PATH = "/mnt/data/radio.log"
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

handler = RotatingFileHandler(LOG_PATH, maxBytes=5*1024*1024, backupCount=3)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), handler]
)

app = Flask(__name__)

COOKIES_PATH = "/mnt/data/cookies.txt"
CACHE_FILE = "/mnt/data/playlist_cache.json"
PLAYLISTS_FILE = "/mnt/data/playlists.json"  # stores all user playlists
MAX_QUEUE_SIZE = 100  # chunks

# -----------------------------
# LOAD & SAVE PLAYLIST DATA
# -----------------------------
def load_playlists():
    if os.path.exists(PLAYLISTS_FILE):
        try:
            with open(PLAYLISTS_FILE, "r") as f:
                data = json.load(f)
                return data.get("playlists", {}), set(data.get("shuffle", []))
        except Exception as e:
            logging.error(f"Failed to load playlists: {e}")
    # Default playlists
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
STREAMS = {}  # { name: {VIDEO_IDS, INDEX, QUEUE, LOCK, LAST_REFRESH} }

# -----------------------------
# HTML
# -----------------------------
HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube Radio</title>
<style>
body { background:#000;color:#0f0;text-align:center;font-family:sans-serif; }
a { color:#0f0; text-decoration:none; }
.playlist-link {
    display:inline-block; padding:10px; border:1px solid #0f0;
    margin:10px; border-radius:10px; width:60%;
}
.delete-btn {
    color:#f00; font-weight:bold; margin-left:10px; text-decoration:none;
    border:1px solid #f00; padding:6px 10px; border-radius:6px;
}
.delete-btn:hover {
    background:#f00; color:#000;
}
input, button { padding:8px; margin:5px; border-radius:5px; border:none; }
input { width:70%; }
button { background:#0f0;color:#000; font-weight:bold; cursor:pointer; }
.tip {
    color:#888;
    font-size:14px;
    margin-top:30px;
}
</style>
</head>
<body>
<h2>🎧 YouTube Mp3</h2>

{% for name in playlists %}
<div style="margin:10px;">
  <a class="playlist-link" href="/listen/{{name}}">
    ▶️ {{name|capitalize}} Radio {% if name in shuffle_playlists %} 🔀 {% endif %}
  </a>
  <a class="delete-btn" href="/delete/{{name}}" title="Delete Playlist" onclick="return confirm('Delete {{name}}?')">🗑️</a>
</div>
{% endfor %}

<h3>Add New Playlist</h3>
<form method="POST" action="/add_playlist">
    <input type="text" name="name" placeholder="Playlist Name" required>
    <input type="url" name="url" placeholder="Playlist URL" required>
    <label><input type="checkbox" name="shuffle"> Shuffle</label>
    <button type="submit">➕ Add Playlist</button>
</form>

<p class="tip">
💡 Tip: If you want latest video plays first, unselect shuffle — works in most playlists.
</p>

</body>
</html>
"""

PLAYER_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{name|capitalize}} Radio</title>
<style>
body { background:#000; color:#0f0; text-align:center; font-family:sans-serif; }
a { color:#0f0; text-decoration:none; }
audio { width:90%; margin:20px auto; display:block; }
</style>
</head>
<body>
<h3>🎶 {{name|capitalize}} Radio</h3>

<audio controls autoplay>
  <source src="/stream/{{name}}" type="audio/mpeg">
  Your browser does not support audio playback.
</audio>

<p style="margin-top:20px; font-size:18px;">
  🔗 Stream URL:<br>
  <a href="/stream/{{name}}" style="color:#0f0;">{{ request.host_url }}stream/{{name }}</a>
</p>

<p style="margin-top:15px;">🎵 YouTube Playlist:<br>
  <a href="{{ playlist_url }}" target="_blank">{{ playlist_name }}</a>
</p>
</body>
</html>
"""

@app.route("/listen/<name>")
def listen(name):
    if name not in PLAYLISTS:
        abort(404)
    playlist_url = PLAYLISTS.get(name)
    playlist_name = f"{name.capitalize()} Playlist"
    return render_template_string(
        PLAYER_HTML,
        name=name,
        playlist_url=playlist_url,
        playlist_name=playlist_name
    )

# -----------------------------
# CACHE
# -----------------------------
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

# -----------------------------
# LOAD PLAYLIST VIDEO IDS
# -----------------------------
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

# -----------------------------
# STREAM WORKER
# -----------------------------
def stream_worker(name):
    stream = STREAMS[name]
    failed_videos = set()
    played_videos = set()
    shuffle_enabled = name in SHUFFLE_PLAYLISTS

    while True:
        try:
            # Reload if playlist empty
            if not stream["VIDEO_IDS"]:
                logging.info(f"[{name}] Playlist empty, reloading...")
                stream["VIDEO_IDS"] = load_playlist_ids(name, force=True)
                failed_videos.clear()
                played_videos.clear()
                stream["INDEX"] = 0
                if not stream["VIDEO_IDS"]:
                    logging.warning(f"[{name}] No videos available after reload, retrying in 10s...")
                    time.sleep(10)
                    continue

            # Auto-refresh every 30min
            if time.time() - stream["LAST_REFRESH"] > 1800:
                logging.info(f"[{name}] Auto-refreshing playlist IDs...")
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
                    logging.warning(f"[{name}] No available videos to play, retrying in 5s...")
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
                    logging.warning(f"[{name}] No available videos to play, retrying in 5s...")
                    time.sleep(5)
                    continue

            url = f"https://www.youtube.com/watch?v={vid}"
            logging.info(f"[{name}] ▶️ Streaming: {url}")

            # Skip if cookies missing
            if not os.path.exists(COOKIES_PATH) or os.path.getsize(COOKIES_PATH) == 0:
                failed_videos.add(vid)
                continue

            # Get direct audio URL
            try:
                result = subprocess.run(
                    ["yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio", "--cookies", COOKIES_PATH, "-g", url],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
                )
                audio_url = result.stdout.strip()
            except subprocess.CalledProcessError:
                failed_videos.add(vid)
                continue

            # Stream via FFmpeg
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

# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def home():
    return render_template_string(HOME_HTML, playlists=PLAYLISTS.keys(), shuffle_playlists=SHUFFLE_PLAYLISTS)

@app.route("/listen/<name>")
def listen(name):
    if name not in PLAYLISTS:
        abort(404)
    return render_template_string(PLAYER_HTML, name=name)

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
    headers = {
        "Content-Type": "audio/mpeg",
        "Content-Disposition": f'attachment; filename="{name}.mp3"'
    }
    return Response(stream_with_context(generate()), headers=headers)

@app.route("/add_playlist", methods=["POST"])
def add_playlist():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    if not name or not url:
        abort(400, "Name and URL required")

    # --- Clean playlist URL ---
    import re
    match = re.search(r"(?:list=)([A-Za-z0-9_-]+)", url)
    if match:
        url = f"https://www.youtube.com/playlist?list={match.group(1)}"
    else:
        abort(400, "Invalid YouTube playlist URL")

    PLAYLISTS[name] = url
    if request.form.get("shuffle"):
        SHUFFLE_PLAYLISTS.add(name)
    save_playlists()  # persist changes

    video_ids = load_playlist_ids(name)
    if not video_ids:
        logging.warning(f"[{name}] Failed to load playlist, not starting stream")
        return redirect(url_for("home"))

    STREAMS[name] = {
        "VIDEO_IDS": video_ids,
        "INDEX": 0,
        "QUEUE": deque(),
        "LOCK": threading.Lock(),
        "LAST_REFRESH": time.time(),
    }
    threading.Thread(target=stream_worker, args=(name,), daemon=True).start()
    logging.info(f"[{name}] Playlist added and stream started")

    return redirect(url_for("home"))
@app.route("/delete/<name>")
def delete_playlist(name):
    if name not in PLAYLISTS:
        abort(404)

    # Stop and remove stream
    if name in STREAMS:
        del STREAMS[name]

    # Remove from playlists, shuffle, cache
    PLAYLISTS.pop(name, None)
    SHUFFLE_PLAYLISTS.discard(name)
    CACHE.pop(name, None)

    save_cache(CACHE)
    save_playlists()
    logging.info(f"[{name}] Playlist deleted")

    return redirect(url_for("home"))

# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    for name in PLAYLISTS:
        STREAMS[name] = {
            "VIDEO_IDS": load_playlist_ids(name),
            "INDEX": 0,
            "QUEUE": deque(),
            "LOCK": threading.Lock(),
            "LAST_REFRESH": time.time(),
        }
        threading.Thread(target=stream_worker, args=(name,), daemon=True).start()

    logging.info("🎧 Multi-Playlist YouTube Radio started!")
    logging.info(f"Logs: {LOG_PATH}")
    app.run(host="0.0.0.0", port=5000)
