from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import uuid
from pathlib import Path

from flask import Blueprint, redirect, render_template, request, session, url_for, jsonify
from werkzeug.utils import secure_filename

from auth import get_db, role_required, csrf_required, DB_PATH
from earnings import get_artist_earnings
import mailer
from cover_gen import generate_cover_from_prompt

artist_bp = Blueprint("artist", __name__, url_prefix="/artist")

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_COVERS = BASE_DIR / "uploads" / "covers"
UPLOAD_PROFILES = BASE_DIR / "uploads" / "profiles"
ALLOWED_AUDIO = {"mp3", "wav", "m4a", "flac", "ogg"}

RAW_FOLDER = os.path.join('uploads', 'raw')
ENCODED_FOLDER = os.path.join('uploads', 'encoded')


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _duplicate_song_check(con, artist_id, file_path):
    """Return existing song dict if the same audio file was uploaded by a different artist, else None."""
    content_hash = _file_sha256(file_path)
    existing = con.execute(
        "SELECT s.id, s.title, a.stage_name FROM songs_uploaded s JOIN artists a ON s.artist_id=a.id WHERE s.content_hash=? AND s.artist_id!=?",
        (content_hash, artist_id)
    ).fetchone()
    return existing, content_hash


@artist_bp.before_request
def check_artist():
    if session.get("role") != "artist":
        return redirect(url_for("index"))


@artist_bp.route("/dashboard")
def dashboard():
    con = get_db()
    artist = con.execute("SELECT * FROM artists WHERE user_id=?", (session["user_id"],)).fetchone()
    if not artist:
        return redirect(url_for("index"))

    songs = con.execute("""
        SELECT id, title, genre, play_count, like_count, skip_count, earnings, uploaded_at, is_public
        FROM songs_uploaded WHERE artist_id=? ORDER BY uploaded_at DESC
    """, (artist["id"],)).fetchall()

    # Per-song listening time from user_song_listening
    song_ids = [s["id"] for s in songs]
    watch_map = {}
    total_watch = 0.0
    if song_ids:
        placeholders = ",".join("?" * len(song_ids))
        watch_rows = con.execute(
            f"""SELECT CAST(REPLACE(song_id, 'uploaded_', '') AS INTEGER) AS sid,
                       SUM(total_seconds) AS total_secs
                FROM user_song_listening
                WHERE song_id LIKE 'uploaded_%'
                  AND CAST(REPLACE(song_id, 'uploaded_', '') AS INTEGER) IN ({placeholders})
                GROUP BY sid""",
            song_ids
        ).fetchall()
        for w in watch_rows:
            watch_map[w["sid"]] = w["total_secs"]
            total_watch += w["total_secs"]

    def fmt_time(secs):
        if secs >= 3600:
            return f"{int(secs // 3600)}h {int(secs % 3600 // 60)}m"
        elif secs >= 60:
            return f"{int(secs // 60)}m {int(secs % 60)}s"
        else:
            return f"{int(secs)}s"

    followers = con.execute("""
        SELECT COUNT(*) FROM user_followed_artists WHERE artist_id=?
    """, (artist["id"],)).fetchone()[0]

    earnings = get_artist_earnings(con, artist["id"])

    # Top songs by watch time
    top_watch = sorted(watch_map.items(), key=lambda x: x[1], reverse=True)[:5]
    top_watch_data = []
    for sid, secs in top_watch:
        s = con.execute("SELECT title FROM songs_uploaded WHERE id=?", (sid,)).fetchone()
        top_watch_data.append({"title": s["title"] if s else f"Song {sid}", "seconds": secs})

    return render_template("artist/dashboard.html",
        artist=artist, songs=songs, followers=followers, earnings=earnings,
        watch_map=watch_map, total_watch=fmt_time(total_watch), fmt_time=fmt_time,
        top_watch=top_watch_data,
        body_class="artist-page")


