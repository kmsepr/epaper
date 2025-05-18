import os
import datetime
import requests
from PIL import Image
from flask import Flask, render_template_string, send_file

app = Flask(__name__)

LOCATIONS = [
    "Kozhikode", "Malappuram", "Kannur", "Thrissur",
    "Kochi", "Thiruvananthapuram", "Palakkad", "Gulf"
]

def get_url_for_location(location, date=None):
    if date is None:
        date = datetime.datetime.now()
    date_str = date.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

def crop_prayer_time_section():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    image_url = f"https://epaper.suprabhaatham.com/wp-content/uploads/epaper/{today}/6.jpg"
    os.makedirs("/mnt/data", exist_ok=True)
    image_path = "/mnt/data/page_6.jpg"
    cropped_path = "/mnt/data/prayer_today.jpg"

    try:
        r = requests.get(image_url, timeout=10)
        r.raise_for_status()
        with open(image_path, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"Error downloading page 6: {e}")
        return False

    try:
        with Image.open(image_path) as img:
            # Adjust crop box (left, upper, right, lower) as per layout
            cropped = img.crop((1200, 200, 1775, 950))
            cropped.save(cropped_path)
        return True
    except Exception as e:
        print(f"Error cropping image: {e}")
        return False

def ensure_fresh_prayer_image():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    meta_path = "/mnt/data/prayer_meta.txt"
    if not os.path.exists(meta_path) or open(meta_path).read().strip() != today:
        if crop_prayer_time_section():
            with open(meta_path, "w") as f:
                f.write(today)

@app.route('/')
def homepage():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Suprabhaatham ePaper</title>
    </head>
    <body style="font-family:sans-serif; text-align:center; margin-top:80px;">
        <h1>Suprabhaatham ePaper</h1>
        <p style="font-size:20px;"><a href="/today">Today's Editions</a></p>
        <p style="font-size:20px;"><a href="/njayar">Njayar Prabhadham Archive</a></p>
        <p style="font-size:20px;"><a href="/prayer">Namaz Time</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/today')
def show_today_links():
    date = datetime.datetime.now().strftime('%Y-%m-%d')
    colors = ['#e3f2fd', '#fce4ec', '#e8f5e9', '#fff3e0', '#ede7f6', '#f3e5f5', '#e0f7fa', '#f9fbe7']
    html_blocks = ""

    for i, loc in enumerate(LOCATIONS):
        url = get_url_for_location(loc)
        bg = colors[i % len(colors)]
        html_blocks += f"""
        <div style="background:{bg}; padding:20px; border-radius:12px; text-align:center;">
            <a href="{url}" target="_blank" style="font-size:20px; font-weight:bold; color:#000; text-decoration:none;">{loc}</a>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Today's Suprabhaatham Editions</title></head>
    <body style="font-family:sans-serif; text-align:center; margin:40px;">
      <h1>Today's Suprabhaatham ePaper ({date})</h1>
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:20px; max-width:800px; margin:0 auto;">
        {html_blocks}
      </div>
      <p style="margin-top:40px;"><a href="/">Back to Home</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/njayar')
def show_njayar_archive():
    start_date = datetime.date(2024, 6, 30)
    today = datetime.date.today()
    sundays = []
    current = start_date
    while current <= today:
        sundays.append(current)
        current += datetime.timedelta(days=7)

    colors = ['#e3f2fd', '#fce4ec', '#e8f5e9', '#fff3e0', '#ede7f6', '#f3e5f5', '#e0f7fa', '#f9fbe7']
    html_blocks = ""
    for i, date in enumerate(reversed(sundays)):
        url = get_url_for_location("Njayar Prabhadham", date)
        label = date.strftime('%Y %B %d')
        bg = colors[i % len(colors)]
        if date == today:
            label += " (Today)"
        html_blocks += f"""
        <div style="background:{bg}; padding:20px; border-radius:12px; text-align:center;">
            <a href="{url}" target="_blank" style="font-size:18px; font-weight:bold; color:#000; text-decoration:none;">{label}</a>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Njayar Prabhadham Archive</title></head>
    <body style="font-family:sans-serif; text-align:center; margin:40px;">
      <h1>Njayar Prabhadham - Sunday Editions</h1>
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:20px; max-width:900px; margin:0 auto;">
        {html_blocks}
      </div>
      <p style="margin-top:40px;"><a href="/">Back to Home</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/prayer')
def show_prayer_image():
    path = "/mnt/data/prayer_today.jpg"
    if os.path.exists(path):
        return send_file(path, mimetype='image/jpeg')
    else:
        return "Prayer time image not available yet.", 404

if __name__ == '__main__':
    ensure_fresh_prayer_image()
    app.run(host='0.0.0.0', port=8000)