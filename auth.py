from __future__ import annotations

import os
import secrets
import sqlite3
from functools import wraps
from typing import Any, Optional

from dotenv import load_dotenv
from flask import Flask, g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "events.db")


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'user',
            profile_pic   TEXT,
            is_active     BOOLEAN DEFAULT 1,
            total_listening_seconds REAL DEFAULT 0,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS artists (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER UNIQUE NOT NULL,
            stage_name        TEXT NOT NULL,
            bio               TEXT,
            genre             TEXT,
            profile_pic       TEXT,
            banner_pic        TEXT,
            invite_code       TEXT UNIQUE NOT NULL,
            invite_used       BOOLEAN DEFAULT 0,
            monthly_listeners INTEGER DEFAULT 0,
            total_earnings    REAL DEFAULT 0.0,
            verified          BOOLEAN DEFAULT 0,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS songs_uploaded (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_id    INTEGER NOT NULL,
            album_id     INTEGER,
            title        TEXT NOT NULL,
            genre        TEXT,
            duration     REAL,
            file_path    TEXT NOT NULL,
            cover_art    TEXT,
            play_count   INTEGER DEFAULT 0,
            like_count   INTEGER DEFAULT 0,
            skip_count   INTEGER DEFAULT 0,
            earnings     REAL DEFAULT 0.0,
            is_public    BOOLEAN DEFAULT 1,
            uploaded_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            processing_status TEXT DEFAULT 'ready',
        tempo        REAL,
        energy       REAL,
        danceability REAL,
        valence      REAL,
        key          INTEGER,
        mode         INTEGER,
        FOREIGN KEY (artist_id) REFERENCES artists(id),
            FOREIGN KEY (album_id)  REFERENCES albums(id)
        );

        CREATE TABLE IF NOT EXISTS albums (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_id    INTEGER NOT NULL,
            title        TEXT NOT NULL,
            cover_art    TEXT,
            genre        TEXT,
            release_date DATE,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (artist_id) REFERENCES artists(id)
        );

        CREATE TABLE IF NOT EXISTS playlists (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            name        TEXT NOT NULL,
            description TEXT,
            is_public   BOOLEAN DEFAULT 0,
            share_id    TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS playlist_songs (
            playlist_id INTEGER NOT NULL,
            song_id     TEXT NOT NULL,
            position    INTEGER,
            added_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (playlist_id, song_id),
            FOREIGN KEY (playlist_id) REFERENCES playlists(id)
        );

        CREATE TABLE IF NOT EXISTS user_followed_artists (
            user_id     INTEGER NOT NULL,
            artist_id   INTEGER NOT NULL,
            followed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, artist_id),
            FOREIGN KEY (user_id)   REFERENCES users(id),
            FOREIGN KEY (artist_id) REFERENCES artists(id)
        );

        CREATE TABLE IF NOT EXISTS user_interests (
            user_id INTEGER NOT NULL,
            genre   TEXT NOT NULL,
            weight  REAL DEFAULT 1.0,
            PRIMARY KEY (user_id, genre),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS earnings_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_id  INTEGER NOT NULL,
            song_id    INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            amount     REAL NOT NULL,
            timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (artist_id) REFERENCES artists(id),
            FOREIGN KEY (song_id)   REFERENCES songs_uploaded(id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            message    TEXT NOT NULL,
            is_read    BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS email_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            to_email    TEXT NOT NULL,
            subject     TEXT NOT NULL,
            email_type  TEXT NOT NULL,
            status      TEXT DEFAULT 'sent',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            song_id    TEXT NOT NULL,
            event_type TEXT NOT NULL,
            ts         INTEGER DEFAULT (strftime('%s', 'now'))
        );
    """)

    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_email = os.getenv("ADMIN_EMAIL", "admin@musicapp.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "Admin@123")

    existing = con.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()
    if not existing:
        hashed = generate_password_hash(admin_password)
        con.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
            (admin_username, admin_email, hashed),
        )
        print(f"[init_db] Admin account seeded: {admin_username} / {admin_email}")

    for col in [("key", "INTEGER"), ("mode", "INTEGER")]:
        try:
            con.execute(f"ALTER TABLE songs_uploaded ADD COLUMN {col[0]} {col[1]}")
        except Exception:
            pass

    streaming_cols = [
        ("is_transcoded", "BOOLEAN DEFAULT 0"),
        ("file_path_high", "TEXT"),
        ("file_path_medium", "TEXT"),
        ("master_file_path", "TEXT"),
        ("stream_count", "INTEGER DEFAULT 0"),
    ]
    for col_name, col_type in streaming_cols:
        try:
            con.execute(f"ALTER TABLE songs_uploaded ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass

    try:
        con.execute("ALTER TABLE users ADD COLUMN total_listening_seconds REAL DEFAULT 0")
    except Exception:
        pass

    try:
        con.execute("ALTER TABLE artists ADD COLUMN profile_pic TEXT DEFAULT 'default_artist.png'")
    except Exception:
        pass

    # Add share_id column to existing playlists
    try:
        con.execute("ALTER TABLE playlists ADD COLUMN share_id TEXT")
    except Exception:
        pass

    # Backfill share_id for existing playlists
    import uuid
    missing = con.execute("SELECT id FROM playlists WHERE share_id IS NULL").fetchall()
    for m in missing:
        con.execute("UPDATE playlists SET share_id=? WHERE id=?", (uuid.uuid4().hex[:12], m[0]))
    try:
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_playlists_share_id ON playlists(share_id)")
    except Exception:
        pass

    con.executescript("""
        CREATE TABLE IF NOT EXISTS user_song_listening (
            user_id        INTEGER NOT NULL,
            song_id        TEXT NOT NULL,
            total_seconds  REAL DEFAULT 0,
            updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, song_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS announcements (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            artist_id   INTEGER NOT NULL,
            title       TEXT NOT NULL,
            message     TEXT NOT NULL,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (artist_id) REFERENCES artists(id)
        );
    """)

    # Backfill user_song_listening from existing play events (safe: only known users + valid song refs)
    try:
        con.execute("""
            INSERT OR IGNORE INTO user_song_listening (user_id, song_id, total_seconds)
            SELECT CAST(e.user_id AS INTEGER), e.song_id, COUNT(*) * COALESCE(s.duration, 0)
            FROM events e
            JOIN songs_uploaded s ON s.id = CAST(REPLACE(e.song_id, 'uploaded_', '') AS INTEGER)
            WHERE e.event_type = 'play'
              AND e.user_id IN (SELECT CAST(id AS TEXT) FROM users)
              AND e.song_id LIKE 'uploaded_%'
            GROUP BY e.user_id, e.song_id
        """)
    except Exception:
        pass  # backfill is best-effort

    con.commit()
    con.close()


def create_user(username: str, email: str, password: str, role: str = "user") -> Optional[int]:
    con = get_db()
    hashed = generate_password_hash(password)
    try:
        cur = con.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (username, email, hashed, role),
        )
        con.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None


def authenticate_user(identifier: str, password: str) -> Optional[sqlite3.Row]:
    con = get_db()
    user = con.execute(
        "SELECT * FROM users WHERE (username=? OR email=?) AND is_active=1",
        (identifier, identifier),
    ).fetchone()
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    con = get_db()
    return con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                return redirect(url_for("index"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def generate_csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def csrf_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or token != session.get("csrf_token"):
            return jsonify({"error": "CSRF validation failed"}), 403
        return view(*args, **kwargs)
    return wrapped
