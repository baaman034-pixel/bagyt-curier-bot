import os, threading, telebot
from flask import Flask
BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
DEFAULT_FROM = "Дордой мир обуви"
couriers = set()

@bot.message_handler(commands=['start'])
def start(m): bot.send_message(m.chat.id, f"🚚 BAGYT\n📦 {DEFAULT_FROM}\nОтправь адрес + номер с фото или без.\nКурьер - включи трансляцию геопозиции")

@bot.message_handler(content_types=['location','live_location'])
def loc(m):
    couriers.add(m.chat.id)
    bot.send_message(m.chat.id, f"✅ Ты в сети!")

@bot.message_handler(content_types=['photo'])
def photo(m):
    cap = (m.caption or "").strip()
    if not cap: 
        bot.send_message(m.chat.id, "Напиши адрес в подписи к фото"); return
    fid = m.photo[-1].file_id
    p = cap.rsplit(' ',1)
    dest, phone = (p[0], p[1]) if len(p)==2 else (cap, "клиент")
    bot.send_message(m.chat.id, f"✅ Заказ с фото\n{DEFAULT_FROM} -> {dest}\n{phone}")
    for cid in couriers:
        try: bot.send_photo(cid, fid, caption=f"🔥 ЗАКАЗ\n{DEFAULT_FROM} -> {dest}\n📞 {phone}")
        except: pass

@bot.message_handler(content_types=['text'])
def txt(m):
    if not m.text: return
    for line in m.text.split('\n'):
        if not line.strip(): continue
        p = line.strip().rsplit(' ',1)
        dest, phone = (p[0], p[1]) if len(p)==2 else (line, "клиент")
        bot.send_message(m.chat.id, f"✅ {DEFAULT_FROM} -> {dest} {phone}")
        for cid in couriers:
            try: bot.send_message(cid, f"🔥 ЗАКАЗ\n{DEFAULT_FROM} -> {dest}\n📞 {phone}")
            except: pass

@app.route('/')
def home(): return "BAGYT LIVE"
def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    while True:
        try: bot.infinity_polling(timeout=60)
        except: pass
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
