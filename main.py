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
geolocator = Nominatim(user_agent="bagyt-bishkek-persist-v16")
couriers = set()

FILE = "orders.json"

def load_orders():
    try:
        if os.path.exists(FILE):
            with open(FILE,'r',encoding='utf-8') as f:
                return json.load(f)
    except: pass
    return []

def save_orders():
    try:
        with open(FILE,'w',encoding='utf-8') as f:
            json.dump(active_orders, f, ensure_ascii=False)
    except: pass

active_orders = load_orders()

MANUAL = {
    "биримдик кут": "Максима Горького 1",
    "мир обуви": "Дордой 14",
}

def get_coords_2gis(addr):
    if not DGIS_KEY: return None
    try:
        q = urllib.parse.quote(f"{addr}, Бишкек")
        url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={q}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=5).json()
        items = r.get('result',{}).get('items',[])
        if items and 'point' in items[0]:
            return (items[0]['point']['lat'], items[0]['point']['lon'])
        # пробуем как фирма
        url = f"https://catalog.api.2gis.com/3.0/items?q={q}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=5).json()
        items = r.get('result',{}).get('items',[])
        if items and 'point' in items[0]:
            return (items[0]['point']['lat'], items[0]['point']['lon'])
    except: pass
    return None

def get_coords(addr):
    low = addr.lower()
    for k,v in MANUAL.items():
        if k in low: addr = v; break
    clean = re.sub(r'(кв\.?|квартира)\s*\.?\s*\d+.*', '', addr, flags=re.I).strip()
    c = get_coords_2gis(clean)
    if c: return c
    try:
        loc = geolocator.geocode(f"{clean}, Бишкек", timeout=8)
        if loc: return (loc.latitude, loc.longitude)
    except: pass
    return None

def normalize_phone(p):
    d=''.join(filter(str.isdigit,p or ''))
    if not d: return ""
    if d.startswith('0'): d='996'+d[1:]
    if not d.startswith('996'): d='996'+d
    return d

def order_kb(oid, phone, dest):
    mk = types.InlineKeyboardMarkup(row_width=2)
    pn = normalize_phone(phone)
    if pn:
        wa_text=f"Здравствуйте! Ваш курьер Bagyt Express будет через 10 минут по адресу {dest}"
        wa_link=f"https://wa.me/{pn}?text={urllib.parse.quote(wa_text, safe='')}"
        mk.add(types.InlineKeyboardButton("📲 WhatsApp клиенту", url=wa_link))
    mk.add(
        types.InlineKeyboardButton("🚀 В пути", callback_data=f"go_{oid}"),
        types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{oid}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{oid}")
    )
    return mk

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🚚 Bagyt Express Бишкек\n/start - старт\n/orders - все заказы\n/history - история\n\nПиши: Адрес Телефон\nПример: Мир обуви 0550997099")

@bot.message_handler(commands=['orders'])
def list_orders(m):
    if not active_orders:
        bot.send_message(m.chat.id, "📭 Нет активных заказов. Напиши новый: Мир обуви 0550997099")
        return
    txt = f"📦 Активных: {len([o for o in active_orders if o.get('status')!='✅ Доставлено'])}\n\n"
    for o in active_orders[-10:]:
        if o.get('status')=='✅ Доставлено': continue
        txt+=f"{o.get('status','🆕')}\n📍 {o['dest']}\n📞 {o['phone']}\nID:{o['id'][:6]}\n---\n"
    bot.send_message(m.chat.id, txt or "Все доставлены ✅")

@bot.message_handler(commands=['history'])
def history(m):
    done = [o for o in active_orders if o.get('status')=='✅ Доставлено']
    txt = f"📊 Сегодня доставлено: {len(done)}\nВсего: {len(active_orders)}\n\n"
    for o in done[-5:]:
        txt+=f"✅ {o['dest']}\n"
    bot.send_message(m.chat.id, txt)

@bot.callback_query_handler(func=lambda c: True)
def callbacks(c):
    try:
        action, oid = c.data.split('_',1)
        order = next((o for o in active_orders if o['id']==oid or o['id'].startswith(oid)), None)
        if not order: 
            bot.answer_callback_query(c.id, "Не найден")
            return
        if action=="go":
            order['status']="🚀 В пути"
            save_orders()
            bot.answer_callback_query(c.id, "В пути!")
            bot.send_message(order['chat_id'], f"🚀 Курьер выехал!\n📍 {order['dest']}")
        elif action=="done":
            order['status']="✅ Доставлено"
            order['done_at']=str(datetime.datetime.now())
            save_orders()
            bot.answer_callback_query(c.id, "Доставлено!")
            bot.edit_message_text(f"✅ ДОСТАВЛЕНО\n📦 {order['dest']}", c.message.chat.id, c.message.message_id)
        elif action=="cancel":
            active_orders.remove(order)
            save_orders()
            bot.answer_callback_query(c.id, "Отменен")
            bot.edit_message_text(f"❌ ОТМЕНЕН {order['dest']}", c.message.chat.id, c.message.message_id)
    except Exception as e:
        print(e)

@bot.message_handler(content_types=['location','live_location'])
def handle_loc(m):
    couriers.add(m.chat.id)
    if not m.location: return
    cur=(m.location.latitude, m.location.longitude)
    for o in active_orders:
        if o.get('status')=='✅ Доставлено': continue
        if not o.get('coords'): continue
        try:
            dist=geodesic(cur, o['coords']).km
            if dist<1.5 and not o.get('notified'):
                mk=order_kb(o['id'], o['phone'], o['dest'])
                bot.send_message(o['chat_id'], f"⏰ Курьер в {dist:.2f} км!\n📍 {o['dest']}", reply_markup=mk)
                bot.send_message(m.chat.id, f"Ты рядом: {o['dest']} {dist:.2f} км", reply_markup=mk)
                o['notified']=True
                save_orders()
        except: pass

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text: return
    if m.text.lower().startswith('/start'): return start(m)
    if m.text.startswith('/'): return
    txt=m.text.strip()
    tmp=bot.send_message(m.chat.id, f"⏳ Ищу: {txt[:35]}...")
    def work():
        ph=re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', txt)
        phone=ph.group() if ph else ""
        dest=txt.replace(phone,'').strip(' -:,') if ph else txt
        coords=get_coords(dest)
        oid=str(uuid.uuid4())
        order={'id':oid,'dest':dest,'phone':phone,'coords':coords,'chat_id':m.chat.id,'notified':False,'status':'🆕 Принят'}
        active_orders.append(order)
        save_orders()
        mk=order_kb(oid, phone, dest)
        res=f"✅ Принято\n📦 {dest}\n{('📞 '+phone) if phone else ''}\n{'📍 Найдено ✅' if coords else '📍 Адрес принял'}\nID:{oid[:6]}"
        try: bot.edit_message_text(res, m.chat.id, tmp.message_id, reply_markup=mk)
        except: bot.send_message(m.chat.id, res, reply_markup=mk)
    threading.Thread(target=work, daemon=True).start()

@app.route('/')
def home(): return f"LIVE {len(active_orders)}"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(timeout=60)

if __name__=="__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
