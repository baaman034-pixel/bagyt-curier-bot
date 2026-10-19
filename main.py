import os, threading, urllib.parse, requests, re
import telebot
from flask import Flask
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from telebot import types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-express-final-bishkek")
DEFAULT_FROM = "Дордой мир обуви"
BRAND = "Bagyt Express"
DGIS_KEY = os.environ.get("DGIS_KEY", "")

couriers = set()
active_orders = []

def get_coords_2gis(addr):
    if not DGIS_KEY: return None
    try:
        url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={urllib.parse.quote(addr + ', Бишкек')}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=4).json()
        if r.get('result', {}).get('items'):
            p = r['result']['items'][0]['point']
            return (p['lat'], p['lon'])
    except: pass
    return None

def get_coords(addr):
    c = get_coords_2gis(addr)
    if c: return c
    try:
        loc = geolocator.geocode(f"{addr}, Бишкек, Кыргызстан", timeout=8)
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

def process_text_order(chat_id, dest, phone, tmp_msg_id, with_photo=False, photo_id=None):
    coords = get_coords(dest)
    status = "📍 Найдено ✅" if coords else "📍 Не найдено ⚠️"
    active_orders.append({'dest': dest, 'phone': phone, 'coords': coords, 'chat_id': chat_id, 'notified': False})
    has_courier = len(couriers) > 0
    warn = "\n⚠️ Нет позиции курьера. Включи трансляцию." if not has_courier else ""
    label = "С ФОТО" if with_photo else "БЕЗ ФОТО"
    final_text = f"✅ Заказ {label} принят\n📦 {dest}\n📞
