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
def show_prayer_table():
    date = datetime.datetime.now().strftime("%Y-%m-%d")
    prayer_data = []
    for loc in LOCATIONS:
        coords = LOCATION_COORDS.get(loc)
        if coords:
            times = get_prayer_times(coords[0], coords[1])
            if times:
                prayer_data.append((loc, times))
            else:
                prayer_data.append((loc, {
                    "Fajr": "N/A", "Dhuhr": "N/A", "Asr": "N/A",
                    "Maghrib": "N/A", "Isha": "N/A", "Sunrise": "N/A"
                }))

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Prayer Times</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                margin: 50px;
                background: #f9f9f9;
            }
            table {
                margin: auto;
                border-collapse: collapse;
                width: 90%;
                max-width: 800px;
                background: white;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }
            th, td {
                border: 1px solid #ccc;
                padding: 12px;
                font-size: 18px;
            }
            th {
                background: #4CAF50;
                color: white;
            }
            tr:nth-child(even) {
                background: #f2f2f2;
            }
        </style>
    </head>
    <body>
        <h1>Prayer Times for Kerala Locations on {{date}}</h1>
        <table>
            <tr>
                <th>Location</th>
                <th>Fajr</th>
                <th>Sunrise</th>
                <th>Dhuhr</th>
                <th>Asr</th>
                <th>Maghrib</th>
                <th>Isha</th>
            </tr>
            {% for loc, times in prayer_data %}
            <tr>
                <td>{{loc}}</td>
                <td>{{times.Fajr}}</td>
                <td>{{times.Sunrise}}</td>
                <td>{{times.Dhuhr}}</td>
                <td>{{times.Asr}}</td>
                <td>{{times.Maghrib}}</td>
                <td>{{times.Isha}}</td>
            </tr>
            {% endfor %}
        </table>
        <p style="margin-top:40px;"><a href="/">Back to Home</a></p>
    </body>
    </html>
    """
    return render_template_string(html, prayer_data=prayer_data, date=date)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)