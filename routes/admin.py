from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for, flash

from auth import get_db, role_required
from werkzeug.security import generate_password_hash
import mailer

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

smtp_configured = bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASS"))


@admin_bp.before_request
def check_admin():
    if session.get("role") != "admin":
        return redirect(url_for("index"))


@admin_bp.route("/dashboard")
def dashboard():
    con = get_db()
    total_users = con.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0]
    total_artists = con.execute("SELECT COUNT(*) FROM artists").fetchone()[0]
    total_songs = con.execute("SELECT COUNT(*) FROM songs_uploaded").fetchone()[0]
    total_earnings = con.execute("SELECT COALESCE(SUM(amount),0) FROM earnings_log").fetchone()[0]
    return render_template("admin/dashboard.html",
        total_users=total_users, total_artists=total_artists,
        total_songs=total_songs, total_earnings=total_earnings,
        body_class="admin-page")


@admin_bp.route("/analytics")
def analytics():
    con = get_db()
    days = int(request.args.get("days", 30))

    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    user_growth = con.execute("""
        SELECT DATE(created_at) as d, COUNT(*) as c FROM users
        WHERE DATE(created_at) >= ? GROUP BY d ORDER BY d
    """, (since,)).fetchall()

    top_songs = con.execute("""
        SELECT title, play_count, like_count, earnings FROM songs_uploaded
        ORDER BY play_count DESC LIMIT 10
    """).fetchall()

    genre_dist = con.execute("""
        SELECT genre, COUNT(*) as c FROM songs_uploaded
        WHERE genre IS NOT NULL GROUP BY genre ORDER BY c DESC
    """).fetchall()

    activity = con.execute("""
        SELECT e.event_type, datetime(e.ts, 'unixepoch') as ts, u.username FROM events e
        JOIN users u ON e.user_id = u.id
        ORDER BY e.ts DESC LIMIT 20
    """).fetchall()

    return jsonify({
        "user_growth": [{"date": r[0], "count": r[1]} for r in user_growth],
        "top_songs": [{"title": r[0], "plays": r[1], "likes": r[2], "earnings": r[3]} for r in top_songs],
        "genre_dist": [{"genre": r[0], "count": r[1]} for r in genre_dist],
        "activity": [{"type": r[0], "time": r[1], "user": r[2]} for r in activity],
    })


@admin_bp.route("/users")
def users():
    con = get_db()
    users_list = con.execute("SELECT id, username, email, role, is_active, created_at FROM users ORDER BY created_at DESC").fetchall()
    return render_template("admin/users.html", users=users_list, body_class="admin-page")


@admin_bp.route("/users/<int:user_id>/ban", methods=["POST"])
def ban_user(user_id: int):
    con = get_db()
    con.execute("UPDATE users SET is_active=0 WHERE id=?", (user_id,))
    con.execute(
        "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
        (user_id, "⛔ Your account has been suspended by platform administration.")
    )
    con.commit()

    user = con.execute(
        'SELECT email, username FROM users WHERE id=?',
        (user_id,)
    ).fetchone()
    if user:
        try:
            mailer.send_account_banned(user['email'], user['username'])
        except Exception:
            pass
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:user_id>/activate", methods=["POST"])
def activate_user(user_id: int):
    con = get_db()
    con.execute("UPDATE users SET is_active=1 WHERE id=?", (user_id,))
    con.execute(
        "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
        (user_id, "✅ Your account has been re-activated. Welcome back!")
    )
    con.commit()

    user = con.execute(
        'SELECT email, username FROM users WHERE id=?',
        (user_id,)
    ).fetchone()
    if user:
        try:
            mailer.send_account_activated(user['email'], user['username'])
        except Exception:
            pass
    return redirect(url_for("admin.users"))


@admin_bp.route("/artists")
def artists():
    con = get_db()
    artists_list = con.execute("""
        SELECT a.id, a.user_id, a.stage_name, a.genre, a.verified, a.invite_used,
               u.email, u.is_active, a.total_earnings, a.monthly_listeners
        FROM artists a JOIN users u ON a.user_id = u.id
        ORDER BY a.created_at DESC
    """).fetchall()
    return render_template("admin/artists.html", artists=artists_list, body_class="admin-page")


@admin_bp.route("/artists/<int:artist_id>/ban", methods=["POST"])
def ban_artist(artist_id: int):
    con = get_db()
    artist = con.execute(
        "SELECT a.user_id, a.stage_name FROM artists a WHERE a.id=?",
        (artist_id,)
    ).fetchone()
    if not artist:
        return redirect(url_for("admin.artists"))
    con.execute("UPDATE users SET is_active=0 WHERE id=?", (artist["user_id"],))
    con.execute(
        "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
        (artist["user_id"], "⛔ Your artist account has been suspended by platform administration.")
    )
    con.commit()
    return redirect(url_for("admin.artists"))


@admin_bp.route("/artists/<int:artist_id>/delete", methods=["POST"])
def delete_artist(artist_id: int):
    con = get_db()
    artist = con.execute(
        "SELECT a.user_id, a.stage_name FROM artists a WHERE a.id=?",
        (artist_id,)
    ).fetchone()
    if not artist:
        return redirect(url_for("admin.artists"))
    user_id = artist["user_id"]
    con.execute("DELETE FROM songs_uploaded WHERE artist_id=?", (artist_id,))
    con.execute("DELETE FROM albums WHERE artist_id=?", (artist_id,))
    con.execute("DELETE FROM announcements WHERE artist_id=?", (artist_id,))
    con.execute("DELETE FROM earnings_log WHERE artist_id=?", (artist_id,))
    con.execute("DELETE FROM artists WHERE id=?", (artist_id,))
    con.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
    con.execute("DELETE FROM user_followed_artists WHERE user_id=?", (user_id,))
    con.execute("DELETE FROM user_interests WHERE user_id=?", (user_id,))
    con.execute("DELETE FROM events WHERE user_id=?", (user_id,))
    con.execute("DELETE FROM user_song_listening WHERE user_id=?", (user_id,))
    con.execute("DELETE FROM users WHERE id=?", (user_id,))
    con.commit()
    return redirect(url_for("admin.artists"))


