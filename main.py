import os, threading, urllib.parse, requests
import telebot
from flask import Flask
from geopy.distance import geodesic
from telebot import types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DGIS_KEY = os.environ.get("DGIS_API_KEY")
YANDEX_KEY = os.environ.get("YANDEX_API_KEY")

print(f"BOT_TOKEN exists: {bool(BOT_TOKEN)}")
print(f"DGIS_KEY exists: {bool(DGIS_KEY)} len={len(DGIS_KEY) if DGIS_KEY else 0}")
print(f"YANDEX_KEY exists: {bool(YANDEX_KEY)}")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
DEFAULT_FROM = "Дордой мир обуви"
BRAND = "Bagyt Express"
couriers = set()
active_orders = []

def get_coords(addr):
    addr = addr.replace("Улица ","").strip()
    if DGIS_KEY:
        try:
            url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={addr}, Бишкек&key={DGIS_KEY}&fields=items.point"
            print(f"2GIS try: {addr}")
            r = requests.get(url, timeout=10).json()
            items = r.get('result', {}).get('items', [])
            if items and 'point' in items[0]:
                lat = items[0]['point']['lat']
                lon = items[0]['point']['lon']
                print(f"2GIS found: {lat},{lon}")
                return (lat, lon)
            else:
                print(f"2GIS no items: {r}")
        except Exception as e:
            print(f"2GIS error: {e}")
    return None

def parse_order(text):
    text = text.strip()
    parts = text.rsplit(' ', 1)
    if len(parts) == 2 and len(''.join(filter(str.isdigit, parts[1]))) >= 9:
        return parts[0].strip(), parts[1].strip()
    return text, "клиент"

def normalize_phone(p):
    d = ''.join(filter(str.isdigit, p))
    if d.startswith('0'): d = '996' + d[1:]
    if not d.startswith('996'): d = '996' + d
    return d

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, f"🚚 {BRAND}\n📦 {DEFAULT_FROM}\n\n✅ Работает БЕЗ ФОТО!\n\nПросто напиши:\n`Улица Дом Телефон`\nПример: Ибраимова 3 0554950070\n\nИли с фото: фото + адрес в подписи\nDGIS: {'✅ подключен' if DGIS_KEY else '❌ нет ключа'}")

@bot.message_handler(content_types=['location','live_location'])
def handle_loc(m):
    couriers.add(m.chat.id)
    if not m.location: return
    cur = (m.location.latitude, m.location.longitude)
    for order in active_orders:
        if order.get('notified') or not order.get('coords'): continue
        dist = geodesic(cur, order['coords']).km
        if dist < 1.5:
            pn = normalize_phone(order['phone'])
            txt = f"Здравствуйте! Курьер {BRAND} уже близко, будет через 10 мин по адресу {order['dest']}. Будьте на связи 📦"
            wa = f"https://wa.me/{pn}?text={urllib.parse.quote(txt)}"
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("📲 WhatsApp клиенту", url=wa))
            msg = f"⏰ 10 МИНУТ!\n📍 {order['dest']}\n📞 {order['phone']}\n📏 {dist:.2f} км"
            try:
                bot.send_message(order['chat_id'], msg, reply_markup=kb)
                bot.send_message(m.chat.id, f"Ты рядом!\n{msg}", reply_markup=kb)
                order['notified']=True
            except: pass

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    cap = (m.caption or "").strip()
    if not cap:
        bot.send_message(m.chat.id, "Добавь адрес в подпись: Адрес Телефон"); return
    dest, phone = parse_order(cap)
    coords = get_coords(dest)
    active_orders.append({'dest': dest, 'phone': phone, 'coords': coords, 'chat_id': m.chat.id, 'notified': False})
    st = "📍 Координаты найдены" if coords else f"⚠️ Не найдено (ключ есть: {bool(DGIS_KEY)})"
    bot.send_message(m.chat.id, f"✅ Фото-заказ\n📦 {dest}\n📞 {phone}\n{st}")

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    dest, phone = parse_order(m.text.strip())
    if len(dest) < 3: return
    coords = get_coords(dest)
    active_orders.append({'dest': dest, 'phone': phone, 'coords': coords, 'chat_id': m.chat.id, 'notified': False})
    st = "📍 Найдено ✅" if coords else f"⚠️ Коорд. не найдены. Ключ 2ГИС: {'ЕСТЬ' if DGIS_KEY else 'НЕТ ❌'}"
    bot.send_message(m.chat.id, f"✅ Заказ БЕЗ ФОТО принят\n📦 {dest}\n📞 {phone}\n{st}")
    for cid in list(couriers):
        if cid==m.chat.id: continue
        try: bot.send_message(cid, f"🔥 ЗАКАЗ (текст)\n{DEFAULT_FROM} -> {dest}\n📞 {phone}")
        except: couriers.discard(cid)

@app.route('/')
def home(): return f"BAGYT V10 {len(active_orders)} DGIS={'YES' if DGIS_KEY else 'NO'}"
def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    while True:
        try: bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"Polling error {e}")

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
