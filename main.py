import os
import time
import threading
import datetime
import requests
import brotli
from flask import Flask, render_template_string, request

app = Flask(__name__)

UPLOAD_FOLDER = "static"
NAMAZ_IMAGE = "prayer.jpeg"
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
    <html>
    <head>
        <title>{title}</title>
        <style>
            body {{ font-family: sans-serif; text-align: center; padding: 40px; background-color: #f9f9f9; }}
            h1 {{ margin-bottom: 30px; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 20px; max-width: 1000px; margin: auto; }}
            .card {{ padding: 20px; border-radius: 12px; box-shadow: 2px 2px 10px rgba(0,0,0,0.1); }}
            .card a {{ text-decoration: none; font-size: 18px; color: white; font-weight: bold; }}
            a.back {{ display: inline-block; margin-top: 40px; font-size: 16px; }}
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
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], NAMAZ_IMAGE)
    if os.path.exists(image_path):
        return render_template_string('''
            <!doctype html>
            <html>
            <head><title>Namaz Time</title></head>
            <body style="text-align:center; padding:20px;">
                <h2>Today's Namaz Time</h2>
                <img src="/static/prayer.jpeg" style="width:100%; max-width:600px; border:1px solid #ccc;">
            </body>
            </html>
        ''')
    else:
        return 'Namaz time image not found.', 404

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

@app.route('/upload', methods=['GET', 'POST'])
def upload_prayer_image():
    if request.method == 'POST':
        if 'image' not in request.files:
            return 'No file part'
        file = request.files['image']
        if file.filename == '':
            return 'No selected file'
        if file and file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], NAMAZ_IMAGE))
            return 'Upload successful'
        else:
            return 'Invalid file format'
    return '''
        <form method="post" enctype="multipart/form-data">
            <input type="file" name="image" required>
            <input type="submit" value="Upload">
        </form>
    '''

def update_epaper_json():
    url = "https://api2.suprabhaatham.com/api/ePaper"
    headers = {
        "Content-Type": "application/json",
        "Accept-Encoding": "br"
    }
    payload = {}  # Adjust if API needs any body parameters

    while True:
        try:
            print("Fetching latest ePaper data...")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()

            # Handle the decompression only if the response is encoded in Brotli
            if response.headers.get('Content-Encoding') == 'br':
                try:
                    decompressed_data = brotli.decompress(response.content).decode('utf-8')
                except Exception as e:
                    print(f"Error during Brotli decompression: {e}")
                    decompressed_data = response.text  # Fallback to plain text if decompression fails
            else:
                decompressed_data = response.text

            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(decompressed_data)

            print("epaper.txt updated successfully.")
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")

        time.sleep(86400)  # Sleep for 24 hours

if __name__ == '__main__':
    threading.Thread(target=update_epaper_json, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)