# -*- coding: utf-8 -*-
import json
import math
import os
import re
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SEARCH_RADIUS_M = 1500
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
    results = []
    for point in POINTS:
        dist = haversine(user_lat, user_lon, point["lat"], point["lon"])
        if dist <= SEARCH_RADIUS_M:
            results.append((point, dist))
    results.sort(key=lambda x: x[1])
    return results[:n]


def get_nearby_names(point: dict) -> list[str]:
    nearby = []
    for pid in point.get("nearby_ids", []):
        for p in POINTS:
            if p["id"] == pid:
                nearby.append(p["name"])
    return nearby


def get_or_generate_story(point: dict, nearby_names: list[str]) -> str:
    if point.get("story"):
        logger.info(f"Кэш: «{point['name']}»")
        return point["story"]

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    nearby_str = ", ".join(nearby_names) if nearby_names else "нет данных"

    prompt = f"""Ты — увлечённый гид по Екатеринбургу. Пользователь только что пришёл к месту "{point['name']}".

Данные о месте:
- Историческая справка: {point['history']}
- Интересный факт: {point['fact']}
- Рядом находятся: {nearby_str}

Напиши живой, увлекательный текст для Telegram-бота (не более 350 слов). Структура:
1. 📍 **{point['name']}** — одно яркое вводное предложение
2. 📜 Историческая справка (2-3 предложения, живым языком)
3. 💡 Интересный факт (1-2 предложения)
4. 🗺 Рядом стоит посетить: перечисли ближайшие места одной строкой

Пиши тепло, как будто рассказываешь другу. Не используй казённый стиль."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=700,
        messages=[{"role": "user", "content": prompt}]
    )
    story = message.content[0].text
    point["story"] = story
    save_points()
    logger.info(f"Сохранён рассказ для «{point['name']}»")
    return story


LOCATION_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("📍 Указать новое место", request_location=True)]],
    resize_keyboard=True
)


def make_nav_keyboard(idx: int, total: int) -> InlineKeyboardMarkup:
    buttons = []
    if idx > 0:
        buttons.append(InlineKeyboardButton("◀ Назад", callback_data=f"nav_{idx - 1}"))
    buttons.append(InlineKeyboardButton(f"{idx + 1} / {total}", callback_data="noop"))
    if idx < total - 1:
        buttons.append(InlineKeyboardButton("Вперёд ▶", callback_data=f"nav_{idx + 1}"))
    return InlineKeyboardMarkup([buttons])


async def show_place(message, context, point, distance, idx, total):
    nearby_names = get_nearby_names(point)
    await message.reply_text("✍️ Готовлю рассказ...")
    try:
        story = get_or_generate_story(point, nearby_names)
        dist_text = f"\n\n📏 _Расстояние: {int(distance)} м_"
        await message.reply_text(story + dist_text, parse_mode="Markdown")
        if point.get("photo_url"):
            await message.reply_photo(photo=point["photo_url"])
        await message.reply_location(latitude=point["lat"], longitude=point["lon"])
    except Exception as e:
        logger.error(f"Ошибка Claude API: {e}")
        await message.reply_text(
            f"📍 *{point['name']}*\n\n"
            f"📜 {point['history']}\n\n"
            f"💡 {point['fact']}\n\n"
            f"📏 _Расстояние: {int(distance)} м_",
            parse_mode="Markdown"
        )

    nav_text = f"📍 *{point['name']}* — место {idx + 1} из {total}"
    if idx + 1 == total:
        await message.reply_text(nav_text, reply_markup=make_nav_keyboard(idx, total), parse_mode="Markdown")
        await message.reply_text("Хочешь узнать о другом месте?", reply_markup=LOCATION_KEYBOARD)
    else:
        await message.reply_text(nav_text, reply_markup=make_nav_keyboard(idx, total), parse_mode="Markdown")


async def handle_coords(update, context, lat, lon):
    await update.message.reply_text("🔍 Ищу интересные места рядом с тобой...")
    places = find_nearest_points(lat, lon)
    if not places:
        await update.message.reply_text(
            f"😔 В радиусе {SEARCH_RADIUS_M} м от тебя пока нет точек.\n"
            "Попробуй в другом месте центра Екатеринбурга!"
        )
        return

    # Сохраняем список в сессии пользователя
    context.user_data["places"] = [(p["id"], int(dist)) for p, dist in places]

    point, distance = places[0]
    await show_place(update.message, context, point, distance, 0, len(places))


async def handle_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "noop":
        return

    idx = int(query.data.split("_")[1])
    places = context.user_data.get("places")

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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Я твой гид по Екатеринбургу.\n\n"
        "Отправь мне своё местоположение — и я расскажу, "
        "что интересного находится рядом с тобой!\n\n"
        "📍 Нажми кнопку ниже или отправь геолокацию вручную.",
        reply_markup=LOCATION_KEYBOARD
    )


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_coords(update, context, update.message.location.latitude, update.message.location.longitude)


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
    text = update.message.text.strip()
    try:
        lat, lon = extract_coords(text)
        if lat is not None and 55 < lat < 58 and 59 < lon < 62:
            await handle_coords(update, context, lat, lon)
            return
    except ValueError:
        pass

    await update.message.reply_text(
        "📍 Отправь мне своё местоположение, и я расскажу, что рядом!\n"
        "Используй кнопку внизу или скрепку → Геопозиция.\n\n"
        "Или просто напиши координаты: _56.841500, 60.604300_",
        parse_mode="Markdown"
    )


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_nav))
    logger.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
