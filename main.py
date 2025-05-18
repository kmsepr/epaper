import datetime
import requests
from flask import Flask, render_template_string

app = Flask(__name__)

LOCATIONS = [
    "Kozhikode", "Malappuram", "Kannur", "Thrissur",
    "Kochi", "Thiruvananthapuram", "Palakkad"
]

# Coordinates for each location (approximate)
LOCATION_COORDS = {
    "Kozhikode": (11.2588, 75.7804),
    "Malappuram": (11.0735, 76.0746),
    "Kannur": (11.8745, 75.3704),
    "Thrissur": (10.5276, 76.2144),
    "Kochi": (9.9312, 76.2673),
    "Thiruvananthapuram": (8.5241, 76.9366),
    "Palakkad": (10.7867, 76.6548),
}

def get_prayer_times(lat, lon, date=None):
    if date is None:
        date = datetime.datetime.now().strftime("%Y-%m-%d")
    url = f"http://api.aladhan.com/v1/timings/{date}"
    params = {
        "latitude": lat,
        "longitude": lon,
        "method": 2,  # Islamic Society of North America (ISNA)
        "school": 1,  # Hanafi
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data['code'] == 200:
            timings = data['data']['timings']
            # Return relevant prayer times only
            return {
                "Fajr": timings["Fajr"],
                "Dhuhr": timings["Dhuhr"],
                "Asr": timings["Asr"],
                "Maghrib": timings["Maghrib"],
                "Isha": timings["Isha"],
                "Sunrise": timings["Sunrise"],
            }
    return None

@app.route('/')
def homepage():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Suprabhaatham ePaper</title>
        <style>
            body {
                font-family: sans-serif;
                text-align: center;
                margin: 50px;
                background: #f9f9f9;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 30px;
                max-width: 800px;
                margin: 40px auto;
            }
            .card {
                background: white;
                border-radius: 12px;
                padding: 30px 20px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
                transition: transform 0.2s;
            }
            .card:hover {
                transform: scale(1.03);
            }
            .card a {
                text-decoration: none;
                color: #333;
                font-size: 20px;
                font-weight: bold;
                display: block;
            }
        </style>
    </head>
    <body>
        <h1>Suprabhaatham ePaper</h1>
        <div class="grid">
            <div class="card"><a href="/today">Today's Editions</a></div>
            <div class="card"><a href="/njayar">Njayar Prabhadham Archive</a></div>
            <div class="card"><a href="/prayer">Namaz Time</a></div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/prayer')
def prayer_from_canvas():
    def fetch_prayer_screenshot():
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        url = f"https://epaper.suprabhaatham.com/details/Kozhikode/{today}/6"
        os.makedirs("/mnt/data", exist_ok=True)
        page_image_path = "/mnt/data/full_page.jpg"

        try:
            with sync_playwright() as p:
                browser = p.firefox.launch(headless=True)  # Use Firefox here
                context = browser.new_context(viewport={"width": 1600, "height": 1200})
                page = context.new_page()
                page.goto(url)
                page.wait_for_timeout(6000)  # wait for JS to render
                page.screenshot(path=page_image_path, full_page=True)
                browser.close()
            return page_image_path
        except Exception as e:
            print(f"Screenshot error: {e}")
            return None

    def crop_and_ocr(image_path):
        try:
            with Image.open(image_path) as img:
                cropped = img.crop((1200, 200, 1775, 950))  # Adjust cropping as needed
                cropped.save(PRAYER_IMAGE_PATH)
            text = pytesseract.image_to_string(Image.open(PRAYER_IMAGE_PATH), lang='mal')
            return text.strip()
        except Exception as e:
            return f"OCR failed: {e}"

    image_path = fetch_prayer_screenshot()
    if not image_path:
        return "Failed to capture image from flipbook."
    text = crop_and_ocr(image_path)
    return render_template_string(f"""
    <html>
    <head>
        <title>Prayer Times (OCR)</title>
        <style>
            body {{
                font-family: sans-serif;
                text-align: center;
                margin: 50px;
                background: #f4f4f4;
            }}
            pre {{
                background: #fff;
                padding: 20px;
                margin: 30px auto;
                max-width: 800px;
                white-space: pre-wrap;
                border-radius: 8px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
                font-size: 18px;
                line-height: 1.6;
            }}
            a {{
                color: #007BFF;
                text-decoration: none;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <h1>ഇന്ന് നമസ്കാര സമയം</h1>
        <pre>{text}</pre>
        <p><a href="/">Back to Home</a></p>
    </body>
    </html>
    """)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)