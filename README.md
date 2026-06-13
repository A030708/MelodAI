
```markdown
# 🎵 Music Recommendation System

A **hybrid, real-time music platform** built with Python (Flask), SQLite, and vanilla HTML/CSS. It combines content-based vector similarity with dynamic popularity scoring, enriched by live Last.fm tags and iTunes audio previews — extended with a **full role-based multi-user system** featuring Admin, Artist, and User roles with AI-powered personalization, artist monetization, and a Tableau-style analytics dashboard.

---

## 📖 Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Role System](#role-system)
- [User Journey](#user-journey)
- [Recommendation Algorithm](#recommendation-algorithm)
- [Earnings Model](#earnings-model)
- [Database Schema](#database-schema)
- [Project Structure](#project-structure)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
- [API Endpoints](#api-endpoints)
- [External APIs Used](#external-apis-used)
- [Dataset](#dataset)
- [Precomputed Artifacts](#precomputed-artifacts)
- [Tech Stack](#tech-stack)
- [Implementation Phases](#implementation-phases)

---

## ✨ Features

### 🎯 Core AI Recommendations — Existing UI (Unchanged)
> This is the main page all users land on after login. The UI, controls, and behavior are identical to the original build.

- 🤖 **Hybrid Recommendations** — Blends cosine similarity (content) with real-time popularity scoring
- 🎚️ **Tunable Alpha Parameter** — Slider from pure popularity (`α=0`) to pure content-based (`α=1`)
- 👍 **Live Feedback Loop** — Like, Play, and Skip actions instantly reshape your personalized profile
- 🎵 **iTunes 30-sec Previews** — Embedded audio players for each recommended track (no API key needed)
- 🏷️ **Last.fm Tag Enrichment** — Optional real-time genre/style tags and trending chart sidebar
- 🔍 **Genre Filtering** — Filter all recommendations to a specific genre
- 📊 **Candidate Pool Tuning** — Trade off between speed (5k) and accuracy (50k candidates)
- 🔄 **Session Reset** — Clear your personal history and start fresh
- 📈 **Trending Sidebar** — Live Last.fm trending tracks panel

### 🆕 AI Enhancements — Same Recommendation Page
> Additive improvements layered onto the existing page without altering its UI

- 🎨 **Cold Start Fix via Onboarding** — Genre and artist preferences selected at signup immediately seed the user profile vector — no cold start
- 🎤 **Followed Artist Boost** — Songs from artists the user follows receive a `+β` score boost in the recommendation engine
- 💡 **Explanation Tags** — Each recommendation card shows a tag such as "Because you follow [Artist]" or "Trending in [Genre]"
- 🤝 **Collaborative Filtering Signal** — Users with similar interaction patterns subtly influence each other's recommendations
- 📋 **Add to Playlist** — Button on each recommendation card to save a track to a user playlist
- 🔔 **Notification Bell** — Added to the top navbar alongside existing controls; non-intrusive

### 🌐 Platform Features — New Pages (Same Dark Theme)
- 🔐 **Role-Based Auth System** — Three roles: `Admin`, `Artist`, `User` with protected routes and middleware
- 🔍 **Global Search** — Search songs and artists across the full platform
- 🎤 **Public Artist Profiles** — Spotify-style artist pages accessible by clicking any artist name

### 🔴 Admin Features
- 📊 **Tableau-Style Analytics Dashboard** — Interactive Chart.js charts: user growth, top songs, revenue overview, genre distribution, real-time activity feed
- ➕ **Artist Onboarding** — Admin enters artist profile info → system generates invite code → emails it to artist
- 👥 **User Management** — View, ban, and activate user accounts
- 🎵 **Content Moderation** — Remove songs and manage platform content
- 📉 **Extended Health Monitor** — Platform-wide stats via `/health`

### 🟡 Artist Features
- 📧 **Invite Code Registration** — Secure one-time code flow initiated by Admin
- 🎨 **Spotify-Style Artist Profile** — Stage name, bio, genre tags, profile photo, banner image
- 📁 **Music Upload** — Upload MP3/WAV files with title, album, genre, and cover art
- 🎼 **Auto Audio Tagging** — `librosa` extracts audio features from uploaded tracks automatically
- 📈 **Artist Analytics Dashboard** — Play counts, likes, follower growth, earnings per track (Chart.js)
- 💰 **Earnings Tracker** — Real-time earnings from plays and likes with monthly trend charts

### 🟢 User Features
- 📝 **Real Registration** — Email + username + password (replaces demo login)
- 🎨 **Onboarding Flow** — Select favorite genres and artists at signup for immediate personalization
- ❤️ **Follow Artists** — Follow artists to boost their songs in your recommendations
- 📋 **Playlist Management** — Create, edit, and manage personal playlists
- 👤 **Profile Page** — View listening history, liked songs, followed artists, and playlists

---

## 🏗️ Architecture Overview

```

