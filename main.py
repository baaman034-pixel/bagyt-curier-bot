import os, threading, urllib.parse, re, requests, uuid, datetime, json
import telebot
from flask import Flask
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from telebot import types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DGIS_KEY = os.environ.get("DGIS_KEY", "").strip()

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-bishkek-v20-final")

FILE = "orders.json"
active_orders = []

# 1. ИСПРАВЛЕНИЯ НАЗВАНИЙ
MANUAL = {
    "биримдик кут": "Максима Горького 1",
    "мир обуви": "Дордой 14",
    "дордой плаза": "Дордой 115",
    "мадина": "Профсоюзная 52",
}

# 2. ТОЧНЫЕ КООРДИНАТЫ - ЗАПОМНИЛ ТВОИ ОШИБКИ
MANUAL_COORDS = {
    "иманалы айдарбеков 173": (42.9287, 74.5712),
    "айдарбеков 173": (42.9287, 74.5712),
    "иманали айдарбеков 173": (42.9287, 74.5712),
    "киевская 199": (42.8753, 74.5908),
    "ул киевская 199": (42.8753, 74.5908),
}

def load_orders():
    try:
        if os.path.exists(FILE):
            with open(FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except: pass
    return []

def save_orders():
    try:
        with open(FILE, 'w', encoding='utf-8') as f:
            json.dump(active_orders, f, ensure_ascii=False)
    except: pass

active_orders = load_orders()

def get_coords_2gis(addr):
    if not DGIS_KEY: return None
    try:
        q = urllib.parse.quote(f"{addr}, Бишкек")
        url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={q}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=6).json()
        items = r.get('result', {}).get('items', [])
        if items and items[0].get('point'):
            return (items[0]['point']['lat'], items[0]['point']['lon'])
        url = f"https://catalog.api.2gis.com/3.0/items?q={q}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=6).json()
        items = r.get('result', {}).get('items', [])
        if items and items[0].get('point'):
            return (items[0]['point']['lat'], items[0]['point']['lon'])
    except: pass
    return None

def get_coords(addr):
    low = addr.lower().strip()
    # Сначала точные координаты из твоих ошибок
    for k, (lat, lon) in MANUAL_COORDS.items():
        if k in low:
            return (lat, lon)
    # Потом замена названий магазинов
    for k, v in MANUAL.items():
        if k in low:
            addr = v; break
    clean = re.sub(r'(кв\.?|квартира)\s*\.?\s*\d+.*', '', addr, flags=re.I).strip()
    c = get_coords_2gis(clean)
    if c: return c
    try:
        loc = geolocator.geocode(f"{clean}, Бишкек, Кыргызстан", timeout=10)
        if loc: return (loc.latitude, loc.longitude)
    except: pass
    return None

def normalize_phone(p):
    d = ''.join(filter(str.isdigit, p or ''))
    if not d: return ""
    if d.startswith('0'): d = '996' + d[1:]
    if not d.startswith('996'): d = '996' + d
    return d

def order_kb(oid, phone, dest):
    mk = types.InlineKeyboardMarkup(row_width=2)
    pn = normalize_phone(phone)
    if pn:
        wa_text = f"Здравствуйте! Ваш курьер Bagyt Express будет через 10 минут по адресу {dest}"
        wa_link = f"https://wa.me/{pn}?text={urllib.parse.quote(wa_text, safe='')}"
        mk.add(types.InlineKeyboardButton("📲 WhatsApp клиенту", url=wa_link))
    mk.add(
        types.InlineKeyboardButton("🚀 В пути", callback_data=f"go_{oid}"),
        types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{oid}"),
    )
    mk.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{oid}"))
    return mk

# УМНЫЙ ПАРСЕР - чинит 1990550997099 -> 199 + 0550997099
def parse_order(text):
    t = text.strip()
    nospace = re.sub(r'\s+', '', t)
    phone = ""
    matches = list(re.finditer(r'0\d{9}', nospace))
    if matches:
        phone = matches[-1].group()
        if phone in t:
            dest = t.replace(phone, '')
        else:
            dest = nospace.replace(phone, '')
            dest = re.sub(r'([а-яА-Я]+)(\d+)$', r'\1 \2', dest)
        dest = dest.strip(' -:,')
    else:
        dest = t
    dest = re.sub(r'\s+', ' ', dest).strip()
    dest = re.sub(r'0\d{9}', '', dest).strip()
    if not dest: dest = "Адрес уточнить"
    return dest, phone

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id,
        "🚚 *Bagyt Express Бишкек v20*\n\n"
        "/start - меню\n/orders - активные\n/map - карта 3 заказов\n/history - история\n\n"
        "Пиши: _Адрес Телефон_\n`Киевская 199 0550997099`",
        parse_mode='Markdown')

