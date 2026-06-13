from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.preprocessing import normalize

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "events.db"

EVENT_WEIGHTS = {"like": 2.0, "unlike": -2.0, "play": 1.0, "skip": -2.0, "seed": 1.0}

from mood import mood_engine

SONGS: pd.DataFrame = None
X_NORM: sparse.csr_matrix = None
SONG_ID_TO_IDX: dict[str, int] = {}


def load_uploaded_songs():
    global SONGS, X_NORM, SONG_ID_TO_IDX
    try:
        from auth import DB_PATH as AUTH_DB_PATH
        con = sqlite3.connect(str(AUTH_DB_PATH), check_same_thread=False)
        con.row_factory = sqlite3.Row
        uploaded = con.execute("""
            SELECT s.id, s.title, a.stage_name as artist, a.profile_pic, s.genre, s.play_count as base_pop,
                   s.uploaded_at, s.tempo, s.energy, s.danceability, s.valence, s.key, s.mode,
                   s.cover_art
            FROM songs_uploaded s JOIN artists a ON s.artist_id = a.id
            WHERE s.is_public=1
        """).fetchall()
        con.close()

        if uploaded:
            upload_rows = []
            features = []
            for u in uploaded:
                t = float(u["tempo"] or 120.0) / 200.0
                e = float(u["energy"] or 0.5)
                d = float(u["danceability"] or 0.5)
                v = float(u["valence"] or 0.5)
                k = float(u["key"] or 0) / 11.0
                m = float(u["mode"] or 0)
                
                upload_rows.append({
                    "song_id": f"uploaded_{u['id']}",
                    "title": u["title"],
                    "artist": u["artist"],
                    "profile_pic": u["profile_pic"],
                    "genre": u["genre"] or "Unknown",
                    "base_pop": float(u["base_pop"] or 0.0),
                    "cover_art": u["cover_art"],
                    "tempo": t,
                    "energy": e,
                    "danceability": d,
                    "valence": v,
                })
                features.append([t, e, d, v, k, m])

            SONGS = pd.DataFrame(upload_rows)
            features_array = np.array(features, dtype=float)
            
            # Normalize features so cosine similarity works well
            if len(features_array) > 0:
                features_array = normalize(features_array, norm="l2", axis=1, copy=False)
            
            X_NORM = sparse.csr_matrix(features_array)

            SONG_ID_TO_IDX = {sid: i for i, sid in enumerate(SONGS["song_id"].values)}
            logger.info("Loaded %d uploaded songs into recommendation pool", len(SONGS))
        else:
            SONGS = pd.DataFrame(columns=["song_id", "title", "artist", "genre", "base_pop"])
            X_NORM = sparse.csr_matrix((0, 6))
            SONG_ID_TO_IDX = {}
            logger.info("No uploaded songs found.")
    except Exception as e:
        logger.warning("Could not load uploaded songs: %s", e)


def init_app():
    global SONGS, X_NORM, SONG_ID_TO_IDX
    load_uploaded_songs()
    mood_engine.load()


