import os, threading, urllib.parse, re, requests, uuid, json
import telebot
from flask import Flask
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from telebot import types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DGIS_KEY = os.environ.get("DGIS_KEY", "").strip()

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-yandex-v24")

FILE = "orders.json"
active_orders = []

# ПРЯМО НА ДОМ - ЗАПОМНИЛ
MANUAL_COORDS = {
    "иманалы айдарбеков 173": (42.9272, 74.5718),
    "айдарбеков 173": (42.9272, 74.5718),
    "киевская 199": (42.8753, 74.5908),
    "ибраимова 115": (42.8759, 74.6123),
    "эмгекчил 7": (42.9450, 74.6010),
}

MANUAL = {
    "биримдик кут": "Максима Горького 1",
    "мир обуви": "Дордой 14",
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
    except: pass
    return None

def get_coords(addr):
    low = addr.lower().strip()
    for k, (lat, lon) in MANUAL_COORDS.items():
        if k in low:
            return (lat, lon)
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
        wa_text = f"Здравствуйте! Ваш курьер Bagyt будет через 10 мин: {dest}"
        wa_link = f"https://wa.me/{pn}?text={urllib.parse.quote(wa_text)}"
        mk.add(types.InlineKeyboardButton("📲 WhatsApp", url=wa_link))
    mk.add(
        types.InlineKeyboardButton("🚀 В пути", callback_data=f"go_{oid}"),
        types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{oid}"),
    )
    mk.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{oid}"))
    return mk

def parse_order(text):
    t = text.strip()
    nospace = re.sub(r'\s+', '', t)
    phone = ""
    matches = list(re.finditer(r'0\d{9}', nospace))
    if matches:
        phone = matches[-1].group()
        dest = t.replace(phone, '') if phone in t else nospace.replace(phone, '')
        dest = dest.strip(' -:,')
    else:
        dest = t
    dest = re.sub(r'\s+', ' ', dest).strip()
    dest = re.sub(r'0\d{9}', '', dest).strip()
    if not dest: dest = "Адрес уточнить"
    return dest, phone

@app.route('/m/<uid>')
def show_map(uid):
    orders = [o for o in active_orders if str(o.get('chat_id'))==uid and o.get('coords') and o.get('status')!='✅ Доставлено'][-50:]
    if not orders:
        return "Нет точек"
    points_js = ",".join([f'{{lat:{o["coords"][0]},lon:{o["coords"][1]},name:"{o["dest"].replace(chr(34),chr(39))}"}}' for o in orders])
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <script src="https://api-maps.yandex.ru/2.1/?lang=ru_RU"></script>
    <style>html,body,#map{{width:100%;height:100%;margin:0;padding:0}}</style>
    </head><body><div id="map"></div>
    <script>
    ymaps.ready(function(){{
        var map = new ymaps.Map("map", {{center:[42.87,74.59], zoom:12, controls:['zoomControl']}});
        var pts = [{points_js}];
        pts.forEach((p,i)=>{{
            var pm = new ymaps.Placemark([p.lat,p.lon],
                {{balloonContent: (i+1)+". "+p.name+"<br><a href='https://yandex.ru/maps/?rtext=~"+p.lat+","+p.lon+"&rtt=auto'>Маршрут</a>"}},
                {{preset:'islands#redIcon', iconContent: i+1}});
            map.geoObjects.add(pm);
        }});
        if(pts.length>0) map.setBounds(map.geoObjects.getBounds(), {{checkZoomRange:true, zoomMargin:50}});
    }});
    </script></body></html>
    """
    return html

@app.route('/')
def home(): return f"BAGYT YANDEX 50 {len(active_orders)}"

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🚚 *Bagyt v24 Яндекс*\nДо 50 точек прямо на дом\nПиши: Адрес Телефон", parse_mode='Markdown')

@bot.message_handler(commands=['map'])
def map_view(m):
    active = [o for o in active_orders if o.get('status') != '✅ Доставлено' and o.get('coords') and str(o.get('chat_id'))==str(m.chat.id)][-50:]
    if not active:
        bot.send_message(m.chat.id, "📭 Нет точек")
        return
    base = os.environ.get("RENDER_EXTERNAL_URL","").rstrip("/")
    if not base:
        base = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME','')}"
    if not base or base=="https://":
        base = "https://bagyt.onrender.com"
    link = f"{base}/m/{m.chat.id}"
    txt = f"🗺 Яндекс: {len(active)} домов - точки прямо на домах\n\n"
    for i,o in enumerate(active):
        txt += f"{i+1}. {o['dest']}\n"
    mk = types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("🔍 ОТКРЫТЬ ЯНДЕКС КАРТУ (видно подъезды)", url=link))
    for i in range(0, len(active), 10):
        chunk = active[i:i+10]
        rtext = "~".join([f"{o['coords'][0]},{o['coords'][1]}" for o in chunk])
        ya_route = f"https://yandex.ru/maps/?rtext={rtext}&rtt=auto"
        mk.add(types.InlineKeyboardButton(f"🚀 Яндекс маршрут {i+1}-{i+len(chunk)}", url=ya_route))
    bot.send_message(m.chat.id, txt, reply_markup=mk)

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
        elif action == "cancel":
            active_orders.remove(order); save_orders()
            bot.answer_callback_query(c.id, "Отменен")
    except: pass

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    txt = m.text.strip()
    tmp = bot.send_message(m.chat.id, f"⏳ Ищу дом: {txt[:40]}...")
    def work():
        dest, phone = parse_order(txt)
        coords = get_coords(dest)
        oid = str(uuid.uuid4())
        order = {'id': oid, 'dest': dest, 'phone': phone, 'coords': coords, 'chat_id': m.chat.id, 'notified': False, 'status': '🆕'}
        active_orders.append(order); save_orders()
        mk = order_kb(oid, phone, dest)
        res = f"✅ Принято прямо на дом\n📦 {dest}\n{'📞 '+phone if phone else ''}\n{'📍 Дом найден ✅' if coords else '📍'}\nID:{oid[:6]}"
        try: bot.edit_message_text(res, m.chat.id, tmp.message_id, reply_markup=mk)
        except: bot.send_message(m.chat.id, res, reply_markup=mk)
    threading.Thread(target=work, daemon=True).start()

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
