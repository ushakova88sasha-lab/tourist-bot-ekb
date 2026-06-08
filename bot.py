# -*- coding: utf-8 -*-
import json
import math
import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import anthropic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SEARCH_RADIUS_M = 400
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


def find_nearest_point(user_lat: float, user_lon: float):
    best = None
    best_dist = float("inf")
    for point in POINTS:
        dist = haversine(user_lat, user_lon, point["lat"], point["lon"])
        if dist < best_dist:
            best_dist = dist
            best = point
    if best_dist <= SEARCH_RADIUS_M:
        return best, best_dist
    return None, best_dist


def get_nearby_names(point: dict) -> list[str]:
    nearby = []
    for pid in point.get("nearby_ids", []):
        for p in POINTS:
            if p["id"] == pid:
                nearby.append(p["name"])
    return nearby


def get_or_generate_story(point: dict, nearby_names: list[str]) -> str:
    # Возвращаем кэш если есть
    if point.get("story"):
        logger.info(f"Кэш: «{point['name']}»")
        return point["story"]

    # Генерируем через Claude
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

    # Сохраняем в кэш
    point["story"] = story
    save_points()
    logger.info(f"Сохранён рассказ для «{point['name']}»")

    return story


async def send_story(update, point, distance):
    nearby_names = get_nearby_names(point)
    await update.message.reply_text("✍️ Готовлю рассказ...")
    try:
        story = get_or_generate_story(point, nearby_names)
        dist_text = f"\n\n📏 _Расстояние до точки: {int(distance)} м_"
        await update.message.reply_text(story + dist_text, parse_mode="Markdown")
        if point.get("photo_url"):
            await update.message.reply_photo(photo=point["photo_url"])
        await update.message.reply_location(latitude=point["lat"], longitude=point["lon"])
    except Exception as e:
        logger.error(f"Ошибка Claude API: {e}")
        fallback = (
            f"📍 *{point['name']}*\n\n"
            f"📜 {point['history']}\n\n"
            f"💡 {point['fact']}\n\n"
            f"📏 _Расстояние: {int(distance)} м_"
        )
        await update.message.reply_text(fallback, parse_mode="Markdown")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[KeyboardButton("📍 Отправить моё местоположение", request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Я твой гид по Екатеринбургу.\n\n"
        "Отправь мне своё местоположение — и я расскажу, "
        "что интересного находится рядом с тобой!\n\n"
        "📍 Нажми кнопку ниже или отправь геолокацию вручную.",
        reply_markup=reply_markup
    )


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_lat = update.message.location.latitude
    user_lon = update.message.location.longitude

    await update.message.reply_text("🔍 Ищу интересные места рядом с тобой...")

    point, distance = find_nearest_point(user_lat, user_lon)

    if point is None:
        await update.message.reply_text(
            f"😔 В радиусе {SEARCH_RADIUS_M} м от тебя пока нет точек в нашей базе.\n"
            "База постоянно пополняется — попробуй в другом месте центра Екатеринбурга!"
        )
        return

    await send_story(update, point, distance)


def extract_coords(text: str):
    import re
    # Google Maps URL: q=56.838036,60.603428 или ll=56.838036,60.603428
    m = re.search(r'[?&](?:q|ll)=([\d.]+)[,]([\d.]+)', text)
    if m:
        return float(m.group(1)), float(m.group(2))
    # Просто два числа через запятую или пробел
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
            await update.message.reply_text("🔍 Ищу интересные места рядом с тобой...")
            point, distance = find_nearest_point(lat, lon)
            if point is None:
                await update.message.reply_text(
                    f"😔 В радиусе {SEARCH_RADIUS_M} м пока нет точек.\n"
                    "Попробуй координаты ближе к центру Екатеринбурга!"
                )
                return
            await send_story(update, point, distance)
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
    logger.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