def get_events_df(conn, user_id: Optional[str] = None) -> pd.DataFrame:
    if user_id:
        rows = conn.execute(
            "SELECT user_id, song_id, event_type, ts FROM events WHERE user_id=? ORDER BY ts ASC",
            (str(user_id),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT user_id, song_id, event_type, ts FROM events ORDER BY ts ASC"
        ).fetchall()
    return pd.DataFrame(rows, columns=["user_id", "song_id", "event_type", "ts"])


def log_event(conn, user_id: str, song_id: str, event_type: str) -> None:
    if event_type not in EVENT_WEIGHTS:
        return
    conn.execute(
        "INSERT INTO events(user_id, song_id, event_type, ts) VALUES (?, ?, ?, ?)",
        (str(user_id), str(song_id), str(event_type), int(time.time())),
    )
    conn.commit()


def reset_user(conn, user_id: str) -> None:
    conn.execute("DELETE FROM events WHERE user_id=?", (str(user_id),))
    conn.commit()


def seed_profile_from_follows(conn, user_id: int, followed_artist_ids: list[int]) -> None:
    """Seed the user's profile vector with songs from followed artists."""
    if not followed_artist_ids or SONGS is None or len(SONGS) == 0:
        return
    placeholders = ",".join("?" * len(followed_artist_ids))
    songs = conn.execute(
        f"SELECT id FROM songs_uploaded WHERE artist_id IN ({placeholders}) AND is_public=1",
        followed_artist_ids
    ).fetchall()
    for s in songs:
        song_id = f"uploaded_{s['id']}"
        conn.execute(
            "INSERT OR IGNORE INTO events(user_id, song_id, event_type, ts) VALUES (?, ?, 'seed', 0)",
            (str(user_id), song_id)
        )
    conn.commit()


def feedback_popularity(events_df: pd.DataFrame) -> np.ndarray:
    if len(SONGS) == 0:
        return np.array([], dtype=float)
    fb = np.zeros(len(SONGS), dtype=float)
    if len(events_df) == 0:
        return fb

    w = events_df["event_type"].map(EVENT_WEIGHTS).astype(float)
    seed_mask = events_df["event_type"] == "seed"
    w[seed_mask] = 0.0
    score = events_df.assign(w=w).groupby("song_id")["w"].sum()

    for sid, val in score.items():
        sid = str(sid)
        if sid in SONG_ID_TO_IDX:
            fb[SONG_ID_TO_IDX[sid]] = float(val)

    if fb.max() > fb.min():
        fb = (fb - fb.min()) / (fb.max() - fb.min() + 1e-9)
    else:
        fb[:] = 0.0
    return fb


def user_vector(user_id: str, events_df: pd.DataFrame):
    if X_NORM is None or X_NORM.shape[0] == 0:
        return None
    uev = events_df[events_df["user_id"] == str(user_id)]
    if len(uev) == 0:
        return None

    idxs, weights = [], []
    for _, r in uev.iterrows():
        sid = str(r["song_id"])
        if sid in SONG_ID_TO_IDX:
            idxs.append(SONG_ID_TO_IDX[sid])
            weights.append(EVENT_WEIGHTS.get(r["event_type"], 0.0))

    if not idxs:
        return None

    weights = np.array(weights, dtype=float)
    U = X_NORM[idxs]
    denom = float(np.sum(np.abs(weights)) + 1e-9)

    uvec = (U.multiply(weights.reshape(-1, 1))).sum(axis=0) / denom
    uvec = np.asarray(uvec)

    uvec = normalize(uvec, norm="l2", axis=1, copy=False)
    return uvec


def collaborative_scores(events_df: pd.DataFrame, user_id: str) -> np.ndarray:
    if len(SONGS) == 0:
        return np.array([], dtype=float)
    scores = np.zeros(len(SONGS), dtype=float)
    all_events = events_df[events_df["event_type"] != "skip"].copy()
    if len(all_events) == 0:
        return scores

    user_songs = set(all_events[all_events["user_id"] == str(user_id)]["song_id"].astype(str).unique())
    if not user_songs:
        return scores

    other = all_events[all_events["user_id"] != str(user_id)]
    if len(other) == 0:
        return scores

    co_occur = other.groupby("user_id")["song_id"].apply(set).reset_index()
    co_occur["match"] = co_occur["song_id"].apply(lambda s: len(s & user_songs))

    relevant = co_occur[co_occur["match"] > 0]
    if len(relevant) == 0:
        return scores

    related_songs = set()
    for s in relevant["song_id"]:
        related_songs |= s

    for sid in related_songs:
        sid_str = str(sid)
        if sid_str in SONG_ID_TO_IDX and sid_str not in user_songs:
            users_with_sid = set(all_events[all_events["song_id"] == sid_str]["user_id"].unique())
            overlap = len(users_with_sid & set(relevant["user_id"]))
            if overlap > 0:
                scores[SONG_ID_TO_IDX[sid_str]] = overlap

    if len(scores) > 0 and scores.max() > scores.min():
        scores = (scores - scores.min()) / (scores.max() - scores.min() + 1e-9)
    return scores


def recommend(
    user_id: str,
    conn,
    k: int = 10,
    alpha: float = 0.85,
    genre: str = "All",
    candidate_pool: int = 20000,
    followed_artist_ids: Optional[list[int]] = None,
    collab_weight: float = 0.3,
    mood: str = "",
) -> pd.DataFrame:
    if SONGS is None or len(SONGS) == 0:
        return pd.DataFrame(columns=["song_id", "title", "artist", "genre", "score", "explanation"])

    events_all = get_events_df(conn)
    fb = feedback_popularity(events_all)
    pop = 0.8 * SONGS["base_pop"].values + 0.2 * fb

    collab = collaborative_scores(events_all, user_id)

    cand = SONGS
    if genre != "All":
        cand = cand[cand["genre"] == genre]

    user_events = get_events_df(conn, user_id)
    skipped = set(user_events[user_events["event_type"] == "skip"]["song_id"].astype(str).tolist())
    cand = cand[~cand["song_id"].isin(skipped)]

    candidate_pool = int(max(2000, min(50000, candidate_pool)))
    cand = cand.assign(pop=pop[cand.index]).sort_values("pop", ascending=False).head(candidate_pool)

    if len(cand) == 0:
        return pd.DataFrame(columns=["song_id", "title", "artist", "genre", "score", "explanation"])

    uvec = user_vector(user_id, user_events)

    beta = 0.15

    followed_artist_names: list[str] = []
    if followed_artist_ids:
        try:
            for aid in followed_artist_ids:
                row = conn.execute("SELECT stage_name FROM artists WHERE id=?", (aid,)).fetchone()
                if row:
                    followed_artist_names.append(str(row[0]).lower().strip())
        except Exception:
            pass

    if uvec is None:
        out = cand.head(k)[["song_id", "title", "artist", "genre", "pop"]].copy()
        out = out.rename(columns={"pop": "score"})
        out["explanation"] = ""
        return out

    idxs = cand.index.to_numpy()
    sims = X_NORM[idxs].dot(uvec.T).ravel()
    sims = (sims - sims.min()) / (sims.max() - sims.min() + 1e-9)

    collab_s = collab[idxs]
    if collab_s.max() > collab_s.min():
        collab_s = (collab_s - collab_s.min()) / (collab_s.max() - collab_s.min() + 1e-9)

    content_score = alpha * sims + (1 - alpha) * cand["pop"].values
    scores = (1 - collab_weight) * content_score + collab_weight * collab_s

    if mood and mood in mood_engine.get_all_moods():
        mood_scores = mood_engine.mood_score(cand["song_id"].tolist(), cand, mood)
        scores = scores * 0.6 + mood_scores * 0.4

    explanation = [""] * len(cand)
    if followed_artist_names:
        for i, (_, row) in enumerate(cand.iterrows()):
            artist_name = str(row.get("artist", "")).lower().strip()
            if artist_name in followed_artist_names:
                scores[i] += beta
                explanation[i] = "Because you follow this artist"

    out = cand.copy()
    out["score"] = scores
    out["explanation"] = explanation
    return out.sort_values("score", ascending=False).head(k)[["song_id", "title", "artist", "genre", "score", "explanation"]]
