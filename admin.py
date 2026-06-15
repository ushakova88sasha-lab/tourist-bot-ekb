# -*- coding: utf-8 -*-
import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session
import db

app = Flask(__name__)
app.secret_key = os.environ.get("ADMIN_SECRET", "change-me-in-production")

ADMIN_LOGIN    = os.environ.get("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
BOT_NAME       = os.environ.get("BOT_NAME", "Турист-бот Екатеринбург")
OWNER_ID       = int(os.environ.get("OWNER_ID", "84822852"))


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


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
