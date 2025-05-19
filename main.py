import datetime
from flask import Flask, render_template_string, redirect, request
import requests
from datetime import datetime as dt, timedelta, date

app = Flask(__name__)

LOCATIONS = [
    "Kozhikode", "Malappuram", "Kannur", "Thrissur",
    "Kochi", "Thiruvananthapuram", "Palakkad", "Gulf"
]

RGB_COLORS = [
    "#FF6B6B", "#6BCB77", "#4D96FF", "#FFD93D",
    "#FF6EC7", "#00C2CB", "#FFA41B", "#845EC2"
]

editorial_cache = {
    "date": None,
    "url": None
}

def get_url_for_location(location, dt_obj=None):
    if dt_obj is None:
        dt_obj = datetime.datetime.now()
    date_str = dt_obj.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

def check_url(url):
    try:
        r = requests.head(url, timeout=3)
        return r.status_code == 200
    except:
        return False

def wrap_grid_page(title, items_html, show_back=True):
    back_html = '<p><a class="back" href="/">Back to Home</a></p>' if show_back else ''
    html_template = f"""
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
    return html_template

@app.route('/')
def homepage():
    cards = ""
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("Editorial", "/editorial"),
        ("Select by Date", "/epaper-date")
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
            <a href="{url}" target="_blank" rel="noopener noreferrer">{loc}</a>
        </div>
        '''
    return render_template_string(wrap_grid_page("Today's Suprabhaatham ePaper Links", cards))

@app.route('/editorial')
def editorial():
    global editorial_cache

    today_date = date.today()
    folder_str = today_date.strftime('%d-%m-%Y')
    filename_prefix = today_date.strftime('%Y-%m-%d')
    base_url = "https://e-files.suprabhaatham.com"
    edition = "Malappuram"
    page_num = 5

    if editorial_cache["date"] == today_date and editorial_cache["url"]:
        return redirect(editorial_cache["url"])

    start_time = dt.strptime("00:05:00.000", "%H:%M:%S.%f")
    end_time = dt.strptime("00:05:20.000", "%H:%M:%S.%f")
    step = timedelta(milliseconds=100)

    current_time = start_time
    found_url = None

    while current_time <= end_time:
        time_str = current_time.strftime("%H-%M-%S-%f")[:-3]
        filename = f"{filename_prefix}-{time_str}-epaper-page-{page_num}-{edition}.jpeg"
        url = f"{base_url}/{folder_str}/{edition}/{filename}"
        if check_url(url):
            found_url = url
            break
        current_time += step

    if not found_url:
        fallback_time = "01-05-87-875"
        fallback_filename = f"{filename_prefix}-{fallback_time}-epaper-page-{page_num}-{edition}.jpeg"
        found_url = f"{base_url}/{folder_str}/{edition}/{fallback_filename}"

    editorial_cache["date"] = today_date
    editorial_cache["url"] = found_url

    return redirect(found_url)

@app.route('/njayar')
def show_njayar_archive():
    start_date = date(2019, 1, 6)
    today = date.today()
    cutoff = date(2024, 6, 30)
    sundays = []
    current = start_date
    while current <= today:
        if current >= cutoff:
            sundays.append(current)
        current += timedelta(days=7)

    cards = ""
    for i, d in enumerate(reversed(sundays)):
        url = get_url_for_location("Njayar Prabhadham", d)
        date_str = d.strftime('%Y-%m-%d')
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'''
        <div class="card" style="background-color:{color};">
            <a href="{url}" target="_blank" rel="noopener noreferrer">{date_str}</a>
        </div>
        '''
    return render_template_string(wrap_grid_page("Njayar Prabhadham - Sunday Editions", cards))

@app.route('/epaper-date', methods=['GET', 'POST'])
def epaper_by_date():
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ePaper by Date</title>
        <style>
            body { font-family: sans-serif; text-align: center; padding: 40px; background-color: #f4f4f4; }
            h1 { margin-bottom: 20px; }
            form { margin-bottom: 30px; }
            input[type="date"] {
                padding: 10px;
                font-size: 16px;
                border: 1px solid #ccc;
                border-radius: 6px;
            }
            button {
                padding: 10px 20px;
                font-size: 16px;
                background-color: #4D96FF;
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 20px;
                max-width: 1000px;
                margin: auto;
            }
            .card {
                padding: 20px;
                border-radius: 12px;
                box-shadow: 2px 2px 10px rgba(0,0,0,0.1);
            }
            .card a {
                text-decoration: none;
                font-size: 18px;
                color: white;
                font-weight: bold;
            }
            a.back {
                display: inline-block;
                margin-top: 40px;
                font-size: 16px;
            }
        </style>
    </head>
    <body>
        <h1>Select a Date</h1>
        <form method="post">
            <input type="date" name="picked_date" max="{today}" required>
            <button type="submit">View Editions</button>
        </form>
        {cards_section}
        <p><a class="back" href="/">Back to Home</a></p>
    </body>
    </html>
    """

    cards_html = ""
    if request.method == 'POST':
        picked_date_str = request.form.get("picked_date")
        try:
            picked_date = dt.strptime(picked_date_str, "%Y-%m-%d").date()
            for i, loc in enumerate(LOCATIONS):
                url = get_url_for_location(loc, picked_date)
                color = RGB_COLORS[i % len(RGB_COLORS)]
                cards_html += f'''
                <div class="card" style="background-color:{color};">
                    <a href="{url}" target="_blank" rel="noopener noreferrer">{loc}</a>
                </div>
                '''
            cards_section = f'<div class="grid">{cards_html}</div>'
        except Exception as e:
            cards_section = f"<p>Error: {str(e)}</p>"
    else:
        cards_section = ""

    return html_template.format(today=date.today().isoformat(), cards_section=cards_section)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
