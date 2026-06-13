from __future__ import annotations

import os
import sqlite3
from typing import Optional

from dotenv import load_dotenv
from mailer import send_earnings_milestone

load_dotenv()

EARN_PER_PLAY = float(os.getenv("EARN_PER_PLAY", "0.004"))
EARN_PER_LIKE = float(os.getenv("EARN_PER_LIKE", "0.010"))


def log_earnings(con: sqlite3.Connection, artist_id: int, song_id: int, event_type: str) -> None:
    if event_type == "play":
        amount = EARN_PER_PLAY
    elif event_type == "like":
        amount = EARN_PER_LIKE
    elif event_type == "skip":
        con.execute(
            "UPDATE songs_uploaded SET skip_count = skip_count + 1 WHERE id = ?",
            (song_id,),
        )
        con.commit()
        return
    elif event_type == "unlike":
        con.execute(
            "UPDATE songs_uploaded SET like_count = MAX(0, like_count - 1) WHERE id = ?",
            (song_id,),
        )
        con.commit()
        return
    else:
        return

    # Fetch artist information to check milestones
    artist = con.execute("SELECT total_earnings, stage_name, user_id FROM artists WHERE id=?", (artist_id,)).fetchone()
    if not artist:
        return

    old_earnings = artist["total_earnings"] or 0.0
    new_earnings = old_earnings + amount

    if event_type == "play":
        con.execute(
            "UPDATE songs_uploaded SET earnings = earnings + ?, play_count = play_count + 1 WHERE id = ?",
            (amount, song_id),
        )
    elif event_type == "like":
        con.execute(
            "UPDATE songs_uploaded SET earnings = earnings + ?, like_count = like_count + 1 WHERE id = ?",
            (amount, song_id),
        )

    con.execute(
        "INSERT INTO earnings_log (artist_id, song_id, event_type, amount) VALUES (?, ?, ?, ?)",
        (artist_id, song_id, event_type, amount),
    )
    con.execute(
        "UPDATE artists SET total_earnings = total_earnings + ? WHERE id = ?",
        (amount, artist_id),
    )

    # Check milestone thresholds
    milestones = [1.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0]
    for m in milestones:
        if old_earnings < m <= new_earnings:
            con.execute(
                "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                (artist["user_id"], f"💰 Milestone reached! You have crossed ${m:.2f} in total earnings.")
            )
            user_info = con.execute("SELECT email FROM users WHERE id=?", (artist["user_id"],)).fetchone()
            if user_info:
                try:
                    send_earnings_milestone(user_info["email"], artist["stage_name"], m, new_earnings)
                except Exception:
                    pass

    con.commit()


def get_artist_earnings(con: sqlite3.Connection, artist_id: int) -> dict:
    total = con.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM earnings_log WHERE artist_id=?",
        (artist_id,),
    ).fetchone()[0]

    monthly = con.execute("""
        SELECT strftime('%Y-%m', timestamp) as month, SUM(amount) as earnings
        FROM earnings_log WHERE artist_id=?
        GROUP BY month ORDER BY month DESC LIMIT 12
    """, (artist_id,)).fetchall()

    per_song = con.execute("""
        SELECT s.id, s.title, s.play_count, s.like_count, s.earnings
        FROM songs_uploaded s WHERE s.artist_id=? ORDER BY s.earnings DESC
    """, (artist_id,)).fetchall()

    return {
        "total": total,
        "monthly": [{"month": r[0], "earnings": r[1]} for r in monthly],
        "per_song": [{"id": r[0], "title": r[1], "plays": r[2], "likes": r[3], "earnings": r[4]} for r in per_song],
    }
