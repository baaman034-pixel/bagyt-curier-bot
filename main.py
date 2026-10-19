import os, telebot
from flask import Flask
import threading

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "Bagyt Express - пиши Адрес Телефон")

@bot.message_handler(content_types=['text'])
def any_text(m):
    print(f"Poluchil: {m.text}")
    bot.send_message(m.chat.id, f"TEST: Ya videl tvoe soobshenie: {m.text}\nTelefon nashel")

@app.route('/')
def home(): return "TEST LIVE"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
