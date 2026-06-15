# CLAUDE.md — Турист-бот Екатеринбург

Этот файл описывает проект для Claude Code и других ИИ-агентов.

## Что за проект

Telegram-бот-гид по Екатеринбургу. Пользователь отправляет геолокацию — бот находит ближайшие достопримечательности и генерирует живые рассказы через Claude AI. Для мест, которых нет в базе, автоматически запрашивает данные у Nominatim (OpenStreetMap) и Claude, сохраняет в `points.json`.

## Запуск локально (Windows)

```bash
set TELEGRAM_TOKEN=...
set ANTHROPIC_API_KEY=...
cd D:\tourist_bot
D:\Python314\python.exe bot.py
```

Админка отдельно:
```bash
D:\Python314\python.exe admin.py
```

## Запуск на VPS (production)

Код: `/root/tourist-bot-ekb/`  
Токены: `/root/tourist-bot-ekb/.env`

```bash
systemctl restart tourist_bot        # перезапустить бот
systemctl restart tourist_admin      # перезапустить админку
journalctl -u tourist_bot -f         # логи в реальном времени
```

После `git pull` — всегда делать `systemctl restart tourist_bot tourist_admin`.

## Архитектура

```
bot.py          — весь код бота (один файл, stateless per request)
admin.py        — Flask веб-админка (порт 5000)
db.py           — SQLite хелпер (логирование пользователей и сообщений)
data/
  points.json   — база достопримечательностей, грузится в POINTS при старте
  admin.db      — SQLite: таблицы users, messages
  sessions.pkl  — сессии python-telegram-bot (PicklePersistence)
  bot.log       — лог бота
```

## Поток обработки геолокации

1. `handle_location` / `handle_text` (координаты текстом) → `handle_coords`
2. `find_nearest_points(lat, lon, n=3)` — Хаверсин, ищет в радиусе `SEARCH_RADIUS_M = 1500 м`
3. **Если точки найдены** → `show_place` для каждой с кнопками ◀/▶ (навигация через `handle_nav`)
4. `get_or_generate_story(point, nearby_names)` — проверяет `point["story"]` (кэш), если нет — генерирует через Claude (max 700 tokens), сохраняет в `points.json`
5. **Если точек нет в радиусе** → `add_new_point(lat, lon)`:
   - `reverse_geocode(lat, lon)` — запрос к Nominatim, возвращает название на русском
   - `generate_point_data(lat, lon, name)` — запрос к Claude, возвращает JSON `{name, history, fact}`
   - Новая точка сохраняется в `points.json` с тегом `ai-generated`
   - Повторный запрос тех же координат — берёт из кэша, Claude не вызывается
6. Fallback: если Claude недоступен — отправляет сырые `history` + `fact` из базы

## Схема points.json

```json
{
  "id": 1,
  "name": "Площадь 1905 года",
  "lat": 56.83892,
  "lon": 60.60572,
  "history": "Историческая справка...",
  "fact": "Интересный факт...",
  "photo_url": "https://upload.wikimedia.org/...",
  "tags": ["площадь", "история"],
  "nearby_ids": [2, 3, 6],
  "story": "Кэшированный рассказ от Claude (добавляется при первом запросе)"
}
```

- `story` — добавляется автоматически при первой генерации, не трогать вручную
- `nearby_ids` — id соседних точек, упоминаются в рассказе
- `photo_url` — прямая ссылка на фото (Wikimedia или пусто)
- Точки с тегом `ai-generated` созданы автоматически через Nominatim + Claude

**После добавления точек вручную — перезапустить бота** (`POINTS` грузится один раз при старте).

## Переменные окружения

| Переменная | Описание |
|---|---|
| `TELEGRAM_TOKEN` | Токен бота от @BotFather |
| `ANTHROPIC_API_KEY` | Ключ Anthropic API |
| `ADMIN_LOGIN` | Логин админки (по умолчанию: admin) |
| `ADMIN_PASSWORD` | Пароль админки (по умолчанию: admin) |

## Модель Claude

`claude-sonnet-4-20250514` — используется для генерации рассказов и данных о новых точках.

## Зависимости

```
python-telegram-bot==22.7
anthropic>=0.28.0
flask>=3.0.0
```

`urllib.request` — stdlib, без установки (для Nominatim).

## Команды бота

- `/start` — приветствие
- `/mesto` — показать кнопку геолокации

## Важные детали

- `POINTS` — глобальный список, обновляется в памяти при `add_new_point`, одновременно пишется в `points.json`
- `save_points()` — перезаписывает весь `points.json` (не append)
- Nominatim требует `User-Agent` заголовок и timeout=5s
- Сессии пользователей (`context.user_data["places"]`) хранят список `(point_id, distance)` для навигации ◀/▶
