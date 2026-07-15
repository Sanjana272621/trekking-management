import sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash

# Keep this in sync with app.py (db/instance/trekking.db under the project root).
DATABASE = Path(__file__).resolve().parent / "instance" / "trekking.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'staff', 'user')),
    contact TEXT,
    is_approved INTEGER NOT NULL DEFAULT 1 CHECK(is_approved IN (0, 1)),
    is_blacklisted INTEGER NOT NULL DEFAULT 0 CHECK(is_blacklisted IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS treks (
    trek_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trek_name TEXT NOT NULL,
    location TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK(difficulty IN ('Easy', 'Moderate', 'Hard')),
    duration INTEGER NOT NULL CHECK(duration > 0),
    total_slots INTEGER NOT NULL CHECK(total_slots > 0),
    available_slots INTEGER NOT NULL CHECK(
        available_slots >= 0 AND available_slots <= total_slots
    ),
    assigned_staff_id INTEGER,
    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK(status IN ('Pending', 'Approved', 'Open', 'Closed', 'Started', 'Completed')),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    description TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0 CHECK(is_archived IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (assigned_staff_id)
        REFERENCES users(user_id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS bookings (
    booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    trek_id INTEGER NOT NULL,
    booking_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'Booked'
        CHECK(status IN ('Booked', 'Cancelled', 'Completed')),

    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (trek_id) REFERENCES treks(trek_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking_per_user_trek
ON bookings(user_id, trek_id)
WHERE status = 'Booked';
"""

def get_connection():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_database():
    conn = get_connection()
    conn.executescript(SCHEMA)

    admin_email = "admin@gmail.com"
    admin_password = "1"

    conn.execute("""
        INSERT INTO users
        (name, email, password_hash, role, is_approved, is_blacklisted)
        VALUES (?, ?, ?, 'admin', 1, 0)
        ON CONFLICT(email) DO UPDATE SET
            name = excluded.name,
            password_hash = excluded.password_hash,
            role = 'admin',
            is_approved = 1,
            is_blacklisted = 0
    """, (
        "System Admin",
        admin_email,
        generate_password_hash(admin_password),
    ))

    conn.commit()
    conn.close()

    print("Database created successfully.")
    print(f"Admin email: {admin_email}")
    print(f"Admin password: {admin_password}")

if __name__ == "__main__":
    init_database()