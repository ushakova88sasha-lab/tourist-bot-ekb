# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run

```bash
TELEGRAM_TOKEN=... ANTHROPIC_API_KEY=... python bot.py
```

Python is at `D:\Python314\python.exe` on this machine.

## Architecture

Single-file bot (`bot.py`), stateless per request. `data/points.json` loaded once at startup into `POINTS` global.

**Flow:** User sends GPS location, text coords (`56.84, 60.60`), or Google Maps URL → `extract_coords` / `handle_location` finds nearest point via Haversine within 400 m → `get_or_generate_story` checks `point["story"]` cache, generates via `claude-sonnet-4-20250514` (max 700 tokens) if missing and saves back to JSON → reply with story + photo (if `photo_url` set) + map pin. On Claude API failure, falls back to raw `history`/`fact` fields.

**Story cache:** Generated stories are saved to `points.json` under `"story"` key. Claude is called at most once per point.

**points.json schema:** `id`, `name`, `lat`, `lon`, `history`, `fact`, `photo_url` (Wikimedia URL or empty), `tags`, `nearby_ids` (list of related point `id`s), `story` (cached, added at runtime). Restart bot after adding points.
