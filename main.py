import os, threading
import telebot
from flask import Flask
from geopy.geocoders import Nominatim

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-bishkek-bot-fixed")

CITY = "Бишкек, Кыргызстан"
DEFAULT_FROM = "Дордой мир обуви"

def check_address(text):
    try:
        clean = text.strip()
        if len(clean) < 3:
            return False
        query = f"{clean}, {CITY}"
        loc = geolocator.geocode(query, timeout=10)
        return bool(loc)
    except:
        return False

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, 
        "🚚 BAGYT COURIER Бишкек\n\n"
        f"📦 Все заказы с точки: {DEFAULT_FROM}\n\n"
        "Отправь КУДА везти и номер клиента:\n"
        "Пример:\n"
        "Восток 5 дом 14 0554050070\n"
        "Иманалы Айдарбекова 173 0554050070")

@bot.message_handler(func=lambda m: True)
def handle(m):
    if not m.text or m.text.startswith('/'):
        return
    lines = [l.strip() for l in m.text.strip().split('\n') if l.strip()]
    bot.send_message(m.chat.id, f"🔍 Ищу {len(lines)} заказов с {DEFAULT_FROM}...")

    for line in lines:
        parts = line.strip().rsplit(' ', 1)
        if len(parts) == 2 and any(c.isdigit() for c in parts[1]) and len(parts[1]) >= 7:
            dest = parts[0]
            phone = parts[1]
        else:
            dest = line.strip()
            phone = "клиент"

        if "дордой" in dest.lower() and " до " in dest.lower():
            idx = line.lower().rfind(" до ")
            dest_part = line[idx+4:].strip()
            p = dest_part.rsplit(' ', 1)
            if len(p) == 2 and any(c.isdigit() for c in p[1]):
                dest = p[0]
                phone = p[1]
            else:
                dest = dest_part

        is_found = check_address(dest)
        status = "нашел ✅" if is_found else "не нашел ⚠️ (но заказ принят)"

        text = (
            f"✅ Заказ принят\n"
            f"📦 Откуда: {DEFAULT_FROM}\n"
            f"📍 Куда: {dest} - {status}\n"
            f"📞 Клиент: {phone}\n"
            f"\nТест для {phone}: Через 10 мин - {phone}\n"
            f"\n📍 Курьеры получили заказ!"
        )
        bot.send_message(m.chat.id, text)

@app.route('/')
def home(): 
    return "BAGYT COURIER BISHKEK LIVE - FROM DORDOY MIR OBUVI"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Bot error: {e}")

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
