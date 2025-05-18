import os
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

def get_url_for_location(location, date=None):
    if date is None:
        date = datetime.datetime.now()
    date_str = date.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

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
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/today')
def show_today_links():
    cards = ""
    for loc in LOCATIONS:
        url = get_url_for_location(loc)
        cards += f'''
        <div class="card">
            <a href="{url}" target="_blank">{loc}</a>
        </div>
        '''
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>Today's Suprabhaatham Links</title>
      <style>
        body {{
          font-family: sans-serif;
          text-align: center;
          padding: 40px;
        }}
        .grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 20px;
          max-width: 800px;
          margin: auto;
        }}
        .card {{
          background-color: #f0f0f0;
          padding: 20px;
          border-radius: 10px;
          box-shadow: 2px 2px 8px rgba(0,0,0,0.1);
        }}
        .card a {{
          text-decoration: none;
          font-size: 20px;
          color: #333;
        }}
      </style>
    </head>
    <body>
      <h1>Today's Suprabhaatham ePaper Links</h1>
      <div class="grid">
        {cards}
      </div>
      <p style="margin-top:40px;"><a href="/">Back to Home</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

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
    for date in reversed(sundays):
        url = get_url_for_location("Njayar Prabhadham", date)
        date_str = date.strftime('%Y-%m-%d')
        cards += f'''
        <div class="card">
            <a href="{url}" target="_blank">{date_str}</a>
        </div>
        '''

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>Njayar Prabhadham Archive</title>
      <style>
        body {{
          font-family: sans-serif;
          text-align: center;
          padding: 40px;
        }}
        .grid {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
          gap: 15px;
          max-width: 900px;
          margin: auto;
        }}
        .card {{
          background-color: #e0f7fa;
          padding: 15px;
          border-radius: 8px;
          box-shadow: 1px 1px 6px rgba(0,0,0,0.1);
        }}
        .card a {{
          text-decoration: none;
          font-size: 16px;
          color: #00695c;
        }}
      </style>
    </head>
    <body>
      <h1>Njayar Prabhadham - Sunday Editions</h1>
      <div class="grid">
        {cards}
      </div>
      <p style="margin-top:40px;"><a href="/">Back to Home</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)