@artist_bp.route("/upload", methods=["GET", "POST"])
def upload():
    con = get_db()
    artist = con.execute("SELECT * FROM artists WHERE user_id=?", (session["user_id"],)).fetchone()
    if not artist:
        return redirect(url_for("artist.dashboard"))

    if request.method == "POST":
        if request.form.get("csrf_token") != session.get("csrf_token"):
            return jsonify({"error": "Invalid CSRF token"}), 403
        title = request.form.get("title", "").strip()
        genre = request.form.get("genre", "").strip()
        album_id = request.form.get("album_id") or None
        cover_prompt = request.form.get("cover_prompt", "").strip()
        generated_cover = request.form.get("generated_cover", "").strip()

        file = request.files.get("audio")
        cover = request.files.get("cover")

        filename = file.filename if file else None
        if not title or not file or not filename:
            return jsonify({"error": "Title and audio file are required."}), 400

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_AUDIO:
            return jsonify({"error": f"Unsupported format: {ext}"}), 400

        # ── PHASE 1: Instant save ──────────────────────────────────
        # Save raw master file
        os.makedirs(RAW_FOLDER, exist_ok=True)
        raw_filename = f"{uuid.uuid4()}_{secure_filename(filename)}"
        raw_path = os.path.join(RAW_FOLDER, raw_filename)
        file.save(raw_path)

        # Duplicate check — same audio file uploaded by a different artist?
        dup, content_hash = _duplicate_song_check(con, artist["id"], raw_path)
        if dup:
            os.remove(raw_path)
            return jsonify({"error": f"'{title}' matches ‘{dup['title']}’ by {dup['stage_name']} — this song already exists on the platform."}), 409

        # Save cover art if provided (prefer pre-generated AI cover)
        cover_filename = None
        if generated_cover:
            cover_filename = generated_cover.replace("covers/", "")
        elif cover and cover.filename:
            cover_name = cover.filename
            cover_ext = cover_name.rsplit(".", 1)[-1].lower() if "." in cover_name else "jpg"
            cover_filename = f"{uuid.uuid4().hex}.{cover_ext}"
            os.makedirs(str(UPLOAD_COVERS), exist_ok=True)
            cover.save(str(UPLOAD_COVERS / cover_filename))

        # Insert initial DB record with processing_status='processing'
        cursor = con.execute(
            '''INSERT INTO songs_uploaded
                   (artist_id, album_id, title, genre, file_path,
                    master_file_path, cover_art, is_public, is_transcoded,
                    processing_status, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, 'processing', ?)''',
            (artist["id"], album_id, title, genre, raw_path, raw_path,
             f"covers/{cover_filename}" if cover_filename else None, content_hash)
        )
        song_id_raw = cursor.lastrowid
        song_id = int(song_id_raw) if song_id_raw is not None else 0
        con.commit()

        # ── PHASE 2: Background processing ─────────────────────────
        # Capture values needed by the background thread (no Flask context)
        artist_id = artist["id"]
        stage_name = artist["stage_name"]
        db_path = str(DB_PATH)

        t = threading.Thread(
            target=process_song_background,
            args=(song_id, raw_path, title, genre, artist_id, stage_name, db_path),
            kwargs={"cover_prompt": cover_prompt},
            daemon=True,
        )
        t.start()

        # Return immediately with 202 Accepted
        return jsonify({"song_id": song_id, "status": "processing"}), 202

    albums = con.execute("SELECT id, title FROM albums WHERE artist_id=?", (artist["id"],)).fetchall()
    return render_template("artist/upload.html", albums=albums, body_class="artist-page")


@artist_bp.route("/bulk-upload", methods=["POST"])
def bulk_upload():
    try:
        con = get_db()
        artist = con.execute("SELECT * FROM artists WHERE user_id=?", (session["user_id"],)).fetchone()
        if not artist:
            return jsonify({"error": "Unauthorized"}), 403

        if request.form.get("csrf_token") != session.get("csrf_token"):
            return jsonify({"error": "Invalid CSRF token"}), 403

        files = request.files.getlist("audio_files")
        if not files or len(files) == 0:
            return jsonify({"error": "No audio files provided"}), 400

        genre = request.form.get("genre", "").strip()
        album_id = request.form.get("album_id") or None
        results = []
        os.makedirs(RAW_FOLDER, exist_ok=True)

        seen_names = set()
        for i, file in enumerate(files):
            filename = file.filename if file else None
            if not filename:
                continue
            # Skip duplicate entries from potential form duplication
            if filename in seen_names:
                continue
            seen_names.add(filename)

            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if ext not in ALLOWED_AUDIO:
                results.append({"title": filename, "status": "skipped", "error": f"Unsupported format: {ext}"})
                continue

            raw_filename = f"{uuid.uuid4()}_{secure_filename(filename)}"
            raw_path = os.path.join(RAW_FOLDER, raw_filename)
            file.save(raw_path)

            title = os.path.splitext(filename)[0].strip()[:200]

            # Duplicate check — same audio file uploaded by a different artist?
            dup, content_hash = _duplicate_song_check(con, artist["id"], raw_path)
            if dup:
                os.remove(raw_path)
                results.append({"title": title, "status": "skipped", "error": f"Matches ‘{dup['title']}’ by {dup['stage_name']} — already exists"})
                continue

            cursor = con.execute(
                '''INSERT INTO songs_uploaded
                       (artist_id, album_id, title, genre, file_path,
                        master_file_path, cover_art, is_public, is_transcoded,
                        processing_status, content_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, 'processing', ?)''',
                (artist["id"], album_id, title, genre, raw_path, raw_path,
                 None, content_hash)
            )
            song_id_raw = cursor.lastrowid
            song_id = int(song_id_raw) if song_id_raw is not None else 0
            con.commit()

            t = threading.Thread(
                target=process_song_background,
                args=(song_id, raw_path, title, genre, artist["id"], artist["stage_name"], str(DB_PATH)),
                daemon=True,
            )
            t.start()

            results.append({"song_id": song_id, "title": title, "status": "processing"})

        return jsonify({"songs": results}), 202
    except Exception as e:
        print(f"[Bulk Upload] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server error: {str(e)[:200]}"}), 500


