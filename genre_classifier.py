from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import normalize

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "data" / "SpotifyFeatures.csv"

_key_map = {
    "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
    "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11,
}
_mode_map = {"Major": 1, "Minor": 0}

_ref_df: pd.DataFrame | None = None
_ref_features: np.ndarray | None = None
_ref_genres: np.ndarray | None = None


def _load():
    global _ref_df, _ref_features, _ref_genres
    if _ref_df is not None:
        return
    df = pd.read_csv(CSV_PATH)
    df["key_int"] = df["key"].map(_key_map).fillna(0).astype(int)
    df["mode_int"] = df["mode"].map(_mode_map).fillna(0).astype(int)
    feats = np.column_stack([
        df["tempo"].values / 200.0,
        df["energy"].values,
        df["danceability"].values,
        df["valence"].values,
        df["key_int"].values / 11.0,
        df["mode_int"].values,
    ])
    _ref_features = normalize(feats, norm="l2", axis=1, copy=False)
    _ref_genres = df["genre"].values
    _ref_df = df


def predict_genre(
    tempo: float,
    energy: float,
    danceability: float,
    valence: float,
    key: int,
    mode: int,
    k: int = 15,
) -> str:
    _load()
    feat = np.array([[tempo / 200.0, energy, danceability, valence, key / 11.0, mode]])
    feat_norm = normalize(feat, norm="l2", axis=1, copy=False)

    sims = _ref_features.dot(feat_norm.T).ravel()
    top_k = min(k, len(sims))
    top_idx = np.argpartition(sims, -top_k)[-top_k:]
    top_idx = top_idx[np.argsort(sims[top_idx])[::-1]]

    genres = _ref_genres[top_idx]
    counts = pd.Series(genres).value_counts()
    return counts.index[0]
