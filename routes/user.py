from __future__ import annotations

import uuid
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from auth import get_db, login_required, generate_csrf_token
from mailer import send_new_follower

user_bp = Blueprint("user", __name__, url_prefix="/user")


@user_bp.before_request
def check_user():
    if request.endpoint and "shared" in request.endpoint:
        return
    if session.get("role") not in ("user", "admin"):
        return redirect(url_for("index"))


@user_bp.route("/profile")
def profile():
    con = get_db()
    user = con.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if not user:
        return redirect(url_for("index"))

    events_raw = con.execute("""
        SELECT e.song_id, e.event_type, e.ts FROM events e
        WHERE e.user_id=? ORDER BY e.ts DESC LIMIT 50
    """, (session["user_id"],)).fetchall()

    events = []
    for e in events_raw:
        events.append({
            "song_id": e["song_id"],
            "event_type": e["event_type"],
            "timestamp": datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d %H:%M") if e["ts"] else "",
        })

    playlists = con.execute("SELECT * FROM playlists WHERE user_id=?", (session["user_id"],)).fetchall()

    liked_songs = con.execute("""
        SELECT DISTINCT e.song_id FROM events e
        WHERE e.user_id=? AND e.event_type='like' ORDER BY e.ts DESC LIMIT 20
    """, (session["user_id"],)).fetchall()

    followed = con.execute("""
        SELECT a.id, a.stage_name, a.genre FROM user_followed_artists ufa
        JOIN artists a ON ufa.artist_id = a.id
        WHERE ufa.user_id=? ORDER BY ufa.followed_at DESC
    """, (session["user_id"],)).fetchall()

    return render_template("user/profile.html",
        user=user, events=events, playlists=playlists,
        liked_songs=[r["song_id"] for r in liked_songs],
        followed=followed, csrf_token=generate_csrf_token())


@user_bp.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():
    con = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        if not username or not email:
            return redirect(url_for("user.edit_profile"))
        try:
            con.execute("UPDATE users SET username=?, email=? WHERE id=?",
                        (username, email, session["user_id"]))
            con.commit()
            session["username"] = username
        except Exception:
            pass
        return redirect(url_for("user.profile"))
    user = con.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    return render_template("user/edit_profile.html", user=user, csrf_token=generate_csrf_token())


@user_bp.route("/change-password", methods=["POST"])
def change_password():
    con = get_db()
    user = con.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if not user:
        return redirect(url_for("index"))
    current = request.form.get("current_password", "")
    new_pass = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")
    if not check_password_hash(user["password_hash"], current):
        return redirect(url_for("user.profile", msg="Current password is incorrect"))
    if new_pass != confirm or len(new_pass) < 6:
        return redirect(url_for("user.profile", msg="Passwords don't match or too short"))
    con.execute("UPDATE users SET password_hash=? WHERE id=?",
                (generate_password_hash(new_pass), session["user_id"]))
    con.commit()
    return redirect(url_for("user.profile", msg="Password changed successfully"))


@user_bp.route("/playlists", methods=["GET", "POST"])
def playlists():
    con = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if name:
            share_id = uuid.uuid4().hex[:12]
            con.execute("INSERT INTO playlists (user_id, name, description, share_id) VALUES (?, ?, ?, ?)",
                (session["user_id"], name, description, share_id))
            con.commit()
        return redirect(url_for("user.playlists"))

    playlists_list = con.execute("""
        SELECT p.*, (SELECT COUNT(*) FROM playlist_songs ps WHERE ps.playlist_id=p.id) as song_count
        FROM playlists p WHERE p.user_id=? ORDER BY p.created_at DESC
    """, (session["user_id"],)).fetchall()

    return render_template("user/playlist.html", playlists=playlists_list)


@user_bp.route("/playlists/<int:playlist_id>")
def view_playlist(playlist_id: int):
    con = get_db()
    pl = con.execute("SELECT * FROM playlists WHERE id=? AND user_id=?",
        (playlist_id, session["user_id"])).fetchone()
    if not pl:
        return redirect(url_for("user.playlists"))

    songs_raw = con.execute("""
        SELECT ps.song_id, ps.position, ps.added_at
        FROM playlist_songs ps WHERE ps.playlist_id=? ORDER BY ps.position ASC
    """, (playlist_id,)).fetchall()

    songs = []
    for s in songs_raw:
        sid = str(s["song_id"]).replace("uploaded_", "")
        song_info = con.execute(
            """SELECT s.id, s.title, a.stage_name AS artist, a.profile_pic, s.cover_art
               FROM songs_uploaded s JOIN artists a ON s.artist_id = a.id
               WHERE s.id=?""",
            (int(sid),) if sid.isdigit() else (0,)
        ).fetchone()
        songs.append({
            "song_id": s["song_id"],
            "position": s["position"],
            "added_at": s["added_at"],
            "id": int(sid) if sid.isdigit() else sid,
            "title": song_info["title"] if song_info else sid,
            "artist": song_info["artist"] if song_info else "-",
            "cover_art": song_info["cover_art"] if song_info else None,
            "profile_pic": song_info["profile_pic"] if song_info else None,
        })

    return render_template("user/playlist.html", playlist=pl, songs=songs)


