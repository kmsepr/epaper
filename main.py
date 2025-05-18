import os
import datetime
import threading
from flask import Flask, render_template_string
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === CONFIGURATION ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = '@YOUR_CHANNEL_USERNAME'  # Replace with your channel username

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
    url = get_today_url()
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Suprabhaatham ePaper Today</title></head>
    <body style="font-family:sans-serif; text-align:center; margin-top:50px;">
      <h1>Suprabhaatham ePaper - Today's Link</h1>
      <p><a href="{url}" target="_blank" style="font-size:20px;">{url}</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

# Telegram bot /start handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    epaper_url = get_today_url()
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    message = f"📰 *Suprabhaatham ePaper - Page 1*\nDate: {date_str}\n[Click to View]({epaper_url})"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode='Markdown')

def run_telegram_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.run_polling()

if __name__ == '__main__':
    # Run telegram bot in a separate thread
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    # Run flask app
    app.run(host='0.0.0.0', port=8000)