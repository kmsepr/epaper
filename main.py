import os
import time
import threading
import datetime
import requests
import brotli
from flask import Flask, render_template_string, request, redirect, url_for
from PIL import Image
from io import BytesIO

app = Flask(__name__)

UPLOAD_FOLDER = "static"
NAMAZ_IMAGE = "prayer.jpg"
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

def get_url_for_location(location, dt_obj=None):
    if dt_obj is None:
        dt_obj = datetime.datetime.now()
    date_str = dt_obj.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

def wrap_grid_page(title, items_html, show_back=True):
    back_html = '<p><a class="back" href="/">Back to Home</a></p>' if show_back else ''
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            body {{
                font-family: 'Segoe UI', sans-serif;
                background: #f0f2f5;
                margin: 0;
                padding: 40px 20px;
                color: #333;
                text-align: center;
            }}
            h1 {{
                font-size: 2em;
                margin-bottom: 30px;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 20px;
                max-width: 1000px;
                margin: auto;
            }}
            .card {{
                padding: 25px 15px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                transition: transform 0.2s ease;
            }}
            .card:hover {{
                transform: translateY(-4px);
            }}
            .card a {{
                text-decoration: none;
                font-size: 1.1em;
                color: #fff;
                font-weight: bold;
                display: block;
            }}
            a.back {{
                display: inline-block;
                margin-top: 40px;
                font-size: 1em;
                color: #555;
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        <div class="grid">{items_html}</div>
        {back_html}
    </body>
    </html>
    """

@app.route('/')
def homepage():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("Prayer Times", "/prayer"),
    ]
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

@app.route('/prayer')
def show_prayer_image():
    if not os.path.exists(os.path.join('static', NAMAZ_IMAGE)):
        return "Prayer image not found", 404
    today = datetime.date.today().strftime("%B %d, %Y")
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Prayer Times</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f4f4f4;
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                }
                .container {
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 0 10px rgba(0,0,0,0.1);
                    text-align: center;
                }
                img {
                    max-width: 100%;
                    height: auto;
                    border-radius: 10px;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Prayer Times - {{ date }}</h2>
                <img src="{{ url_for('static', filename=filename) }}" alt="Prayer Times">
            </div>
        </body>
        </html>
    ''', filename=NAMAZ_IMAGE, date=today)

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
        cards += f'''
        <div class="card" style="background-color:{color};">
            <a href="{url}" target="_blank" rel="noopener noreferrer">{date_str}</a>
        </div>
        '''
    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

def auto_crop_namaz_section():
    try:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        page6_url = f"https://cdn.sprbm.com/pdf2image/{today}/6.jpg"
        response = requests.get(page6_url, timeout=10)
        response.raise_for_status()

        img = Image.open(BytesIO(response.content))
        # Adjust coordinates to match Namaz box on Page 6 (for Kozhikode)
        cropped = img.crop((300, 1200, 1000, 1600))
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        cropped.save(os.path.join(UPLOAD_FOLDER, NAMAZ_IMAGE))
        print("Prayer image updated.")
    except Exception as e:
        print(f"[Error in auto_crop_namaz_section] {e}")

import requests

def update_epaper_json():
    url = "https://api2.suprabhaatham.com/api/ePaper"
    try:
        response = requests.post(url, json={}, timeout=10)
        response.raise_for_status()

        # requests handles Brotli transparently if 'brotli' is installed
        data = response.text

        with open("epaper.txt", "w", encoding="utf-8") as f:
            f.write(data)

        print("epaper.txt updated successfully.")
    except Exception as e:
        print(f"[Error updating epaper.txt] {e}")

        time.sleep(86400)  # Run daily

if __name__ == '__main__':
    threading.Thread(target=update_epaper_json, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)