def process_song_background(song_id, raw_path, title, genre, artist_id, stage_name, db_path, cover_prompt=""):
    """Phase 2: runs in a daemon thread — transcode, generate cover, notify."""
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row

        transcode_result = transcode_audio(raw_path, song_id)

        # ── Generate AI cover art if prompt provided ──
        cover_filename = None
        if cover_prompt:
            try:
                cover_filename = f"ai_{uuid.uuid4().hex}.jpg"
                cover_path = str(UPLOAD_COVERS / cover_filename)
                generate_cover_from_prompt(
                    prompt=cover_prompt,
                    output_path=cover_path,
                )
            except Exception as e:
                print(f"[Background] AI cover generation error for song {song_id}: {e}")
                cover_filename = None

        if cover_filename:
            con.execute(
                "UPDATE songs_uploaded SET cover_art=? WHERE id=?",
                (f"covers/{cover_filename}", song_id)
            )

        # ── Update DB ──
        if transcode_result:
            con.execute(
                '''UPDATE songs_uploaded SET
                       file_path_high = ?,
                       file_path_medium = ?,
                       duration = ?,
                       is_transcoded = 1,
                       processing_status = 'ready'
                   WHERE id = ?''',
                (
                    transcode_result['file_path_high'],
                    transcode_result['file_path_medium'],
                    transcode_result['duration'],
                    song_id
                )
            )
        else:
            con.execute(
                "UPDATE songs_uploaded SET processing_status='ready', is_transcoded=0 WHERE id=?",
                (song_id,)
            )
        con.commit()

        # ── Notify followers ──
        try:
            followers = con.execute(
                """SELECT f.user_id, u.username, u.email
                   FROM user_followed_artists f
                   JOIN users u ON f.user_id = u.id
                   WHERE f.artist_id=?""", (artist_id,)
            ).fetchall()
            for f in followers:
                con.execute(
                    "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                    (f["user_id"], f'New song from {stage_name}: "{title}"')
                )
                try:
                    mailer.send_new_song_to_follower(
                        f["email"], f["username"], stage_name, title, song_id, genre
                    )
                except Exception:
                    pass
            con.commit()
        except Exception as e:
            print(f"[Background] Notification error for song {song_id}: {e}")

        try:
            import recommender
            recommender.load_uploaded_songs()
        except Exception as e:
            print(f"[Background] Recommender reload error for song {song_id}: {e}")

        print(f"[Background] Song {song_id} processing complete.")

    except Exception as e:
        print(f"[Background] FATAL error processing song {song_id}: {e}")
        try:
            con.execute(
                "UPDATE songs_uploaded SET processing_status='failed' WHERE id=?",
                (song_id,)
            )
            con.commit()
        except Exception:
            pass
    finally:
        try:
            con.close()
        except Exception:
            pass


