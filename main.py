import os, threading, urllib.parse, re, requests
import telebot
from flask import Flask
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from telebot import types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DGIS_KEY = os.environ.get("DGIS_KEY", "").strip()
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-bishkek-final")
couriers = set()
active_orders = []

def get_coords(addr):
    # Убираем кв для поиска
    clean = re.sub(r'(кв\.?|квартира)\s*\.?\s*\d+.*', '', addr, flags=re.I).strip()
    if DGIS_KEY:
        try:
            q = urllib.parse.quote(f"{clean}, Бишкек")
            url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={q}&fields=items.point&key={DGIS_KEY}"
            r = requests.get(url, timeout=5).json()
            items = r.get('result',{}).get('items',[])
            if items:
                p = items[0]['point']
                return (p['lat'], p['lon'])
        except Exception as e:
            print(f"2GIS err {e}")
    try:
        loc = geolocator.geocode(f"{clean}, Бишкек", timeout=8)
        if loc:
            return (loc.latitude, loc.longitude)
    except: pass
    return None

def normalize_phone(p):
    d=''.join(filter(str.isdigit,p or ''))
    if not d: return ""
    if d.startswith('0'): d='996'+d[1:]
    if not d.startswith('996'): d='996'+d
    return d

def split_kv(addr):
    m=re.search(r'(кв\.?|квартира)\s*\.?\s*(\d+[а-яА-Я]?)', addr, re.I)
    if m:
        return addr.replace(m.group(0),'').strip(' ,.'), m.group(0), addr
    return addr, "", addr

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🚚 Bagyt Express Бишкек\nВключи трансляцию тут и пиши:\nАдрес Телефон\nПример: Эмгекчил-7 кв 15 0554050070")

@bot.message_handler(content_types=['location','live_location'])
def handle_loc(m):
    couriers.add(m.chat.id)
    if not m.location: return
    cur=(m.location.latitude, m.location.longitude)
    for o in active_orders:
        if o.get('notified') or not o.get('coords'): continue
        try:
            dist=geodesic(cur, o['coords']).km
            if dist<1.5:
                pn=normalize_phone(o.get('phone'))
                wa_text=f"Здравствуйте! Ваш курьер Bagyt Express будет через 10 минут по адресу {o['dest']}"
                wa_link=f"https://wa.me/{pn}?text={urllib.parse.quote(wa_text, safe='')}" if pn else None
                mk=None
                if wa_link:
                    mk=types.InlineKeyboardMarkup()
                    mk.add(types.InlineKeyboardButton("📲 WhatsApp клиенту", url=wa_link))
                bot.send_message(o['chat_id'], f"⏰ Курьер в {dist:.2f} км!\n📍 {o['dest']}", reply_markup=mk)
                bot.send_message(m.chat.id, f"Ты рядом: {o['dest']} {dist:.2f} км", reply_markup=mk)
                o['notified']=True
        except Exception as e:
            print(e)

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    txt=m.text.strip()
    tmp=bot.send_message(m.chat.id, f"⏳ Ищу: {txt[:35]}...")
    def work():
        ph=re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', txt)
        phone=ph.group() if ph else ""
        dest=txt.replace(phone,'').strip(' -:,') if ph else txt
        house, kv, full = split_kv(dest)
        coords=get_coords(house) # кв считаем отдельно
        active_orders.append({'dest':full,'phone':phone,'coords':coords,'chat_id':m.chat.id,'notified':False})
        if coords:
            res=f"✅ Принято\n📦 {full}\n{('📞 '+phone) if phone else ''}\n📍 Найдено ✅ {kv}"
        else:
            res=f"✅ Принято\n📦 {full}\n{('📞 '+phone) if phone else ''}\n📍 Адрес принял"
        try: bot.edit_message_text(res, m.chat.id, tmp.message_id)
        except: bot.send_message(m.chat.id, res)
    threading.Thread(target=work, daemon=True).start()

@app.route('/')
def home(): return f"LIVE {len(active_orders)}"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(timeout=60)

if __name__=="__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
