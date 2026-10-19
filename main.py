import os, threading, urllib.parse, requests, re
import telebot
from flask import Flask
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from telebot import types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-express-final")
DEFAULT_FROM = "Дордой мир обуви"
BRAND = "Bagyt Express"
DGIS_KEY = os.environ.get("DGIS_KEY", "")

couriers = set()
active_orders = []

def get_coords_2gis(addr):
    if not DGIS_KEY: return None
    try:
        url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={urllib.parse.quote(addr + ', Бишкек')}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=5).json()
        if r.get('result', {}).get('items'):
            p = r['result']['items'][0]['point']
            return (p['lat'], p['lon'])
    except: pass
    return None

def get_coords(addr):
    c = get_coords_2gis(addr)
    if c: return c
    try:
        loc = geolocator.geocode(f"{addr}, Бишкек, Кыргызстан", timeout=10)
        if loc: return (loc.latitude, loc.longitude)
    except: pass
    return None

def normalize_phone(p):
    digits = ''.join(filter(str.isdigit, p))
    if digits.startswith('0'): digits = '996' + digits[1:]
    if not digits.startswith('996'): digits = '996' + digits
    return digits

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, f"🚚 {BRAND}\nВключи трансляцию геопозиции тут в боте и получай уведомления за 1.5 км\nЗаказ: Адрес Телефон")

@bot.message_handler(content_types=['location','live_location'])
def handle_loc(m):
    couriers.add(m.chat.id)
    if not m.location: return
    cur_pos = (m.location.latitude, m.location.longitude)
    for order in active_orders:
        if order.get('notified'): continue
        if not order.get('coords'): continue
        dist = geodesic(cur_pos, order['coords']).km
        if dist < 1.5:
            phone_norm = normalize_phone(order['phone'])
            text = f"Здравствуйте! Ваш курьер {BRAND} уже близко, будет через 10 минут по адресу {order['dest']}. Пожалуйста будьте на связи 📦"
            wa_link = f"https://wa.me/{phone_norm}?text={urllib.parse.quote(text)}"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📲 Написать клиенту в WhatsApp", url=wa_link))
            msg = f"⏰ КУРЬЕР В 10 МИНУТАХ!\n📍 {order['dest']}\n📞 {order['phone']}\n📏 {dist:.2f} км"
            try:
                bot.send_message(order['chat_id'], msg, reply_markup=markup)
                bot.send_message(m.chat.id, f"Ты рядом!\n{msg}", reply_markup=markup)
                order['notified'] = True
            except: pass

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    cap = (m.caption or "").strip()
    if not cap:
        bot.send_message(m.chat.id, "Добавь адрес в подпись"); return
    phone_match = re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', cap)
    if not phone_match:
        bot.send_message(m.chat.id, "Не нашел телефон"); return
    phone = phone_match.group()
    dest = cap.replace(phone, '').strip(' -:,')
    coords = get_coords(dest)
    status = "📍 Найдено ✅" if coords else "📍 Не найдено ⚠️"
    active_orders.append({'dest': dest, 'phone': phone, 'coords': coords, 'chat_id': m.chat.id, 'notified': False})
    bot.send_message(m.chat.id, f"✅ Заказ С ФОТО принят\n📦 {dest}\n📞 {phone}\n{status}")
    for cid in list(couriers):
        if cid == m.chat.id: continue
        try: bot.send_photo(cid, m.photo[-1].file_id, caption=f"🔥 ЗАКАЗ\n{DEFAULT_FROM} -> {dest}\n📞 {phone}")
        except: couriers.discard(cid)

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    for line in m.text.split('\n'):
        line=line.strip()
        if len(line)<5: continue
        phone_match = re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', line)
        if not phone_match: continue
        phone = phone_match.group()
        dest = line.replace(phone, '').strip(' -:,')
        if not dest: continue
        coords = get_coords(dest)
        status = "📍 Найдено ✅" if coords else "📍 Не найдено ⚠️"
        # Проверка есть ли курьер онлайн
        has_courier = len(couriers) > 0
        warn = "\n⚠️ Нет позиции курьера. Включи трансляцию заново." if not has_courier else ""
        active_orders.append({'dest': dest, 'phone': phone, 'coords': coords, 'chat_id': m.chat.id, 'notified': False})
        bot.send_message(m.chat.id, f"✅ Заказ БЕЗ ФОТО принят\n📦 {dest}\n📞 {phone}\n{status}{warn}")
        for cid in list(couriers):
            if cid == m.chat.id: continue
            try: bot.send_message(cid, f"🔥 ЗАКАЗ\n{DEFAULT_FROM} -> {dest}\n📞 {phone}")
            except: couriers.discard(cid)

@app.route('/')
def home(): return f"BAGYT EXPRESS BISHKEK LIVE {len(active_orders)}"
def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    while True:
        try: bot.infinity_polling(timeout=60)
        except: pass
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
