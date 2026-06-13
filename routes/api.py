from __future__ import annotations

from flask import Blueprint, jsonify, request, session
import os
import re
import uuid
import logging
from pathlib import Path

from auth import get_db

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_COVERS = BASE_DIR / "uploads" / "covers"

api_bp = Blueprint("api", __name__, url_prefix="/api")
logger = logging.getLogger("api")



@api_bp.route("/upload-status/<int:song_id>")
def upload_status(song_id: int):
    """Polling endpoint: returns the processing_status of a song."""
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 403
    con = get_db()
    row = con.execute(
        "SELECT processing_status FROM songs_uploaded WHERE id=?", (song_id,)
    ).fetchone()
    if not row:
        return jsonify({"status": "not_found"})
    return jsonify({"status": row["processing_status"]})


@api_bp.route("/notifications")
def get_notifications():
    if "user_id" not in session:
        return jsonify({"notifications": [], "unread": 0})
    con = get_db()
    unread_count = con.execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
        (session["user_id"],)
    ).fetchone()[0]
    notifs = con.execute("""
        SELECT id, message, is_read, created_at FROM notifications
        WHERE user_id=? ORDER BY created_at DESC LIMIT 20
    """, (session["user_id"],)).fetchall()
    return jsonify({
        "notifications": [{
            "id": n["id"],
            "message": n["message"],
            "is_read": bool(n["is_read"]),
            "created_at": n["created_at"],
        } for n in notifs],
        "unread": unread_count,
    })


@api_bp.route("/notifications/read", methods=["POST"])
def mark_notifications_read():
    if "user_id" not in session:
        return jsonify({"ok": False})
    con = get_db()
    con.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (session["user_id"],))
    con.commit()
    return jsonify({"ok": True})


@api_bp.route("/admin/stats")
def admin_stats():
    if session.get("role") != "admin":
        return jsonify({"error": "Unauthorized"}), 403
    con = get_db()
    total_users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_artists = con.execute("SELECT COUNT(*) FROM artists").fetchone()[0]
    total_earnings = con.execute("SELECT COALESCE(SUM(amount),0) FROM earnings_log").fetchone()[0]
    return jsonify({
        "users": total_users,
        "artists": total_artists,
        "earnings": total_earnings,
    })


@api_bp.route("/artist/stats/<int:artist_id>")
def artist_stats(artist_id: int):
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 403
    con = get_db()
    artist = con.execute("SELECT * FROM artists WHERE id=?", (artist_id,)).fetchone()
    if not artist:
        return jsonify({"error": "Not found"}), 404

    songs = con.execute("""
        SELECT id, title, play_count, like_count, skip_count, earnings
        FROM songs_uploaded WHERE artist_id=? ORDER BY play_count DESC
    """, (artist_id,)).fetchall()

    return jsonify({
        "stage_name": artist["stage_name"],
        "total_earnings": artist["total_earnings"],
        "monthly_listeners": artist["monthly_listeners"],
        "songs": [{
            "id": s["id"],
            "title": s["title"],
            "plays": s["play_count"],
            "likes": s["like_count"],
            "skips": s["skip_count"],
            "earnings": s["earnings"],
        } for s in songs],
    })


@api_bp.route("/generate-cover", methods=["POST"])
def generate_cover():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    try:
        from cover_gen import generate_cover_from_prompt

        cover_filename = f"ai_{uuid.uuid4().hex}.jpg"
        cover_path = str(UPLOAD_COVERS / cover_filename)
        result = generate_cover_from_prompt(
            prompt=prompt,
            output_path=cover_path,
            size=512,
        )
        if result:
            return jsonify({
                "cover_url": f"/uploads/covers/{cover_filename}",
                "cover_filename": f"covers/{cover_filename}",
            })
        return jsonify({"error": "Cover generation failed"}), 500
    except Exception as e:
        logger.error("Cover generation error: %s", e)
        return jsonify({"error": str(e)}), 500


@api_bp.route("/chat", methods=["POST"])
def chat():
    if "user_id" not in session:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "No message provided"}), 400

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return jsonify({"response": "DJ MelodAI is currently offline. Please configure the Gemini API key."})

    try:
        from google import genai
        import recommender
        
        client = genai.Client(api_key=api_key)
        
        # Build context of available songs
        songs_context = ""
        if recommender.SONGS is not None and len(recommender.SONGS) > 0:
            # Send top 100 songs to fit in context
            top_songs = recommender.SONGS.head(100)
            songs_list = []
            for _, r in top_songs.iterrows():
                sid = str(r['song_id']).replace('uploaded_', '')
                songs_list.append(f"ID: {sid} | Title: {r['title']} | Artist: {r['artist']} | Genre: {r['genre']}")
            songs_context = "\n".join(songs_list)

        system_instruction = f"""You are DJ MelodAI, a cool, friendly, and knowledgeable AI music assistant. 
Your goal is to help users find great music from independent artists on the platform.
You can recommend songs from the provided catalog. 
If you want to recommend a specific song and provide a play button, use the exact format: [PLAY:song_id] where song_id is the ID of the track.

Here is the current catalog of available songs:
{songs_context}

Keep your responses concise and conversational."""

        response = client.models.generate_content(
            model='gemini-flash-latest',
            contents=message,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
            ),
        )
        return jsonify({"response": response.text})
    except Exception as e:
        logger.error("Error in DJ MelodAI chat: %s", e)
        return jsonify({"response": "Sorry, I'm having trouble connecting right now. Try again later!"}), 500



