import os, threading, urllib.parse
import telebot
from flask import Flask
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-v3")
DEFAULT_FROM = "Дордой мир обуви"

couriers = set()
active_orders = [] # храним заказы для проверки 10 мин

def get_coords(addr):
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
    bot.send_message(m.chat.id, f"🚚 BAGYT\n📦 {DEFAULT_FROM}\n\nТы: отправь фото + адрес в подписи\nКурьер: включи трансляцию геопозиции")

@bot.message_handler(content_types=['location','live_location'])
def handle_loc(m):
    couriers.add(m.chat.id)
    if not m.location: return
    
    cur_pos = (m.location.latitude, m.location.longitude)
    
    # Проверяем все активные заказы
    for order in active_orders:
        if order.get('notified'): continue
        if not order.get('coords'): continue
        
        dist = geodesic(cur_pos, order['coords']).km
        # если меньше 1.5 км = примерно 10 мин по Бишкеку
        if dist < 1.5:
            phone_norm = normalize_phone(order['phone'])
            text = f"Здравствуйте! Курьер Bagyt будет у вас через 10 минут 📦 по адресу {order['dest']}"
            wa_link = f"https://wa.me/{phone_norm}?text={urllib.parse.quote(text)}"
            
            msg = (
                f"⏰ КУРЬЕР В 10 МИНУТАХ!\n"
                f"📍 {order['dest']}\n"
                f"📞 {order['phone']}\n"
                f"📏 Осталось {dist:.2f} км\n\n"
                f"Нажми чтобы написать клиенту в WhatsApp:\n"
                f"👉 {wa_link}"
            )
            try:
                bot.send_message(order['chat_id'], msg)
                bot.send_message(m.chat.id, f"Ты рядом с клиентом!\n{msg}")
                order['notified'] = True
            except: pass

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    cap = (m.caption or "").strip()
    if not cap:
        bot.send_message(m.chat.id, "Добавь адрес в подпись к фото"); return
    fid = m.photo[-1].file_id
    p = cap.rsplit(' ', 1)
    dest, phone = (p[0], p[1]) if len(p)==2 else (cap, "клиент")
    
    coords = get_coords(dest)
    active_orders.append({'dest': dest, 'phone': phone, 'coords': coords, 'chat_id': m.chat.id, 'notified': False})
    
    phone_norm = normalize_phone(phone)
    wa_link = f"https://wa.me/{phone_norm}?text={urllib.parse.quote(f'Здравствуйте! Ваш заказ из {DEFAULT_FROM} принят ✅ Едет по адресу {dest}')}"
    
    bot.send_message(m.chat.id, f"✅ Заказ с фото принят\n📦 {DEFAULT_FROM} -> {dest}\n📞 {phone}\n\nСразу написать клиенту:\n👉 {wa_link}")
    
    for cid in list(couriers):
        if cid == m.chat.id: continue
        try: bot.send_photo(cid, fid, caption=f"🔥 ЗАКАЗ\n{DEFAULT_FROM} -> {dest}\n📞 {phone}")
        except: couriers.discard(cid)

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    for line in m.text.split('\n'):
        if not line.strip(): continue
        p = line.strip().rsplit(' ', 1)
        dest, phone = (p[0], p[1]) if len(p)==2 else (line.strip(), "клиент")
        coords = get_coords(dest)
        active_orders.append({'dest': dest, 'phone': phone, 'coords': coords, 'chat_id': m.chat.id, 'notified': False})
        
        phone_norm = normalize_phone(phone)
        wa_link = f"https://wa.me/{phone_norm}?text={urllib.parse.quote(f'Здравствуйте! Ваш заказ из {DEFAULT_FROM} принят ✅')}"
        bot.send_message(m.chat.id, f"✅ Принят: {dest} {phone}\n👉 WhatsApp: {wa_link}")
        
        for cid in list(couriers):
            if cid == m.chat.id: continue
            try: bot.send_message(cid, f"🔥 ЗАКАЗ\n{DEFAULT_FROM} -> {dest}\n📞 {phone}")
            except: couriers.discard(cid)

@app.route('/')
def home(): return f"BAGYT LIVE {len(active_orders)} orders"
def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    while True:
        try: bot.infinity_polling(timeout=60)
        except: pass
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