@bot.message_handler(commands=['orders'])
def list_orders(m):
    active = [o for o in active_orders if o.get('status') != '✅ Доставлено']
    if not active:
        bot.send_message(m.chat.id, "📭 Нет активных")
        return
    txt = f"📦 Активных: {len(active)}\n\n"
    for o in active[-15:]:
        txt += f"{o.get('status','🆕')}\n📍 {o['dest']}\n📞 {o['phone']} ID:{o['id'][:6]}\n---\n"
    bot.send_message(m.chat.id, txt)

@bot.message_handler(commands=['history'])
def history(m):
    done = [o for o in active_orders if o.get('status') == '✅ Доставлено']
    txt = f"📊 Доставлено: {len(done)} Всего: {len(active_orders)}\n\n"
    for o in done[-10:]: txt += f"✅ {o['dest']}\n"
    bot.send_message(m.chat.id, txt)

@bot.message_handler(commands=['map'])
def map_view(m):
    active = [o for o in active_orders if o.get('status') != '✅ Доставлено' and o.get('coords')]
    if not active:
        bot.send_message(m.chat.id, "📭 Нет точек. Создай: Иманалы Айдарбеков 173 0550997099")
        return
    lats = [o['coords'][0] for o in active]
    lons = [o['coords'][1] for o in active]
    center_lat = sum(lats)/len(lats)
    center_lon = sum(lons)/len(lons)
    markers = "&".join([f"markers={lat},{lon},red" for lat, lon in zip(lats,lons)])
    map_url = f"https://staticmap.openstreetmap.de/staticmap.php?center={center_lat},{center_lon}&zoom=13&size=800x600&{markers}"
    try:
        bot.send_photo(m.chat.id, map_url, caption=f"🗺 Bagyt: {len(active)} заказов")
    except:
        bot.send_message(m.chat.id, f"🗺 На карте {len(active)} заказов:\n" + "\n".join([f"{i+1}. {o['dest']}" for i,o in enumerate(active)]))
    dirs = "/".join([f"{lat},{lon}" for lat, lon in zip(lats,lons)])
    gmaps = f"https://www.google.com/maps/dir/{dirs}/"
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton(f"🚀 Маршрут по {len(active)} точкам", url=gmaps))
    bot.send_message(m.chat.id, f"Заказов: {len(active)}\nПостроить маршрут:", reply_markup=mk)
    for o in active:
        try:
            bot.send_location(m.chat.id, o['coords'][0], o['coords'][1])
            bot.send_message(m.chat.id, f"📦 {o['dest']}")
        except: pass

@bot.callback_query_handler(func=lambda c: True)
def callbacks(c):
    try:
        action, oid = c.data.split('_', 1)
        order = next((o for o in active_orders if o['id'] == oid), None)
        if not order: return
        if action == "go":
            order['status'] = "🚀 В пути"; order['notified']=True; save_orders()
            bot.answer_callback_query(c.id, "В пути!")
        elif action == "done":
            order['status'] = "✅ Доставлено"; save_orders()
            bot.answer_callback_query(c.id, "Доставлено!")
            bot.edit_message_text(f"✅ ДОСТАВЛЕНО\n📦 {order['dest']}", c.message.chat.id, c.message.message_id)
        elif action == "cancel":
            active_orders.remove(order); save_orders()
            bot.answer_callback_query(c.id, "Отменен")
            bot.edit_message_text(f"❌ ОТМЕНЕН {order['dest']}", c.message.chat.id, c.message.message_id)
    except: pass

@bot.message_handler(content_types=['location','live_location'])
def handle_loc(m):
    if not m.location: return
    cur = (m.location.latitude, m.location.longitude)
    for o in active_orders:
        if o.get('status')=='✅ Доставлено' or o.get('notified') or not o.get('coords'): continue
        try:
            dist = geodesic(cur, o['coords']).km
            if dist < 1.5:
                mk = order_kb(o['id'], o['phone'], o['dest'])
                bot.send_message(m.chat.id, f"Ты рядом {dist:.2f} км: {o['dest']}", reply_markup=mk)
                o['notified']=True; save_orders()
        except: pass

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    txt = m.text.strip()
    tmp = bot.send_message(m.chat.id, f"⏳ Ищу: {txt[:40]}...")
    def work():
        dest, phone = parse_order(txt)
        coords = get_coords(dest)
        oid = str(uuid.uuid4())
        order = {'id': oid, 'dest': dest, 'phone': phone, 'coords': coords, 'chat_id': m.chat.id, 'notified': False, 'status': '🆕 Принят'}
        active_orders.append(order); save_orders()
        mk = order_kb(oid, phone, dest)
        res = f"✅ Принято\n📦 {dest}\n{('📞 '+phone) if phone else ''}\n{'📍 Найдено ✅' if coords else '📍 Адрес принял'}\nID:{oid[:6]}"
        try: bot.edit_message_text(res, m.chat.id, tmp.message_id, reply_markup=mk)
        except: bot.send_message(m.chat.id, res, reply_markup=mk)
    threading.Thread(target=work, daemon=True).start()

@app.route('/')
def home(): return f"BAGYT LIVE {len(active_orders)}"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
