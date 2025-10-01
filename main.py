import os
import time
import json
import threading
import datetime
import requests
import brotli
import feedparser # <--- NEW IMPORT
from flask import Flask, render_template_string, request, redirect, url_for

app = Flask(__name__)

UPLOAD_FOLDER = "static"
EPAPER_TXT = "epaper.txt"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

LOCATIONS = [
    "Kozhikode", "Malappuram", "Kannur", "Thrissur",
    "Kochi", "Thiruvananthapuram", "Palakkad", "Gulf"
]
RGB_COLORS = [
    "#FF6B6B", "#6BCB77", "#4D96FF", "#FFD93D",
    "#FF6EC7", "#00C2CB", "#FFA41B", "#845EC2"
]

# <--- NEW CONSTANTS FOR RSS FEEDS
PSC_RSS_URL = "https://cdn.mysitemapgenerator.com/shareapi/rss/30091483705"
HINDU_RSS_URL = "https://www.thehindu.com/news/national/?service=rss"
ALJAZEERA_RSS_URL = "https://www.aljazeera.com/xml/rss/all.xml"
# --->

def get_url_for_location(location, dt_obj=None):
    if dt_obj is None:
        dt_obj = datetime.datetime.now()
    date_str = dt_obj.strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/{location}/{date_str}/1"

def wrap_grid_page(title, items_html, show_back=True):
    back_html = '<p><a class="back" href="/">Back to Home</a></p>' if show_back else ''
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            body {{
                font-family: 'Segoe UI', sans-serif;
                background: #f0f2f5;
                margin: 0;
                padding: 40px 20px;
                color: #333;
                text-align: center;
            }}
            h1 {{
                font-size: 2em;
                margin-bottom: 30px;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 20px;
                max-width: 1000px;
                margin: auto;
            }}
            .card {{
                padding: 25px 15px;
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                transition: transform 0.2s ease;
            }}
            .card:hover {{
                transform: translateY(-4px);
            }}
            .card a {{
                text-decoration: none;
                font-size: 1.1em;
                color: #fff;
                font-weight: bold;
                display: block;
            }}
            a.back {{
                display: inline-block;
                margin-top: 40px;
                font-size: 1em;
                color: #555;
                text-decoration: underline;
            }}
            /* <--- NEW STYLES FOR NEWS LIST */
            .news-list {{
                max-width: 800px;
                margin: 30px auto;
                list-style: none;
                padding: 0;
                text-align: left;
            }}
            .news-item {{
                background: #fff;
                border-radius: 8px;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
                padding: 15px;
                margin-bottom: 15px;
            }}
            .news-item a {{
                color: #007bff;
                text-decoration: none;
                font-size: 1.1em;
                font-weight: 600;
            }}
            .news-item a:hover {{
                text-decoration: underline;
            }}
            .news-item p {{
                color: #666;
                font-size: 0.9em;
                margin-top: 5px;
            }}
            /* ---> */
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        <div class="grid">{items_html}</div>
        {back_html}
    </body>
    </html>
    """

# <--- NEW HELPER FUNCTION FOR NEWS LIST
def wrap_news_page(title, content_html, show_back=True):
    back_html = '<p style="text-align:center;"><a class="back" href="/">Back to Home</a></p>' if show_back else ''
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            /* All the styles from wrap_grid_page up to a.back... */
            body {{
                font-family: 'Segoe UI', sans-serif;
                background: #f0f2f5;
                margin: 0;
                padding: 40px 20px;
                color: #333;
                text-align: center;
            }}
            h1 {{
                font-size: 2em;
                margin-bottom: 30px;
            }}
            a.back {{
                display: inline-block;
                margin-top: 40px;
                font-size: 1em;
                color: #555;
                text-decoration: underline;
            }}
            .news-list {{
                max-width: 800px;
                margin: 30px auto;
                list-style: none;
                padding: 0;
                text-align: left;
            }}
            .news-item {{
                background: #fff;
                border-radius: 8px;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
                padding: 15px;
                margin-bottom: 15px;
            }}
            .news-item a {{
                color: #007bff;
                text-decoration: none;
                font-size: 1.1em;
                font-weight: 600;
            }}
            .news-item a:hover {{
                text-decoration: underline;
            }}
            .news-item p {{
                color: #666;
                font-size: 0.9em;
                margin-top: 5px;
            }}
        </style>
    </head>
    <body>
        <h1>{title}</h1>
        {content_html}
        {back_html}
    </body>
    </html>
    """
# --->

# <--- NEW FUNCTION TO FETCH RSS
def fetch_rss_feed(url):
    try:
        feed = feedparser.parse(url)
        return feed.entries
    except Exception as e:
        print(f"Error fetching RSS feed from {url}: {e}")
        return []
# --->

