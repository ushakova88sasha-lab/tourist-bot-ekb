# -*- coding: utf-8 -*-
import json
import math
import os
import re
import logging
import urllib.request
import urllib.parse
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, PicklePersistence
)
import requests
import db

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bot.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
YANDEX_API_KEY = os.environ.get("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.environ.get("YANDEX_FOLDER_ID", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "84822852"))

SEARCH_RADIUS_M = 1500
CURRENT_PLACE_RADIUS_M = 100
POINTS_FILE = "data/points.json"

with open(POINTS_FILE, "r", encoding="utf-8") as f:
    POINTS = json.load(f)


def save_points():
    with open(POINTS_FILE, "w", encoding="utf-8") as f:
        json.dump(POINTS, f, ensure_ascii=False, indent=2)


def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def find_nearest_points(user_lat: float, user_lon: float, n: int = 3):
    results = [(point, haversine(user_lat, user_lon, point["lat"], point["lon"])) for point in POINTS]
    results.sort(key=lambda x: x[1])
    nearby = [(p, d) for p, d in results if d <= SEARCH_RADIUS_M]
    return nearby[:n] if nearby else results[:n]


def get_nearby_names(point: dict) -> list[str]:
    nearby = []
    for pid in point.get("nearby_ids", []):
        for p in POINTS:
            if p["id"] == pid:
                nearby.append(p["name"])
    return nearby


def reverse_geocode(lat: float, lon: float) -> str:
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&accept-language=ru"
    req = urllib.request.Request(url, headers={"User-Agent": "TouristBot/1.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read())
    address = data.get("address", {})
    name = (
        data.get("name")
        or address.get("road")
        or data.get("display_name", "неизвестное место")
    )
    city = address.get("city") or address.get("town") or address.get("village") or ""
    if city and city not in name:
        name = f"{name}, {city}"
    return name


def geocode_address(query: str) -> list:
    url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(query)}&format=json&limit=3&accept-language=ru&addressdetails=1"
    req = urllib.request.Request(url, headers={"User-Agent": "TouristBot/1.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        results = json.loads(resp.read())
    output = []
    for r in results[:3]:
        addr = r.get("address", {})
        name = (r.get("name") or addr.get("name") or addr.get("road") or r.get("display_name", "").split(",")[0]).strip()
        city = addr.get("city") or addr.get("town") or addr.get("village") or ""
        short = f"{name}, {city}" if city and city not in name else name
        output.append({"name": short, "lat": float(r["lat"]), "lon": float(r["lon"])})
    return output


SEARCH_INSTRUCTIONS = (
    "Попробуй написать точнее, например:\n\n"
    "• Цирк Екатеринбург\n"
    "• улица Ленина 1, Екатеринбург\n"
    "• Храм на Крови Екатеринбург\n\n"
    "Или нажми кнопку ниже и отправь геолокацию 👇"
)


class YandexQuotaError(Exception):
    pass


def yandex_gpt(prompt: str) -> str:
    response = requests.post(
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        headers={"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"},
        json={
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"stream": False, "temperature": 0.7, "maxTokens": "1000"},
            "messages": [{"role": "user", "text": prompt}]
        },
        timeout=30
    )
    if response.status_code == 429 or (response.status_code == 402):
        raise YandexQuotaError("Лимит токенов YandexGPT исчерпан")
    response.raise_for_status()
    return response.json()["result"]["alternatives"][0]["message"]["text"]


def generate_point_data(lat: float, lon: float, place_name: str) -> dict:
    prompt = f"""Ты — гид по городам России. Нужна информация о месте.

Название: {place_name}
Координаты: {lat}, {lon}

Важно:
- Пиши только то, в чём абсолютно уверен
- НЕ указывай конкретные даты и годы, если не уверен на 100% — лучше вообще не упоминать год
- НЕ упоминай магазины, ТЦ, кафе или жилые здания
- Лучше написать меньше, но достоверно

Верни только JSON, без пояснений:
{{
  "name": "точное красивое название места",
  "history": "история этого места, 2-3 предложения — без конкретных дат если не уверен",
  "fact": "интересный факт об этом месте, 1-2 предложения — без конкретных дат если не уверен"
}}"""

    text = yandex_gpt(prompt).strip()
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    raise ValueError(f"Gemini не вернул JSON: {text}")


def add_new_point(lat: float, lon: float) -> dict | None:
    try:
        place_name = reverse_geocode(lat, lon)
        logger.info(f"Nominatim: «{place_name}» для {lat}, {lon}")
        data = generate_point_data(lat, lon, place_name)
        new_id = max((p["id"] for p in POINTS), default=0) + 1
        point = {
            "id": new_id,
            "name": data.get("name", place_name),
            "lat": lat,
            "lon": lon,
            "history": data.get("history", ""),
            "fact": data.get("fact", ""),
            "photo_url": "",
            "tags": ["ai-generated"],
            "nearby_ids": []
        }
        POINTS.append(point)
        save_points()
        logger.info(f"Новая точка #{new_id} добавлена: «{point['name']}»")
        return point
    except Exception as e:
        logger.error(f"Ошибка генерации новой точки: {e}")
        return None


def get_or_generate_story(point: dict, nearby_names: list[str]) -> str:
    if point.get("story"):
        logger.info(f"Кэш: «{point['name']}»")
        return point["story"]

    nearby_str = ", ".join(nearby_names) if nearby_names else ""

    nearby_block = f"\n4. 🗺 **Рядом стоит посетить:** {nearby_str}" if nearby_str else ""
    prompt = f"""Ты — эрудированный и увлечённый местный гид, который рассказывает другу о достопримечательностях. Пользователь сейчас находится у места "{point['name']}".

Напиши для Telegram-бота живой, детальный и увлекательный текст (до 350 слов).

У тебя есть базовые вводные:
- Историческая справка: {point['history']}
- Интересный факт: {point['fact']}

ИНСТРУКЦИЯ ПО НАПОЛНЕНИЮ ФАКТАМИ:
Если это место богато историей, а вводные данные слишком короткие или обобщённые, тебе ЗАПРЕЩЕНО писать "воду" и общие фразы.
Используй свои энциклопедические знания об этом объекте! Добавь в текст конкретные исторические детали: реальные даты, имена связанных с ним исторических личностей, конкретные названия событий или произведений (например, если это Дом Чайковского — назови конкретные симфонии или оперы, напиши, в какие годы он тут жил). Рассказ должен быть информативным и глубоким.

Соблюдай структуру:
1. 📍 **{point['name']}** — одно яркое, цепляющее предложение.
2. 📜 **История места:** Увлекательный исторический экскурс. Напиши его простым языком, но с обилием реальных исторических фактов (4–6 предложений).
3. 💡 **Интересный факт:** 1-2 предложения с действительно цепляющим, конкретным фактом.{nearby_block}

Стиль: Теплый, дружеский, без экскурсионного официоза и канцелярита, но при этом исторически точный и содержательный. Используй Markdown для жирного шрифта."""

    story = yandex_gpt(prompt)
    point["story"] = story
    save_points()
    logger.info(f"Сохранён рассказ для «{point['name']}»")
    return story


LOCATION_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("📍 Указать моё место расположения", request_location=True)]],
    resize_keyboard=True
)


