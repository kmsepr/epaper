import datetime
import time
from flask import Flask, render_template_string, redirect
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

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
    if not date:
        date = datetime.date.today().strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date}/1"

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
        <div class="grid">
            {items_html}
        </div>
        {back_html}
    </body>
    </html>
    """

@app.route('/')
def homepage():
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("Editorial", "/editorial")
    ]
    cards = ""
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
    today = datetime.date.today().strftime('%Y-%m-%d')
    cards = ""
    for i, loc in enumerate(LOCATIONS):
        url = get_url_for_location(loc, today)
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'''
        <div class="card" style="background-color:{color};">
            <a href="{url}" target="_blank">{loc}</a>
        </div>
        '''
    return render_template_string(wrap_grid_page("Today's Suprabhaatham ePaper Links", cards))

@app.route('/editorial')
def editorial():
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("/usr/bin/chromedriver")  # adjust path if needed

        with webdriver.Chrome(service=service, options=chrome_options) as driver:
            driver.get("https://epaper.suprabhaatham.com")
            time.sleep(7)
            img_elements = driver.find_elements("tag name", "img")
            for img in img_elements:
                src = img.get_attribute("src")
                if src and "epaper-page-5" in src and "Kozhikode" in src:
                    return redirect(src)
        return "Editorial image not found", 404
    except WebDriverException as e:
        print("WebDriver Error:", e)
        return "Unable to load headless browser.", 500

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
        url = get_url_for_location("Njayar Prabhadham", date.strftime('%Y-%m-%d'))
        date_str = date.strftime('%Y-%m-%d')
        color = RGB_COLORS[i % len(RGB_COLORS)]
        label = "Today" if date == today else date_str
        cards += f'''
        <div class="card" style="background-color:{color};">
            <a href="{url}" target="_blank">{label}</a>
        </div>
        '''
    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)