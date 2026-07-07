CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'staff', 'user')),
    contact TEXT,
    is_approved INTEGER NOT NULL DEFAULT 1,
    is_blacklisted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS treks (
    trek_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trek_name TEXT NOT NULL,
    location TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK(difficulty IN ('Easy', 'Moderate', 'Hard')),
    duration INTEGER NOT NULL,
    total_slots INTEGER NOT NULL,
    available_slots INTEGER NOT NULL,
    assigned_staff_id INTEGER,
    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK(status IN ('Pending', 'Approved', 'Open', 'Closed', 'Started', 'Completed')),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    description TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (assigned_staff_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS bookings (
    booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    trek_id INTEGER NOT NULL,
    booking_date TEXT DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'Booked'
        CHECK(status IN ('Booked', 'Cancelled', 'Completed')),

    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (trek_id) REFERENCES treks(trek_id)
);