# -*- coding: utf-8 -*-
import os
import re
import json
import html as html_lib
import urllib.request
import urllib.parse
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, Response
import db

app = Flask(__name__)
app.secret_key = os.environ.get("ADMIN_SECRET", "change-me-in-production")

ADMIN_LOGIN    = os.environ.get("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
BOT_NAME       = os.environ.get("BOT_NAME", "Турист-бот Екатеринбург")
OWNER_ID       = int(os.environ.get("OWNER_ID", "84822852"))


@app.template_filter("format_msg")
def format_msg(text):
    safe = html_lib.escape(text)
    # Render [button text] as visual chips
    def btn_chip(m):
        label = m.group(1)
        return (
            f'<span style="display:inline-block;background:#e8f0fe;border:1px solid #c5d5f5;'
            f'border-radius:6px;padding:2px 10px;font-size:12px;color:#3c5a9a;margin:2px 4px 2px 0;">'
            f'{label}</span>'
        )
    safe = re.sub(r'\[([^\]]+)\]', btn_chip, safe)
    safe = safe.replace('\n', '<br>')
    return safe


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if (request.form.get("login") == ADMIN_LOGIN and
                request.form.get("password") == ADMIN_PASSWORD):
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "Неверный логин или пароль"
    return render_template("login.html", error=error, bot_name=BOT_NAME)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    stats = db.get_stats()
    recent = db.get_recent_messages(20)
    return render_template("dashboard.html", stats=stats, recent=recent, bot_name=BOT_NAME)


@app.route("/users")
@login_required
def users():
    users_list = db.get_users()
    return render_template("users.html", users=users_list, bot_name=BOT_NAME, owner_id=OWNER_ID)


@app.route("/users/<int:chat_id>")
@login_required
def dialog(chat_id):
    user = db.get_user(chat_id)
    messages = db.get_messages(chat_id)
    return render_template("dialog.html", user=user, messages=messages, bot_name=BOT_NAME, owner_id=OWNER_ID)


@app.route("/users/<int:chat_id>/send", methods=["POST"])
@login_required
def send_message(chat_id):
    text = request.form.get("text", "").strip()
    if text:
        token = os.environ.get("TELEGRAM_TOKEN", "")
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data
        )
        try:
            urllib.request.urlopen(req, timeout=10)
            db.log_message(chat_id, "out", text)
        except Exception:
            pass
    return redirect(url_for("dialog", chat_id=chat_id))


@app.route("/photo/<file_id>")
@login_required
def proxy_photo(file_id):
    token = os.environ.get("TELEGRAM_TOKEN", "")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}") as r:
        data = json.loads(r.read())
    file_path = data["result"]["file_path"]
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{file_path}") as r:
        content = r.read()
    return Response(content, mimetype="image/jpeg")


@app.route("/document/<file_id>")
@login_required
def proxy_document(file_id):
    token = os.environ.get("TELEGRAM_TOKEN", "")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}") as r:
        data = json.loads(r.read())
    file_path = data["result"]["file_path"]
    filename = file_path.split("/")[-1]
    with urllib.request.urlopen(f"https://api.telegram.org/file/bot{token}/{file_path}") as r:
        content = r.read()
    return Response(
        content,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
