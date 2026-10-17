import os, threading, requests
import telebot
from flask import Flask
from geopy.geocoders import Nominatim

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-bishkek-bot")

CITY = "Бишкек, Кыргызстан"

def check_address(text):
    try:
        query = f"{text}, {CITY}"
        loc = geolocator.geocode(query, timeout=10)
        if loc:
            return True
        return False
    except:
        return False

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🚚 BAGYT COURIER Бишкек\n\nОтправь адрес в формате:\nИманалы Айдарбеков 173 0554050070\n\nЯ найду на карте Бишкека и напишу клиенту.")

@bot.message_handler(func=lambda m: True)
def handle(m):
    lines = m.text.strip().split('\n')
    found = 0
    result_text = ""
    bot.send_message(m.chat.id, f"🔍 Ищу {len(lines)} адресов на карте Бишкека...")
    
    for line in lines:
        if not line.strip(): continue
        # отделяем номер
        parts = line.strip().rsplit(' ', 1)
        addr = parts[0] if len(parts)>1 else line
        phone = parts[1] if len(parts)>1 and any(c.isdigit() for c in parts[1]) else "клиент"
        
        is_found = check_address(addr)
        if is_found:
            found += 1
            status = "нашел"
        else:
            status = "не нашел"
        
        result_text += f"{addr} - {status}\n"
        
        if is_found and phone != "клиент":
            result_text += f"Тест для {phone}: Через 10 мин - {phone}\n"

    bot.send_message(m.chat.id, f"✅ Принял {found}: {result_text}\n\n📍 Включи трансляцию!")

@app.route('/')
def home(): return "BAGYT COURIER BISHKEK LIVE"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(e)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
