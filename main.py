import os
import time
import json
import threading
import datetime
import requests
import brotli
from flask import Flask, render_template_string, request, redirect, url_for

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
        ("Njayar Prabhadham Archive", "/njayar")
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

def update_epaper_json():
    url = "https://api2.suprabhaatham.com/api/ePaper"
    headers = {
        "Content-Type": "application/json",
        "Accept-Encoding": "br"
    }
    payload = {}

    while True:
        try:
            print("Fetching latest ePaper data...")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()

            if response.headers.get('Content-Encoding') == 'br':
                try:
                    decompressed_data = brotli.decompress(response.content).decode('utf-8')
                except Exception as e:
                    print(f"Error during Brotli decompression: {e}")
                    decompressed_data = response.text
            else:
                decompressed_data = response.text

            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(decompressed_data)

            print("epaper.txt updated successfully.")
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")

        time.sleep(86400)  # Wait for 24 hours

@app.route('/malappuram/pages')
def show_malappuram_pages():
    if not os.path.exists(EPAPER_TXT):
        return "epaper.txt not found", 404

    try:
        with open(EPAPER_TXT, "r", encoding="utf-8") as f:
            data = json.load(f)

        pages = [
            entry for entry in data.get("data", [])
            if entry.get("Location") == "Malappuram"
        ]

        if not pages:
            return "No pages found for Malappuram.", 404

        cards = ""
        for i, page in enumerate(sorted(pages, key=lambda x: x.get("PageNo", 0))):
            img_url = page.get("Image")
            page_no = page.get("PageNo", "N/A")
            date = page.get("Date", "")
            cards += f'''
            <div class="card" style="background-color:{RGB_COLORS[i % len(RGB_COLORS)]};">
                <a href="{img_url}" target="_blank">Page {page_no}<br><small>{date}</small></a>
            </div>
            '''

        return render_template_string(wrap_grid_page("Malappuram - All Pages", cards))

    except Exception as e:
        return f"Error: {e}", 500

if __name__ == '__main__':
    threading.Thread(target=update_epaper_json, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)