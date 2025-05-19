import os
import datetime
import requests
from flask import Flask, render_template_string
from PIL import Image
from io import BytesIO

app = Flask(__name__)

LOCATIONS = [
    "Kozhikode", "Malappuram", "Kannur", "Thrissur",
    "Kochi", "Thiruvananthapuram", "Palakkad", "Gulf"
]

RGB_COLORS = [
    "#FF6B6B", "#6BCB77", "#4D96FF", "#FFD93D",
    "#FF6EC7", "#00C2CB", "#FFA41B", "#845EC2"
]

def get_url_for_location(location, date=None):
    if date is None:
        date = datetime.datetime.now()
    date_str = date.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

def wrap_grid_page(title, items_html, show_back=True):
    back_html = '<p><a class="back" href="/">Back to Home</a></p>' if show_back else ''
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <style>
            body {{
                font-family: sans-serif;
                text-align: center;
                padding: 40px;
                background-color: #f9f9f9;
            }}
            h1 {{
                margin-bottom: 30px;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 20px;
                max-width: 1000px;
                margin: auto;
            }}
            .card {{
                padding: 20px;
                border-radius: 12px;
                box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
            }}
            .card a {{
                text-decoration: none;
                font-size: 18px;
                color: white;
                font-weight: bold;
            }}
            a.back {{
                display: inline-block;
                margin-top: 40px;
                font-size: 16px;
            }}
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        <div class="grid">
            {items_html}
        </div>
        {back_html}
    </body>
    </html>
    """
    return html_template

@app.route('/')
def homepage():
    cards = ""
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("Namaz Times", "/prayer")
    ]
    for i, (label, link) in enumerate(links):
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'''
        <div class="card" style="background-color:{color};">
            <a href="{link}">{label}</a>
        </div>
        '''
    return render_template_string(wrap_grid_page("Suprabhaatham ePaper", cards, show_back=False))

@app.route('/today')
def show_today_links():
    cards = ""
    for i, loc in enumerate(LOCATIONS):
        url = get_url_for_location(loc)
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'''
        <div class="card" style="background-color:{color};">
            <a href="{url}" target="_blank">{loc}</a>
        </div>
        '''
    return render_template_string(wrap_grid_page("Today's Suprabhaatham ePaper Links", cards))

def crop_lower_left(image, width_ratio=0.4, height_ratio=0.25):
    w, h = image.size
    left = 0
    upper = int(h * (1 - height_ratio))
    right = int(w * width_ratio)
    lower = h
    return image.crop((left, upper, right, lower))

@app.route('/prayer')
def show_prayer_crop():
    today = datetime.datetime.now().strftime('%d-%m-%Y')
    img_url = f"https://e-files.suprabhaatham.com/{today}/Malappuram/{today}-00-05-35-356-epaper-page-5-Malappuram.jpeg"
    
    try:
        response = requests.get(img_url)
        image = Image.open(BytesIO(response.content)).convert("RGB")
        cropped = crop_lower_left(image)
        
        # Save to static file (you can clear/overwrite each day)
        os.makedirs("static", exist_ok=True)
        cropped_path = "static/cropped_namaz.jpg"
        cropped.save(cropped_path)

        return render_template_string(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Namaz Times</title>
            <style>
                body {{ font-family: sans-serif; padding: 40px; background: #f5f5f5; text-align: center; }}
                img {{ max-width: 100%; height: auto; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.2); }}
                a {{ display: block; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <h1>Namaz Times from Suprabhaatham</h1>
            <img src="/static/cropped_namaz.jpg" alt="Cropped Namaz Times">
            <a href="/">Back to Home</a>
        </body>
        </html>
        """)
    except Exception as e:
        return f"Failed to load or process image: {str(e)}"

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
    for i, date in enumerate(reversed(sundays)):
        url = get_url_for_location("Njayar Prabhadham", date)
        date_str = date.strftime('%Y-%m-%d')
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'''
        <div class="card" style="background-color:{color};">
            <a href="{url}" target="_blank">{date_str}</a>
        </div>
        '''
    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)