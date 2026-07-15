import os
import sqlite3
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for
from flask import session, flash, g, abort
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env", override=True)

app = Flask(__name__)

DEFAULT_DB = "db/instance/trekking.db"


def _resolve_sqlite_path() -> Path:
    raw = (
        os.environ.get("SQLITE_PATH")
        or os.environ.get("DATABASE_URL")
        or DEFAULT_DB
    ).strip()

    if "://" in raw:
        raw = DEFAULT_DB

    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


app.config["DATABASE"] = str(_resolve_sqlite_path())
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "dev-secret-key"
)

def get_db():
    if "db" not in g:
        Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


@app.teardown_appcontext
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

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()

    if g.user["role"] == "admin":
        stats = {
            "treks": db.execute(
                "SELECT COUNT(*) FROM treks WHERE is_archived = 0"
            ).fetchone()[0],
            "users": db.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'user'"
            ).fetchone()[0],
            "staff": db.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'staff' AND is_approved = 1"
            ).fetchone()[0],
            "bookings": db.execute(
                "SELECT COUNT(*) FROM bookings"
            ).fetchone()[0],
        }
        pending_staff = db.execute("""
            SELECT *
            FROM users
            WHERE role = 'staff' AND is_approved = 0
            ORDER BY created_at DESC
        """).fetchall()
        return render_template(
            "admin_dashboard.html",
            stats=stats,
            pending_staff=pending_staff,
        )

    if g.user["role"] == "staff":
        treks = db.execute("""
            SELECT t.*,
                   (SELECT COUNT(*)
                    FROM bookings b
                    WHERE b.trek_id = t.trek_id AND b.status = 'Booked')
                   AS participant_count
            FROM treks t
            WHERE t.assigned_staff_id = ?
              AND t.is_archived = 0
            ORDER BY t.start_date
        """, (g.user["user_id"],)).fetchall()
        return render_template("staff_dashboard.html", treks=treks)

    bookings = db.execute("""
        SELECT b.*,
               t.trek_name,
               t.location,
               t.start_date,
               t.end_date,
               t.status AS trek_status,
               s.name AS staff_name
        FROM bookings b
        JOIN treks t ON t.trek_id = b.trek_id
        LEFT JOIN users s ON s.user_id = t.assigned_staff_id
        WHERE b.user_id = ?
        ORDER BY b.booking_date DESC
    """, (g.user["user_id"],)).fetchall()
    return render_template("user_dashboard.html", bookings=bookings)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

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


def _approved_staff():
    return get_db().execute("""
        SELECT user_id, name
        FROM users
        WHERE role = 'staff' AND is_approved = 1 AND is_blacklisted = 0
        ORDER BY name
    """).fetchall()


def _get_assigned_trek(trek_id):
    trek = get_db().execute("""
        SELECT *
        FROM treks
        WHERE trek_id = ? AND assigned_staff_id = ? AND is_archived = 0
    """, (trek_id, g.user["user_id"])).fetchone()

    if trek is None:
        abort(404)

    return trek


@app.route("/admin/dashboard")
@role_required("admin")
def admin_dashboard():
    return redirect(url_for("dashboard"))


@app.route("/staff/dashboard")
@role_required("staff")
def staff_dashboard():
    return redirect(url_for("dashboard"))


@app.route("/user/dashboard")
@role_required("user")
def user_dashboard():
    return redirect(url_for("dashboard"))


@app.route("/admin/treks")
@role_required("admin")
def admin_treks():
    treks = get_db().execute("""
        SELECT t.*, s.name AS staff_name
        FROM treks t
        LEFT JOIN users s ON s.user_id = t.assigned_staff_id
        WHERE t.is_archived = 0
        ORDER BY t.start_date DESC
    """).fetchall()
    return render_template(
        "admin_treks.html",
        treks=treks,
        staff_members=_approved_staff(),
    )