def transcode_audio(raw_path, song_id):
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(raw_path)

        encoded_dir = os.path.join(ENCODED_FOLDER, str(song_id))
        os.makedirs(encoded_dir, exist_ok=True)

        high_path = os.path.normpath(os.path.join(encoded_dir, 'high.mp3'))
        medium_path = os.path.normpath(os.path.join(encoded_dir, 'medium.mp3'))

        audio.export(high_path, format='mp3', bitrate='320k')
        audio.export(medium_path, format='mp3', bitrate='128k')

        duration_seconds = len(audio) / 1000.0

        return {
            'file_path_high': f'encoded/{song_id}/high.mp3',
            'file_path_medium': f'encoded/{song_id}/medium.mp3',
            'duration': duration_seconds,
            'is_transcoded': True
        }

    except Exception as transcode_error:
        print(f'[Transcode Error] song_id={song_id} : {transcode_error}')
        # Fallback to direct file copy if ffmpeg/pydub fails
        import shutil
        encoded_dir = os.path.join(ENCODED_FOLDER, str(song_id))
        os.makedirs(encoded_dir, exist_ok=True)
        
        high_path = os.path.normpath(os.path.join(encoded_dir, 'high.mp3'))
        medium_path = os.path.normpath(os.path.join(encoded_dir, 'medium.mp3'))
        shutil.copyfile(raw_path, high_path)
        shutil.copyfile(raw_path, medium_path)
        
        return {
            'file_path_high': f'encoded/{song_id}/high.mp3',
            'file_path_medium': f'encoded/{song_id}/medium.mp3',
            'duration': 0.0,
            'is_transcoded': True
        }


# ── Announcements ──

