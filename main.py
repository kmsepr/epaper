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
    "AnotherChannel": "https://t.me/s/AnotherChannel"
}
XML_FOLDER = "telegram_xml"
os.makedirs(XML_FOLDER, exist_ok=True)

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
            link = date_tag["href"] if date_tag else url
            text_tag = msg.select_one(".tgme_widget_message_text")
            desc_html = text_tag.decode_contents() if text_tag else ""
            item = ET.SubElement(ch, "item")
            ET.SubElement(item, "title").text = BeautifulSoup(desc_html, "html.parser").get_text(strip=True)[:80]
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
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width,initial-scale=1.0">
        <title>Browser - {url}</title>
        <style>
            body {{margin:0;background:#000;height:100vh;display:flex;flex-direction:column;}}
            iframe {{border:none;flex:1;width:100%;}}
            .topbar {{
                background:#111;color:white;display:flex;align-items:center;
                padding:6px;gap:8px;font-family:sans-serif;
            }}
            input[type=text] {{
                flex:1;padding:6px;border-radius:4px;border:none;outline:none;
            }}
            button {{background:#0078cc;color:white;border:none;padding:6px 10px;border-radius:4px;}}
        </style>
    </head>
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
            function go(e) {{
                e.preventDefault();
                const url = document.getElementById('addr').value.trim();
                window.location = '/browse?url=' + encodeURIComponent(url);
            }}
            function home() {{ window.location = '/'; }}
        </script>
    </body>
    </html>
    """

# ------------------ Telegram HTML ------------------
@app.route("/telegram/<channel_name>")
def telegram_html(channel_name):
    path = os.path.join(XML_FOLDER, f"{channel_name}.xml")
    if not os.path.exists(path):
        fetch_telegram_xml(channel_name, TELEGRAM_CHANNELS.get(channel_name, ""))
    try:
        feed = feedparser.parse(path)
        posts = ""
        for e in reversed(feed.entries[:30]):
            title = e.get("title", "")
            link = e.get("link", "#")
            posts += f"<div class='post'><a href='{link}' target='_blank'>{title}</a></div>"
        return f"""
        <html><head><meta name='viewport' content='width=device-width,initial-scale=1.0'>
        <style>
        body{{font-family:sans-serif;background:#f9f9f9;padding:10px;}}
        a{{text-decoration:none;color:#0078cc;}}
        .post{{background:#fff;margin:10px 0;padding:10px;border-radius:8px;}}
        </style></head><body>
        <h2>{channel_name}</h2>
        {posts or "<p>No posts.</p>"}
        <p><a href="/">🏠 Home</a></p>
        </body></html>
        """
    except Exception as e:
        return f"<p>Error: {e}</p>"

# ------------------ ePaper Routes ------------------
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
    start = datetime.date(2019, 1, 6)
    today = datetime.date.today()
    cutoff = datetime.date(2024, 6, 30)
    sundays = []
    d = start
    while d <= today:
        if d >= cutoff:
            sundays.append(d)
        d += datetime.timedelta(days=7)
    cards = ""
    for i, d in enumerate(reversed(sundays)):
        url = get_url_for_location("Njayar Prabhadham", d)
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background:{color}"><a href="/browse?url={url}">{d}</a></div>'
    return render_template_string(wrap_home("Njayar Prabhadham - Sundays", cards))

# ------------------ Home (Browser Hub) ------------------
def wrap_home(title, inner):
    return f"""
    <!DOCTYPE html><html><head>
    <meta name="viewport" content="width=device-width,initial-scale=1.0">
    <title>{title}</title>
    <style>
        body{{font-family:'Segoe UI',sans-serif;background:#f0f2f5;margin:0;padding:20px;text-align:center;}}
        h1{{margin-bottom:20px;}}
        .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:15px;max-width:800px;margin:auto;}}
        .card{{padding:20px;border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,0.1);}}
        .card a{{color:white;text-decoration:none;font-weight:bold;display:block;}}
        .add{{background:#555;cursor:pointer;color:white;font-size:2em;}}
        #modal{{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);
                align-items:center;justify-content:center;}}
        #modal .box{{background:white;padding:20px;border-radius:10px;width:90%;max-width:350px;text-align:left;}}
        input{{width:100%;margin-bottom:10px;padding:8px;}}
        button{{background:#0078cc;color:white;border:none;padding:8px 12px;border-radius:6px;}}
        .edit,.del{{position:absolute;top:6px;font-size:0.8em;background:rgba(255,255,255,0.8);
                     border:none;border-radius:4px;}}
        .del{{right:8px;}} .edit{{right:40px;}}
    </style></head>
    <body>
        <h1>{title}</h1>
        <div class="grid" id="grid">{inner}<div class="card add" onclick="openModal()">+</div></div>
        <div id="modal">
            <div class="box">
                <h3 id="modalTitle">Add Website</h3>
                <input type="text" id="name" placeholder="Name">
                <input type="text" id="url" placeholder="URL (https://...)">
                <button onclick="save()">Save</button>
                <button onclick="closeModal()" style="background:#777;">Cancel</button>
            </div>
        </div>
        <script>
            let editIndex=null;
            function openModal(i=null) {{
                editIndex=i;
                document.getElementById('modal').style.display='flex';
                if(i!==null){{
                    let data=JSON.parse(localStorage.getItem('customGrids')||'[]')[i];
                    name.value=data.name;url.value=data.url;
                }} else{{name.value='';url.value='';}}
            }}
            function closeModal(){{document.getElementById('modal').style.display='none';}}
            function save(){{
                let n=name.value.trim(),u=url.value.trim();
                if(!n||!u)return alert('Enter name & URL');
                let arr=JSON.parse(localStorage.getItem('customGrids')||'[]');
                if(editIndex!==null)arr[editIndex]={{name:n,url:u}};else arr.push({{name:n,url:u}});
                localStorage.setItem('customGrids',JSON.stringify(arr));
                closeModal();render();
            }}
            function del(i){{
                if(!confirm('Delete this site?'))return;
                let arr=JSON.parse(localStorage.getItem('customGrids')||'[]');
                arr.splice(i,1);
                localStorage.setItem('customGrids',JSON.stringify(arr));
                render();
            }}
            function render(){{
                document.querySelectorAll('.custom').forEach(e=>e.remove());
                let arr=JSON.parse(localStorage.getItem('customGrids')||'[]');
                let grid=document.getElementById('grid');
                arr.forEach((g,i)=>{{
                    let d=document.createElement('div');
                    d.className='card custom';
                    d.style.background='{RGB_COLORS[3]}';
                    d.innerHTML=`<a href="/browse?url=${{encodeURIComponent(g.url)}}" target="_self">${{g.name}}</a>
                                 <button class='del' onclick='del(${{i}})'>✕</button>
                                 <button class='edit' onclick='openModal(${{i}})'>✎</button>`;
                    grid.insertBefore(d,grid.lastElementChild);
                }});
            }}
            render();
        </script>
    </body></html>
    """

@app.route("/")
def home():
    cards = ""
    for i, (label, link) in enumerate([
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
    ]):
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background:{color}"><a href="{link}">{label}</a></div>'
    for i, (name, _) in enumerate(TELEGRAM_CHANNELS.items()):
        color = RGB_COLORS[(i + 2) % len(RGB_COLORS)]
        cards += f'<div class="card" style="background:{color}"><a href="/telegram/{name}">{name}</a></div>'
    return render_template_string(wrap_home("Mini Browser Home", cards))

# ------------------ Run ------------------
if __name__ == "__main__":
    threading.Thread(target=update_epaper_json, daemon=True).start()
    threading.Thread(target=telegram_updater, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)