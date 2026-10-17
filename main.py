import os, threading
import telebot
from flask import Flask

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

DEFAULT_FROM = "Дордой мир обуви"
couriers = set()

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, f"🚚 BAGYT COURIER\n📦 {DEFAULT_FROM}\n\nОтправь адрес + номер, можно с фото.\nКурьер: включи 📍 трансляцию.")

@bot.message_handler(content_types=['location', 'live_location'])
def loc(m):
    couriers.add(m.chat.id)
    bot.send_message(m.chat.id, f"✅ В сети! Курьеров: {len(couriers)}")

@bot.message_handler(content_types=['photo'])
def photo(m):
    caption = (m.caption or "").strip()
    if not caption:
        bot.send_message(m.chat.id, "📸 Добавь адрес в подпись: Восток 5 12 0550997099")
        return
    file_id = m.photo[-1].file_id
    # парсим
    parts = caption.rsplit(' ',1)
    dest = parts[0] if len(parts)==2 else caption
    phone = parts[1] if len(parts)==2 else "клиент"
    
    bot.send_message(m.chat.id, f"✅ Заказ с фото принят\n📦 {DEFAULT_FROM}\n📍 {dest}\n📞 {phone}")
    for cid in list(couriers):
        if cid != m.chat.id:
            try:
                bot.send_photo(cid, file_id, caption=f"🔥 ЗАКАЗ!\n📦 {DEFAULT_FROM}\n📍 {dest}\n📞 {phone}")
            except: couriers.discard(cid)

@bot.message_handler(content_types=['text'])
def text(m):
    if not m.text or m.text.startswith('/'): return
    for line in m.text.split('\n'):
        if not line.strip(): continue
        parts = line.strip().rsplit(' ',1)
        dest = parts[0] if len(parts)==2 else line
        phone = parts[1] if len(parts)==2 else "клиент"
        bot.send_message(m.chat.id, f"✅ Принят\n📦 {DEFAULT_FROM}\n📍 {dest}\n📞 {phone}")
        for cid in list(couriers):
            if cid != m.chat.id:
                try: bot.send_message(cid, f"🔥 ЗАКАЗ!\n📦 {DEFAULT_FROM}\n📍 {dest}\n📞 {phone}")
                except: couriers.discard(cid)

@app.route('/')
def home(): return f"BAGYT LIVE - {len(couriers)} couriers"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    while True:
        try: bot.infinity_polling(timeout=60)
        except Exception as e: print(e)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
