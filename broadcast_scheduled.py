#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import sqlite3
import urllib.request
import urllib.parse
import json
import os
from datetime import datetime

# Читаем токен из .env
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
TOKEN = ""
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith("TELEGRAM_TOKEN="):
                TOKEN = line.split("=", 1)[1].strip()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "admin.db")

# file_id фото (уже загружено в Telegram, повторная загрузка не нужна)
PHOTO_FILE_ID = "AgACAgIAAxkDAAIBqGo8JjoQIweY6yQXfqOHUk4tllYcAAJCIGsbrJLgSU5jQtigLRYgAQADAgADeAADPAQ"

CAPTION = """🔍 Теперь бот умеет искать по адресу!
Больше не нужно делиться геолокацией — просто напиши, что ищешь:

«Цирк Екатеринбург», «Храм на Крови», «ул. Ленина 1» — и бот покажет варианты. <b>Останется только выбрать нужный</b>"""


def get_users():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    users = conn.execute("SELECT chat_id FROM users").fetchall()
    conn.close()
    return [u["chat_id"] for u in users]


def send_photo(chat_id):
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "photo": PHOTO_FILE_ID,
        "caption": CAPTION,
        "parse_mode": "HTML"
    }).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def log_message(chat_id):
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    conn.execute(
        "INSERT INTO messages (chat_id, direction, text, created_at) VALUES (?, ?, ?, ?)",
        (chat_id, "out", f"📢 [рассылка] {CAPTION}", now)
    )
    conn.commit()
    conn.close()


if not TOKEN:
    print("❌ TELEGRAM_TOKEN не найден в .env")
    sys.exit(1)

users = get_users()
print(f"Рассылка для {len(users)} пользователей — {datetime.now()}")
for chat_id in users:
    try:
        send_photo(chat_id)
        log_message(chat_id)
        print(f"✅ {chat_id}")
    except Exception as e:
        print(f"❌ {chat_id}: {e}")
