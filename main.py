from datetime import datetime, timedelta, date
import requests
from flask import Flask, render_template_string
import os

app = Flask(__name__)

LOCATIONS = [
    "Kozhikode",
    "Malappuram",
    "Kannur",
    "Thrissur",
    "Kochi",
    "Thiruvananthapuram",
    "Palakkad",
    "Gulf"
]

RGB_COLORS = [
    "#FF6B6B",  # Red
    "#6BCB77",  # Green
    "#4D96FF",  # Blue
    "#FFD93D",  # Yellow
    "#FF6EC7",  # Pink
    "#00C2CB",  # Cyan
    "#FFA41B",  # Orange
    "#845EC2"   # Purple
]

def get_url_for_location(location, date=None):
    if date is None:
        date = datetime.datetime.now()
    date_str = date.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

def wrap_grid_page(title, items_html):
    return f"""
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
      <p><a class="back" href="/">Back to Home</a></p>
    </body>
    </html>
    """


@app.route('/')
def homepage():
    # Call Aladhan API
    try:
        response = requests.get("https://api.aladhan.com/v1/timingsByAddress", params={
            'address': 'Kozhikode, Kerala, India',
            'method': 2
        })
        timings = response.json()['data']['timings']

        # Parse and apply offset
        def adjust(prayer_name, offset_minutes):
            time_str = timings[prayer_name]
            dt = datetime.strptime(time_str, '%H:%M')
            dt += timedelta(minutes=offset_minutes)
            return dt.strftime('%I:%M %p')

        namaz_times = {
            "Fajr": adjust("Fajr", -19),
            "Dhuhr": adjust("Dhuhr", 3),
            "Asr": adjust("Asr", 1),
            "Maghrib": adjust("Maghrib", 3),
            "Isha": adjust("Isha", 15)
        }

    except Exception as e:
        namaz_times = {
            "Fajr": "N/A",
            "Dhuhr": "N/A",
            "Asr": "N/A",
            "Maghrib": "N/A",
            "Isha": "N/A"
        }

    namaz_html = ""
    for prayer, time in namaz_times.items():
        namaz_html += f'''
        <div class="card" style="background-color:#D1C4E9;">
            <strong>{prayer}</strong><br>{time}
        </div>
        '''

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Suprabhaatham ePaper</title>
        <style>
            body {{
                font-family: sans-serif;
                text-align: center;
                padding: 40px;
                background-color: #f0f0f0;
            }}
            h1 {{
                margin-bottom: 30px;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 20px;
                max-width: 900px;
                margin: auto;
            }}
            .card {{
                padding: 20px;
                border-radius: 10px;
                box-shadow: 2px 2px 8px rgba(0,0,0,0.1);
                background-color: #81D4FA;
                color: #000;
                font-size: 18px;
            }}
            .card a {{
                text-decoration: none;
                color: white;
                font-weight: bold;
                font-size: 20px;
            }}
        </style>
    </head>
    <body>
        <h1>Suprabhaatham ePaper</h1>
        <div class="grid">
            <div class="card" style="background-color:#4DB6AC;"><a href="/today">Today's Editions</a></div>
            <div class="card" style="background-color:#BA68C8;"><a href="/njayar">Njayar Prabhadham Archive</a></div>
        </div>

        <h2 style="margin-top:50px;">Namaz Times - Kozhikode</h2>
        <div class="grid">
            {namaz_html}
        </div>
    </body>
    </html>
    """
    return render_template_string(html)

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

@app.route('/njayar')
def show_njayar_archive():
    start_date = datetime.date(2019, 1, 6)
    today = datetime.date.today()
    sundays = []
    current = start_date
    while current <= today:
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