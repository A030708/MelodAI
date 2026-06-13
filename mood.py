from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 8 moods
MOODS = [
    "energetic", "chill", "happy", "sad",
    "focused", "party", "romantic", "dark",
]

# Columns uploaded songs carry (librosa-extracted, normalised 0-1 or BPM tempo)
FEATURE_COLS = ["tempo", "energy", "danceability", "valence"]

# Each mood defines (feature, low, high) rules — a song must match ALL its rules.
# Values are for librosa-extracted features after min-max normalisation:
#   tempo  → normalised 0-1  (actual BPM ~60-200 mapped to 0-1)
#   energy → RMS-energy normalised 0-1
#   danceability → 0-1
#   valence → 0-1
MOOD_RULES: dict[str, list[tuple[str, float, float]]] = {
    "energetic": [
        ("energy", 0.55, 1.0),
        ("tempo", 0.45, 1.0),
    ],
    "chill": [
        ("energy", 0.0, 0.35),
        ("tempo", 0.0, 0.45),
    ],
    "happy": [
        ("valence", 0.55, 1.0),
        ("danceability", 0.45, 1.0),
        ("energy", 0.3, 1.0),
    ],
    "sad": [
        ("valence", 0.0, 0.35),
        ("energy", 0.0, 0.40),
    ],
    "focused": [
        ("danceability", 0.0, 0.40),
        ("energy", 0.0, 0.55),
    ],
    "party": [
        ("energy", 0.6, 1.0),
        ("danceability", 0.5, 1.0),
        ("tempo", 0.4, 1.0),
    ],
    "romantic": [
        ("energy", 0.0, 0.45),
        ("valence", 0.35, 0.75),
        ("tempo", 0.15, 0.55),
    ],
    "dark": [
        ("energy", 0.4, 1.0),
        ("valence", 0.0, 0.25),
    ],
}


class MoodEngine:
    def __init__(self):
        self._loaded = False

    def load(self):
        self._loaded = True

    def compute_moods(self, features: dict[str, float]) -> list[str]:
        moods = []
        for mood, rules in MOOD_RULES.items():
            match = True
            for feat, lo, hi in rules:
                val = features.get(feat)
                if val is None:
                    match = False
                    break
                if not (lo <= val <= hi):
                    match = False
                    break
            if match:
                moods.append(mood)
        return moods if moods else ["chill"]

    def mood_score(
        self, song_ids: list[str], songs_df: pd.DataFrame, target_mood: str
    ) -> np.ndarray:
        if len(song_ids) == 0:
            return np.array([], dtype=float)
        scores = np.zeros(len(song_ids), dtype=float)
        for i, sid in enumerate(song_ids):
            row = songs_df[songs_df["song_id"] == sid]
            if len(row) == 0:
                continue
            r = row.iloc[0]
            feats = {c: r[c] for c in FEATURE_COLS}
            moods = self.compute_moods(feats)
            if target_mood in moods:
                scores[i] = 1.0
            elif target_mood == "energetic" and "party" in moods:
                scores[i] = 0.6
            elif target_mood == "party" and "energetic" in moods:
                scores[i] = 0.6
            elif target_mood == "chill" and "romantic" in moods:
                scores[i] = 0.5
            elif target_mood == "romantic" and "chill" in moods:
                scores[i] = 0.5
            elif target_mood == "happy" and "energetic" in moods:
                scores[i] = 0.4
            elif target_mood == "sad" and "chill" in moods:
                scores[i] = 0.4
        return scores

    def get_all_moods(self) -> list[str]:
        return MOODS


mood_engine = MoodEngine()