def make_nav_keyboard(idx: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    if idx > 0:
        buttons.append(InlineKeyboardButton("◀ Назад", callback_data=f"nav_{idx - 1}"))
    if idx < total - 1:
        buttons.append(InlineKeyboardButton("Вперёд ▶", callback_data=f"nav_{idx + 1}"))
    return InlineKeyboardMarkup([buttons])


async def show_place(message, context, point, distance, idx, total):
    chat_id = message.chat_id
    nearby_names = get_nearby_names(point)
    typing_msg = await message.reply_text("✍️ Готовлю рассказ...")
    story = None
    try:
        story = get_or_generate_story(point, nearby_names)
    except YandexQuotaError as e:
        logger.error(f"Лимит YandexGPT: {e}")
        try:
            await context.bot.send_message(OWNER_ID, "⚠️ Лимит токенов YandexGPT исчерпан! Нужно пополнить баланс.")
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Ошибка YandexGPT: {e}")

    try:
        await typing_msg.delete()
    except Exception:
        pass

    if story:
        dist_text = f"\n\n📏 От тебя до этого места: {int(distance)} м"
        if "ai-generated" in point.get("tags", []):
            dist_text += "\n\n⚠️ _Информация сгенерирована ИИ._"
        await message.reply_text(story + dist_text, parse_mode="Markdown")
        db.log_message(chat_id, "out", story + dist_text)
        if point.get("photo_url"):
            await message.reply_photo(photo=point["photo_url"])
            db.log_message(chat_id, "out", f"🖼 Фото: {point['name']}")
    else:
        fallback = (
            f"📍 {point['name']}\n\n"
            f"📜 {point['history']}\n\n"
            f"💡 {point['fact']}\n\n"
            f"📏 От тебя до этого места: {int(distance)} м"
        )
        await message.reply_text(fallback)
        db.log_message(chat_id, "out", fallback)

    nav = make_nav_keyboard(idx, total)
    nav_buttons = " ".join(
        btn.text for row in nav.inline_keyboard for btn in row
    ) if nav.inline_keyboard else ""
    nav_text = f"📍 {point['name']}" if total == 1 else f"📍 {point['name']} — место {idx + 1} из {total}"
    await message.reply_text(nav_text, reply_markup=nav)
    db.log_message(chat_id, "out", nav_text + (f"  [{nav_buttons}]" if nav_buttons else ""))


async def show_current_place(message, context, point, distance, nearby_count):
    chat_id = message.chat_id
    nearby_names = get_nearby_names(point)
    typing_msg = await message.reply_text("✍️ Готовлю рассказ...")
    story = None
    try:
        story = get_or_generate_story(point, nearby_names)
    except YandexQuotaError as e:
        logger.error(f"Лимит YandexGPT: {e}")
        try:
            await context.bot.send_message(OWNER_ID, "⚠️ Лимит токенов YandexGPT исчерпан! Нужно пополнить баланс.")
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Ошибка YandexGPT: {e}")

    try:
        await typing_msg.delete()
    except Exception:
        pass

    if story:
        dist_text = f"\n\n📏 От тебя: {int(distance)} м" if distance > 0 else ""
        if "ai-generated" in point.get("tags", []):
            dist_text += "\n\n⚠️ _Информация сгенерирована ИИ._"
        await message.reply_text(story + dist_text, parse_mode="Markdown")
        db.log_message(chat_id, "out", story + dist_text)
        if point.get("photo_url"):
            await message.reply_photo(photo=point["photo_url"])
            db.log_message(chat_id, "out", f"🖼 Фото: {point['name']}")
    else:
        fallback = f"📍 {point['name']}\n\n📜 {point['history']}\n\n💡 {point['fact']}"
        if distance > 0:
            fallback += f"\n\n📏 От тебя: {int(distance)} м"
        await message.reply_text(fallback)
        db.log_message(chat_id, "out", fallback)

    if nearby_count > 0:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"🗺 Интересные места рядом ({nearby_count})", callback_data="nav_0")]])
        nav_text = f"📍 {point['name']}"
        await message.reply_text(nav_text, reply_markup=kb)
        db.log_message(chat_id, "out", f"{nav_text}  [Интересные места рядом ({nearby_count})]")
    else:
        nav_text = f"📍 {point['name']}"
        await message.reply_text(nav_text)
        db.log_message(chat_id, "out", nav_text)


