import os, threading, urllib.parse, requests, re
import telebot
from flask import Flask
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from telebot import types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DGIS_KEY = os.environ.get("DGIS_KEY", "").strip()
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-final-3")

couriers = set()
active_orders = []

def get_coords(addr):
    # 1. Пробуем 2ГИС
    if DGIS_KEY:
        try:
            q = urllib.parse.quote(addr + ", Бишкек")
            url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={q}&fields=items.point&key={DGIS_KEY}"
            r = requests.get(url, timeout=6).json()
            items = r.get('result',{}).get('items',[])
            if items: return (items[0]['point']['lat'], items[0]['point']['lon'])
        except: pass
    # 2. OSM
    try:
        loc = geolocator.geocode(f"{addr}, Бишкек", timeout=10)
        if loc: return (loc.latitude, loc.longitude)
    except: pass
    return None

def normalize_phone(p):
    d=''.join(filter(str.isdigit,p))
    if d.startswith('0'): d='996'+d[1:]
    if not d.startswith('996'): d='996'+d
    return d

def split_kv(addr):
    m=re.search(r'(кв\.?|квартира)\s*\.?\s*(\d+[а-яА-Я]?)', addr, re.I)
    if m:
        kv=m.group(0)
        house=addr.replace(kv,'').strip(' ,.')
        return house, kv, addr
    return addr, "", addr

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🚚 Bagyt Express\nВключи трансляцию геопозиции тут и пиши:\nАдрес Телефон\nМожно с фото. Можно и без телефона - просто адрес")

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
                pn=normalize_phone(o['phone']) if o.get('phone') else ""
                if pn:
                    wa_text=f"Здравствуйте! Ваш курьер Bagyt Express будет через 10 мин по адресу {o['dest']}. Пожалуйста будьте на связи"
wa_link=f"https://wa.me/{pn}?text={urllib.parse.quote(wa_text, safe='')}"
                    mk=types.InlineKeyboardMarkup()
                    mk.add(types.InlineKeyboardButton("📲 WhatsApp клиенту", url=wa_link))
                else:
                    mk=None
                bot.send_message(o['chat_id'], f"⏰ Курьер в {dist:.1f} км! 📍 {o['dest']}", reply_markup=mk)
                bot.send_message(m.chat.id, f"Ты рядом: {o['dest']} {dist:.2f} км", reply_markup=mk)
                o['notified']=True
        except: pass

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    cap=(m.caption or m.text or "").strip()
    if not cap: cap="Заказ с фото"
    tmp=bot.send_message(m.chat.id, f"⏳ Принимаю фото...")
    def work():
        ph=re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', cap)
        phone=ph.group() if ph else "0700000000"
        dest=cap.replace(phone,'').strip() if ph else cap
        house,kv,full=split_kv(dest)
        coords=get_coords(house)
        active_orders.append({'dest':full,'phone':phone,'coords':coords,'chat_id':m.chat.id,'notified':False})
        status=f"📍 Найдено ✅ {kv}" if coords else "📍 Адрес принял, координаты уточню"
        bot.edit_message_text(f"✅ Заказ С ФОТО\n📦 {full}\n📞 {phone}\n{status}", m.chat.id, tmp.message_id)
    threading.Thread(target=work, daemon=True).start()

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    txt=m.text.strip()
    if len(txt)<3: return
    
    tmp=bot.send_message(m.chat.id, f"⏳ Ищу: {txt}...")
    
    def work():
        ph=re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', txt)
        phone=ph.group() if ph else ""
        dest=txt.replace(phone,'').strip(' -:,') if ph else txt
        
        house,kv,full=split_kv(dest)
        coords=get_coords(house) # Для квартиры ищем только дом
        
        # Как считается квартира:
        # Эмгекчил-7 кв 15 -> на карте ищем Эмгекчил-7, а курьеру показываем полностью кв 15
        # Салкын тор -> ищем как жилой массив, без номера дома тоже ок
        
        active_orders.append({'dest':full,'phone':phone,'coords':coords,'chat_id':m.chat.id,'notified':False})
        
        if coords:
            if kv: res=f"✅ Принято\n📦 {full}\n📍 Дом найден ✅ + {kv}\nКвартира считается отдельно от дома"
            else: res=f"✅ Принято\n📦 {full}\n📍 Найдено ✅ {coords[0]:.5f}"
        else:
            if phone: res=f"✅ Принято\n📦 {full}\n📞 {phone}\n📍 Координаты: Салкын тор / массив - принял, уточню у курьера"
            else: res=f"✅ Принято\n📦 {full}\n📍 Адрес принял. Отправь телефон клиента"
        
        try: bot.edit_message_text(res, m.chat.id, tmp.message_id)
        except: bot.send_message(m.chat.id, res)

    threading.Thread(target=work, daemon=True).start()

@app.route('/')
def home(): return "LIVE"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(timeout=60)

if __name__=="__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
