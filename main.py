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
    headers = {
        "Referer": f"https://epaper.suprabhaatham.com/details/Kozhikode/{today}/6",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    os.makedirs("/mnt/data", exist_ok=True)
    image_path = "/mnt/data/page_6.jpg"
    cropped_path = "/mnt/data/prayer_today.jpg"

    try:
        r = requests.get(image_url, headers=headers, timeout=10)
        r.raise_for_status()
        with open(image_path, "wb") as f:
            f.write(r.content)
    except Exception as e:
        print(f"Error downloading page 6: {e}")
        return False

    try:
        with Image.open(image_path) as img:
            # Crop box (left, upper, right, lower) - adjust if needed
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
def show_prayer_table():
    times = [
        ("കാസർകോട്",  "4:43", "12:30", "3:49", "6:51", "8:07", "6:05"),
        ("കോഴിക്കോട്", "4:42", "12:26", "3:46", "6:46", "8:01", "6:04"),
        ("മലപ്പുറം",   "4:42", "12:25", "3:46", "6:45", "8:00", "6:03"),
        ("പാലക്കാട്",  "4:40", "12:23", "3:44", "6:42", "7:57", "6:01"),
        ("കൊച്ചി",    "4:43", "12:24", "3:45", "6:42", "7:57", "6:04"),
        ("പത്തനംതിട്ട", "4:43", "12:22", "3:44", "6:39", "7:54", "6:03"),
        ("തിരുവനന്തപുരം", "4:43", "12:22", "3:43", "6:37", "7:51", "6:03"),
        ("ഗൂഡല്ലൂർ",   "4:40", "12:24", "3:44", "6:44", "7:59", "6:01"),
    ]

    headers = ["സ്ഥലം", "സുബ്ഹ്", "ലൂഹർ", "അസർ", "മഗ്‌രിബ്", "ഇശാഅ്", "ഉദയം"]

    table_rows = ""
    for row in times:
        table_rows += "<tr>" + "".join(f"<td>{col}</td>" for col in row) + "</tr>"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>പ്രാർത്ഥന സമയം</title>
        <style>
            body {{
                font-family: 'Noto Sans Malayalam', sans-serif;
                text-align: center;
                margin: 50px;
                background: #f9f9f9;
            }}
            table {{
                margin: auto;
                border-collapse: collapse;
                width: 90%;
                max-width: 800px;
                background: white;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }}
            th, td {{
                border: 1px solid #ccc;
                padding: 12px;
                font-size: 18px;
            }}
            th {{
                background: #4CAF50;
                color: white;
            }}
            tr:nth-child(even) {{
                background: #f2f2f2;
            }}
        </style>
    </head>
    <body>
        <h1>ഇന്ന് നമസ്കാര സമയങ്ങൾ</h1>
        <table>
            <tr>{"".join(f"<th>{h}</th>" for h in headers)}</tr>
            {table_rows}
        </table>
        <p style="margin-top:40px;"><a href="/">Back to Home</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

if __name__ == '__main__':
    ensure_fresh_prayer_image()
    app.run(host='0.0.0.0', port=8000)