async def process_coords(message, uid, context, lat, lon):
    searching_msg = await message.reply_text("🔍 Определяю место...", reply_markup=LOCATION_KEYBOARD)
    all_nearby = find_nearest_points(lat, lon)
    current_point = None
    current_dist = 0

    if all_nearby and all_nearby[0][1] <= CURRENT_PLACE_RADIUS_M:
        current_point, current_dist = all_nearby[0]
        other_nearby = [(p, d) for p, d in all_nearby if d <= SEARCH_RADIUS_M and p["id"] != current_point["id"]]
    else:
        try:
            await searching_msg.edit_text("🌐 Узнаю о месте у ИИ...")
        except Exception:
            pass
        current_point = add_new_point(lat, lon)
        other_nearby = [(p, d) for p, d in all_nearby if d <= SEARCH_RADIUS_M]
        if not current_point:
            if other_nearby:
                current_point, current_dist = other_nearby[0]
                other_nearby = other_nearby[1:]
            else:
                reply = "😔 Не удалось определить место. Попробуй ещё раз!"
                await message.reply_text(reply)
                db.log_message(uid, "out", reply)
                try:
                    await searching_msg.delete()
                except Exception:
                    pass
                return

    context.user_data["places"] = [(p["id"], int(d)) for p, d in other_nearby]
    try:
        await searching_msg.delete()
    except Exception:
        pass
    await show_current_place(message, context, current_point, current_dist, len(other_nearby))


