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
geolocator = Nominatim(user_agent="bagyt-bishkek-final-v17")

FILE = "orders.json"
active_orders = []
couriers = set()

MANUAL = {
    "биримдик кут": "Максима Горького 1",
    "мир обуви": "Дордой 14",
    "дордой плаза": "Дордой 115",
    "мадина": "Профсоюзная 52",
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
    except Exception as e:
        print(f"save err {e}")

active_orders = load_orders()

def get_coords_2gis(addr):
    if not DGIS_KEY:
        return None
    try:
        q = urllib.parse.quote(f"{addr}, Бишкек")
        # 1. как адрес
        url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={q}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=6).json()
        items = r.get('result', {}).get('items', [])
        if items and items[0].get('point'):
            return (items[0]['point']['lat'], items[0]['point']['lon'])
        # 2. как фирма / магазин
        url = f"https://catalog.api.2gis.com/3.0/items?q={q}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=6).json()
        items = r.get('result', {}).get('items', [])
        if items and items[0].get('point'):
            return (items[0]['point']['lat'], items[0]['point']['lon'])
    except Exception as e:
        print(f"2gis err {e}")
    return None

def get_coords(addr):
    low = addr.lower()
    for k, v in MANUAL.items():
        if k in low:
            addr = v
            break
    clean = re.sub(r'(кв\.?|квартира)\s*\.?\s*\d+.*', '', addr, flags=re.I).strip()
    c = get_coords_2gis(clean)
    if c:
        return c
    try:
        loc = geolocator.geocode(f"{clean}, Бишкек, Кыргызстан", timeout=10)
        if loc:
            return (loc.latitude, loc.longitude)
    except:
        pass
    return None

def normalize_phone(p):
    d = ''.join(filter(str.isdigit, p or ''))
    if not d:
        return ""
    if d.startswith('0'):
        d = '996' + d[1:]
    if not d.startswith('996'):
        d = '996' + d
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

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id,
        "🚚 *Bagyt Express Бишкек*\n\n"
        "/start - меню\n"
        "/orders - активные заказы\n"
        "/map - карта заказов\n"
        "/history - история\n\n"
        "Пиши: _Адрес Телефон_\n"
        "Пример: `Мир обуви 0550997099`",
        parse_mode='Markdown')

@bot.message_handler(commands=['orders'])
def list_orders(m):
    active = [o for o in active_orders if o.get('status') != '✅ Доставлено']
    if not active:
        bot.send_message(m.chat.id, "📭 Нет активных заказов")
        return
    txt = f"📦 Активных: {len(active)}\n\n"
    for o in active[-15:]:
        txt += f"{o.get('status','🆕 Принят')}\n📍 {o['dest']}\n📞 {o['phone']} | ID:{o['id'][:6]}\n---\n"
    bot.send_message(m.chat.id, txt)

@bot.message_handler(commands=['history'])
def history(m):
    done = [o for o in active_orders if o.get('status') == '✅ Доставлено']
    txt = f"📊 Сегодня доставлено: {len(done)}\nВсего заказов: {len(active_orders)}\n\n"
    for o in done[-10:]:
        txt += f"✅ {o['dest']}\n"
    bot.send_message(m.chat.id, txt or "Пока 0 доставок")

@bot.message_handler(commands=['map'])
def map_view(m):
    active = [o for o in active_orders if o.get('status') != '✅ Доставлено' and o.get('coords')]
    if not active:
        bot.send_message(m.chat.id, "📭 Нет активных точек на карте. Создай заказ: Эмгекчил-7 0554050070")
        return
    bot.send_message(m.chat.id, f"🗺 На карте {len(active)} точек. Кидаю:")
    for o in active:
        try:
            lat, lon = o['coords']
            bot.send_location(m.chat.id, lat, lon)
            bot.send_message(m.chat.id,
                f"📦 {o['dest']}\n📞 {o['phone']}\n{o.get('status')}",
                reply_markup=order_kb(o['id'], o['phone'], o['dest']))
        except Exception as e:
            print(e)

@bot.callback_query_handler(func=lambda c: True)
def callbacks(c):
    try:
        action, oid = c.data.split('_', 1)
        order = next((o for o in active_orders if o['id'] == oid), None)
        if not order:
            bot.answer_callback_query(c.id, "Заказ не найден")
            return
        if action == "go":
            order['status'] = "🚀 В пути"
            order['notified'] = True
            save_orders()
            bot.answer_callback_query(c.id, "Выехал!")
            bot.send_message(order['chat_id'], f"🚀 Курьер выехал!\n📍 {order['dest']}")
            bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=order_kb(order['id'], order['phone'], order['dest']))
        elif action == "done":
            order['status'] = "✅ Доставлено"
            order['done_at'] = str(datetime.datetime.now())
            save_orders()
            bot.answer_callback_query(c.id, "Доставлено ✅")
            bot.edit_message_text(f"✅ ДОСТАВЛЕНО\n📦 {order['dest']}\n📞 {order['phone']}", c.message.chat.id, c.message.message_id)
        elif action == "cancel":
            active_orders.remove(order)
            save_orders()
            bot.answer_callback_query(c.id, "Отменен")
            bot.edit_message_text(f"❌ ОТМЕНЕН\n📦 {order['dest']}", c.message.chat.id, c.message.message_id)
    except Exception as e:
        print(f"callback err {e}")

@bot.message_handler(content_types=['location', 'live_location'])
def handle_loc(m):
    couriers.add(m.chat.id)
    if not m.location:
        return
    cur = (m.location.latitude, m.location.longitude)
    for o in active_orders:
        if o.get('status') == '✅ Доставлено' or o.get('notified') or not o.get('coords'):
            continue
        try:
            dist = geodesic(cur, o['coords']).km
            if dist < 1.5:
                mk = order_kb(o['id'], o['phone'], o['dest'])
                bot.send_message(o['chat_id'], f"⏰ Курьер в {dist:.2f} км!\n📍 {o['dest']}", reply_markup=mk)
                bot.send_message(m.chat.id, f"Ты рядом {dist:.2f} км: {o['dest']}", reply_markup=mk)
                o['notified'] = True
                save_orders()
        except:
            pass

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'):
        return
    txt = m.text.strip()
    tmp = bot.send_message(m.chat.id, f"⏳ Ищу: {txt[:40]}...")
    def work():
        ph = re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', txt)
        phone = ph.group() if ph else ""
        dest = txt.replace(phone, '').strip(' -:,') if ph else txt
        coords = get_coords(dest)
        oid = str(uuid.uuid4())
        order = {'id': oid, 'dest': dest, 'phone': phone, 'coords': coords, 'chat_id': m.chat.id, 'notified': False, 'status': '🆕 Принят'}
        active_orders.append(order)
        save_orders()
        mk = order_kb(oid, phone, dest)
        res = f"✅ Принято\n📦 {dest}\n{('📞 '+phone) if phone else ''}\n{'📍 Найдено ✅' if coords else '📍 Адрес принял'}\nID:{oid[:6]}"
        try:
            bot.edit_message_text(res, m.chat.id, tmp.message_id, reply_markup=mk)
        except:
            bot.send_message(m.chat.id, res, reply_markup=mk)
    threading.Thread(target=work, daemon=True).start()

@app.route('/')
def home():
    return f"BAGYT LIVE {len(active_orders)} orders"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