@admin_bp.route("/add-artist", methods=["GET", "POST"])
def add_artist():
    con = get_db()
    if request.method == "POST":
        stage_name = request.form.get("stage_name", "").strip()
        artist_email = request.form.get("email", "").strip()
        genre = request.form.get("genre", "").strip()
        bio = request.form.get("bio", "").strip()
        password = request.form.get("password", "")

        if not password:
            return render_template("admin/add_artist.html", msg="Password is required.", body_class="admin-page")

        hashed = generate_password_hash(password)
        existing_user = con.execute("SELECT id, username FROM users WHERE email=?", (artist_email,)).fetchone()
        if existing_user:
            user_id = existing_user["id"]
            con.execute("UPDATE users SET password_hash=?, role='artist', is_active=1 WHERE id=?",
                        (hashed, user_id))
        else:
            username = artist_email.split("@")[0].lower()
            try:
                cur = con.execute(
                    "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, 'artist')",
                    (username, artist_email, hashed),
                )
                user_id = cur.lastrowid
            except sqlite3.IntegrityError:
                msg = "Username already exists"
                return render_template("admin/add_artist.html", msg=msg, body_class="admin-page")

        con.execute("""
            INSERT INTO artists (user_id, stage_name, bio, genre, invite_code)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, stage_name, bio, genre, f"auto_{user_id}"))
        con.commit()

        msg = f"Artist '{stage_name}' created! They can log in immediately."
        return render_template("admin/add_artist.html", msg=msg,
                               email=artist_email, password=password,
                               body_class="admin-page")

    return render_template("admin/add_artist.html", smtp_configured=smtp_configured,
                           body_class="admin-page")


@admin_bp.route("/send-invite/<int:artist_id>", methods=["POST"])
def send_invite(artist_id: int):
    con = get_db()
    artist = con.execute(
        "SELECT a.stage_name, a.invite_code, u.email FROM artists a JOIN users u ON a.user_id = u.id WHERE a.id = ?",
        (artist_id,)
    ).fetchone()
    if not artist:
        return jsonify({"ok": False, "error": "Artist not found"}), 404

    sent = mailer.send_invite_code(artist["email"], artist["stage_name"], artist["invite_code"])
    return jsonify({"ok": sent})


@admin_bp.route("/songs/<int:song_id>", methods=["DELETE"])
def delete_song(song_id: int):
    con = get_db()
    # Query song and artist details before deletion for the notification email
    song = con.execute("""
        SELECT s.title, s.artist_id, a.stage_name, u.email, u.id as user_id
        FROM songs_uploaded s
        JOIN artists a ON s.artist_id = a.id
        JOIN users u ON a.user_id = u.id
        WHERE s.id = ?
    """, (song_id,)).fetchone()

    con.execute("DELETE FROM songs_uploaded WHERE id=?", (song_id,))
    con.commit()

    if song:
        con.execute(
            "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
            (song["user_id"], f"⚠️ Your song \"{song['title']}\" has been removed by platform moderation.")
        )
        con.commit()

        try:
            mailer.send_song_status(
                song['email'],
                song['stage_name'],
                song['title'],
                'removed',
                reason='Content policy violation'
            )
        except Exception:
            pass

    try:
        import recommender
        recommender.load_uploaded_songs()
    except Exception as e:
        print(f"[Admin Delete] Recommender reload error: {e}")

    return jsonify({"ok": True})


# ── Admin Broadcast ──

@admin_bp.route("/broadcast", methods=["GET", "POST"])
def broadcast():
    if request.method == "POST":
        subject_line = request.form.get("subject", "").strip()
        announcement_html = (request.form.get("body") or request.form.get("message") or "").strip()
        target = request.form.get("target", "all").strip()

        if not subject_line or not announcement_html:
            return render_template("admin/broadcast.html", msg="Subject and message are required.", msg_type="error", body_class="admin-page")

        con = get_db()

        if target == 'users_only':
            recipients = con.execute(
                "SELECT id, email, username FROM users WHERE role='user' AND is_active=1"
            ).fetchall()
        elif target == 'artists_only':
            recipients = con.execute(
                "SELECT u.id, u.email, a.stage_name as username FROM artists a JOIN users u ON u.id=a.user_id WHERE u.is_active=1"
            ).fetchall()
        else:
            recipients = con.execute(
                "SELECT id, email, username FROM users WHERE is_active=1"
            ).fetchall()

        for r in recipients:
            con.execute(
                "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                (r["id"], f"📢 Broadcast: {subject_line}")
            )
            try:
                mailer.send_admin_broadcast(
                    r['email'],
                    r['username'],
                    subject_line,
                    announcement_html
                )
            except Exception:
                pass

        con.commit()
        flash(f'Broadcast sent to {len(recipients)} recipients.')
        return redirect('/admin/broadcast')

    return render_template("admin/broadcast.html", body_class="admin-page")


# ── Admin Email Logs View ──

@admin_bp.route("/email-logs")
def email_logs():
    con = get_db()
    logs = con.execute(
        '''SELECT * FROM email_logs
           ORDER BY created_at DESC
           LIMIT 500'''
    ).fetchall()
    return render_template('admin/email_logs.html', logs=logs, body_class="admin-page")