@user_bp.route("/playlists/<int:playlist_id>/add", methods=["POST"])
def add_to_playlist(playlist_id: int):
    con = get_db()
    song_id = request.form.get("song_id", "")
    if song_id:
        max_pos = con.execute(
            "SELECT COALESCE(MAX(position),0)+1 FROM playlist_songs WHERE playlist_id=?",
            (playlist_id,),
        ).fetchone()[0]
        con.execute(
            "INSERT OR IGNORE INTO playlist_songs (playlist_id, song_id, position) VALUES (?, ?, ?)",
            (playlist_id, song_id, max_pos),
        )
        con.commit()
    return redirect(url_for("index", msg="Added to playlist!"))


@user_bp.route("/playlists/<int:playlist_id>/songs/<song_id>/delete", methods=["DELETE"])
@user_bp.route("/playlists/<int:playlist_id>/songs/<song_id>", methods=["DELETE"])
def remove_from_playlist(playlist_id: int, song_id: str):
    con = get_db()
    con.execute("DELETE FROM playlist_songs WHERE playlist_id=? AND song_id=?",
        (playlist_id, song_id))
    con.commit()
    return jsonify({"ok": True})


# ── Public shared playlist ──

@user_bp.route("/playlists/shared/<share_id>")
def shared_playlist(share_id: str):
    con = get_db()
    pl = con.execute(
        "SELECT p.*, u.username FROM playlists p JOIN users u ON p.user_id = u.id WHERE p.share_id=?",
        (share_id,),
    ).fetchone()
    if not pl:
        return render_template("user/playlist.html", error="Playlist not found")

    songs_raw = con.execute("""
        SELECT ps.song_id, ps.position, ps.added_at
        FROM playlist_songs ps WHERE ps.playlist_id=? ORDER BY ps.position ASC
    """, (pl["id"],)).fetchall()

    songs = []
    for s in songs_raw:
        sid = str(s["song_id"]).replace("uploaded_", "")
        song_info = con.execute(
            """SELECT s.id, s.title, a.stage_name AS artist, a.profile_pic, s.cover_art
               FROM songs_uploaded s JOIN artists a ON s.artist_id = a.id
               WHERE s.id=?""",
            (int(sid),) if sid.isdigit() else (0,)
        ).fetchone()
        songs.append({
            "song_id": s["song_id"],
            "position": s["position"],
            "added_at": s["added_at"],
            "id": int(sid) if sid.isdigit() else sid,
            "title": song_info["title"] if song_info else sid,
            "artist": song_info["artist"] if song_info else "-",
            "cover_art": song_info["cover_art"] if song_info else None,
            "profile_pic": song_info["profile_pic"] if song_info else None,
        })

    return render_template("user/playlist.html", playlist=pl, songs=songs, shared=True)


@user_bp.route("/follow/<int:artist_id>", methods=["POST"])
def follow_artist(artist_id: int):
    con = get_db()

    if request.form.get("_method") == "DELETE":
        con.execute("DELETE FROM user_followed_artists WHERE user_id=? AND artist_id=?",
            (session["user_id"], artist_id))
        con.commit()
        return redirect(request.referrer or url_for("index"))

    # Check if already following
    check = con.execute(
        "SELECT 1 FROM user_followed_artists WHERE user_id=? AND artist_id=?",
        (session["user_id"], artist_id),
    ).fetchone()

    if not check:
        con.execute(
            "INSERT OR IGNORE INTO user_followed_artists (user_id, artist_id) VALUES (?, ?)",
            (session["user_id"], artist_id),
        )
        con.execute("UPDATE artists SET monthly_listeners = monthly_listeners + 1 WHERE id=?", (artist_id,))
        
        # Get artist details for notification/email
        artist_info = con.execute(
            "SELECT a.user_id, a.stage_name, u.email FROM artists a JOIN users u ON a.user_id = u.id WHERE a.id=?",
            (artist_id,)
        ).fetchone()

        if artist_info:
            follower_name = session.get("username", "A user")
            con.execute(
                "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                (artist_info["user_id"], f"👥 {follower_name} started following you!")
            )

            try:
                send_new_follower(artist_info["email"], artist_info["stage_name"], follower_name)
            except Exception:
                pass
        con.commit()
    else:
        con.commit()

    return redirect(request.referrer or url_for("index"))
