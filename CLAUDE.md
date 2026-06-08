# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Run

```bash
TELEGRAM_TOKEN=... ANTHROPIC_API_KEY=... python bot.py
```

## Architecture

Single-file bot (`bot.py`), stateless per request. `data/points.json` loaded once at startup into `POINTS` global.

**Flow:** User GPS → `handle_location` finds nearest point via Haversine within 400 m → `generate_story` calls `claude-sonnet-4-20250514` (max 700 tokens) → reply with story + map pin. On Claude API failure, falls back to raw `history`/`fact` fields.

**points.json schema:** `id`, `name`, `lat`, `lon`, `history`, `fact`, `photo_url`, `tags`, `nearby_ids` (list of related point `id`s). Restart bot after adding points.
