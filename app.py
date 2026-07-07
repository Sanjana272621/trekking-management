import os
import sqlite3
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for
from flask import session, flash, g, abort
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)

app.config["DATABASE"] = os.environ.get("DATABASE_URL")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


@app.close_app
def close_db(error=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()

@app.before_request
def load_current_user():
    g.user = None

    user_id = session.get("user_id")

    if user_id:
        g.user = get_db().execute("""
            SELECT *
            FROM users
            WHERE user_id = ?
        """, (user_id,)).fetchone()

        if g.user is None or g.user["is_blacklisted"]:
            session.clear()

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped_view

def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if g.user is None:
                return redirect(url_for("login"))

            if g.user["role"] not in roles:
                abort(403)

            return view(*args, **kwargs)

        return wrapped_view

    return decorator

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]

        user = get_db().execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (email,)).fetchone()

        if user is None or not check_password_hash(
            user["password_hash"], password
        ):
            flash("Invalid email or password.", "danger")

        elif user["is_blacklisted"]:
            flash("Your account has been blocked.", "danger")

        elif user["role"] == "staff" and not user["is_approved"]:
            flash("Your staff account is waiting for admin approval.", "warning")

        else:
            session.clear()
            session["user_id"] = user["user_id"]

            return redirect(url_for("dashboard"))

    return render_template("login.html")

@app.route("/register/<role>", methods=["GET", "POST"])
def register(role):
    if role not in ("user", "staff"):
        abort(404)

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        contact = request.form["contact"].strip()
        password = request.form["password"]

        approved = 0 if role == "staff" else 1

        try:
            get_db().execute("""
                INSERT INTO users
                (name, email, password_hash, role, contact, is_approved)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                name,
                email,
                generate_password_hash(password),
                role,
                contact,
                approved
            ))

            get_db().commit()

            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("That email is already registered.", "danger")

    return render_template("register.html", role=role)