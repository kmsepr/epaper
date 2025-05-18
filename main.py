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
    html_links = ""
    for loc in LOCATIONS:
        url = get_url_for_location(loc)
        html_links += f'<li><a href="{url}" target="_blank" style="font-size:22px;">{loc}</a></li>'
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>Today's Suprabhaatham Links</title>
    </head>
    <body style="font-family:sans-serif; text-align:center; margin-top:50px;">
      <h1>Today's Suprabhaatham ePaper Links</h1>
      <ul style="list-style:none; padding:0;">
        {html_links}
      </ul>
      <p><a href="/">Back to Home</a></p>
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

    html_links = ""
    for date in reversed(sundays):
        url = get_url_for_location("Njayar Prabhadham", date)
        date_str = date.strftime('%Y-%m-%d')
        html_links += f'<li><a href="{url}" target="_blank" style="font-size:18px;">{date_str}</a></li>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <title>Njayar Prabhadham Archive</title>
    </head>
    <body style="font-family:sans-serif; text-align:center; margin-top:50px;">
      <h1>Njayar Prabhadham - Sunday Editions</h1>
      <ul style="list-style:none; padding:0;">
        {html_links}
      </ul>
      <p><a href="/">Back to Home</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)