┌──────────────────────────────────────────────────────────────────┐
│                            Browser                               │
│                  (HTML + CSS + Vanilla JS)                       │
│         Dark Glassmorphism Theme — Consistent Across All Pages   │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTP
┌───────────────────────────▼──────────────────────────────────────┐
│                      Flask Web Server                            │
│                                                                  │
│  Core Routes:  /, /login, /logout, /register, /onboarding       │
│                /event, /reset, /health, /search                  │
│                                                                  │
│  Blueprints:                                                     │
│  /admin/*→ admin.py   (dashboard, user mgmt, artist add)     │
│  /artist/*  → artist.py  (upload, analytics, profile)           │
│  /user/*→ user.py    (profile, playlists, follows)          │
│  /api/*     → api.py     (JSON endpoints for JS calls)          │
│                                                                  │
│  Middleware: auth.py → Role-based access control                 │
└──────┬──────────────────┬─────────────────────┬─────────────────┘
       │                  │                     │
┌──────▼──────┐  ┌────────▼────────┐  ┌─────────▼───────────────┐
│  Recommender│  │   SQLite DB     │  │     External APIs        │
│  Engine     │  │  (events.db)    │  │  iTunes Search API       │
│  (numpy /   │  │                 │  │  Last.fm API             │
│   scipy +   │  │  users          │  │  SMTP (invite emails)    │
│  librosa)   │  │  artists        │  └─────────────────────────┘
│             │  │  songs_uploaded │
│  • Cosine   │  │  albums         │  ┌─────────────────────────┐
│  • Collab   │  │  playlists      │  │     File Storage         │
│  • Boost β  │  │  events         │  │  uploads/songs/          │
│  • Profile  │  │  earnings_log   │  │  uploads/covers/         │
│    Vector   │  │  notifications  │  │  uploads/profiles/       │
└──────┬──────┘  └─────────────────┘  └─────────────────────────┘
       │
┌──────▼──────────────────────────┐
│       Precomputed Artifacts     │
│  songs.parquet   — metadata     │
│  X_norm.npz      — feature vecs │
│  tfidf.joblib    — TF-IDF model │
│  scaler.joblib   — feature scale│
└─────────────────────────────────┘

```

---

## 👥 Role System

### 🔴 Admin
```

Access    : Full platform control
Login     : Email + password (seeded on first run via --init-db)
Dashboard : /admin/dashboard

Capabilities:
  ✅ Add artists → enter profile info → generate invite code → email to artist
  ✅ Manage all users (view / ban / activate / delete)
  ✅ Content moderation (remove songs, flag content)
  ✅ Tableau-style analytics dashboard:
       • User growth chart (daily / weekly / monthly)
       • Top songs by plays, likes, revenue
       • Top artists by followers and earnings
       • Genre distribution pie and bar charts
       • Real-time activity feed
       • Platform revenue overview cards
  ✅ Extended platform health monitor (/health)
  ✅ System configuration panel

```

### 🟡 Artist
```

Access    : Artist dashboard only
Login     : One-time invite code → set password → full access
Dashboard : /artist/dashboard

Registration Flow:

  1. Admin fills artist profile info (name, email, genre, bio)
  2. System generates a unique one-time invite code
  3. Code is emailed to the artist via SMTP
  4. Artist visits /artist/register?code=XXXX
  5. Artist sets password and completes Spotify-style profile
  6. Artist lands on personal dashboard

Capabilities:
  ✅ Upload songs (MP3 / WAV + metadata + cover art)
  ✅ Auto audio feature extraction via librosa on upload
  ✅ Manage albums and discography
  ✅ Set songs as public or private
  ✅ Per-track analytics (plays, likes, skips, earnings)
  ✅ Follower growth charts
  ✅ Earnings dashboard with monthly trend charts
  ✅ Public Spotify-style artist profile page

```

### 🟢 User
```

Access    : Full user features + AI recommendation page
Login     : Email + password (self-registration)
Landing   : / — existing AI recommendation page (UNCHANGED)

Registration Flow:

  1. User visits /register
  2. Enters username, email, password
  3. /onboarding Step 1 — selects favorite genres
  4. /onboarding Step 2 — selects favorite artists
  5. Lands on / — AI recommendation page
     (profile vector already seeded — cold start eliminated)

Capabilities:
  ✅ Full AI recommendation page (existing, completely unchanged)
  ✅ Like / Play / Skip (existing feedback loop, unchanged)
  ✅ Genre filter, Alpha, K, Speed, Last.fm controls (unchanged)
  ✅ Follow artists → boosts their songs in recommendations
  ✅ Add songs to playlists directly from recommendation cards
  ✅ Create and manage playlists
  ✅ View public artist profile pages
  ✅ User profile page (history, liked songs, playlists, followed artists)
  ✅ Session reset (existing, unchanged)

```

---

## 🗺️ User Journey

```

NEW USER
   │
   ▼
/register
(username + email + password)
   │
   ▼
/onboarding — Step 1
(Select favorite genres: Pop, Hip-Hop, Rock, Jazz ...)
   │
   ▼
/onboarding — Step 2
(Select favorite artists from the platform)
   │
   ▼
   / ◄─────────────────────────────────────────────────────────┐
   │                                                           │
   │  ┌──────────────────────────────────────────────────────┐ │
   │  │          EXISTING AI RECOMMENDATION PAGE             │ │
   │  │                  (UI UNCHANGED)                      │ │
   │  │                                                      │ │
   │  │  Top navbar:                                         │ │
   │  │  User | Genre | Alpha | K | Speed | Last.fm          │ │
   │  │  Refresh | Logout | 🔔 Notifications (new)           │ │
   │  │                                                      │ │
   │  │  ┌── Sidebar ─────┐  ┌── Rec Cards Grid ──────────┐ │ │
   │  │  │ Trending       │  │                            │ │ │
   │  │  │ Last.fm        │  │  [Art] Song Title          │ │ │
   │  │  │                │  │  Artist Name               │ │ │
   │  │  │ • Track 1      │  │  [Genre Tag] score X.XXX   │ │ │
   │  │  │ • Track 2      │  │  ▶ ─────────────────── 🔊  │ │ │
   │  │  │ • Track 3      │  │  Open (iTunes/Apple Music) │ │ │
   │  │  │ ...            │  │  [Play] [Like] [Skip]      │ │ │
   │  │  │                │  │  + [Add to Playlist] 🆕    │ │ │
   │  │  │ Reset History  │  │  + "Because you follow X"🆕│ │ │
   │  │  └────────────────┘  └────────────────────────────┘ │ │
   │  └──────────────────────────────────────────────────────┘ │
   │                                                           │
   ├── /user/profile        (history, liked songs, playlists)  │
   ├── /user/playlists      (manage playlists)                 │
   ├── /artist/<id>/public  (public artist profile)            │
   └── /search              (find songs and artists) ──────────┘

RETURNING USER
   │
   ▼
/login → role check
   ├── user   →  /                    (AI recommendation page)
   ├── artist →  /artist/dashboard
   └── admin  →  /admin/dashboard

ARTIST ONBOARDING FLOW
   │
Admin fills form at /admin/add-artist
   │
   ▼
System generates invite code → emails to artist
   │
   ▼
/artist/register?code=XXXX
   │
   ▼
/artist/dashboard
   ├── /artist/upload         (upload new song)
   ├── /artist/albums         (manage albums)
   └── /artist/profile        (edit profile)

```

---

## 🤖 Recommendation Algorithm

> The algorithm powers the existing unchanged recommendation page. The scoring formula has been extended with a followed-artist boost term.

### Scoring Formula

```

Score(song) = α · Similarity + (1 − α) · Popularity + β · ArtistBoost

```

| Term | Description |
|---|---|
| **α (Alpha)** | Blend weight, configurable `0.0`–`1.0` in the UI slider (unchanged) |
| **Similarity** | Cosine similarity between candidate and user profile vector |
| **Popularity** | `0.8 × base_pop + 0.2 × feedback_pop` (global signal) |
| **β (Beta)** | Fixed boost weight `0.15` applied when the song's artist is followed by the user |
| **ArtistBoost** | `1.0` if the song belongs to a followed artist, `0.0` otherwise |

### User Profile Vector

Built dynamically from interaction history **and** onboarding preferences:

$$\vec{u} = \frac{\sum_{i \in \text{events}} w_i \cdot \vec{x}_i \;+\; \sum_{j \in \text{prefs}} p_j \cdot \vec{g}_j}{\sum_i |w_i| + \sum_j |p_j|}$$

Then L2-normalized: $\hat{u} = \vec{u} / \|\vec{u}\|_2$

| Symbol | Description |
|---|---|
| $w_i$ | Interaction weight for event $i$ |
| $\vec{x}_i$ | Feature vector of interacted song $i$ |
| $p_j$ | Onboarding preference weight for genre or artist $j$ |
| $\vec{g}_j$ | Mean feature vector of genre or artist $j$ |

### Interaction Weights

| Event | Weight | Effect |
|---|---|---|
| ❤️ Like | `+2.0` | Strongly pulls future recs toward similar tracks |
| ▶️ Play | `+1.0` | Gently steers toward similar tracks |
| ⏭️ Skip | `−2.0` | Actively pushes recs away from this style |
| 🎤 Follow Artist | `+1.5` | Boosts all songs by that artist in the profile vector |
| 🎨 Onboarding Genre | `+1.0` | Seeds the profile vector before the first interaction |
| 🎨 Onboarding Artist | `+1.2` | Seeds the vector with the artist's mean track vector |

### Candidate Selection Pipeline

```

All Songs (dataset N ≈ 100k+ and artist uploads)
    → Genre filter (optional — existing UI control, unchanged)
    → Exclude seen songs (already interacted with)
    → Flag songs belonging to followed artists for β boost
    → Top-K by Popularity (pool: 5k / 10k / 20k / 50k — existing control)
    → Cosine similarity against user profile vector
    → Collaborative filtering adjustment
    → Final α-blend + β-boost scoring
    → Attach explanation tag per result
    → Return Top-K (existing K control, unchanged)

```

> **Cold Start — Eliminated**: Onboarding genre and artist selections seed the profile vector immediately. Users receive personalized recommendations from their very first page load.

> **Uploaded Songs**: Tracks uploaded by artists are vectorized at upload time using `librosa`-extracted audio features and the existing `tfidf.joblib` and `scaler.joblib`. They are indexed into the recommendation engine and treated identically to dataset songs.

---

## 💰 Earnings Model

Artists earn based on user interactions with their uploaded songs:

```python
EARNINGS_RATES = {
    'play': 0.004,   # $0.004 per stream
    'like': 0.010,   # $0.010 per like
    'skip': 0.000    # No earnings on skip
}
```

### Earnings Formula

```
Song Earnings  = (play_count × 0.004) + (like_count × 0.010)
Total Earnings = Σ Song Earnings across all of the artist's songs
```

All earnings events are written to the `earnings_log` table with a timestamp, enabling:

- Per-song earnings breakdown in the artist dashboard
- Monthly earnings trend charts
- Admin-level platform revenue overview

> **Note**: Earnings are tracked in the database. Real payment processing (e.g. Stripe) is outside the current scope but the schema is designed to support it.

---

## 🗄️ Database Schema

```sql
-- ─────────────────────────────────────────────────────
-- EXISTING TABLE (modified — user_id is now a FK)
-- ─────────────────────────────────────────────────────

CREATE TABLE events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    song_id    TEXT NOT NULL,
    event_type TEXT NOT NULL,  -- 'play' | 'like' | 'skip'
    timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ─────────────────────────────────────────────────────
-- NEW TABLES
-- ─────────────────────────────────────────────────────

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',  -- 'admin' | 'artist' | 'user'
    profile_pic   TEXT,
    is_active     BOOLEAN DEFAULT 1,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE artists (
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

CREATE TABLE songs_uploaded (
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
    -- Audio features extracted by librosa at upload time
    tempo        REAL,
    energy       REAL,
    danceability REAL,
    valence      REAL,
    FOREIGN KEY (artist_id) REFERENCES artists(id),
    FOREIGN KEY (album_id)  REFERENCES albums(id)
);

CREATE TABLE albums (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_id    INTEGER NOT NULL,
    title        TEXT NOT NULL,
    cover_art    TEXT,
    genre        TEXT,
    release_date DATE,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (artist_id) REFERENCES artists(id)
);

CREATE TABLE playlists (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    is_public   BOOLEAN DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE playlist_songs (
    playlist_id INTEGER NOT NULL,
    song_id     TEXT NOT NULL,
    position    INTEGER,
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (playlist_id, song_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id)
);

CREATE TABLE user_followed_artists (
    user_id     INTEGER NOT NULL,
    artist_id   INTEGER NOT NULL,
    followed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, artist_id),
    FOREIGN KEY (user_id)   REFERENCES users(id),
    FOREIGN KEY (artist_id) REFERENCES artists(id)
);

CREATE TABLE user_interests (
    user_id INTEGER NOT NULL,
    genre   TEXT NOT NULL,
    weight  REAL DEFAULT 1.0,
    PRIMARY KEY (user_id, genre),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE earnings_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_id  INTEGER NOT NULL,
    song_id    INTEGER NOT NULL,
    event_type TEXT NOT NULL,  -- 'play' | 'like'
    amount     REAL NOT NULL,
    timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (artist_id) REFERENCES artists(id),
    FOREIGN KEY (song_id)   REFERENCES songs_uploaded(id)
);

CREATE TABLE notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    message    TEXT NOT NULL,
    is_read    BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

---

## 📁 Project Structure

```
Music_Recommendation/
│
├── app.py                    # Flask app — core routes, startup, config
├── auth.py                   # Auth system — register, login, role middleware
├── recommender.py            # AI engine — extracted and enhanced from app.py
├── earnings.py               # Earnings calculation and logging
├── mailer.py                 # SMTP email — sends artist invite codes
├── .env                      # API keys and secrets (not committed to git)
├── events.db                 # SQLite database — all tables
│
├── routes/                   # Flask Blueprints
│   ├── admin.py              # /admin/* — dashboard, user management, artist add
│   ├── artist.py             # /artist/* — upload, analytics, profile
│   ├── user.py               # /user/* — playlists, follows, profile
│   └── api.py                # /api/* — JSON endpoints for JS calls
│
├── artifacts/                # Precomputed ML artifacts (UNCHANGED)
│   ├── songs.parquet         # Song metadata
│   ├── X_norm.npz            # Sparse normalized feature matrix
│   ├── tfidf.joblib          # TF-IDF vectorizer
│   └── scaler.joblib         # Feature scaler
│
├── data/
│   └── SpotifyFeatures.csv   # Raw Spotify dataset (source for artifacts)
│
├── uploads/                  # Artist-uploaded content (gitignored)
│   ├── songs/                # MP3 and WAV audio files
│   ├── covers/               # Album and song cover art
│   └── profiles/             # Artist profile and banner images
│
├── templates/
│   ├── base.html             # Shared dark glassmorphism base layout
│   │
│   │   ── EXISTING (COMPLETELY UNCHANGED) ───────────────────────
│   ├── index.html            # ★ AI Recommendation Page — users land here
│   │
│   │   ── NEW PAGES (same dark glassmorphism theme) ─────────────
│   ├── login.html            # Role-aware login page
│   ├── register.html         # User registration page
│   ├── onboarding.html       # Genre and artist preference selection
│   ├── search.html           # Global search results
│   │
│   ├── admin/
│   │   ├── dashboard.html    # Tableau-style analytics dashboard
│   │   ├── users.html        # User management table
│   │   ├── artists.html      # Artist management table
│   │   └── add_artist.html   # Add artist form — generates invite code
│   │
│   ├── artist/
│   │   ├── dashboard.html    # Artist earnings and analytics
│   │   ├── upload.html       # Song upload form
│   │   ├── albums.html       # Album management
│   │   └── profile_edit.html # Edit artist profile
│   │
│   └── user/
│       ├── profile.html      # User profile, history, liked songs
│       ├── playlist.html     # Playlist view and management
│       └── artist_page.html  # Public artist profile page
│
└── static/
    │   ── EXISTING (DO NOT MODIFY) ─────────────────────────────
    ├── styles.css            # ★ Dark glassmorphism theme — core styles
    │
    │   ── NEW (extend the same theme) ──────────────────────────
    ├── admin.css             # Admin dashboard extension styles
    ├── artist.css            # Artist dashboard extension styles
    ├── charts.js             # Chart.js — analytics visualizations
    └── player.js             # Enhanced audio player controls
```

---

## ⚙️ Setup & Installation

### Prerequisites

- Python **3.9+**
- pip
- SMTP email account (Gmail recommended — for artist invite codes)

### 1. Clone / enter the project

```bash
cd Music_Recommendation
```

### 2. Install dependencies

```bash
pip install flask numpy pandas scipy scikit-learn requests \
            python-dotenv pyarrow werkzeug librosa
```

> - `pyarrow` — required to read `songs.parquet`
> - `joblib` — bundled with `scikit-learn`
> - `werkzeug` — password hashing and secure file upload handling
> - `librosa` — audio feature extraction from artist-uploaded tracks

### 3. Set up environment variables

Create or edit `.env` in the project root:

```env
# ── Existing ────────────────────────────────────────────
LASTFM_API_KEY=your_lastfm_api_key_here
LASTFM_SHARED_SECRET=your_lastfm_shared_secret_here
FLASK_SECRET_KEY=your_random_secret_key_here

# ── New: Email for artist invite codes ──────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password_here
SMTP_FROM=noreply@musicapp.com

# ── New: Admin seed account ─────────────────────────────
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@musicapp.com
ADMIN_PASSWORD=change_me_on_first_run

# ── New: Earnings rates (optional override) ─────────────
EARN_PER_PLAY=0.004
EARN_PER_LIKE=0.010
```

> **Last.fm API key** is optional — the app works without it, but the trending sidebar and tag enrichment will be disabled. Get a free key at [last.fm/api](https://www.last.fm/api/account/create).

> **SMTP credentials** are optional — if not configured, invite codes are printed to the console instead of emailed.

### 4. Initialize the database

```bash
python app.py --init-db
```

> Creates all database tables and seeds the first admin account using the values in `.env`.

---

## 🔧 Configuration

### Recommendation Page Controls (Existing — Unchanged)

| Parameter | Default | Description |
|---|---|---|
| **Genre** | `All` | Filter recommendations to a specific genre |
| **Alpha (α)** | `0.85` | Blend ratio — higher = more content-based |
| **K** | `10` | Number of recommendations to return (5–30) |
| **Speed (Pool)** | `20000` | Candidate pool size — larger = more accurate but slower |
| **Last.fm Enrich** | Off | Toggle live tag fetching per track (requires API key) |

### New System Configuration

| Parameter | Default | Description |
|---|---|---|
| **Artist Boost (β)** | `0.15` | Score weight added to songs by followed artists |
| **Onboarding Genre Weight** | `1.0` | Profile vector seed weight for genre preferences |
| **Onboarding Artist Weight** | `1.2` | Profile vector seed weight for artist preferences |
| **Earn Per Play** | `$0.004` | Configurable via `.env` |
| **Earn Per Like** | `$0.010` | Configurable via `.env` |
| **Max Upload Size** | `50 MB` | Maximum audio file size for artist uploads |
| **Allowed Formats** | `MP3, WAV` | Accepted audio formats for artist uploads |

---

## 🚀 Running the App

```bash
# First time only — creates tables and seeds admin account
python app.py --init-db

# Every subsequent run
python app.py
```

The development server starts on **[http://127.0.0.1:5000](http://127.0.0.1:5000)** with hot-reload enabled.

### Where Each Role Lands After Login

| Role | Redirects To | Page Description |
|---|---|---|
| **User** | `/` | AI Recommendation Page (existing, unchanged) |
| **Artist** | `/artist/dashboard` | Artist analytics and upload dashboard |
| **Admin** | `/admin/dashboard` | Tableau-style platform analytics |

### First-Run Checklist

```
1. python app.py --init-db   → Creates all DB tables, seeds admin account
2. python app.py             → Start the development server
3. Admin logs in at /login   → Redirected to /admin/dashboard
4. Admin visits /admin/add-artist → Fills artist info → invite code generated and emailed
5. Artist opens email → visits /artist/register?code=XXXX → sets password and profile
6. New users register at /register → complete onboarding → land on AI recommendation page
```

---

## 🔌 API Endpoints

### Core Routes (Existing — Unchanged)

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | ★ AI Recommendation page — all users land here |
| `GET` | `/login` | Login page |
| `POST` | `/login` | Submit credentials → role-based redirect |
| `GET` | `/logout` | Clears session, redirects to login |
| `POST` | `/event` | Log a `play`, `like`, or `skip` event |
| `POST` | `/reset` | Delete all events for the current user |
| `GET` | `/health` | JSON health check (extended — see below) |

### New — Auth and Onboarding

| Method | Route | Description |
|---|---|---|
| `GET/POST` | `/register` | User registration page |
| `GET/POST` | `/onboarding` | Genre and artist preference selection |
| `GET` | `/search` | Global search across songs and artists |

### New — Admin Routes `/admin/*`

| Method | Route | Description |
|---|---|---|
| `GET` | `/admin/dashboard` | Tableau-style analytics dashboard |
| `GET` | `/admin/users` | User management table |
| `POST` | `/admin/users/<id>/ban` | Ban a user account |
| `POST` | `/admin/users/<id>/activate` | Activate a user account |
| `GET` | `/admin/artists` | Artist management table |
| `GET/POST` | `/admin/add-artist` | Add artist form — generates and emails invite code |
| `DELETE` | `/admin/songs/<id>` | Remove a song from the platform |
| `GET` | `/admin/analytics` | Analytics JSON data for Chart.js dashboard |

### New — Artist Routes `/artist/*`

| Method | Route | Description |
|---|---|---|
| `GET/POST` | `/artist/register` | Invite code registration and account creation |
| `GET` | `/artist/dashboard` | Artist analytics and earnings overview |
| `GET/POST` | `/artist/upload` | Song upload form and submission |
| `GET/POST` | `/artist/albums` | Album creation and management |
| `GET/POST` | `/artist/profile` | Edit artist profile information |
| `GET` | `/artist/<id>/public` | Public-facing artist profile page |

### New — User Routes `/user/*`

| Method | Route | Description |
|---|---|---|
| `GET` | `/user/profile` | User profile page |
| `GET/POST` | `/user/playlists` | View and create playlists |
| `POST` | `/user/playlists/<id>/add` | Add a song to a playlist |
| `DELETE` | `/user/playlists/<id>/songs/<sid>` | Remove a song from a playlist |
| `POST` | `/user/follow/<artist_id>` | Follow an artist |
| `DELETE` | `/user/follow/<artist_id>` | Unfollow an artist |

### New — JSON API `/api/*`

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/recommendations` | Fetch recommendation JSON (existing, extended) |
| `GET` | `/api/admin/stats` | Platform statistics for dashboard charts |
| `GET` | `/api/artist/stats/<id>` | Artist-specific analytics JSON |
| `GET` | `/api/notifications` | Unread notifications for the current user |
| `POST` | `/api/notifications/read` | Mark notifications as read |

### `/health` Response Example (Extended)

```json
{
  "ok": true,
  "songs_rows": 232725,
  "uploaded_songs": 148,
  "x_shape": [232725, 512],
  "lastfm_enabled": true,
  "total_users": 1024,
  "total_artists": 37,
  "active_sessions": 12
}
```

---

## 🌐 External APIs Used

### iTunes Search API

- **No API key required**
- Fetches 30-second MP3 audio preview URLs (`previewUrl`)
- Provides direct Apple Music / iTunes track links
- Upgrades album artwork to `600×600px`
- Cached in memory for **24 hours** per track

### Last.fm API

- **Requires `LASTFM_API_KEY`** (see [Setup](#setup--installation))
- `track.getInfo` — fetches up to 5 genre/style tags per song, album art, and direct Last.fm URL
- `chart.getTopTracks` — powers the **Trending** sidebar panel
- Cached in memory: **24 hours** for track info, **1 hour** for trending charts

### SMTP Email

- **Requires SMTP credentials in `.env`**
- Sends artist invite codes when Admin adds a new artist
- Uses Python stdlib `smtplib` and `email.mime`
- Falls back to console output if SMTP is not configured

---

## 📊 Dataset

**Source**: `data/SpotifyFeatures.csv` — a Spotify audio features dataset containing tracks with:

| Column | Description |
|---|---|
| `genre` | Music genre (e.g. Pop, Hip-Hop, Rock) |
| `artist_name` | Artist name |
| `track_name` | Track title |
| `popularity` | Spotify popularity score (0–100) |
| `acousticness`, `danceability`, `energy`, `instrumentalness`, `liveness`, `loudness`, `speechiness`, `tempo`, `valence` | Audio feature descriptors |

> The raw CSV is processed offline to generate the precomputed artifacts in `/artifacts/`.
> Artist-uploaded songs are processed at upload time via `librosa` and stored in the `songs_uploaded` table.

---

## 🗄️ Precomputed Artifacts

These files are generated from the raw dataset offline and loaded at startup:

| File | Description |
|---|---|
| `songs.parquet` | Cleaned song metadata with `song_id`, `title`, `artist`, `genre`, `base_pop`, and `text` columns |
| `X_norm.npz` | Sparse CSR matrix of L2-normalized TF-IDF + scaled audio feature vectors. Shape: `(N_songs, D_features)` |
| `tfidf.joblib` | Fitted `TfidfVectorizer` for text feature extraction |
| `scaler.joblib` | Fitted `MinMaxScaler` (or similar) for normalizing numeric audio features |

> **Important**: `X_norm.npz` row count must match `songs.parquet` row count exactly — validated at startup.
> The same `tfidf.joblib` and `scaler.joblib` are reused to vectorize artist-uploaded songs at upload time, ensuring consistent feature spaces.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3, Flask, Flask Blueprints |
| **Auth** | Werkzeug (password hashing), Flask sessions |
| **Recommender** | NumPy, SciPy (sparse matrices), scikit-learn |
| **Audio Analysis** | librosa — feature extraction for artist uploads |
| **Data** | Pandas, PyArrow (Parquet), SQLite3 |
| **HTTP / APIs** | Requests, python-dotenv |
| **Email** | smtplib + email.mime (Python stdlib) |
| **Frontend** | Jinja2, Vanilla HTML5/CSS3, Vanilla JS |
| **Charts** | Chart.js — admin and artist analytics dashboards |
| **Audio** | HTML5 `<audio>` element + iTunes Search API |
| **File Uploads** | Werkzeug secure file handling |
| **Persistence** | SQLite (`events.db`) |

---

## 🗺️ Implementation Phases

```
PHASE 1 — Foundation                              [Auth + DB]
├── Extended SQLite schema (all new tables)
├── Auth system (register / login / role middleware)
├── Role-based redirects after login
├── base.html extending the existing dark glassmorphism theme
└── Admin account seeded on --init-db

PHASE 2 — Admin Dashboard                        [Analytics + Control]
├── Tableau-style dashboard (Chart.js)
│   ├── User growth line chart (daily / weekly / monthly)
│   ├── Top songs bar chart (by plays, likes, revenue)
│   ├── Genre distribution pie chart
│   ├── Platform revenue overview cards
│   └── Real-time activity feed
├── Add artist form → invite code generation → SMTP email
├── User management table (view / ban / activate)
└── Content moderation panel (remove songs)

PHASE 3 — Artist System                          [Upload + Earnings]
├── Invite code registration flow
├── Spotify-style artist profile setup
├── Song upload (MP3 / WAV + metadata + cover art)
├── librosa audio feature extraction on upload
├── Song indexing into recommendation engine
├── Artist analytics dashboard (Chart.js)
├── Per-song and total earnings tracker
└── Public artist profile page

PHASE 4 — User System                            [Social + Playlists]
├── Registration form at /register
├── Two-step onboarding flow at /onboarding
│   ├── Step 1 — genre preference selection
│   └── Step 2 — artist follow selection
├── Profile vector seeding from onboarding selections
├── Follow / unfollow artists
├── Playlist creation and management
├── Add to Playlist button on recommendation cards
├── User profile page
└── Global search across songs and artists

PHASE 5 — AI Enhancement                         [Smarter Recs]
├── Onboarding selections → immediate profile vector seeding
├── Followed artist β boost integrated into scoring
├── Uploaded songs indexed and scored alongside dataset songs
├── Collaborative filtering adjustment layer
├── Explanation tags rendered on each recommendation card
└── Notifications triggered on new uploads from followed artists

PHASE 6 — Polish and Production                  [Final]
├── In-app notification system
├── Mobile-responsive layout adjustments
├── Performance optimisation (query caching, DB indexing)
├── Error handling and structured logging
└── Production WSGI deployment via Gunicorn
```

---

## 📝 Notes

- **★ The AI Recommendation Page (`index.html`) is 100% unchanged** — the same UI, the same controls (Genre, Alpha, K, Speed, Last.fm Enrich, Refresh, Logout, Reset History), and the same behavior as the original build. All new features are purely additive.
- **UI Consistency** — Every new page (admin, artist, user) extends `base.html` and uses the same dark glassmorphism theme as `index.html`. The file `styles.css` is never modified.
- **Minimal additions to the recommendation page** — the only new elements are an "Add to Playlist" button on each card, an explanation tag badge, and a notification bell in the top navbar. All are non-intrusive.
- **Interaction events** are persisted to SQLite, so user history survives server restarts.
- **iTunes audio previews** are 30 seconds and may not be available for every track.
- **Invite codes** are single-use — invalidated immediately once an artist completes registration.
- **Admin account** is seeded once on `--init-db` from `.env` values. Change the password after the first login.
- **`uploads/`** directory is excluded from version control via `.gitignore`.
- For production deployment, replace the development server with a WSGI server:

  ```bash
  gunicorn -w 4 -b 0.0.0.0:5000 app:app
  ```

---

*Built with Flask · Powered by Spotify Features Dataset · Audio previews via iTunes Search API · Tags via Last.fm · Analytics via Chart.js · Audio analysis via librosa*

```

---