async def handle_coords(update, context, lat, lon):
    await process_coords(update.message, update.effective_user.id, context, lat, lon)


async def handle_address_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id

    if query.data == "addr_none":
        await query.edit_message_text(SEARCH_INSTRUCTIONS, reply_markup=None)
        db.log_message(uid, "out", SEARCH_INSTRUCTIONS)
        return

    idx = int(query.data.split("_")[1])
    results = context.user_data.get("geocode_results", [])
    if not results or idx >= len(results):
        await query.edit_message_text("Сессия устарела — напиши адрес заново.")
        return

    r = results[idx]
    db.log_message(uid, "in", f"[выбрал адрес: {r['name']}]")
    await query.edit_message_reply_markup(reply_markup=None)
    await process_coords(query.message, uid, context, r["lat"], r["lon"])


async def handle_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    _log_user(update)

    idx = int(query.data.split("_")[1])
    places = context.user_data.get("places")
    db.log_message(uid, "in", f"[кнопка навигации → место {idx + 1}]")

    if not places:
        await query.edit_message_text("Сессия устарела — отправь геолокацию заново.")
        return

    point_id, distance = places[idx]
    point = next((p for p in POINTS if p["id"] == point_id), None)
    if not point:
        return

    # Убираем кнопки со старого сообщения
    await query.edit_message_reply_markup(reply_markup=None)

    await show_place(query.message, context, point, distance, idx, len(places))


def _log_user(update: Update):
    u = update.effective_user
    if u:
        db.upsert_user(u.id, u.username, u.first_name, u.last_name)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_user(update)
    uid = update.effective_user.id
    db.log_message(uid, "in", "/start")
    text = ("Привет! 👋\n\n"
            "Я твой гид по интересным местам.\n\n"
            "Отправь мне своё местоположение — и я расскажу, "
            "что интересного находится рядом с тобой!\n\n"
            "📱 Нажми кнопку ниже или отправь геолокацию вручную.\n\n"
            "⚠️ Геолокация работает только со смартфона — с компьютера отправить её не получится.")
    await update.message.reply_text(text, reply_markup=LOCATION_KEYBOARD)
    db.log_message(uid, "out", text)


