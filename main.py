import os, threading, urllib.parse, re, requests, uuid, json
import telebot
from flask import Flask
from telebot import types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DGIS_KEY = (os.environ.get("DGIS_KEY") or os.environ.get("DGIS_API_KEY") or "").strip()

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

FILE = "orders.json"
MANUAL_FILE = "manual_points.json"

MANUAL_COORDS = {
    "иманалы айдарбеков 173": (42.88385, 74.57490),
    "эмгекчил-7 5": (42.91230, 74.56450),
}

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path,'r',encoding='utf-8') as f:
                return json.load(f)
    except: pass
    return default

def save_json(path, data):
    try:
        with open(path,'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=2)
    except: pass

active_orders = load_json(FILE, [])
manual_db = load_json(MANUAL_FILE, {})
def save_orders(): save_json(FILE, active_orders)
def save_manual(): save_json(MANUAL_FILE, manual_db)

def in_bishkek(lat, lon):
    return 42.70 < lat < 43.05 and 74.30 < lon < 74.95

def get_coords_2gis(addr):
    if not DGIS_KEY:
        print("DGIS_KEY EMPTY")
        return None
    try:
        q = urllib.parse.quote(addr)
        url = f"https://catalog.api.2gis.com/3.0/items?q={q}&fields=items.point&key={DGIS_KEY}&region_id=38"
        r = requests.get(url, timeout=8).json()
        items = r.get('result', {}).get('items', [])
        for it in items:
            p = it.get('point')
            if p and in_bishkek(p['lat'], p['lon']):
                print(f"2GIS OK: {addr} -> {p}")
                return (p['lat'], p['lon'])
        url2 = f"https://catalog.api.2gis.com/3.0/items/geocode?q={q}&fields=items.point&key={DGIS_KEY}"
        r2 = requests.get(url2, timeout=8).json()
        items2 = r2.get('result', {}).get('items', [])
        if items2 and items2[0].get('point'):
            p = items2[0]['point']
            if in_bishkek(p['lat'], p['lon']):
                return (p['lat'], p['lon'])
    except Exception as e:
        print(f"2GIS err {e}")
    return None

def get_coords(addr):
    low = addr.lower().strip()
    for k,v in manual_db.items():
        if k in low: return tuple(v)
    for k,v in MANUAL_COORDS.items():
        if k in low: return tuple(v)
    clean = re.sub(r'(?i)кв.*', '', addr).strip()
    return get_coords_2gis(f"{clean}, Бишкек")

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
        wa_text = f"Здравствуйте! Курьер Bagyt через 10 мин: {dest}"
        mk.add(types.InlineKeyboardButton("📲 WhatsApp", url=f"https://wa.me/{pn}?text={urllib.parse.quote(wa_text)}"))
    mk.add(types.InlineKeyboardButton("🚀 В пути", callback_data=f"go_{oid}"),
            types.InlineKeyboardButton("✅ Доставлено", callback_data=f"done_{oid}"))
    mk.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"cancel_{oid}"))
    return mk

def parse_order(text):
    t = text.strip()
    phone = ""
    m = list(re.finditer(r'0\d{9}', re.sub(r'\s+','',t)))
    dest = t
    if m:
        phone = m[-1].group()
        dest = t.replace(phone, '') if phone in t else re.sub(r'0\d{9}','',t)
    dest = re.sub(r'\s+',' ', dest).strip(' -:,')
    return dest or "Адрес уточнить", phone

@app.route('/m/<uid>')
def show_map(uid):
    orders = [o for o in active_orders if str(o.get('chat_id'))==uid and o.get('coords') and o.get('status')!='✅ Доставлено'][-50:]
    if not orders: return "Нет точек"
    pts = ",".join([f'{{lat:{o["coords"][0]},lon:{o["coords"][1]},name:"{o["dest"].replace(chr(34),chr(39))}"}}' for o in orders])
    return f"""<html><head><meta name='viewport' content='width=device-width,initial-scale=1.0'>
    <script src="https://api-maps.yandex.ru/2.1/?lang=ru_RU"></script>
    <style>html,body,#map{{width:100%;height:100%;margin:0}}</style></head><body><div id="map"></div>
    <script>ymaps.ready(function(){{
        var map=new ymaps.Map("map",{{center:[42.87,74.59],zoom:12,controls:['zoomControl']}});
        var pts=[{pts}];
        pts.forEach((p,i)=>{{map.geoObjects.add(new ymaps.Placemark([p.lat,p.lon],{{balloonContent:(i+1)+". "+p.name}},{{preset:'islands#redIcon',iconContent:i+1}}))}});
        if(pts.length) map.setBounds(map.geoObjects.getBounds(),{{checkZoomRange:true,zoomMargin:40}});
    }});</script></body></html>"""

