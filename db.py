# -*- coding: utf-8 -*-
import sqlite3
from datetime import datetime, date

DB_PATH = "data/admin.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id     INTEGER PRIMARY KEY,
                username    TEXT,
                first_name  TEXT,
                last_name   TEXT,
                first_seen  TEXT,
                last_active TEXT,
                msg_count   INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id    INTEGER,
                direction  TEXT,
                text       TEXT,
                created_at TEXT
            );
        """)


def upsert_user(chat_id, username, first_name, last_name):
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (chat_id, username, first_name, last_name, first_seen, last_active, msg_count)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(chat_id) DO UPDATE SET
                username    = excluded.username,
                first_name  = excluded.first_name,
                last_name   = excluded.last_name,
                last_active = excluded.last_active,
                msg_count   = msg_count + 1
        """, (chat_id, username, first_name, last_name, now, now))


def log_message(chat_id, direction, text):
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (chat_id, direction, text, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, direction, text, now)
        )


def get_stats():
    today = date.today().isoformat()
    with get_conn() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        active_today = conn.execute(
            "SELECT COUNT(*) FROM users WHERE last_active >= ?", (today,)
        ).fetchone()[0]
        total_messages = conn.execute("SELECT COUNT(*) FROM messages WHERE direction = 'in'").fetchone()[0]
    return {"total_users": total_users, "active_today": active_today, "total_messages": total_messages}


def get_recent_messages(limit=20):
    with get_conn() as conn:
        return conn.execute("""
            SELECT m.*, u.first_name, u.username
            FROM messages m
            LEFT JOIN users u ON m.chat_id = u.chat_id
            WHERE m.direction = 'in'
            ORDER BY m.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()


def get_users():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users ORDER BY last_active DESC"
        ).fetchall()


def get_user(chat_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()


def get_messages(chat_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC",
            (chat_id,)
        ).fetchall()