async def cmd_place(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_user(update)
    uid = update.effective_user.id
    db.log_message(uid, "in", "/mesto")
    reply = "📍 Отправь своё местоположение — нажми синюю кнопку ниже:"
    await update.message.reply_text(reply, reply_markup=LOCATION_KEYBOARD)
    db.log_message(uid, "out", reply)


async def cmd_broadcast_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != OWNER_ID:
        return
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Использование: /broadcast_me Текст сообщения")
        return
    await context.bot.send_message(OWNER_ID, text)
    db.log_message(OWNER_ID, "out", f"📢 [рассылка] {text}")
    await update.message.reply_text("✅ Отправлено тебе — проверяй!")


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != OWNER_ID:
        return
    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text("Использование: /broadcast Текст сообщения")
        return
    users = db.get_users()
    sent, failed = 0, 0
    for u in users:
        try:
            await context.bot.send_message(u["chat_id"], text)
            db.log_message(u["chat_id"], "out", f"📢 [рассылка] {text}")
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ Отправлено: {sent}\n❌ Ошибок: {failed}")


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_user(update)
    lat = update.message.location.latitude
    lon = update.message.location.longitude
    db.log_message(update.effective_user.id, "in", f"📍 Геолокация: {lat}, {lon}")
    await handle_coords(update, context, lat, lon)


def extract_coords(text: str):
    m = re.search(r'[?&](?:q|ll)=([\d.]+)[,]([\d.]+)', text)
    if m:
        return float(m.group(1)), float(m.group(2))
    parts = text.replace(",", " ").split()
    if len(parts) == 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            pass
    return None, None


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_user(update)
    text = update.message.text.strip()
    db.log_message(update.effective_user.id, "in", text)

    if "Указать моё место расположения" in text:
        reply = (
            "📍 Чтобы поделиться геолокацией:\n\n"
            "📱 *На телефоне:* нажми синюю кнопку внизу → подтверди в диалоге\n"
            "💻 *На компьютере:* нажми скрепку 📎 → Геопозиция → выбери место → Отправить\n\n"
            "Или просто напиши координаты: _56.841500, 60.604300_"
        )
        await update.message.reply_text(reply, reply_markup=LOCATION_KEYBOARD, parse_mode="Markdown")
        db.log_message(update.effective_user.id, "out", reply)
        return

    try:
        lat, lon = extract_coords(text)
        if lat is not None and 55 < lat < 58 and 59 < lon < 62:
            await handle_coords(update, context, lat, lon)
            return
    except ValueError:
        pass

    # Поиск по введённому адресу через Nominatim
    try:
        results = geocode_address(text)
    except Exception as e:
        logger.error(f"geocode_address error: {e}")
        results = []

    uid = update.effective_user.id

    if not results:
        await update.message.reply_text(SEARCH_INSTRUCTIONS, reply_markup=LOCATION_KEYBOARD)
        db.log_message(uid, "out", SEARCH_INSTRUCTIONS)
        return

    context.user_data["geocode_results"] = results
    buttons = [
        [InlineKeyboardButton(r["name"], callback_data=f"addr_{i}")]
        for i, r in enumerate(results)
    ]
    buttons.append([InlineKeyboardButton("❌ Не то", callback_data="addr_none")])
    reply = "Нашла несколько вариантов — выбери нужный:"
    await update.message.reply_text(reply, reply_markup=InlineKeyboardMarkup(buttons))
    db.log_message(uid, "out", reply)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_user(update)
    uid = update.effective_user.id
    file_id = update.message.photo[-1].file_id
    caption = update.message.caption or ""
    db.log_message(uid, "in", f"📷:{file_id}" + (f":{caption}" if caption else ""))
    reply = "📍 Отправь мне геолокацию — расскажу что интересного рядом!\nИспользуй кнопку внизу или скрепку → Геопозиция."
    await update.message.reply_text(reply, reply_markup=LOCATION_KEYBOARD)
    db.log_message(uid, "out", reply)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_user(update)
    uid = update.effective_user.id
    name = update.message.document.file_name or "файл"
    db.log_message(uid, "in", f"📎 Файл: {name}")
    reply = "📍 Отправь мне геолокацию — расскажу что интересного рядом!\nИспользуй кнопку внизу или скрепку → Геопозиция."
    await update.message.reply_text(reply, reply_markup=LOCATION_KEYBOARD)
    db.log_message(uid, "out", reply)


async def handle_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _log_user(update)
    uid = update.effective_user.id
    db.log_message(uid, "in", "🎭 Стикер")
    reply = "📍 Отправь мне геолокацию — расскажу что интересного рядом!"
    await update.message.reply_text(reply, reply_markup=LOCATION_KEYBOARD)
    db.log_message(uid, "out", reply)


async def post_init(app):
    db.init_db()
    await app.bot.set_my_commands([
        BotCommand("mesto", "Указать моё место расположения"),
    ])


def main():
    persistence = PicklePersistence(filepath="data/sessions.pkl")
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .persistence(persistence)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mesto", cmd_place))
    app.add_handler(CommandHandler("broadcast_me", cmd_broadcast_me))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_address_choice, pattern=r"^addr_"))
    app.add_handler(CallbackQueryHandler(handle_nav, pattern=r"^nav_"))
    logger.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