@app.route('/')
def home(): return f"BAGYT 2GIS ONLY Live! Cargo:{len(active_orders)} DGIS:{'OK' if DGIS_KEY else 'NO'}"

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, f"🚚 *Bagyt v28 2GIS only*\n2ГИС: {'✅ подключен' if DGIS_KEY else '❌ нет ключа - добавь DGIS_KEY в Render'}\n\nПиши: Адрес + телефон\nПример: Эмгекчил-7 5 0554050070\n\n/map - карта", parse_mode='Markdown')

@bot.message_handler(commands=['map'])
def map_view(m):
    active = [o for o in active_orders if str(o.get('chat_id'))==str(m.chat.id) and o.get('status')!='✅ Доставлено' and o.get('coords')][-50:]
    if not active:
        bot.send_message(m.chat.id, "📭 Нет точек"); return
    base = os.environ.get("RENDER_EXTERNAL_URL","").rstrip("/") or f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME','')}"
    if not base or base=="https://": base="https://bagyt-bot.onrender.com"
    link = f"{base}/m/{m.chat.id}"
    txt = f"🗺 {len(active)} домов (2ГИС):\n\n" + "\n".join([f"{i+1}. {o['dest']}" for i,o in enumerate(active)])
    mk = types.InlineKeyboardMarkup()
    mk.add(types.InlineKeyboardButton("🔍 ОТКРЫТЬ КАРТУ", url=link))
    bot.send_message(m.chat.id, txt, reply_markup=mk)

@bot.message_handler(commands=['fix'])
def fix_cmd(m):
    cnt=0
    for o in active_orders:
        if str(o.get('chat_id'))!=str(m.chat.id): continue
        nc = get_coords(o['dest'])
        if nc: o['coords']=nc; cnt+=1
    save_orders()
    bot.send_message(m.chat.id, f"✅ Перепроверил {cnt} через 2ГИС. /map")

@bot.callback_query_handler(func=lambda c: True)
def cbs(c):
    try:
        act, oid = c.data.split('_',1)
        o = next((x for x in active_orders if x['id']==oid), None)
        if not o: return
        if act=="go": o['status']="🚀 В пути"
        elif act=="done": o['status']="✅ Доставлено"
        elif act=="cancel": active_orders.remove(o)
        save_orders(); bot.answer_callback_query(c.id, "OK")
    except: pass

@bot.message_handler(content_types=['location'])
def learn(m):
    if not m.location: return
    cap = (m.caption or "").lower().strip()
    if cap:
        manual_db[cap]=[m.location.latitude, m.location.longitude]
        save_manual()
        bot.send_message(m.chat.id, f"✅ Запомнил {cap} навсегда")

@bot.message_handler(content_types=['text'])
def handle(m):
    if not m.text or m.text.startswith('/'): return
    tmp = bot.send_message(m.chat.id, "⏳ Ищу в 2ГИС до подъезда...")
    def work():
        dest, phone = parse_order(m.text)
        coords = get_coords(dest)
        oid = str(uuid.uuid4())[:8]
        active_orders.append({'id':oid,'dest':dest,'phone':phone,'coords':coords,'chat_id':m.chat.id,'status':'🆕'})
        save_orders()
        res = f"{'✅ 2ГИС нашел до дома' if coords else '❌ 2ГИС не нашел'}: {dest}"
        try: bot.edit_message_text(res, m.chat.id, tmp.message_id, reply_markup=order_kb(oid, phone, dest))
        except: bot.send_message(m.chat.id, res, reply_markup=order_kb(oid, phone, dest))
    threading.Thread(target=work, daemon=True).start()

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__=="__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