@app.route("/admin/treks/create", methods=["GET", "POST"])
@role_required("admin")
def create_trek():
    if request.method == "POST":
        staff_id = request.form.get("assigned_staff_id") or None
        total_slots = int(request.form["total_slots"])

        get_db().execute("""
            INSERT INTO treks (
                trek_name, location, difficulty, duration,
                total_slots, available_slots, assigned_staff_id,
                status, start_date, end_date, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["trek_name"].strip(),
            request.form["location"].strip(),
            request.form["difficulty"],
            int(request.form["duration"]),
            total_slots,
            total_slots,
            staff_id,
            request.form["status"],
            request.form["start_date"],
            request.form["end_date"],
            request.form.get("description", "").strip() or None,
        ))
        get_db().commit()
        flash("Trek created successfully.", "success")
        return redirect(url_for("admin_treks"))

    return render_template(
        "create_treck.html",
        staff_members=_approved_staff(),
    )


@app.route("/admin/treks/<int:trek_id>/assign", methods=["POST"])
@role_required("admin")
def assign_staff(trek_id):
    staff_id = request.form["staff_id"]
    db = get_db()
    trek = db.execute(
        "SELECT trek_id FROM treks WHERE trek_id = ?",
        (trek_id,),
    ).fetchone()

    if trek is None:
        abort(404)

    db.execute(
        "UPDATE treks SET assigned_staff_id = ? WHERE trek_id = ?",
        (staff_id, trek_id),
    )
    db.commit()
    flash("Staff assigned successfully.", "success")
    return redirect(url_for("admin_treks"))


@app.route("/admin/staff/pending")
@role_required("admin")
def pending_staff():
    staff_members = get_db().execute("""
        SELECT *
        FROM users
        WHERE role = 'staff' AND is_approved = 0
        ORDER BY created_at DESC
    """).fetchall()
    return render_template(
        "pending_staff.html",
        staff_members=staff_members,
    )


@app.route("/admin/staff/<int:staff_id>/approve", methods=["POST"])
@role_required("admin")
def approve_staff(staff_id):
    db = get_db()
    result = db.execute("""
        UPDATE users
        SET is_approved = 1
        WHERE user_id = ? AND role = 'staff'
    """, (staff_id,))
    db.commit()

    if result.rowcount == 0:
        abort(404)

    flash("Staff member approved.", "success")
    return redirect(request.referrer or url_for("pending_staff"))


@app.route("/treks")
@role_required("user")
def view_treks():
    search_text = request.args.get("q", "").strip()
    difficulty = request.args.get("difficulty", "").strip()
    location = request.args.get("location", "").strip()
    has_filters = bool(search_text or difficulty or location)

    query = """
        SELECT t.*, s.name AS staff_name
        FROM treks t
        LEFT JOIN users s ON s.user_id = t.assigned_staff_id
        WHERE t.is_archived = 0
          AND t.status IN ('Open', 'Approved')
    """
    params = []

    if search_text:
        pattern = f"%{search_text.lower()}%"
        query += """
          AND (
              LOWER(t.trek_name) LIKE ?
              OR LOWER(t.location) LIKE ?
          )
        """
        params.extend([pattern, pattern])

    if difficulty:
        query += " AND t.difficulty = ?"
        params.append(difficulty)

    if location:
        query += " AND LOWER(t.location) LIKE ?"
        params.append(f"%{location.lower()}%")

    query += " ORDER BY t.start_date"

    treks = get_db().execute(query, params).fetchall()
    return render_template(
        "trecks.html",
        treks=treks,
        search_text=search_text,
        difficulty=difficulty,
        location=location,
        has_filters=has_filters,
    )


@app.route("/treks/<int:trek_id>/book", methods=["POST"])
@role_required("user")
def book_trek(trek_id):
    db = get_db()

    try:
        db.execute("BEGIN IMMEDIATE")
        trek = db.execute("""
            SELECT *
            FROM treks
            WHERE trek_id = ? AND is_archived = 0
        """, (trek_id,)).fetchone()

        if trek is None or trek["status"] != "Open" or trek["available_slots"] < 1:
            db.execute("ROLLBACK")
            flash("This trek is not available for booking.", "danger")
            return redirect(url_for("view_treks"))

        db.execute("""
            INSERT INTO bookings (user_id, trek_id, status)
            VALUES (?, ?, 'Booked')
        """, (g.user["user_id"], trek_id))
        db.execute("""
            UPDATE treks
            SET available_slots = available_slots - 1
            WHERE trek_id = ?
        """, (trek_id,))
        db.commit()
        flash("Trek booked successfully.", "success")

    except sqlite3.IntegrityError:
        db.execute("ROLLBACK")
        flash("You already have an active booking for this trek.", "warning")

    return redirect(url_for("dashboard"))


@app.route("/staff/treks/<int:trek_id>/edit", methods=["GET", "POST"])
@role_required("staff")
def staff_update_trek(trek_id):
    trek = _get_assigned_trek(trek_id)

    if request.method == "POST":
        available_slots = int(request.form["available_slots"])
        status = request.form["status"]

        if available_slots < 0 or available_slots > trek["total_slots"]:
            flash("Available slots must be between 0 and total slots.", "danger")
            return redirect(url_for("staff_update_trek", trek_id=trek_id))

        if status not in ("Open", "Closed", "Started"):
            flash("Invalid status.", "danger")
            return redirect(url_for("staff_update_trek", trek_id=trek_id))

        get_db().execute("""
            UPDATE treks
            SET available_slots = ?, status = ?
            WHERE trek_id = ?
        """, (available_slots, status, trek_id))
        get_db().commit()
        flash("Trek updated successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("staff_edit_trek.html", trek=trek)


@app.route("/staff/treks/<int:trek_id>/participants")
@role_required("staff")
def staff_participants(trek_id):
    trek = _get_assigned_trek(trek_id)
    participants = get_db().execute("""
        SELECT b.booking_id,
               b.user_id,
               b.booking_date,
               b.status AS booking_status,
               u.name,
               u.email,
               u.contact
        FROM bookings b
        JOIN users u ON u.user_id = b.user_id
        WHERE b.trek_id = ?
        ORDER BY b.booking_date
    """, (trek_id,)).fetchall()
    return render_template(
        "participants.html",
        trek=trek,
        participants=participants,
    )


@app.route("/staff/treks/<int:trek_id>/complete", methods=["POST"])
@role_required("staff")
def complete_trek(trek_id):
    _get_assigned_trek(trek_id)
    db = get_db()
    db.execute("""
        UPDATE treks
        SET status = 'Completed'
        WHERE trek_id = ?
    """, (trek_id,))
    db.execute("""
        UPDATE bookings
        SET status = 'Completed'
        WHERE trek_id = ? AND status = 'Booked'
    """, (trek_id,))
    db.commit()
    flash("Trek marked as completed.", "success")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
