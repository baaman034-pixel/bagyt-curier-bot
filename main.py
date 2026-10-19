import os, threading, urllib.parse, requests, re
import telebot
from flask import Flask
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from telebot import types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-final-bishkek")
DEFAULT_FROM = "Dordoi mir obuvi"
BRAND = "Bagyt Express"
DGIS_KEY = os.environ.get("DGIS_KEY", "")

couriers = set()
active_orders = []

def get_coords_2gis(addr):
    if not DGIS_KEY: return None
    try:
        q = urllib.parse.quote(addr + ", Bishkek")
        url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={q}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=4).json()
        if r.get('result',{}).get('items'):
            p = r['result']['items'][0]['point']
            return (p['lat'], p['lon'])
    except: pass
    return None

def get_coords(addr):
    c = get_coords_2gis(addr)
    if c: return c
    try:
        loc = geolocator.geocode(f"{addr}, Bishkek, Kyrgyzstan", timeout=8)
        if loc: return (loc.latitude, loc.longitude)
    except: pass
    return None

def normalize_phone(p):
    d = ''.join(filter(str.isdigit, p))
    if d.startswith('0'): d = '996' + d[1:]
    if not d.startswith('996'): d = '996' + d
    return d

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, f"{BRAND} - Vklyuchi translaciyu i pishi: Adres Telefon")

@bot.message_handler(content_types=['location','live_location'])
def handle_loc(m):
    couriers.add(m.chat.id)
    if not m.location: return
    cur = (m.location.latitude, m.location.longitude)
    for order in active_orders:
        if order.get('notified'): continue
        if not order.get('coords'): continue
        dist = geodesic(cur, order['coords']).km
        if dist < 1.5:
            pn = normalize_phone(order['phone'])
            txt = f"Zdravstvuite! Kuryer {BRAND} budet cherez 10 min {order['dest']}"
            link = f"https://wa.me/{pn}?text={urllib.parse.quote(txt)}"
            mk = types.InlineKeyboardMarkup()
            mk.add(types.InlineKeyboardButton("Napisat v WhatsApp", url=link))
            msg = f"KURYER V 10 MIN! {order['dest']} {order['phone']} {dist:.2f} km"
            try:
                bot.send_message(order['chat_id'], msg, reply_markup=mk)
                bot.send_message(m.chat.id, f"Ty ryadom! {msg}", reply_markup=mk)
                order['notified']=True
            except: pass

def process_order(chat_id, dest, phone, tmp_id, with_photo=False, photo_id=None):
    coords = get_coords(dest)
    status = "Naydeno OK" if coords else "Ne naydeno"
    active_orders.append({'dest':dest,'phone':phone,'coords':coords,'chat_id':chat_id,'notified':False})
    label = "S FOTO" if with_photo else "BEZ FOTO"
    final = f"Zakaz {label} prinyat\n{dest}\n{phone}\n{status}"
    try: bot.edit_message_text(final, chat_id, tmp_id)
    except: bot.send_message(chat_id, final)
    for cid in list(couriers):
        if cid==chat_id: continue
        try:
            if with_photo: bot.send_photo(cid, photo_id, caption=f"ZAKAZ {dest} {phone}")
            else: bot.send_message(cid, f"ZAKAZ {dest} {phone}")
        except: couriers.discard(cid)

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    cap=(m.caption or "").strip()
    if not cap: return
    ph=re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', cap)
    if not ph: return
    phone=ph.group(); dest=cap.replace(phone,'').strip(' -:,')
    tmp=bot.send_message(m.chat.id, f"Prinimayu: {dest}...")
    threading.Thread(target=process_order, args=(m.chat.id,dest,phone,tmp.message_id,True,m.photo[-1].file_id), daemon=True).start()

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    for line in m.text.split('\n'):
        line=line.strip()
        if len(line)<5: continue
        ph=re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', line)
        if not ph: continue
        phone=ph.group(); dest=line.replace(phone,'').strip(' -:,')
        if not dest: continue
        tmp=bot.send_message(m.chat.id, f"Prinimayu: {dest}...")
        threading.Thread(target=process_order, args=(m.chat.id,dest,phone,tmp.message_id,False,None), daemon=True).start()

@app.route('/')
def home(): return f"LIVE {len(active_orders)}"
def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    while True:
        try: bot.infinity_polling(timeout=60)
        except: continue
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
