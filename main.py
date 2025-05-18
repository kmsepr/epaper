import datetime
from flask import Flask
from telegram import Bot

# === CONFIGURATION ===
BOT_TOKEN = '7881893598:AAGgCDjKRaLMmsnglQsnXOzkwb3OpoEvb_M'  # Replace with your bot token
CHANNEL_ID = '@malayalam_news1'  # Replace with your Telegram channel username

app = Flask(__name__)

def get_today_url():
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    return f"https://epaper.suprabhaatham.com/details/Kozhikode/{date_str}/1"

def send_epaper_link():
    epaper_url = get_today_url()
    bot = Bot(token=BOT_TOKEN)
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    message = f"📰 *Suprabhaatham ePaper - Page 1*\nDate: {date_str}\n[Click to View]({epaper_url})"
    bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='Markdown')

@app.route('/')
def home():
    return "Suprabhaatham ePaper Bot is running."

@app.route('/send')
def trigger_send():
    send_epaper_link()
    return "Message sent to Telegram."

@app.route('/today')
def show_today_link():
    return get_today_url(), 200, {'Content-Type': 'text/plain'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)