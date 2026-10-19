import os, threading, urllib.parse, requests, re
import telebot
from flask import Flask
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from telebot import types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DGIS_KEY = os.environ.get("DGIS_KEY", "").strip()
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-bishkek-final")

couriers = set()
active_orders = []

def get_coords_2gis(addr):
    if not DGIS_KEY: return None
    try:
        q = urllib.parse.quote(addr + ", Бишкек")
        url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={q}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=6).json()
        items = r.get('result', {}).get('items', [])
        if items:
            p = items[0]['point']
            return (p['lat'], p['lon'])
    except: pass
    return None

def get_coords_osm(addr):
    try:
        loc = geolocator.geocode(f"{addr}, Бишкек", timeout=10)
        if loc: return (loc.latitude, loc.longitude)
    except: pass
    return None

def normalize_phone(p):
    d=''.join(filter(str.isdigit,p))
    if d.startswith('0'): d='996'+d[1:]
    if not d.startswith('996'): d='996'+d
    return d

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🚚 Bagyt Express\nВключи трансляцию геопозиции тут и пиши:\nАдрес Телефон")

@bot.message_handler(content_types=['location','live_location'])
def handle_loc(m):
    couriers.add(m.chat.id)
    if not m.location: return
    cur=(m.location.latitude, m.location.longitude)
    for o in active_orders:
        if o.get('notified') or not o.get('coords'): continue
        try:
            dist=geodesic(cur, o['coords']).km
            if dist < 1.5:
                pn=normalize_phone(o['phone'])
                txt=f"Здравствуйте! Курьер Bagyt Express близко, будет через 10 мин {o['dest']}"
                link=f"https://wa.me/{pn}?text={urllib.parse.quote(txt)}"
                mk=types.InlineKeyboardMarkup()
                mk.add(types.InlineKeyboardButton("📲 WhatsApp клиенту", url=link))
                bot.send_message(o['chat_id'], f"⏰ Курьер в 10 МИН!\n📍 {o['dest']}\n📏 {dist:.2f} км", reply_markup=mk)
                bot.send_message(m.chat.id, f"Ты рядом: {o['dest']}", reply_markup=mk)
                o['notified']=True
        except: pass

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    text = m.text.strip()
    print(f"Text: {text}")
    # 1. СРАЗУ отвечаем как в тесте - это точно работает
    tmp = bot.send_message(m.chat.id, f"⏳ Принимаю: {text}")
    
    def work():
        # 2. Потом в фоне ищем координаты с 2ГИС
        ph=re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', text)
        if not ph:
            bot.edit_message_text("❌ Не нашел телефон. Пиши: Адрес Телефон", m.chat.id, tmp.message_id)
            return
        phone=ph.group()
        dest=text.replace(phone,'').strip(' -:,')
        coords = get_coords_2gis(dest)
        if not coords:
            coords = get_coords_osm(dest)
        status = "📍 Найдено ✅" if coords else "📍 Не найдено ⚠️"
        print(f"{dest} -> {status} {coords}")
        active_orders.append({'dest':dest,'phone':phone,'coords':coords,'chat_id':m.chat.id,'notified':False})
        final = f"✅ Заказ БЕЗ ФОТО принят\n📦 {dest}\n📞 {phone}\n{status}"
        try: bot.edit_message_text(final, m.chat.id, tmp.message_id)
        except: bot.send_message(m.chat.id, final)

    threading.Thread(target=work, daemon=True).start()

@app.route('/')
def home(): return "BAGYT LIVE WITH 2GIS"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(timeout=60)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
