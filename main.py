import os, threading, urllib.parse, requests
import telebot
from flask import Flask
from geopy.distance import geodesic
from telebot import types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DGIS_KEY = os.environ.get("DGIS_API_KEY") or "47f4a193-a03c-4af0-8cbc-894fd6ddc6ad"

print(f"DGIS_KEY OK: {bool(DGIS_KEY)}")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
DEFAULT_FROM = "Дордой мир обуви"
BRAND = "Bagyt Express"

couriers = {}  # chat_id -> (lat,lon)
active_orders = []

def get_coords(addr):
    addr = addr.replace("Улица ","").replace("улица ","").strip()
    try:
        url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={addr}, Бишкек&key={DGIS_KEY}&fields=items.point"
        r = requests.get(url, timeout=15).json()
        items = r.get('result', {}).get('items', [])
        if items and 'point' in items[0]:
            return (items[0]['point']['lat'], items[0]['point']['lon'])
    except Exception as e:
        print(f"2GIS err {e}")
    return None

def parse_order(text):
    parts = text.strip().rsplit(' ', 1)
    if len(parts)==2 and len(''.join(filter(str.isdigit, parts[1])))>=9:
        return parts[0].strip(), parts[1].strip()
    return text.strip(), "клиент"

def normalize_phone(p):
    d=''.join(filter(str.isdigit,p))
    if d.startswith('0'): d='996'+d[1:]
    if not d.startswith('996'): d='996'+d
    return d

def check_nearby_orders(courier_id, courier_pos):
    for order in active_orders:
        if order.get('notified') or not order.get('coords'): continue
        dist = geodesic(courier_pos, order['coords']).km
        if dist < 1.5:
            pn = normalize_phone(order['phone'])
            txt = f"Здравствуйте! Курьер {BRAND} уже близко, будет через 10 мин по адресу {order['dest']}. Будьте на связи 📦"
            wa = f"https://wa.me/{pn}?text={urllib.parse.quote(txt)}"
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("📲 WhatsApp клиенту", url=wa))
            msg = f"⏰ 10 МИНУТ!\n📍 {order['dest']}\n📞 {order['phone']}\n📏 {dist:.2f} км от тебя"
            try:
                bot.send_message(order['chat_id'], msg, reply_markup=kb)
                bot.send_message(courier_id, f"Ты рядом с клиентом!\n{msg}", reply_markup=kb)
                order['notified']=True
            except: pass

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, f"🚚 {BRAND}\nВключи трансляцию геопозиции тут в боте и получай уведомления за 1.5 км\nЗаказ: Адрес Телефон")

@bot.message_handler(content_types=['location','live_location'])
def handle_loc(m):
    if not m.location: return
    cur = (m.location.latitude, m.location.longitude)
    couriers[m.chat.id]=cur
    print(f"Courier {m.chat.id} at {cur}")
    check_nearby_orders(m.chat.id, cur)

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    dest, phone = parse_order(m.text)
    if len(dest)<3: return
    coords = get_coords(dest)
    active_orders.append({'dest':dest,'phone':phone,'coords':coords,'chat_id':m.chat.id,'notified':False})
    st = "📍 Найдено ✅" if coords else "⚠️ Не найдено"
    bot.send_message(m.chat.id, f"✅ Заказ БЕЗ ФОТО принят\n📦 {dest}\n📞 {phone}\n{st}")
    
    # СРАЗУ проверяем если курьер уже рядом
    if coords:
        for cid, cpos in couriers.items():
            check_nearby_orders(cid, cpos)
    
    for cid in list(couriers.keys()):
        if cid==m.chat.id: continue
        try: bot.send_message(cid, f"🔥 НОВЫЙ ЗАКАЗ\n{DEFAULT_FROM} -> {dest}\n📞 {phone}")
        except: couriers.pop(cid, None)

@app.route('/')
def home(): return f"BAGYT V12 {len(active_orders)} couriers={len(couriers)}"
def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    while True:
        try: bot.infinity_polling(timeout=60)
        except Exception as e: print(f"Poll {e}")

if __name__=="__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