@app.route('/')
def homepage():
    # <--- UPDATED LINKS LIST
    links = [
        ("Today's Editions", "/today"),
        ("Njayar Prabhadham Archive", "/njayar"),
        ("PSC Updates", "/psc-updates"), # <--- NEW
        ("Latest News", "/latest-news") # <--- NEW
    ]
    # --->
    cards = ""
    for i, (label, link) in enumerate(links):
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{link}">{label}</a></div>'
    return render_template_string(wrap_grid_page("Suprabhaatham ePaper & News Hub", cards, show_back=False)) # <--- UPDATED TITLE

@app.route('/today')
def show_today_links():
    cards = ""
    for i, loc in enumerate(LOCATIONS):
        url = get_url_for_location(loc)
        color = RGB_COLORS[i % len(RGB_COLORS)]
        cards += f'<div class="card" style="background-color:{color};"><a href="{url}" target="_blank">{loc}</a></div>'
    return render_template_string(wrap_grid_page("Today's Suprabhaatham ePaper Links", cards))

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

# <--- NEW ROUTE FOR PSC UPDATES
@app.route('/psc-updates')
def show_psc_updates():
    items = fetch_rss_feed(PSC_RSS_URL)
    list_html = '<ul class="news-list">'
    if not items:
        list_html += '<li>No updates available or failed to fetch feed.</li>'
    else:
        for item in items[:20]: # Show up to 20 items
            title = item.get('title', 'No Title')
            link = item.get('link', '#')
            published = item.get('published', '')
            list_html += f'''
            <li class="news-item">
                <a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>
                <p>{published}</p>
            </li>
            '''
    list_html += '</ul>'
    return render_template_string(wrap_news_page("PSC Updates", list_html))
# --->

# <--- NEW ROUTE FOR LATEST NEWS
@app.route('/latest-news')
def show_latest_news():
    # You can choose to combine feeds or display them separately. 
    # Let's combine The Hindu (National) and Al Jazeera (World).
    
    hindu_items = fetch_rss_feed(HINDU_RSS_URL)
    aljazeera_items = fetch_rss_feed(ALJAZEERA_RSS_URL)
    
    # Simple list of all items from both sources
    items = hindu_items[:10] + aljazeera_items[:10] # Top 10 from each
    
    list_html = '<ul class="news-list">'
    if not items:
        list_html += '<li>No news available or failed to fetch feeds.</li>'
    else:
        # Sort items by date (optional, RSS feeds are often sorted already)
        # For simplicity, let's just display the combined list
        for item in items: 
            title = item.get('title', 'No Title')
            link = item.get('link', '#')
            source = item.feed.get('title', 'Source') if hasattr(item, 'feed') else 'External'
            published = item.get('published', item.get('updated', ''))
            
            list_html += f'''
            <li class="news-item">
                <a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>
                <p><strong>{source}</strong> - {published}</p>
            </li>
            '''
    list_html += '</ul>'
    return render_template_string(wrap_news_page("Latest National & World News", list_html))
# --->

def update_epaper_json():
    url = "https://api2.suprabhaatham.com/api/ePaper"
    headers = {
        "Content-Type": "application/json",
        "Accept-Encoding": "br"
    }
    payload = {}

    while True:
        try:
            print("Fetching latest ePaper data...")
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()

            if response.headers.get('Content-Encoding') == 'br':
                try:
                    decompressed_data = brotli.decompress(response.content).decode('utf-8')
                except Exception as e:
                    print(f"Error during Brotli decompression: {e}")
                    decompressed_data = response.text
            else:
                decompressed_data = response.text

            with open(EPAPER_TXT, "w", encoding="utf-8") as f:
                f.write(decompressed_data)

            print("epaper.txt updated successfully.")
        except Exception as e:
            print(f"[Error updating epaper.txt] {e}")

        time.sleep(86400)  # Wait for 24 hours

@app.route('/malappuram/pages')
def show_malappuram_pages():
    if not os.path.exists(EPAPER_TXT):
        return "epaper.txt not found", 404

    try:
        with open(EPAPER_TXT, "r", encoding="utf-8") as f:
            data = json.load(f)

        pages = [
            entry for entry in data.get("data", [])
            if entry.get("Location") == "Malappuram"
        ]

        if not pages:
            return "No pages found for Malappuram.", 404

        cards = ""
        for i, page in enumerate(sorted(pages, key=lambda x: x.get("PageNo", 0))):
            img_url = page.get("Image")
            page_no = page.get("PageNo", "N/A")
            date = page.get("Date", "")
            cards += f'''
            <div class="card" style="background-color:{RGB_COLORS[i % len(RGB_COLORS)]};">
                <a href="{img_url}" target="_blank">Page {page_no}<br><small>{date}</small></a>
            </div>
            '''

        return render_template_string(wrap_grid_page("Malappuram - All Pages", cards))

    except Exception as e:
        return f"Error: {e}", 500

if __name__ == '__main__':
    if not os.path.exists(EPAPER_TXT):
         # Create an empty file to prevent immediate errors if the thread hasn't run yet
         open(EPAPER_TXT, 'a').close() 
         
    threading.Thread(target=update_epaper_json, daemon=True).start()
    app.run(host='0.0.0.0', port=8000)
