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
geolocator = Nominatim(user_agent="bagyt-express-final-v2")

couriers = set()
active_orders = []

def get_coords_2gis(addr):
    if not DGIS_KEY: return None
    try:
        q = urllib.parse.quote(addr + ", Бишкек")
        url = f"https://catalog.api.2gis.com/3.0/items/geocode?q={q}&fields=items.point&key={DGIS_KEY}"
        r = requests.get(url, timeout=6).json()
        items = r.get('result', {}).get('items', [])
        if items:
            p = items[0]['point']
            return (p['lat'], p['lon'])
    except: pass
    return None

def get_coords_osm(addr):
    try:
        loc = geolocator.geocode(f"{addr}, Бишкек, Кыргызстан", timeout=10)
        if loc: return (loc.latitude, loc.longitude)
    except: pass
    return None

def get_coords(addr):
    c = get_coords_2gis(addr)
    if c: return c
    return get_coords_osm(addr)

def normalize_phone(p):
    d=''.join(filter(str.isdigit,p))
    if d.startswith('0'): d='996'+d[1:]
    if not d.startswith('996'): d='996'+d
    return d

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🚚 Bagyt Express\nВключи трансляцию геопозиции тут и пиши:\nАдрес Телефон\nМожно с фото товара")

@bot.message_handler(content_types=['location','live_location'])
def handle_loc(m):
    couriers.add(m.chat.id)
    if not m.location: return
    cur=(m.location.latitude, m.location.longitude)
    for o in active_orders:
        if o.get('notified') or not o.get('coords'): continue
        try:
            dist=geodesic(cur, o['coords']).km
            if dist < 1.5:
                pn=normalize_phone(o['phone'])
                # ТЕКСТ ДЛЯ WHATSAPP - только латиница, чтобы не было %25
                wa_text=f"Zdravstvuite! Vash kuryer Bagyt Express uzhe blizko, budet cherez 10 min po adresu {o['dest']}. Pozhaluista budte na svyazi"
                wa_link=f"https://wa.me/{pn}?text={urllib.parse.quote(wa_text)}"
                mk=types.InlineKeyboardMarkup()
                mk.add(types.InlineKeyboardButton("📲 WhatsApp клиенту", url=wa_link))
                msg=f"⏰ КУРЬЕР В 10 МИН!\n📍 {o['dest']}\n📞 {o['phone']}\n📏 {dist:.2f} км"
                bot.send_message(o['chat_id'], msg, reply_markup=mk)
                bot.send_message(m.chat.id, f"Ты рядом: {o['dest']}\n{dist:.2f} км", reply_markup=mk)
                o['notified']=True
        except Exception as e:
            print(f"loc error {e}")

def process_order(chat_id, dest, phone, tmp_id, with_photo=False, photo_id=None):
    coords=get_coords(dest)
    status="📍 Найдено ✅" if coords else "📍 Не найдено ⚠️"
    active_orders.append({'dest':dest,'phone':phone,'coords':coords,'chat_id':chat_id,'notified':False})
    label="С ФОТО" if with_photo else "БЕЗ ФОТО"
    final=f"✅ Заказ {label} принят\n📦 {dest}\n📞 {phone}\n{status}"
    try: bot.edit_message_text(final, chat_id, tmp_id)
    except: bot.send_message(chat_id, final)
    # Рассылаем курьерам
    for cid in list(couriers):
        if cid==chat_id: continue
        try:
            if with_photo:
                bot.send_photo(cid, photo_id, caption=f"📦 ЗАКАЗ С ФОТО\n{dest}\n{phone}")
            else:
                bot.send_message(cid, f"📦 ЗАКАЗ\n{dest}\n{phone}")
        except:
            couriers.discard(cid)

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    cap=(m.caption or "").strip()
    if not cap:
        bot.send_message(m.chat.id, "Добавь адрес и телефон в подпись к фото")
        return
    tmp=bot.send_message(m.chat.id, f"⏳ Принимаю фото: {cap}")
    def work():
        ph=re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', cap)
        if not ph:
            bot.edit_message_text("❌ Не нашел телефон в подписи", m.chat.id, tmp.message_id)
            return
        phone=ph.group()
        dest=cap.replace(phone,'').strip(' -:,')
        process_order(m.chat.id, dest, phone, tmp.message_id, True, m.photo[-1].file_id)
    threading.Thread(target=work, daemon=True).start()

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if not m.text or m.text.startswith('/'): return
    for line in m.text.split('\n'):
        line=line.strip()
        if len(line)<5: continue
        ph=re.search(r'(\+?996|0)?\s*\d{3}\s*\d{3}\s*\d{3,4}', line)
        if not ph: continue
        phone=ph.group()
        dest=line.replace(phone,'').strip(' -:,')
        if not dest: continue
        tmp=bot.send_message(m.chat.id, f"⏳ Принимаю: {dest}...")
        threading.Thread(target=process_order, args=(m.chat.id, dest, phone, tmp.message_id, False, None), daemon=True).start()

@app.route('/')
def home(): return f"BAGYT EXPRESS LIVE {len(active_orders)}"

def run_bot():
    bot.delete_webhook(drop_pending_updates=True)
    bot.infinity_polling(timeout=60)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