@artist_bp.route("/announce", methods=["GET", "POST"])
def announce():
    con = get_db()
    artist = con.execute("SELECT * FROM artists WHERE user_id=?", (session["user_id"],)).fetchone()
    if not artist:
        return redirect(url_for("artist.dashboard"))

    # Ensure announcements table exists (safe migration for existing DBs)
    try:
        con.execute("SELECT 1 FROM announcements LIMIT 1")
    except Exception:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS announcements (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                artist_id   INTEGER NOT NULL,
                title       TEXT NOT NULL,
                message     TEXT NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (artist_id) REFERENCES artists(id)
            )
        """)
        con.commit()

    if request.method == "POST":
        if request.form.get("csrf_token") != session.get("csrf_token"):
            return redirect(url_for("artist.announce"))
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        if not title or not message:
            return render_template("artist/announce.html", artist=artist, announcements=[], msg="Title and message are required.", body_class="artist-page")
        if len(title) > 200:
            return render_template("artist/announce.html", artist=artist, announcements=[], msg="Title must be under 200 characters.", body_class="artist-page")
        if len(message) > 2000:
            return render_template("artist/announce.html", artist=artist, announcements=[], msg="Message must be under 2000 characters.", body_class="artist-page")
        con.execute("INSERT INTO announcements (artist_id, title, message) VALUES (?, ?, ?)",
                    (artist["id"], title, message))
        followers = con.execute(
            "SELECT user_id FROM user_followed_artists WHERE artist_id=?", (artist["id"],)
        ).fetchall()
        for f in followers:
            con.execute(
                "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                (f["user_id"], f'📢 {artist["stage_name"]}: {title}')
            )
        con.commit()
        return redirect(url_for("artist.dashboard", msg="Announcement sent to followers!"))

    # Show past announcements
    announcements = con.execute(
        "SELECT id, title, message, created_at FROM announcements WHERE artist_id=? ORDER BY created_at DESC LIMIT 20",
        (artist["id"],)
    ).fetchall()
    return render_template("artist/announce.html", artist=artist, announcements=announcements, body_class="artist-page")


@artist_bp.route("/albums", methods=["GET", "POST"])
def albums():
    con = get_db()
    artist = con.execute("SELECT * FROM artists WHERE user_id=?", (session["user_id"],)).fetchone()
    if not artist:
        return redirect(url_for("artist.dashboard"))

    if request.method == "POST":
        if request.form.get("csrf_token") != session.get("csrf_token"):
            return redirect(url_for("artist.albums"))
        title = request.form.get("title", "").strip()
        genre = request.form.get("genre", "").strip()
        if title:
            con.execute("INSERT INTO albums (artist_id, title, genre) VALUES (?, ?, ?)",
                (artist["id"], title, genre))
            con.commit()
        return redirect(url_for("artist.albums"))

    albums_list = con.execute("""
        SELECT a.*, (SELECT COUNT(*) FROM songs_uploaded s WHERE s.album_id=a.id) as song_count
        FROM albums a WHERE a.artist_id=? ORDER BY a.created_at DESC
    """, (artist["id"],)).fetchall()
    return render_template("artist/albums.html", albums=albums_list, body_class="artist-page")


@artist_bp.route("/profile", methods=["GET", "POST"])
def profile_edit():
    con = get_db()
    artist = con.execute("SELECT * FROM artists WHERE user_id=?", (session["user_id"],)).fetchone()
    if not artist:
        return redirect(url_for("artist.dashboard"))

    if request.method == "POST":
        if request.form.get("csrf_token") != session.get("csrf_token"):
            return redirect(url_for("artist.profile_edit"))
        stage_name = request.form.get("stage_name", "").strip()
        bio = request.form.get("bio", "").strip()
        genre = request.form.get("genre", "").strip()

        profile_pic = artist["profile_pic"]
        if request.form.get("remove_pic"):
            profile_pic = 'default_artist.png'
        file = request.files.get("profile_pic")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            if ext not in {"png", "jpg", "jpeg"}:
                return render_template("artist/profile_edit.html", artist=artist, msg="Only PNG and JPG files are allowed.", body_class="artist-page")
            os.makedirs(str(UPLOAD_PROFILES), exist_ok=True)
            import time as _time
            filename = f"artist_{artist['id']}_{int(_time.time())}.{ext}"
            file_path = UPLOAD_PROFILES / filename
            file.save(str(file_path))
            profile_pic = filename

        con.execute("UPDATE artists SET stage_name=?, bio=?, genre=?, profile_pic=? WHERE id=?",
            (stage_name, bio, genre, profile_pic, artist["id"]))
        con.commit()
        return redirect(url_for("artist.dashboard", msg="Profile updated!"))

    return render_template("artist/profile_edit.html", artist=artist, body_class="artist-page")


@artist_bp.route("/song/<int:song_id>/delete", methods=["POST"])
def delete_song(song_id: int):
    if request.form.get("csrf_token") != session.get("csrf_token"):
        return redirect(url_for("artist.dashboard"))
    con = get_db()
    artist = con.execute("SELECT * FROM artists WHERE user_id=?", (session["user_id"],)).fetchone()
    if not artist:
        return redirect(url_for("artist.dashboard"))

    song = con.execute("SELECT * FROM songs_uploaded WHERE id=? AND artist_id=?",
        (song_id, artist["id"])).fetchone()
    if not song:
        return redirect(url_for("artist.dashboard"))

    # Delete related records
    con.execute("DELETE FROM earnings_log WHERE song_id=?", (song_id,))
    con.execute("DELETE FROM playlist_songs WHERE song_id=?", (song_id,))
    con.execute("DELETE FROM songs_uploaded WHERE id=?", (song_id,))

    # Recalculate artist total earnings
    total = con.execute("SELECT COALESCE(SUM(amount),0) FROM earnings_log WHERE artist_id=?",
        (artist["id"],)).fetchone()[0]
    con.execute("UPDATE artists SET total_earnings=? WHERE id=?", (total, artist["id"]))
    con.commit()

    try:
        import recommender
        recommender.load_uploaded_songs()
    except Exception as e:
        print(f"[Delete] Recommender reload error: {e}")

    return redirect(url_for("artist.dashboard"))


@artist_bp.route("/<int:artist_id>/public")
def public_profile(artist_id: int):
    con = get_db()
    artist = con.execute("SELECT * FROM artists WHERE id=?", (artist_id,)).fetchone()
    if not artist:
        return "Artist not found", 404

    is_following = False
    if "user_id" in session:
        check = con.execute(
            "SELECT 1 FROM user_followed_artists WHERE user_id=? AND artist_id=?",
            (session["user_id"], artist_id),
        ).fetchone()
        is_following = bool(check)

    songs = con.execute("""
        SELECT id, title, genre, play_count, like_count, cover_art, uploaded_at,
               is_transcoded, duration, file_path_high, file_path_medium
        FROM songs_uploaded WHERE artist_id=? AND is_public=1
        ORDER BY uploaded_at DESC
    """, (artist_id,)).fetchall()

    followers = con.execute("SELECT COUNT(*) FROM user_followed_artists WHERE artist_id=?", (artist_id,)).fetchone()[0]

    announcements = con.execute("""
        SELECT title, message, created_at FROM announcements
        WHERE artist_id=? ORDER BY created_at DESC LIMIT 5
    """, (artist_id,)).fetchall()

    return render_template("user/artist_page.html",
        artist=artist, songs=songs, followers=followers, is_following=is_following,
        announcements=announcements)
