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
geolocator = Nominatim(user_agent="bagyt-bishkek-v1")

couriers = set()
active_orders = []

def get_coords_2gis(addr):
    if not DGIS_KEY: return None
    try:
        q = urllib.parse.quote(addr + ", Бишкек")
        url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={q}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=5)
        data = r.json()
        items = data.get('result', {}).get('items', [])
        if items:
            p = items[0]['point']
            return (p['lat'], p['lon'])
    except Exception as e:
        print(f"2GIS error: {e}")
    return None

def get_coords_osm(addr):
    try:
        loc = geolocator.geocode(f"{addr}, Бишкек, Кыргызстан", timeout=10)
        if loc: return (loc.latitude, loc.longitude)
    except Exception as e:
        print(f"OSM error: {e}")
    return None

def get_coords(addr):
    c = get_coords_2gis(addr)
    if c:
        print(f"2GIS found: {addr} -> {c}")
        return c
    c = get_coords_osm(addr)
    if c:
        print(f"OSM found: {addr} -> {c}")
    return c

def normalize_phone(p):
    d=''.join(filter(str.isdigit,p))
    if d.startswith('0'): d='996'+d[1:]
    if not d.startswith('996'): d='996'+d
    return d

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🚚 Bagyt Express\nВключи трансляцию тут и пиши: Адрес Телефон")

@bot.message_handler(content_types=['location','live_location'])
def handle_loc(m):
    couriers.add(m.chat.id)
    if not m.location: return
    cur=(m.location.latitude, m.location.longitude)
    for o in active_orders:
        if o.get('notified'): continue
        if not o.get('coords'): continue
        try:
            dist=geodesic(cur,o['coords']).km
            if dist<1.5:
                pn=normalize_phone(o['phone'])
                txt=f"Здравствуйте! Ваш курьер Bagyt Express уже близко, будет через 10 мин по адресу {o['dest']}. Будьте на связи"
                link=f"https://wa.me/{pn}?text={urllib.parse.quote(txt)}"
                mk=types.InlineKeyboardMarkup()
                mk.add(types.InlineKeyboardButton("📲 Написать в WhatsApp", url=link))
                msg=f"⏰ КУРЬЕР В 10 МИН!\n📍 {o['dest']}\n📞 {o['phone']}\n📏 {dist:.2f} км"
                bot.send_message(o['chat_id'], msg, reply_markup=mk)
                bot.send_message(m.chat.id, f"Ты рядом!\n{msg}", reply_markup=mk)
                o['notified']=True
        except: pass

def process_order(chat_id, dest, phone, tmp_id):
    coords=get_coords(dest)
    status="📍 Найдено ✅" if coords else "📍 Не найдено ⚠️"
    active_orders.append({'dest':dest,'phone':phone,'coords':coords,'chat_id':chat_id,'notified':False})
    final=f"✅ Заказ БЕЗ ФОТО принят\n📦 {dest}\n📞 {phone}\n{status}"
    try: bot.edit_message_text(final, chat_id, tmp_id)
    except: bot.send_message(chat_id, final)

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    for line in m.text.split('\n'):
        line=line.strip()
        if len(line)<5: continue
        # ищем телефон
        ph=re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', line)
        if not ph: continue
        phone=ph.group()
        dest=line.replace(phone,'').strip(' -:,')
        if not dest: continue
        # СРАЗУ отвечаем, до поиска координат
        tmp=bot.send_message(m.chat.id, f"⏳ Принимаю: {dest}...")
        threading.Thread(target=process_order, args=(m.chat.id,dest,phone,tmp.message_id), daemon=True).start()

@app.route('/')
def home(): return f"BAGYT LIVE {len(active_orders)}"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(timeout=60)

if __name__=="__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
