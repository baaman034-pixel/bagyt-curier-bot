import os, threading
import telebot
from flask import Flask
from geopy.geocoders import Nominatim

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
geolocator = Nominatim(user_agent="bagyt-bishkek-bot-v2")

CITY = "Бишкек, Кыргызстан"
DEFAULT_FROM = "Дордой мир обуви"

# Список курьеров (кто включил трансляцию)
couriers = set()

def check_address(text):
    try:
        if len(text.strip()) < 3:
            return False
        loc = geolocator.geocode(f"{text}, {CITY}", timeout=10)
        return bool(loc)
    except:
        return False

@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, 
        f"🚚 BAGYT COURIER\n📦 Точка: {DEFAULT_FROM}\n\n"
        "Для курьеров: включи 📍 Трансляция геопозиции\n"
        "Для отправки заказа: пришли адрес + номер\n"
        "Можно с фото: фото + подпись с адресом")

# Курьер включил геопозицию - запоминаем его
@bot.message_handler(content_types=['location', 'live_location'])
def handle_location(m):
    couriers.add(m.chat.id)
    bot.send_message(m.chat.id, f"✅ Ты в сети! Получишь заказы с {DEFAULT_FROM}\nКурьеров онлайн: {len(couriers)}")

def process_order(dest, phone, photo_file_id=None, photo_caption_extra=""):
    is_found = check_address(dest)
    status = "нашел ✅" if is_found else "принят ⚠️"
    
    order_text = (
        f"✅ Заказ принят\n"
        f"📦 Откуда: {DEFAULT_FROM}\n"
        f"📍 Куда: {dest} - {status}\n"
        f"📞 Клиент: {phone}\n\n"
        f"Тест для {phone}: Через 10 мин - {phone}\n\n"
        f"📍 Курьеры получили заказ!"
    )
    
    courier_text = (
        f"🔥 НОВЫЙ ЗАКАЗ!\n"
        f"📦 Откуда: {DEFAULT_FROM}\n"
        f"📍 Куда: {dest}\n"
        f"📞 Клиент: {phone}\n"
        f"🗺️ {dest}, Бишкек"
    )
    
    return order_text, courier_text

@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    caption = (m.caption or "").strip()
    photo_id = m.photo[-1].file_id
    
    if not caption:
        bot.send_message(m.chat.id, "📸 Фото есть! Теперь добавь в подпись к фото адрес и номер:\nВосток 5 12 0550997099")
        return

    # Разбираем подпись как обычный заказ
    parts = caption.rsplit(' ', 1)
    if len(parts) == 2 and any(c.isdigit() for c in parts[1]) and len(parts[1]) >= 7:
        dest = parts[0]
        phone = parts[1]
    else:
        dest = caption
        phone = "клиент"

    # Убираем "Дордой до"
    if "дордой" in dest.lower() and " до " in dest.lower():
        dest = caption.lower().split(" до ")[-1].split(phone)[0].strip() if phone != "клиент" else caption.lower().split(" до ")[-1].strip()
        # берем оригинал после " до "
        idx = caption.lower().rfind(" до ")
        dest = caption[idx+4:].replace(phone, "").strip() if phone != "клиент" else caption[idx+4:].strip()

    order_text, courier_text = process_order(dest, phone, photo_id)
    
    # Отвечаем тебе
    bot.send_message(m.chat.id, order_text)
    bot.send_photo(m.chat.id, photo_id, caption=f"📸 Фото заказа сохранено\n{order_text}")

    # Рассылаем курьерам
    for courier_id in list(couriers):
        if courier_id == m.chat.id:
            continue
        try:
           
