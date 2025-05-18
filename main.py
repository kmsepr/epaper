import os
import requests
import datetime
from flask import Flask, render_template_string

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
    cards = ""
    links = [("Today's Editions", "/today"), ("Njayar Prabhadham Archive", "/njayar")]
    for i, (label, link) in enumerate(links):
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'''
        <div class="card" style="background-color:{color};">
            <a href="{link}">{label}</a>
        </div>
        '''
    return render_template_string(wrap_grid_page("Suprabhaatham ePaper", cards))

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