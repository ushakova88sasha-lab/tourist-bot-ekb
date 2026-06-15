# Турист-бот Екатеринбург

Telegram-бот-гид по Екатеринбургу. Пользователь отправляет геолокацию — бот находит до 3 ближайших достопримечательностей и генерирует живые рассказы через Claude AI.

Для мест, которых нет в базе, бот автоматически запрашивает данные у Nominatim (OpenStreetMap) и Claude, сохраняет в базу — и при следующем запросе отвечает мгновенно из кэша.

---

## Возможности

- Геолокация, текстовые координаты (`56.841500, 60.604300`) и ссылки Google Maps
- 3 ближайших места с навигацией ◀/▶
- Рассказы генерируются один раз и кэшируются в `points.json`
- Фото места + пин на карте
- **Авто-генерация новых точек**: неизвестное место → Nominatim → Claude → сохраняется в базу
- Веб-админка: пользователи, диалоги, статистика
- Работает 24/7 на VPS через systemd

---

## Технологии

- Python 3.12+
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) 22.7
- [Anthropic Claude API](https://docs.anthropic.com) (claude-sonnet-4-20250514)
- Flask (веб-админка)
- SQLite (логирование)
- Nominatim / OpenStreetMap (обратное геокодирование)

---

## Структура проекта

```
├── bot.py              # Весь код бота
├── admin.py            # Flask веб-админка (порт 5000)
├── db.py               # SQLite хелпер
├── requirements.txt    # Зависимости
├── CLAUDE.md           # Документация для ИИ-агентов
├── templates/          # HTML-шаблоны админки (Bootstrap 5)
└── data/
    ├── points.json     # База достопримечательностей
    ├── admin.db        # SQLite: пользователи и сообщения
    ├── sessions.pkl    # Сессии бота
    └── bot.log         # Лог
```

---

## Установка на VPS (Ubuntu)

```bash
git clone https://github.com/ushakova88sasha-lab/tourist-bot-ekb.git /root/tourist-bot-ekb
cd /root/tourist-bot-ekb
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Создай файл с токенами:
```bash
nano /root/tourist-bot-ekb/.env
```
```
TELEGRAM_TOKEN=токен_от_BotFather
ANTHROPIC_API_KEY=ключ_от_Anthropic
```

Создай systemd-сервисы:
```bash
cat > /etc/systemd/system/tourist_bot.service << 'EOF'
[Unit]
Description=Tourist Bot Ekb
After=network.target

[Service]
WorkingDirectory=/root/tourist-bot-ekb
EnvironmentFile=/root/tourist-bot-ekb/.env
ExecStart=/root/tourist-bot-ekb/venv/bin/python3 bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/tourist_admin.service << 'EOF'
[Unit]
Description=Tourist Bot Admin Panel
After=network.target

[Service]
WorkingDirectory=/root/tourist-bot-ekb
EnvironmentFile=/root/tourist-bot-ekb/.env
ExecStart=/root/tourist-bot-ekb/venv/bin/python3 admin.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable tourist_bot tourist_admin
systemctl start tourist_bot tourist_admin
```

---

## Обновление кода

```bash
cd /root/tourist-bot-ekb
git pull
systemctl restart tourist_bot tourist_admin
```

---

## Добавить новую точку вручную

Добавь объект в `data/points.json` и перезапусти бота:

```json
{
  "id": 31,
  "name": "Название места",
  "lat": 56.XXXXX,
  "lon": 60.XXXXX,
  "history": "Историческая справка...",
  "fact": "Интересный факт...",
  "photo_url": "https://...",
  "tags": ["тег"],
  "nearby_ids": [1, 2]
}
```

---

## Переменные окружения

| Переменная | Описание |
|---|---|
| `TELEGRAM_TOKEN` | Токен от @BotFather |
| `ANTHROPIC_API_KEY` | Ключ Anthropic API |
| `ADMIN_LOGIN` | Логин админки (по умолчанию: admin) |
| `ADMIN_PASSWORD` | Пароль админки (по умолчанию: admin) |
