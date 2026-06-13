from __future__ import annotations

import argparse
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from flask import Flask, g, redirect, render_template, request, session, url_for, Response, send_file, send_from_directory, jsonify

from auth import get_db, close_db, login_required, generate_csrf_token, csrf_required
from recommender import init_app, recommend, get_events_df, log_event, reset_user
import recommender  # for recommender.SONGS
import mailer

logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("app")

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

# ── Flask app factory ──

def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

    app.teardown_appcontext(close_db)

    for d in ['uploads/raw', 'uploads/encoded', 'uploads/covers', 'uploads/profiles']:
        os.makedirs(d, exist_ok=True)

    from routes.admin import admin_bp
    from routes.artist import artist_bp
    from routes.user import user_bp
    from routes.api import api_bp

    app.register_blueprint(admin_bp)
    app.register_blueprint(artist_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(api_bp)

    # Run DB migrations on every startup (safe — ALTER TABLE ADD COLUMN is idempotent)
    _run_migrations()

    # Inject CSRF token into all templates
    @app.context_processor
    def inject_csrf():
        return {"csrf_token": generate_csrf_token()}

    return app


def _run_migrations():
    import sqlite3
    from auth import DB_PATH
    try:
        con = sqlite3.connect(DB_PATH, check_same_thread=False)
        con.execute("PRAGMA journal_mode=WAL")
        # Ensure email_logs table exists (may be missing if init_db was never run)
        con.execute("""CREATE TABLE IF NOT EXISTS email_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            to_email    TEXT NOT NULL,
            subject     TEXT NOT NULL,
            email_type  TEXT NOT NULL,
            status      TEXT DEFAULT 'sent',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        streaming_cols = [
            ("is_transcoded", "BOOLEAN DEFAULT 0"),
            ("file_path_high", "TEXT"),
            ("file_path_medium", "TEXT"),
            ("master_file_path", "TEXT"),
            ("stream_count", "INTEGER DEFAULT 0"),
            ("processing_status", "TEXT DEFAULT 'ready'"),
            ("loudness", "REAL DEFAULT 0"),
            ("speechiness", "REAL DEFAULT 0"),
            ("instrumentalness", "REAL DEFAULT 0"),
            ("detected_mood", "TEXT DEFAULT ''"),
            ("content_hash", "TEXT DEFAULT ''"),
        ]
        for col_name, col_type in streaming_cols:
            try:
                con.execute(f"ALTER TABLE songs_uploaded ADD COLUMN {col_name} {col_type}")
                logger.info("Migration: added %s to songs_uploaded", col_name)
            except Exception:
                pass
        # Reset songs stuck in 'processing' from a previous server session
        stuck = con.execute("SELECT COUNT(*) FROM songs_uploaded WHERE processing_status='processing'").fetchone()[0]
        if stuck:
            con.execute("UPDATE songs_uploaded SET processing_status='failed' WHERE processing_status='processing'")
            logger.info("Reset %d orphaned song(s) from 'processing' to 'failed'", stuck)
        con.commit()
        con.close()
    except Exception as e:
        logger.warning("Migration skipped: %s", e)
app = create_app()
init_app()

from scheduler import start_scheduler
scheduler = start_scheduler()


# ── Before request ──

@app.before_request
def load_user():
    if "user_id" in session:
        con = get_db()
        user = con.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if user and not user["is_active"]:
            session.clear()
            return redirect(url_for("login"))
        if user:
            session["role"] = user["role"]
            session["username"] = user["username"]


# ── Auth routes ──

@app.get("/login")
def login():
    if "user_id" in session:
        return redirect(url_for("index"))
    return render_template("login.html", body_class="login-bg-page")


@app.post("/login")
def login_post():
    from auth import authenticate_user
    identifier = request.form.get("identifier", "").strip()
    password = request.form.get("password", "")
    user = authenticate_user(identifier, password)
    if user:
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]

        if user["role"] == "admin":
            return redirect(url_for("admin.dashboard"))
        elif user["role"] == "artist":
            return redirect(url_for("artist.dashboard"))
        return redirect(url_for("index"))

    return render_template("login.html", msg="Invalid credentials", body_class="login-bg-page")





@app.get("/register")
def register():
    return render_template("register.html", body_class="register-page")


@app.post("/register")
def register_post():
    from auth import create_user
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    if not username or not email or not password:
        return render_template("register.html", msg="All fields required", body_class="register-page")

    user_id = create_user(username, email, password, role="user")
    if user_id is None:
        return render_template("register.html", msg="Username or email already taken", body_class="register-page")

    try:
        con = get_db()
        user = con.execute('SELECT email, username FROM users WHERE id=?', (user_id,)).fetchone()
        if user:
            mailer.send_welcome_user(user['email'], user['username'])
        con.execute(
            "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
            (user_id, f"🎉 Welcome to MelodAI, {username}! Enjoy your personalized experience.")
        )
        con.commit()
    except Exception as e:
        logger.warning("Failed to send welcome user email or log notification: %s", e)

    session["user_id"] = user_id
    session["username"] = username
    session["role"] = "user"

    return redirect(url_for("onboarding_artists"))


@app.get("/onboarding")
def onboarding_step1():
    if "user_id" not in session:
        return redirect(url_for("login"))
    con = get_db()
    genres_rows = con.execute("SELECT DISTINCT genre FROM songs_uploaded WHERE is_public=1 AND genre != '' AND genre IS NOT NULL ORDER BY genre").fetchall()
    genres = ["All"] + [r["genre"] for r in genres_rows]
    if len(genres) == 1:
        genres = ["All", "Pop", "Hip-Hop", "Electronic", "Rock", "R&B"]
    return render_template("onboarding.html", step=1, genres=genres, artists=[], body_class="onboarding-page")


@app.post("/onboarding")
@csrf_required
def onboarding_post():
    if "user_id" not in session:
        return redirect(url_for("login"))
    con = get_db()
    step = int(request.form.get("step", "1"))

    if step == 1:
        selected = request.form.getlist("genres")
        for genre in selected:
            con.execute(
                "INSERT OR IGNORE INTO user_interests (user_id, genre, weight) VALUES (?, ?, 1.0)",
                (session["user_id"], genre),
            )
        con.commit()
        artists_list = con.execute("SELECT id, stage_name, genre FROM artists WHERE invite_used=1 ORDER BY stage_name").fetchall()
        return render_template("onboarding.html", step=2, artists=artists_list, body_class="onboarding-page")

    elif step == 2:
        selected = request.form.getlist("artist_ids")
        for aid in selected:
            con.execute(
                "INSERT OR IGNORE INTO user_followed_artists (user_id, artist_id) VALUES (?, ?)",
                (session["user_id"], int(aid)),
            )
        con.commit()
        return redirect(url_for("index"))

    return redirect(url_for("index"))


@app.get("/onboarding/artists")
def onboarding_artists():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "user":
        return redirect(url_for("index"))
    con = get_db()
    artists = con.execute(
        "SELECT id, stage_name, profile_pic, genre FROM artists WHERE invite_used=1 ORDER BY monthly_listeners DESC, total_earnings DESC"
    ).fetchall()
    return render_template("onboarding.html", artists=artists, body_class="onboarding-page")


@app.post("/onboarding/select")
def onboarding_select():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") != "user":
        return redirect(url_for("index"))
    selected = request.form.getlist("artist_ids")
    if len(selected) < 3:
        con = get_db()
        artists = con.execute(
            "SELECT id, stage_name, profile_pic, genre FROM artists WHERE invite_used=1 ORDER BY monthly_listeners DESC, total_earnings DESC"
        ).fetchall()
        return render_template("onboarding.html", artists=artists, msg="Please select at least 3 artists.", body_class="onboarding-page")
    con = get_db()
    for aid in selected:
        con.execute(
            "INSERT OR IGNORE INTO user_followed_artists (user_id, artist_id) VALUES (?, ?)",
            (session["user_id"], int(aid)),
        )
    con.commit()
    try:
        from recommender import seed_profile_from_follows
        seed_profile_from_follows(con, session["user_id"], [int(a) for a in selected])
    except Exception:
        pass
    return redirect(url_for("index"))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename: str):
    return send_from_directory(str(BASE_DIR / "uploads"), filename)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/health")
def health():
    return {
        "ok": True,
        "songs_rows": len(recommender.SONGS) if recommender.SONGS is not None else 0,
    }


@app.get("/eval")
@login_required
def evaluate():
    from recommender import recommend, get_events_df
    user_id = session["user_id"]
    con = get_db()
    events = get_events_df(con, user_id)
    if len(events) == 0:
        return jsonify({"precision": 0, "recall": 0, "n_events": 0})

    held_out = events.sample(frac=0.2, random_state=42)
    train = events.drop(held_out.index)

    liked_in_held = set(held_out[held_out["event_type"] == "like"]["song_id"].astype(str))
    played_in_held = set(held_out[held_out["event_type"] == "play"]["song_id"].astype(str))
    relevant = liked_in_held | played_in_held

    recs = recommend(user_id=user_id, conn=con, k=10)
    if len(recs) == 0:
        return jsonify({"precision": 0, "recall": 0, "n_events": len(events)})

    recommended = set(recs["song_id"].astype(str))
    hits = recommended & relevant
    precision = len(hits) / max(len(recommended), 1)
    recall = len(hits) / max(len(relevant), 1)

    return jsonify({
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "n_events": len(events),
        "recommended": len(recommended),
        "relevant_in_held": len(relevant),
        "hits": len(hits),
    })


@app.get("/search")
def search():
    q = request.args.get("q", "").strip()
    vibe = request.args.get("vibe", "").strip()
    songs_result = []
    artists_result = []
    vibe_mode = False

    if vibe:
        vibe_mode = True
        songs_result = _vibe_search(vibe)

    elif q and recommender.SONGS is not None and len(recommender.SONGS) > 0:
        mask = recommender.SONGS["title"].str.lower().str.contains(q.lower(), na=False) | \
               recommender.SONGS["artist"].str.lower().str.contains(q.lower(), na=False)
        songs_result = recommender.SONGS[mask].head(20).to_dict(orient="records")
        for s in songs_result:
            sid = str(s["song_id"]).replace("uploaded_", "")
            try:
                s["id"] = int(sid)
            except Exception:
                s["id"] = sid

        con = get_db()
        # Enrich with artist profile pic for fallback cover
        for s in songs_result:
            if not s.get("cover_art") and not s.get("profile_pic"):
                row = con.execute(
                    "SELECT a.profile_pic FROM songs_uploaded su JOIN artists a ON su.artist_id=a.id WHERE su.id=?",
                    (s.get("id"),)
                ).fetchone()
                if row:
                    s["profile_pic"] = row["profile_pic"]
        followed_set = set()
        if "user_id" in session:
            f_rows = con.execute("SELECT artist_id FROM user_followed_artists WHERE user_id=?", (session["user_id"],)).fetchall()
            followed_set = {r["artist_id"] for r in f_rows}

        artists_result_raw = con.execute("""
            SELECT id, stage_name, genre FROM artists
            WHERE invite_used=1 AND stage_name LIKE ? LIMIT 20
        """, (f"%{q}%",)).fetchall()
        
        for a in artists_result_raw:
            a_dict = dict(a)
            a_dict["is_following"] = a["id"] in followed_set
            artists_result.append(a_dict)

    return render_template("search.html", q=q, songs=songs_result, artists=artists_result, vibe_mode=vibe_mode, vibe_query=vibe)


def _vibe_search(query: str) -> list[dict]:
    """Use Gemini to interpret a natural language vibe query and find matching songs."""
    if recommender.SONGS is None or len(recommender.SONGS) == 0:
        return []

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return []

    try:
        song_catalog = []
        for _, r in recommender.SONGS.head(200).iterrows():
            sid = str(r["song_id"]).replace("uploaded_", "")
            song_catalog.append(f'{sid}|{r["title"]}|{r["artist"]}|{r["genre"]}')

        catalog_str = "\n".join(song_catalog)

        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = f"""You are a music search AI. Given a user's vibe description, find the most matching songs from the catalog.

User query: "{query}"

Catalog (id|title|artist|genre):
{catalog_str}

Return up to 10 song IDs that best match the vibe. Only return IDs, one per line, no extra text.
If no songs match, return "NONE"."""

        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=200,
            ),
        )
        text = response.text.strip()
        if text == "NONE" or not text:
            return []

        ids = []
        for line in text.split("\n"):
            line = line.strip()
            if line and line.isdigit():
                try:
                    sid = f"uploaded_{line}"
                    match = recommender.SONGS[recommender.SONGS["song_id"] == sid]
                    if not match.empty:
                        s = match.iloc[0].to_dict()
                        s["id"] = int(line)
                        s["vibe_match"] = True
                        ids.append(s)
                except Exception:
                    pass
        return ids[:10]
    except Exception as e:
        logger.warning("Vibe search error: %s", e)
        return []


# ── Search suggestions API ──

@app.get("/api/search/suggestions")
def search_suggestions():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 1:
        return jsonify({"suggestions": [], "correction": ""})

    suggestions = []
    correction = ""

    # Song suggestions from the in-memory DataFrame
    if recommender.SONGS is not None and len(recommender.SONGS) > 0:
        mask = recommender.SONGS["title"].str.lower().str.contains(q.lower(), na=False)
        matching = recommender.SONGS[mask].head(5)
        for _, r in matching.iterrows():
            suggestions.append({
                "type": "song",
                "label": f'{r["title"]} — {r["artist"]}',
                "value": r["title"],
            })

    # Artist suggestions from DB
    con = get_db()
    artist_rows = con.execute(
        "SELECT stage_name FROM artists WHERE invite_used=1 AND stage_name LIKE ? LIMIT 5",
        (f"%{q}%",),
    ).fetchall()
    for a in artist_rows:
            suggestions.append({
                "type": "artist",
                "label": a["stage_name"],
                "value": a["stage_name"],
            })

    # Fuzzy correction — if no direct matches, suggest closest
    if not suggestions and len(q) >= 3:
        all_titles = []
        if recommender.SONGS is not None and len(recommender.SONGS) > 0:
            all_titles = recommender.SONGS["title"].dropna().unique().tolist()
        all_artists = [r["stage_name"] for r in con.execute(
            "SELECT stage_name FROM artists WHERE invite_used=1"
        ).fetchall()]
        all_names = all_titles + all_artists
        import difflib
        close = difflib.get_close_matches(q, all_names, n=1, cutoff=0.6)
        if close:
            correction = close[0]

    return jsonify({"suggestions": suggestions[:8], "correction": correction})


# ── Listening Activity ──

@app.get("/activity")
@login_required
def activity():
    user_id = session["user_id"]
    con = get_db()
    activity_list = con.execute(
        """SELECT usl.song_id, usl.total_seconds,
                  COALESCE(su.title, '(deleted)') AS title,
                  COALESCE(a.stage_name, '-') AS artist,
                  COALESCE(su.genre, '-') AS genre,
                  COUNT(e.id) AS play_count
           FROM user_song_listening usl
           LEFT JOIN songs_uploaded su ON su.id = CAST(REPLACE(usl.song_id, 'uploaded_', '') AS INTEGER)
           LEFT JOIN artists a ON a.id = su.artist_id
           LEFT JOIN events e ON e.user_id = usl.user_id AND e.song_id = usl.song_id AND e.event_type = 'play'
           WHERE usl.user_id = ?
           GROUP BY usl.song_id
           ORDER BY usl.total_seconds DESC""",
        (user_id,),
    ).fetchall()

    rows = []
    for r in activity_list:
        secs = r["total_seconds"]
        if secs >= 3600:
            fmt = f"{int(secs // 3600)}h {int(secs % 3600 // 60)}m"
        elif secs >= 60:
            fmt = f"{int(secs // 60)}m {int(secs % 60)}s"
        else:
            fmt = f"{int(secs)}s"
        rows.append({
            "song_id": r["song_id"],
            "title": r["title"],
            "artist": r["artist"],
            "genre": r["genre"],
            "total_seconds": secs,
            "time_fmt": fmt,
            "play_count": r["play_count"] or 0,
        })

    total = sum(float(r["total_seconds"]) for r in rows)
    if total >= 3600:
        total_fmt = f"{int(total // 3600)}h {int(total % 3600 // 60)}m"
    elif total >= 60:
        total_fmt = f"{int(total // 60)}m"
    else:
        total_fmt = f"{int(total)}s"

    return render_template(
        "activity.html",
        rows=rows,
        total_time=total_fmt,
        csrf_token=generate_csrf_token(),
    )


# ── Main index / recommendations ──

@app.get("/")
@login_required
def index():
    user_id = session["user_id"]
    genre = request.args.get("genre", "All")
    msg = request.args.get("msg", "")
    mood = request.args.get("mood", "")

    try:
        alpha = float(request.args.get("alpha", "0.85"))
    except Exception:
        alpha = 0.85
    try:
        k = int(request.args.get("k", "10"))
    except Exception:
        k = 10
    try:
        candidate_pool = int(request.args.get("pool", "20000"))
    except Exception:
        candidate_pool = 20000
    try:
        collab_weight = float(request.args.get("collab", "0.3"))
    except Exception:
        collab_weight = 0.3

    k = max(5, min(30, k))
    alpha = max(0.0, min(1.0, alpha))
    collab_weight = max(0.0, min(1.0, collab_weight))

    con = get_db()
    followed = con.execute(
        "SELECT artist_id FROM user_followed_artists WHERE user_id=?", (user_id,)
    ).fetchall()
    followed_ids = [r["artist_id"] for r in followed]

    recs = recommend(
        user_id=user_id, conn=con, k=k, alpha=alpha, genre=genre,
        candidate_pool=candidate_pool, followed_artist_ids=followed_ids,
        collab_weight=collab_weight, mood=mood,
    )
    rec_items: List[Dict[str, Any]] = recs.to_dict(orient="records") if len(recs) > 0 else []  # type: ignore

    for item in rec_items:
        sid = str(item.get("song_id", "")).replace("uploaded_", "")
        try:
            item["id"] = int(sid)
        except Exception:
            item["id"] = sid

    ids = [item["id"] for item in rec_items if isinstance(item.get("id"), int)]
    if ids:
        placeholders = ",".join("?" * len(ids))
        upload_rows = con.execute(
            f"""SELECT su.id, su.is_transcoded, su.file_path_high, su.file_path_medium, su.cover_art, a.profile_pic
                FROM songs_uploaded su JOIN artists a ON su.artist_id=a.id WHERE su.id IN ({placeholders})""",
            ids
        ).fetchall()
        upload_map = {r["id"]: r for r in upload_rows}
    else:
        upload_map = {}

    for item in rec_items:
        uid = item.get("id")
        if isinstance(uid, int) and uid in upload_map:
            db_row = upload_map[uid]
            item["is_transcoded"] = bool(db_row["is_transcoded"])
            item["file_path_high"] = db_row["file_path_high"]
            item["file_path_medium"] = db_row["file_path_medium"]
            item["cover_art"] = db_row["cover_art"]
            item["profile_pic"] = db_row["profile_pic"]
        else:
            item["is_transcoded"] = False

    trending = con.execute("""
        SELECT s.id, s.title, a.stage_name as artist
        FROM songs_uploaded s JOIN artists a ON s.artist_id = a.id
        WHERE s.is_public=1 ORDER BY s.play_count DESC LIMIT 6
    """).fetchall()
    
    genres_rows = con.execute("SELECT DISTINCT genre FROM songs_uploaded WHERE is_public=1 AND genre != '' AND genre IS NOT NULL ORDER BY genre").fetchall()
    genres = ["All"] + [r["genre"] for r in genres_rows]
    if len(genres) == 1:
        genres = ["All", "Pop", "Hip-Hop", "Electronic", "Rock", "R&B"]

    user_events = get_events_df(con, user_id)
    counts = user_events["event_type"].value_counts().to_dict() if len(user_events) else {}

    playlists = con.execute("SELECT id, name FROM playlists WHERE user_id=?", (user_id,)).fetchall()

    from mood import mood_engine
    moods = mood_engine.get_all_moods()

    user_row = con.execute("SELECT total_listening_seconds FROM users WHERE id=?", (user_id,)).fetchone()
    total_secs = user_row["total_listening_seconds"] if user_row else 0
    if total_secs >= 3600:
        listening_time = f"{int(total_secs // 3600)}h {int(total_secs % 3600 // 60)}m"
    else:
        listening_time = f"{int(total_secs // 60)}m" if total_secs >= 60 else f"{int(total_secs)}s"

    return render_template(
        "index.html",
        user_id=user_id, alpha=alpha, k=k, genre=genre, genres=genres,
        recommendations=rec_items, trending=trending, counts=counts,
        pool=candidate_pool, msg=msg, playlists=playlists,
        moods=moods, active_mood=mood, collab_weight=collab_weight,
        listening_time=listening_time,
        show_player=True,
    )


@app.post("/event")
@login_required
@csrf_required
def event():
    user_id = session["user_id"]
    song_id = request.form.get("song_id", "")
    event_type = request.form.get("event_type", "")
    if song_id and event_type:
        con = get_db()
        log_event(con, user_id, song_id, event_type)

        numeric_id = song_id.replace("uploaded_", "")
        try:
            sid = int(numeric_id)
            row = con.execute("SELECT artist_id FROM songs_uploaded WHERE id=?", (sid,)).fetchone()
            if row:
                from earnings import log_earnings
                log_earnings(con, row["artist_id"], sid, event_type)
        except Exception:
            pass

    is_ajax = request.headers.get("X-CSRF-Token") is not None
    if is_ajax:
        return jsonify({"ok": True, "event": event_type, "song_id": song_id})

    genre = request.form.get("genre", "All")
    alpha = request.form.get("alpha", "0.85")
    k = request.form.get("k", "10")
    pool = request.form.get("pool", "20000")
    msg = {"play": "Played", "like": "Liked", "unlike": "Unliked", "skip": "Skipped"}.get(event_type, "Updated")
    return redirect(url_for("index", genre=genre, alpha=alpha, k=k, pool=pool, msg=msg))


@app.post("/reset")
@login_required
@csrf_required
def reset():
    user_id = session["user_id"]
    con = get_db()
    reset_user(con, user_id)

    genre = request.form.get("genre", "All")
    alpha = request.form.get("alpha", "0.85")
    k = request.form.get("k", "10")
    pool = request.form.get("pool", "20000")

    return redirect(url_for("index", genre=genre, alpha=alpha, k=k, pool=pool, msg="History reset"))


# ── Streaming ──

@app.route('/stream/<int:song_id>')
def stream_song(song_id):
    if 'username' not in session:
        return jsonify({"error": "Login required"}), 403

    conn = get_db()
    song = conn.execute('SELECT * FROM songs_uploaded WHERE id = ?', (song_id,)).fetchone()
    if not song:
        logger.warning("Stream 404: song_id=%s not found", song_id)
        return jsonify({"error": "Song not found"}), 404
    if not song['is_public']:
        logger.warning("Stream 403: song_id=%s is private", song_id)
        return jsonify({"error": "This song is private"}), 403
    quality = request.args.get('q', 'medium')
    db_path = song['file_path_high'] if quality == 'high' else song['file_path_medium']
    if db_path:
        file_path = os.path.normpath(os.path.join('uploads', db_path))
    else:
        file_path = os.path.normpath(os.path.join('uploads', 'encoded', str(song_id), 'high.mp3' if quality == 'high' else 'medium.mp3'))

    if not os.path.exists(file_path) and song['is_transcoded']:
        master = song['master_file_path']
        if master and os.path.exists(master):
            file_path = master
            logger.info("Stream: song_id=%s using master fallback: %s", song_id, file_path)
        else:
            logger.warning("Stream 404: song_id=%s file not found at %s (master=%s)", song_id, file_path, master)
            return jsonify({"error": "Audio file not found on disk"}), 404

    if not os.path.exists(file_path):
        logger.warning("Stream 503: song_id=%s file missing at %s (is_transcoded=%s)", song_id, file_path, song['is_transcoded'])
        return jsonify({"error": "Song is still processing. Try again shortly."}), 503

    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {'.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.ogg': 'audio/ogg',
                '.m4a': 'audio/mp4', '.flac': 'audio/flac', '.aac': 'audio/aac',
                '.wma': 'audio/x-ms-wma'}
    mime = mime_map.get(ext, 'audio/mpeg')

    range_header = request.headers.get('Range', None)
    conn.execute('UPDATE songs_uploaded SET stream_count = stream_count + 1 WHERE id = ?', (song_id,))
    is_new_play = not range_header or range_header == 'bytes=0-'
    if is_new_play:
        from earnings import log_earnings
        log_earnings(conn, song['artist_id'], song_id, 'play')
        if 'username' in session:
            dur = song['duration'] or 0
            uid = session['user_id']
            conn.execute(
                "UPDATE users SET total_listening_seconds = total_listening_seconds + ? WHERE id = ?",
                (dur, uid),
            )
            conn.execute(
                "INSERT INTO user_song_listening (user_id, song_id, total_seconds) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, song_id) DO UPDATE SET total_seconds = total_seconds + ?, updated_at = CURRENT_TIMESTAMP",
                (uid, f"uploaded_{song_id}", dur, dur),
            )
            conn.commit()

    file_size = os.path.getsize(file_path)

    if range_header:
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if not match:
            return jsonify({"error": "Invalid range"}), 416
        byte1 = int(match.group(1))
        byte2 = int(match.group(2)) if match.group(2) else file_size - 1

        length = byte2 - byte1 + 1

        with open(file_path, 'rb') as f:
            f.seek(byte1)
            data = f.read(length)

        response = Response(data, status=206, mimetype=mime)
        response.headers['Content-Range'] = f'bytes {byte1}-{byte2}/{file_size}'
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Content-Length'] = str(length)
        response.headers['Content-Type'] = mime
        response.headers['Cache-Control'] = 'no-cache'
        return response
    else:
        response = send_file(file_path, mimetype=mime, conditional=True, as_attachment=False)
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Content-Length'] = str(file_size)
        response.headers['Cache-Control'] = 'no-cache'
        return response


# ── Diagnostics (debug only) ──

@app.route("/debug/song/<int:song_id>")
def debug_song(song_id):
    conn = get_db()
    song = conn.execute('SELECT * FROM songs_uploaded WHERE id = ?', (song_id,)).fetchone()
    if not song:
        return jsonify({"error": "not found"}), 404
    result = dict(song)
    result["_high_exists"] = os.path.exists(os.path.normpath(os.path.join('uploads', song['file_path_high']))) if song['file_path_high'] else False
    result["_medium_exists"] = os.path.exists(os.path.normpath(os.path.join('uploads', song['file_path_medium']))) if song['file_path_medium'] else False
    result["_master_exists"] = os.path.exists(song['master_file_path']) if song['master_file_path'] else False
    result["_cwd"] = os.getcwd()
    return jsonify(result)


# ── Queue System (in-memory, documented limitation) ──

play_queues: dict[str, list[dict]] = {}

@app.route('/queue/add', methods=['POST'])
def add_to_queue():
    if 'username' not in session:
        return jsonify({"error": "Login required"}), 403
    data = request.get_json()
    if not data or not data.get('song_id'):
        return jsonify({"error": "song_id required"}), 400

    user_key = session['username']
    if user_key not in play_queues:
        play_queues[user_key] = []
    play_queues[user_key].append({
        "song_id": data['song_id'],
        "source": data.get('source', 'dataset'),
        "preview_url": data.get('preview_url', None),
    })
    return jsonify({"status": "added", "queue_length": len(play_queues[user_key])})


@app.route('/queue', methods=['GET'])
def get_queue():
    if 'username' not in session:
        return jsonify({"error": "Login required"}), 403
    return jsonify(play_queues.get(session['username'], []))


@app.route('/queue/next', methods=['GET'])
def get_next_in_queue():
    if 'username' not in session:
        return jsonify({"error": "Login required"}), 403
    queue = play_queues.get(session['username'], [])
    if not queue:
        return jsonify({"status": "empty", "next": None})
    next_song = queue.pop(0)
    play_queues[session['username']] = queue
    return jsonify({"status": "ok", "next": next_song})


@app.get('/api/recommendations')
def api_recommendations():
    if 'user_id' not in session:
        return jsonify({"songs": []})
    limit = request.args.get("limit", 1, type=int)
    con = get_db()
    followed = [r["artist_id"] for r in con.execute(
        "SELECT artist_id FROM user_followed_artists WHERE user_id=?", (session["user_id"],)
    ).fetchall()]
    recs = recommend(
        user_id=session["user_id"], conn=con, k=limit, genre="All",
        followed_artist_ids=followed,
    )
    songs = []
    if len(recs) > 0:
        for _, r in recs.iterrows():
            sid = str(r["song_id"]).replace("uploaded_", "")
            try:
                sid = int(sid)
            except Exception:
                pass
            songs.append({
                "id": sid,
                "song_id": r["song_id"],
                "title": r["title"],
                "artist": r["artist"],
                "cover_art": r.get("cover_art"),
                "source": "upload",
            })
    return jsonify({"songs": songs})


@app.route('/queue/clear', methods=['POST'])
def clear_queue():
    if 'username' not in session:
        return jsonify({"error": "Login required"}), 403
    play_queues[session['username']] = []
    return jsonify({"status": "cleared", "queue_length": 0})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-db", action="store_true", help="Initialize database and exit")
    args = parser.parse_args()

    if args.init_db:
        from auth import init_db as _init_db
        _init_db()
        init_app()
    else:
        app.run(debug=True, port=5000)
