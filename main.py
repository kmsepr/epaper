#!/usr/bin/env python3
import os
import time
import json
import threading
import logging
import subprocess
import random
import re
from collections import deque
from flask import Flask, Response, render_template_string, abort, stream_with_context, request, redirect, url_for, jsonify
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
MAX_QUEUE_SIZE = 200  # number of 4KB chunks allowed in queue (controls memory)
INITIAL_BUFFER_CHUNKS = 8  # how many chunks we want in queue before client gets first bytes
CHUNK_SIZE = 4096

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
    # Default playlists (examples)
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
STREAMS = {}  # name -> stream state
CACHE = {}

# -----------------------------
# HTML TEMPLATES (modernized)
# -----------------------------
HOME_HTML = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube Radio</title>
<style>
:root { --bg:#0b0b0b; --card:#0f1720; --accent:#00ff8a; --muted:#8f9aa3; --danger:#ff5c5c; }
body { margin:0; padding:20px; background:var(--bg); color:var(--accent); font-family:Inter, system-ui, sans-serif; }
.header { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:18px; }
h1 { margin:0; font-size:20px; }
.controls { display:flex; gap:8px; align-items:center; }
.grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(220px,1fr)); gap:14px; }
.card { background:linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01)); padding:14px; border-radius:12px; border:1px solid rgba(255,255,255,0.03); }
.card h3 { margin:0 0 8px 0; font-size:18px; color:var(--accent); text-transform:capitalize; }
.card p { margin:0 0 10px 0; color:var(--muted); font-size:13px; }
.card a.button { display:inline-block; padding:8px 10px; border-radius:8px; text-decoration:none; color:#000; background:var(--accent); font-weight:600; margin-right:6px; }
.card a.delete { padding:7px 9px; border-radius:8px; text-decoration:none; color:var(--accent); border:1px solid var(--danger); }
.form { margin-top:18px; background:transparent; display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
input[type="text"], input[type="url"] { padding:10px; border-radius:8px; border:1px solid rgba(255,255,255,0.04); background:transparent; color:var(--accent); min-width:200px; }
label { color:var(--muted); font-size:13px; }
.small { font-size:13px; color:var(--muted); margin-top:8px; }
.footer { margin-top:24px; color:var(--muted); font-size:13px; }
@media (max-width:560px){ .controls{width:100%; justify-content:space-between} .form{flex-direction:column; align-items:stretch} input { width:100%; } }
</style>
</head>
<body>
<div class="header">
  <h1>🎧 YouTube Radio</h1>
  <div class="controls">
    <a href="/" style="text-decoration:none; color:var(--muted);">Home</a>
    <span class="small">Playlists: {{playlists|length}}</span>
  </div>
</div>

<div class="grid">
{% for name, url in playlists.items() %}
  <div class="card">
    <h3>{{name}}</h3>
    <p>{{ url }}</p>
    <div>
      <a class="button" href="/listen/{{ name }}">Listen</a>
      <a class="delete" href="/delete/{{ name }}" onclick="return confirm('Delete {{name}}?')">Delete</a>
      <a class="delete" href="/reload/{{ name }}" style="margin-left:6px;">Reload</a>
      <a class="delete" href="/skip/{{ name }}" style="margin-left:6px;">Skip</a>
    </div>
  </div>
{% endfor %}
</div>

<form class="form" method="POST" action="/add_playlist">
  <input type="text" name="name" placeholder="Playlist name (unique)" required>
  <input type="url" name="url" placeholder="YouTube playlist URL" required>
  <label><input type="checkbox" name="shuffle"> Shuffle</label>
  <button style="padding:10px 12px; border-radius:8px; background:var(--accent); border:none; font-weight:700; cursor:pointer;" type="submit">Add</button>
</form>

<p class="footer">Tip: If you want the newest videos first, do not select Shuffle.</p>
</body>
</html>
"""

PLAYER_HTML = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{name|capitalize}} Radio</title>
<style>
body{background:#000;color:#0f0;font-family:Inter, sans-serif;text-align:center;padding:18px;}
audio{width:96%;max-width:760px;margin:16px auto;display:block;}
.meta{color:#9ad9b3;margin-top:12px;}
.meta a{color:#9ad9b3;text-decoration:none;}
.controls{margin-top:12px;}
.btn{display:inline-block;padding:8px 12px;border-radius:8px;background:#0f0;color:#000;margin:6px;text-decoration:none;font-weight:700;}
.small{color:#8f9aa3;font-size:14px;margin-top:10px;}
</style>
</head>
<body>
<h2>🎶 {{name|capitalize}} Radio</h2>

<audio controls autoplay>
  <source src="/stream/{{name}}" type="audio/mpeg">
  Your browser doesn't support audio.
</audio>

<div class="meta">
  <div>Now playing:</div>
  {% if current_title %}
    <div style="margin-top:8px;"><a href="{{ current_url }}" target="_blank">{{ current_title }}</a></div>
  {% else %}
    <div style="margin-top:8px;">— loading —</div>
  {% endif %}
</div>

<div class="controls">
  <a class="btn" href="/">◀ Back</a>
  <a class="btn" href="/reload/{{name}}">🔁 Reload</a>
  <a class="btn" href="/skip/{{name}}">⏭ Skip</a>
</div>

<div class="small">Stream URL: <a href="/stream/{{name}}">{{request.host_url}}stream/{{name}}</a></div>
</body>
</html>
"""

# -----------------------------
# CACHE HELPERS
# -----------------------------
def load_cache():
    global CACHE
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                CACHE = json.load(f)
        except Exception as e:
            logging.error(f"Failed to load cache: {e}")
            CACHE = {}
    else:
        CACHE = {}

def save_cache():
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(CACHE, f)
    except Exception as e:
        logging.error(f"Failed to save cache: {e}")

load_cache()

# -----------------------------
# YT-DLP: get playlist ids
# -----------------------------
def load_playlist_ids(name, force=False):
    now = time.time()
    cached = CACHE.get(name, {})
    if not force and cached and now - cached.get("time", 0) < 1800:
        logging.info(f"[{name}] Using cached playlist IDs ({len(cached.get('ids',[]))} videos)")
        return cached.get("ids", [])

    url = PLAYLISTS[name]
    try:
        logging.info(f"[{name}] Refreshing playlist IDs from yt-dlp...")
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
        save_cache()
        logging.info(f"[{name}] Loaded {len(video_ids)} video IDs successfully")
        return video_ids
    except Exception as e:
        logging.error(f"[{name}] Playlist load failed: {e}")
        return cached.get("ids", [])

# -----------------------------
# Utility to fetch direct audio URL + title using yt-dlp (best-effort)
# -----------------------------
def resolve_audio_url_and_title(yt_url):
    """
    Use yt-dlp to:
    - get a playable audio URL (-g)
    - get title metadata (-j)
    Return (audio_url, title) or (None, None) on failure.
    """
    try:
        # get audio URL
        p1 = subprocess.run(
            ["yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio", "--cookies", COOKIES_PATH, "-g", yt_url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        audio_url = p1.stdout.strip().splitlines()[0].strip() if p1.stdout else None

        # get title
        p2 = subprocess.run(
            ["yt-dlp", "--no-warnings", "--skip-download", "-j", yt_url, "--cookies", COOKIES_PATH],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        info = json.loads(p2.stdout) if p2.stdout else {}
        title = info.get("title", None)
        return audio_url, title
    except Exception as e:
        logging.debug(f"resolve_audio_url_and_title failed for {yt_url}: {e}")
        return None, None

# -----------------------------
# STREAM WORKER (producer)
# -----------------------------
def stream_worker(name):
    state = STREAMS[name]
    failed_videos = set()
    played_videos = set()
    shuffle_enabled = name in SHUFFLE_PLAYLISTS

    while True:
        try:
            # Ensure we have video IDs
            if not state["VIDEO_IDS"]:
                logging.info(f"[{name}] Playlist empty, loading...")
                state["VIDEO_IDS"] = load_playlist_ids(name, force=True)
                failed_videos.clear()
                played_videos.clear()
                state["INDEX"] = 0
                if not state["VIDEO_IDS"]:
                    logging.warning(f"[{name}] No videos available; retrying in 10s")
                    time.sleep(10)
                    continue

            # Auto refresh every 30 minutes
            if time.time() - state.get("LAST_REFRESH", 0) > 1800:
                logging.info(f"[{name}] Auto-refreshing playlist IDs...")
                state["VIDEO_IDS"] = load_playlist_ids(name, force=True)
                failed_videos.clear()
                played_videos.clear()
                state["INDEX"] = 0
                state["LAST_REFRESH"] = time.time()
                if shuffle_enabled:
                    random.shuffle(state["VIDEO_IDS"])

            # pick video
            vid = None
            if shuffle_enabled:
                available = [v for v in state["VIDEO_IDS"] if v not in failed_videos and v not in played_videos]
                if not available:
                    played_videos.clear()
                    available = [v for v in state["VIDEO_IDS"] if v not in failed_videos]
                if not available:
                    logging.warning(f"[{name}] No available videos after filtering; retrying in 5s")
                    time.sleep(5)
                    continue
                vid = random.choice(available)
                played_videos.add(vid)
            else:
                for _ in range(len(state["VIDEO_IDS"])):
                    idx = state["INDEX"] % len(state["VIDEO_IDS"])
                    cand = state["VIDEO_IDS"][idx]
                    state["INDEX"] += 1
                    if cand not in failed_videos:
                        vid = cand
                        break
                if vid is None:
                    logging.warning(f"[{name}] No available videos in non-shuffle mode; sleeping")
                    time.sleep(5)
                    continue

            yt_url = f"https://www.youtube.com/watch?v={vid}"
            logging.info(f"[{name}] Selected video {yt_url}")

            # Check cookies presence
            if not os.path.exists(COOKIES_PATH) or os.path.getsize(COOKIES_PATH) == 0:
                logging.warning(f"[{name}] Cookies missing/empty — marking video as failed")
                failed_videos.add(vid)
                time.sleep(1)
                continue

            audio_url, title = resolve_audio_url_and_title(yt_url)
            if not audio_url:
                logging.warning(f"[{name}] Could not resolve audio url for {yt_url}; marking failed")
                failed_videos.add(vid)
                continue

            # update metadata in state for player page
            with state["LOCK"]:
                state["CURRENT_TITLE"] = title or f"Video {vid}"
                state["CURRENT_URL"] = yt_url
                state["CURRENT_VIDEO_ID"] = vid
                # clear skip event
                state["SKIP_EVENT"].clear()

            # start ffmpeg to re-encode/convert to mp3 stream
            cmd = [
                "ffmpeg", "-re", "-i", audio_url,
                "-b:a", "48k", "-ac", "1", "-f", "mp3", "pipe:1", "-loglevel", "warning"
            ]
            logging.info(f"[{name}] Starting ffmpeg for {vid}")
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # register process object
            with state["LOCK"]:
                state["PROC"] = proc

            # read stdout and place into queue (producer)
            try:
                while True:
                    # skip requested?
                    if state["SKIP_EVENT"].is_set():
                        logging.info(f"[{name}] Skip requested; terminating ffmpeg")
                        try:
                            proc.kill()
                        except Exception:
                            pass
                        break

                    chunk = proc.stdout.read(CHUNK_SIZE)
                    if not chunk:
                        # stream ended naturally
                        break

                    # backpressure: drop if queue full
                    if len(state["QUEUE"]) < MAX_QUEUE_SIZE:
                        state["QUEUE"].append(chunk)
                        # notify any waiting consumers that we have data
                        with state["REFILL_COND"]:
                            state["REFILL_COND"].notify_all()
                    else:
                        # queue full; small sleep to avoid hogging CPU & let consumer drain
                        time.sleep(0.03)
            finally:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
                try:
                    proc.stderr.close()
                except Exception:
                    pass
                proc.wait()
                with state["LOCK"]:
                    state["PROC"] = None

            # small gap between videos
            time.sleep(0.2)

        except Exception as e:
            logging.exception(f"[{name}] Worker exception: {e}")
            time.sleep(3)

# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def home():
    return render_template_string(HOME_HTML, playlists=PLAYLISTS, shuffle_playlists=SHUFFLE_PLAYLISTS)

@app.route("/listen/<name>")
def listen(name):
    if name not in PLAYLISTS:
        abort(404)
    state = STREAMS.get(name, {})
    current_title = state.get("CURRENT_TITLE")
    current_url = state.get("CURRENT_URL")
    return render_template_string(PLAYER_HTML, name=name, current_title=current_title, current_url=current_url)

@app.route("/stream/<name>")
def stream_audio(name):
    if name not in STREAMS:
        abort(404)
    state = STREAMS[name]

    def generate():
        # Wait until we have some buffered chunks or timeout
        start_wait = time.time()
        timeout = 8.0  # seconds
        while True:
            if len(state["QUEUE"]) >= INITIAL_BUFFER_CHUNKS:
                logging.debug(f"[{name}] Initial buffer ready ({len(state['QUEUE'])} chunks). Starting stream.")
                break
            if time.time() - start_wait > timeout:
                logging.debug(f"[{name}] Buffer timeout after {timeout}s, starting with {len(state['QUEUE'])} chunks.")
                break
            # wait on condition
            with state["REFILL_COND"]:
                state["REFILL_COND"].wait(timeout=0.5)

        # continuous streaming
        while True:
            # If skip requested and queue has some items, clear queue immediately to jump next
            if state["SKIP_EVENT"].is_set():
                # clear queue to make worker pick new video
                with state["LOCK"]:
                    state["QUEUE"].clear()
                # allow worker a moment
                time.sleep(0.15)

            if state["QUEUE"]:
                chunk = state["QUEUE"].popleft()
                yield chunk
            else:
                # no data, wait briefly
                with state["REFILL_COND"]:
                    state["REFILL_COND"].wait(timeout=0.2)
                # nothing yielded yet; loop re-checks

    headers = {
        "Content-Type": "audio/mpeg",
        "Content-Disposition": f'inline; filename="{name}.mp3"'
    }
    return Response(stream_with_context(generate()), headers=headers)

@app.route("/add_playlist", methods=["POST"])
def add_playlist():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    if not name or not url:
        abort(400, "Name and URL required")

    # Clean playlist URL (extract list=)
    match = re.search(r"(?:list=)([A-Za-z0-9_-]+)", url)
    if match:
        url = f"https://www.youtube.com/playlist?list={match.group(1)}"
    else:
        abort(400, "Invalid YouTube playlist URL")

    if name in PLAYLISTS:
        abort(400, "Playlist name already exists (use unique name)")

    PLAYLISTS[name] = url
    if request.form.get("shuffle"):
        SHUFFLE_PLAYLISTS.add(name)
    save_playlists()

    # try load video ids
    video_ids = load_playlist_ids(name)
    if not video_ids:
        logging.warning(f"[{name}] Failed to load playlist; added but won't start stream now")
        return redirect(url_for("home"))

    # initialize stream state and start worker
    STREAMS[name] = {
        "VIDEO_IDS": video_ids,
        "INDEX": 0,
        "QUEUE": deque(),
        "LOCK": threading.Lock(),
        "REFILL_COND": threading.Condition(),
        "LAST_REFRESH": time.time(),
        "CURRENT_TITLE": None,
        "CURRENT_URL": None,
        "CURRENT_VIDEO_ID": None,
        "PROC": None,
        "SKIP_EVENT": threading.Event()
    }
    t = threading.Thread(target=stream_worker, args=(name,), daemon=True)
    t.start()
    logging.info(f"[{name}] Playlist added and worker started")
    return redirect(url_for("home"))

@app.route("/delete/<name>")
def delete_playlist(name):
    if name not in PLAYLISTS:
        abort(404)

    # try terminate worker's ffmpeg if running
    state = STREAMS.get(name)
    if state:
        with state["LOCK"]:
            proc = state.get("PROC")
            if proc:
                try:
                    proc.kill()
                except Exception:
                    pass
        # drop state
        STREAMS.pop(name, None)

    # remove persisted data
    PLAYLISTS.pop(name, None)
    SHUFFLE_PLAYLISTS.discard(name)
    CACHE.pop(name, None)
    save_cache()
    save_playlists()
    logging.info(f"[{name}] Playlist deleted")
    return redirect(url_for("home"))

@app.route("/reload/<name>")
def reload_playlist(name):
    """Manual reload of playlist IDs"""
    if name not in PLAYLISTS:
        abort(404)
    try:
        ids = load_playlist_ids(name, force=True)
        if not ids:
            logging.warning(f"[{name}] Manual reload returned no ids")
            return jsonify({"status":"error","message":"No videos loaded"}), 500

        # update stream state
        state = STREAMS.get(name)
        if state:
            with state["LOCK"]:
                state["VIDEO_IDS"] = ids
                state["INDEX"] = 0
                state["LAST_REFRESH"] = time.time()
                state["SKIP_EVENT"].set()  # cause worker to break from current and pick new list
        else:
            # not started - create and start
            STREAMS[name] = {
                "VIDEO_IDS": ids,
                "INDEX": 0,
                "QUEUE": deque(),
                "LOCK": threading.Lock(),
                "REFILL_COND": threading.Condition(),
                "LAST_REFRESH": time.time(),
                "CURRENT_TITLE": None,
                "CURRENT_URL": None,
                "CURRENT_VIDEO_ID": None,
                "PROC": None,
                "SKIP_EVENT": threading.Event()
            }
            threading.Thread(target=stream_worker, args=(name,), daemon=True).start()

        logging.info(f"[{name}] Playlist manually reloaded")
        return redirect(url_for("listen", name=name))
    except Exception as e:
        logging.exception(f"[{name}] Reload failed: {e}")
        return jsonify({"status":"error","message":"reload failed"}), 500

@app.route("/skip/<name>")
def skip_current(name):
    """Request worker to skip to next video"""
    if name not in STREAMS:
        abort(404)
    state = STREAMS[name]
    logging.info(f"[{name}] Skip requested via /skip")
    # set event — worker checks it and kills ffmpeg
    state["SKIP_EVENT"].set()
    # clear queue so consumer will wait for next track
    with state["LOCK"]:
        state["QUEUE"].clear()
    # small pause to let worker act
    time.sleep(0.15)
    return redirect(url_for("listen", name=name))

# -----------------------------
# STARTUP: initialize STREAMS for existing playlists
# -----------------------------
if __name__ == "__main__":
    # initialize streams for each playlist (but only if playlist can be loaded)
    for name in list(PLAYLISTS.keys()):
        ids = load_playlist_ids(name)
        STREAMS[name] = {
            "VIDEO_IDS": ids,
            "INDEX": 0,
            "QUEUE": deque(),
            "LOCK": threading.Lock(),
            "REFILL_COND": threading.Condition(),
            "LAST_REFRESH": time.time(),
            "CURRENT_TITLE": None,
            "CURRENT_URL": None,
            "CURRENT_VIDEO_ID": None,
            "PROC": None,
            "SKIP_EVENT": threading.Event()
        }
        # only start worker if we got ids
        if ids:
            threading.Thread(target=stream_worker, args=(name,), daemon=True).start()
            logging.info(f"[{name}] Worker thread started at startup")
        else:
            logging.warning(f"[{name}] No video ids loaded at startup; worker not started")

    logging.info("🎧 YouTube Radio (upgraded) started!")
    logging.info(f"Logs: {LOG_PATH}")
    app.run(host="0.0.0.0", port=8000)
