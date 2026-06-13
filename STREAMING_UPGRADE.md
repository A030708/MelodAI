🎵 MelodAI — Full Streaming Upgrade Plan
Migration: iTunes 30-Second Previews → Spotify-Style Full Audio Streaming
📖 Table of Contents
Overview
Current State vs Target State
Architecture Changes
New Dependencies
Database Schema Changes
File Storage Structure
Backend Implementation
Frontend Implementation
Queue System
Hybrid Strategy
Implementation Phases
File Changes Summary
Important Notes for Agent
📌 Overview
The current application uses the iTunes Search API to fetch 30-second audio preview URLs for song playback. This must be upgraded to a Spotify-style full streaming system where:

Artists upload full-length songs (MP3/WAV) via their dashboard
The server transcodes uploads into streaming-ready formats at two quality levels
A /stream/<song_id> endpoint serves audio with HTTP Range request support enabling seeking, buffering, and adaptive quality switching
The existing HTML5 audio player in index.html is updated to consume the new stream endpoint
iTunes preview URLs remain as a fallback for dataset songs that have no uploaded equivalent
The entire change is additive — the existing UI of index.html is preserved exactly and only the audio source logic changes
🔄 Current State vs Target State
Current State — Problem
text

User clicks Play
      │
      ▼
App calls iTunes Search API
      │
      ▼
Gets 30-second preview URL (external CDN)
      │
      ▼
HTML5 audio tag plays 30-second clip
      │
      ▼
SONG ENDS after 30 seconds
No seeking possible
No full playback
No queue continuity
No auto-advance
Target State — Spotify-Like
text

User clicks Play
      │
      ▼
App checks: Is this an uploaded song?
      │
      ├── YES (uploaded + transcoded)
      │     │
      │     ▼
      │   GET /stream/<song_id>?q=medium
      │   Flask reads file in byte chunks
      │   HTTP Range headers enable seeking
      │   Full song plays (3 to 5 minutes)
      │   Progress bar shows real duration
      │   User can seek to any timestamp
      │   Song ends → auto-advance to next
      │
      └── NO (dataset song, no upload)
            │
            ▼
          iTunes preview URL (fallback)
          30-second clip as before
          Badge shows "30s Preview"
🏗️ Architecture Changes
Before
text

Browser audio tag
      │
      └── External iTunes CDN (30 second preview only)
After
text

Browser audio tag
      │
      ├── /stream/<id>?q=high    Uploaded songs FULL LENGTH
      │        │
      │        └── Flask streams from:
      │             uploads/encoded/<song_id>/high.mp3
      │             uploads/encoded/<song_id>/medium.mp3
      │
      └── iTunes preview URL     Dataset songs FALLBACK 30s
Full Updated Architecture Diagram
text

┌──────────────────────────────────────────────────────────────┐
│                         Browser                              │
│           HTML5 audio element + Queue Manager JS             │
│           Dark glassmorphism UI — completely unchanged       │
└──────────────────────┬───────────────────────────────────────┘
                       │ HTTP with Range headers
┌──────────────────────▼───────────────────────────────────────┐
│                   Flask Web Server                           │
│                                                              │
│  Existing routes — COMPLETELY UNCHANGED:                     │
│  GET  /                                                      │
│  GET  /login                                                 │
│  POST /login                                                 │
│  GET  /logout                                                │
│  POST /event                                                 │
│  POST /reset                                                 │
│  GET  /health                                                │
│                                                              │
│  New routes ADDED in this upgrade:                           │
│  GET  /stream/<song_id>     Full audio stream endpoint       │
│  POST /queue/add            Add song to play queue           │
│  GET  /queue                Get current queue contents       │
│  GET  /queue/next           Pop and return next song         │
│  POST /queue/clear          Clear the full queue             │
└──────┬───────────────────────────────────────────────────────┘
       │
       ├── routes/artist.py — upload route MODIFIED
       │   Now: Receive file → Save raw → Transcode → Save encoded
       │   Previously: Receive file → Save only
       │
       └── File Storage Layout
           uploads/
           ├── raw/
           │   └── original master files WAV FLAC MP3
           ├── encoded/
           │   └── <song_id>/
           │       ├── high.mp3      320kbps WiFi desktop
           │       └── medium.mp3    128kbps mobile slow network
           ├── covers/               unchanged
           └── profiles/             unchanged
📦 New Dependencies
Python Package
Bash

pip install pydub
System-Level ffmpeg Installation
pydub is a Python wrapper around ffmpeg. ffmpeg must be installed at the operating system level separately.

Bash

# Ubuntu or Debian

sudo apt-get install ffmpeg

# macOS with Homebrew

brew install ffmpeg

# Windows

# Download installer from <https://ffmpeg.org/download.html>

# Add the bin folder to your system PATH environment variable

# Restart terminal after adding to PATH

# Verify with: ffmpeg -version

Updated Full pip Install Command
Replace the existing install command in README.md with:

Bash

pip install flask numpy pandas scipy scikit-learn requests \
            python-dotenv pyarrow werkzeug librosa pydub
Verify ffmpeg is Working
Bash

ffmpeg -version

# Should print version info — if command not found, PATH is not set correctly

🗄️ Database Schema Changes
The following ALTER TABLE statements add new columns to the existing songs_uploaded table. Do NOT drop or modify any existing columns. These are purely additive changes.

Run These on Existing events.db
SQL

ALTER TABLE songs_uploaded
    ADD COLUMN master_file_path TEXT;

ALTER TABLE songs_uploaded
    ADD COLUMN file_path_high TEXT;

ALTER TABLE songs_uploaded
    ADD COLUMN file_path_medium TEXT;

ALTER TABLE songs_uploaded
    ADD COLUMN is_transcoded BOOLEAN DEFAULT 0;

ALTER TABLE songs_uploaded
    ADD COLUMN codec TEXT DEFAULT 'mp3';

ALTER TABLE songs_uploaded
    ADD COLUMN bitrate_high INTEGER DEFAULT 320;

ALTER TABLE songs_uploaded
    ADD COLUMN bitrate_medium INTEGER DEFAULT 128;

ALTER TABLE songs_uploaded
    ADD COLUMN stream_count INTEGER DEFAULT 0;
Column Descriptions
Column Type Description
master_file_path TEXT Path to the original uploaded file before transcoding. Example: uploads/raw/uuid_song.wav
file_path_high TEXT Path to 320kbps transcoded MP3. Example: uploads/encoded/42/high.mp3
file_path_medium TEXT Path to 128kbps transcoded MP3. Example: uploads/encoded/42/medium.mp3
is_transcoded BOOLEAN 0 while processing, 1 when both encoded files are ready to stream
codec TEXT Audio codec used. Currently always mp3. Future values: opus, aac
bitrate_high INTEGER Bitrate in kbps for the high quality file. Default 320
bitrate_medium INTEGER Bitrate in kbps for the medium quality file. Default 128
stream_count INTEGER Number of times the stream endpoint was actually hit. Separate from play_count which is user button clicks
Complete Updated songs_uploaded Schema for Reference
SQL

CREATE TABLE songs_uploaded (
    -- EXISTING COLUMNS — DO NOT CHANGE ANY OF THESE
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_id       INTEGER NOT NULL,
    album_id        INTEGER,
    title           TEXT NOT NULL,
    genre           TEXT,
    duration        REAL,
    file_path       TEXT NOT NULL,
    cover_art       TEXT,
    play_count      INTEGER DEFAULT 0,
    like_count      INTEGER DEFAULT 0,
    skip_count      INTEGER DEFAULT 0,
    earnings        REAL DEFAULT 0.0,
    is_public       BOOLEAN DEFAULT 1,
    uploaded_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    tempo           REAL,
    energy          REAL,
    danceability    REAL,
    valence         REAL,

    -- NEW COLUMNS ADDED IN THIS STREAMING UPGRADE
    master_file_path  TEXT,
    file_path_high    TEXT,
    file_path_medium  TEXT,
    is_transcoded     BOOLEAN DEFAULT 0,
    codec             TEXT DEFAULT 'mp3',
    bitrate_high      INTEGER DEFAULT 320,
    bitrate_medium    INTEGER DEFAULT 128,
    stream_count      INTEGER DEFAULT 0,

    FOREIGN KEY (artist_id) REFERENCES artists(id),
    FOREIGN KEY (album_id)  REFERENCES albums(id)
);
📁 File Storage Structure
Create this directory structure inside the project root. The uploads/raw and uploads/encoded directories are new. The covers and profiles directories already exist.

text

Music_Recommendation/
│
└── uploads/
    │
    ├── raw/
    │   └── Store original master files here before transcoding
    │       Naming pattern: uuid4_original_filename.wav
    │       Example: a1b2c3d4_my_song.wav
    │       Keep these files as backup masters permanently
    │
    ├── encoded/
    │   └── <song_id>/
    │       ├── high.mp3
    │       │   320kbps MP3 for WiFi and desktop users
    │       │
    │       └── medium.mp3
    │           128kbps MP3 for mobile and slower networks
    │
    │   Full example path:
    │   uploads/encoded/42/high.mp3
    │   uploads/encoded/42/medium.mp3
    │
    ├── covers/
    │   └── Album and song cover art — already exists — unchanged
    │
    └── profiles/
        └── Artist profile and banner images — already exists — unchanged
Add to .gitignore
text

uploads/raw/
uploads/encoded/
uploads/covers/
uploads/profiles/
Create Directories in Python at Startup
Add this to app.py startup section:

Python

import os

# Create upload directories if they do not exist

os.makedirs(os.path.join('uploads', 'raw'), exist_ok=True)
os.makedirs(os.path.join('uploads', 'encoded'), exist_ok=True)
os.makedirs(os.path.join('uploads', 'covers'), exist_ok=True)
os.makedirs(os.path.join('uploads', 'profiles'), exist_ok=True)
🔧 Backend Implementation
File: app.py
Action: ADD these new routes at the bottom of the file. Do NOT remove or modify any existing routes.
Python

import os
import re
from flask import send_file, request, jsonify, session, Response

# ==============================================================

# STREAMING ENDPOINT

# Serves full audio files with HTTP Range request support

# HTTP Range requests allow the browser to

# - Seek to any point in the track without re-downloading

# - Show accurate buffering progress in the audio player

# - Resume from a specific byte position after network pause

# ==============================================================

@app.route('/stream/<int:song_id>')
def stream_song(song_id):
    """
    Spotify-style audio streaming endpoint.

    Supports HTTP Range requests so the HTML5 audio element
    can seek, buffer, and display accurate progress.

    Query parameters:
        q=high    serves 320kbps MP3
        q=medium  serves 128kbps MP3 (default)

    Returns:
        206 Partial Content when Range header is present (seeking)
        200 OK with full file on first load (no Range header)
        404 if song record or audio file does not exist
        403 if song is private or user is not logged in
        503 if song upload is still being transcoded
    """

    # Require authenticated session — no anonymous streaming
    if 'username' not in session:
        return jsonify({"error": "Login required"}), 403

    # Fetch song record from database
    conn = get_db_connection()
    song = conn.execute(
        'SELECT * FROM songs_uploaded WHERE id = ?',
        (song_id,)
    ).fetchone()
    conn.close()

    # Song must exist
    if not song:
        return jsonify({"error": "Song not found"}), 404

    # Song must be set to public
    if not song['is_public']:
        return jsonify({"error": "This song is private"}), 403

    # Song must have finished transcoding
    if not song['is_transcoded']:
        return jsonify({
            "error": "Song is still processing. Try again shortly."
        }), 503

    # Select quality tier based on query parameter
    quality = request.args.get('q', 'medium')

    if quality == 'high':
        file_path = os.path.join(
            'uploads', 'encoded', str(song_id), 'high.mp3'
        )
    else:
        file_path = os.path.join(
            'uploads', 'encoded', str(song_id), 'medium.mp3'
        )

    # Verify the physical file exists on disk
    if not os.path.exists(file_path):
        return jsonify({"error": "Audio file not found on disk"}), 404

    # Increment stream delivery counter
    conn = get_db_connection()
    conn.execute(
        '''UPDATE songs_uploaded
           SET stream_count = stream_count + 1
           WHERE id = ?''',
        (song_id,)
    )
    conn.commit()
    conn.close()

    # Get total file size in bytes
    file_size = os.path.getsize(file_path)

    # Check for Range header — sent by browser when user seeks
    range_header = request.headers.get('Range', None)

    if range_header:
        # Parse the Range header value
        # Format is: bytes=START-END or bytes=START-
        byte1 = 0
        byte2 = file_size - 1

        match = re.search(r'bytes=(\d+)-(\d*)', range_header)

        if match:
            groups = match.groups()
            byte1 = int(groups[0])
            if groups[1]:
                byte2 = int(groups[1])

        # Calculate length of the requested byte range
        length = byte2 - byte1 + 1

        # Read only the requested byte range from the file
        with open(file_path, 'rb') as audio_file:
            audio_file.seek(byte1)
            data = audio_file.read(length)

        # Build 206 Partial Content response for Range request
        response = Response(
            data,
            status=206,
            mimetype='audio/mpeg'
        )
        response.headers['Content-Range'] = (
            f'bytes {byte1}-{byte2}/{file_size}'
        )
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Content-Length'] = str(length)
        response.headers['Content-Type'] = 'audio/mpeg'
        response.headers['Cache-Control'] = 'no-cache'

        return response

    else:
        # No Range header on first request — serve entire file
        response = send_file(
            file_path,
            mimetype='audio/mpeg',
            conditional=True,
            as_attachment=False
        )
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Content-Length'] = str(file_size)
        response.headers['Cache-Control'] = 'no-cache'

        return response

# ==============================================================

# QUEUE SYSTEM

# In-session play queue stored in server memory

# Each user session has its own isolated queue

# In production replace play_queues dict with Redis

# ==============================================================

# In-memory queue store — keyed by username

play_queues = {}

@app.route('/queue/add', methods=['POST'])
def add_to_queue():
    """
    Add a song to the current user's play queue.

    Request body JSON:
        song_id     int or string   ID of the song to add
        source      string          'upload' or 'dataset'
        preview_url string          iTunes URL if dataset song
    """
    if 'username' not in session:
        return jsonify({"error": "Login required"}), 403

    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    song_id = data.get('song_id')
    source = data.get('source', 'dataset')
    preview_url = data.get('preview_url', None)

    if not song_id:
        return jsonify({"error": "song_id is required"}), 400

    user_key = session['username']

    if user_key not in play_queues:
        play_queues[user_key] = []

    play_queues[user_key].append({
        "song_id": song_id,
        "source": source,
        "preview_url": preview_url
    })

    return jsonify({
        "status": "added",
        "queue_length": len(play_queues[user_key])
    })

@app.route('/queue', methods=['GET'])
def get_queue():
    """Return the current user's full play queue as JSON array."""
    if 'username' not in session:
        return jsonify({"error": "Login required"}), 403

    user_key = session['username']
    return jsonify(play_queues.get(user_key, []))

@app.route('/queue/next', methods=['GET'])
def get_next_in_queue():
    """
    Pop the first song from the queue and return it.
    Called by the frontend JavaScript when the current song ends.
    Returns status empty with null next when queue is empty.
    """
    if 'username' not in session:
        return jsonify({"error": "Login required"}), 403

    user_key = session['username']
    queue = play_queues.get(user_key, [])

    if not queue:
        return jsonify({"status": "empty", "next": None})

    next_song = queue.pop(0)
    play_queues[user_key] = queue

    return jsonify({"status": "ok", "next": next_song})

@app.route('/queue/clear', methods=['POST'])
def clear_queue():
    """Clear all songs from the current user's play queue."""
    if 'username' not in session:
        return jsonify({"error": "Login required"}), 403

    user_key = session['username']
    play_queues[user_key] = []

    return jsonify({"status": "cleared", "queue_length": 0})
File: routes/artist.py
Action: MODIFY the existing upload route to add transcoding pipeline after file save
Python

import os
import uuid
import librosa
from pydub import AudioSegment
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, jsonify, session

artist_bp = Blueprint('artist', __name__, url_prefix='/artist')

# Allowed audio formats for upload

ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'flac', 'm4a', 'aiff'}

# Storage directory constants

RAW_FOLDER     = os.path.join('uploads', 'raw')
ENCODED_FOLDER = os.path.join('uploads', 'encoded')

def allowed_audio_file(filename):
    """Return True if filename has an allowed audio extension."""
    return (
        '.' in filename and
        filename.rsplit['.', 1](1).lower() in ALLOWED_AUDIO_EXTENSIONS
    )

def transcode_audio(raw_path, song_id):
    """
    Transcode an uploaded audio file into two streaming-ready
    MP3 files at different quality levels.

    This function is called after the initial DB record is
    inserted so the song_id is available for folder naming.

    Args:
        raw_path  : Absolute or relative path to the raw master file
        song_id   : Integer database ID of the songs_uploaded record

    Returns:
        dict with keys:
            file_path_high    relative path to 320kbps file
            file_path_medium  relative path to 128kbps file
            duration          float duration in seconds
            is_transcoded     True on success
        None if transcoding failed for any reason
    """
    try:
        # Load the audio file — pydub detects format automatically
        audio = AudioSegment.from_file(raw_path)

        # Create output directory named after the song DB ID
        encoded_dir = os.path.join(ENCODED_FOLDER, str(song_id))
        os.makedirs(encoded_dir, exist_ok=True)

        high_path   = os.path.join(encoded_dir, 'high.mp3')
        medium_path = os.path.join(encoded_dir, 'medium.mp3')

        # Export high quality version at 320kbps
        audio.export(high_path, format='mp3', bitrate='320k')

        # Export medium quality version at 128kbps
        audio.export(medium_path, format='mp3', bitrate='128k')

        # Calculate duration from pydub length in milliseconds
        duration_seconds = len(audio) / 1000.0

        return {
            'file_path_high'  : os.path.join('encoded', str(song_id), 'high.mp3'),
            'file_path_medium': os.path.join('encoded', str(song_id), 'medium.mp3'),
            'duration'        : duration_seconds,
            'is_transcoded'   : True
        }

    except Exception as transcode_error:
        print(f'[Transcode Error] song_id={song_id} : {transcode_error}')
        return None

@artist_bp.route('/upload', methods=['GET', 'POST'])
def upload_song():
    """
    Artist song upload endpoint with transcoding pipeline.

    Full workflow on POST:
        Step 1  Validate audio file type and presence
        Step 2  Read metadata fields from form
        Step 3  Save raw master file to uploads/raw/
        Step 4  Insert initial DB record with is_transcoded=0
        Step 5  Call transcode_audio() to create encoded files
        Step 6  Extract audio features with librosa
        Step 7  Update DB record with encoded paths and features
        Step 8  Return JSON success response with song_id

    On GET:
        Render the upload form template
    """

    if request.method == 'GET':
        return render_template('artist/upload.html')

    # ----------------------------------------------------------
    # STEP 1 — Validate uploaded file
    # ----------------------------------------------------------

    if 'audio' not in request.files:
        return jsonify({"error": "No audio file in request"}), 400

    file = request.files['audio']

    if not file or file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if not allowed_audio_file(file.filename):
        return jsonify({
            "error": (
                "Invalid file type. "
                "Allowed formats: MP3, WAV, FLAC, M4A, AIFF"
            )
        }), 400

    # ----------------------------------------------------------
    # STEP 2 — Read form metadata
    # ----------------------------------------------------------

    title     = request.form.get('title', '').strip()
    genre     = request.form.get('genre', '').strip()
    album_id  = request.form.get('album_id', None)
    is_public = request.form.get('is_public', '1') == '1'

    if not title:
        return jsonify({"error": "Song title is required"}), 400

    # ----------------------------------------------------------
    # STEP 3 — Save raw master file to uploads/raw/
    # ----------------------------------------------------------

    os.makedirs(RAW_FOLDER, exist_ok=True)

    # Generate unique filename to avoid collisions
    raw_filename = f"{uuid.uuid4()}_{secure_filename(file.filename)}"
    raw_path     = os.path.join(RAW_FOLDER, raw_filename)
    file.save(raw_path)

    # ----------------------------------------------------------
    # STEP 4 — Insert initial DB record with is_transcoded = 0
    # ----------------------------------------------------------

    conn = get_db_connection()

    # Get artist ID from session user
    artist = conn.execute(
        'SELECT id FROM artists WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()

    if not artist:
        conn.close()
        return jsonify({"error": "Artist profile not found"}), 404

    cursor = conn.execute(
        '''INSERT INTO songs_uploaded
               (artist_id, album_id, title, genre, file_path,
                master_file_path, is_public, is_transcoded)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0)''',
        (
            artist['id'],
            album_id,
            title,
            genre,
            raw_path,
            raw_path,
            is_public
        )
    )
    song_id = cursor.lastrowid
    conn.commit()

    # ----------------------------------------------------------
    # STEP 5 — Transcode audio into high and medium MP3 files
    # ----------------------------------------------------------

    transcode_result = transcode_audio(raw_path, song_id)

    if not transcode_result:
        # Transcoding failed — record exists but is_transcoded stays 0
        # Artist can retry by re-uploading
        conn.close()
        return jsonify({
            "status"  : "partial",
            "song_id" : song_id,
            "warning" : (
                "File saved but transcoding failed. "
                "Please check ffmpeg is installed and retry."
            )
        }), 500

    # ----------------------------------------------------------
    # STEP 6 — Extract audio features with librosa
    # ----------------------------------------------------------

    try:
        y, sr = librosa.load(raw_path, sr=None, mono=True)

        tempo_array, _ = librosa.beat.beat_track(y=y, sr=sr)
        tempo        = float(tempo_array)
        energy       = float(librosa.feature.rms(y=y).mean())
        danceability = float(
            librosa.feature.zero_crossing_rate(y).mean()
        )
        valence      = float(
            librosa.feature.spectral_centroid(y=y, sr=sr).mean()
        )

    except Exception as librosa_error:
        print(f'[Librosa Error] song_id={song_id} : {librosa_error}')
        # Use zero defaults if librosa fails — do not block upload
        tempo        = 0.0
        energy       = 0.0
        danceability = 0.0
        valence      = 0.0

    # ----------------------------------------------------------
    # STEP 7 — Update DB record with encoded paths and features
    # ----------------------------------------------------------

    conn.execute(
        '''UPDATE songs_uploaded SET
               file_path_high   = ?,
               file_path_medium = ?,
               duration         = ?,
               is_transcoded    = 1,
               tempo            = ?,
               energy           = ?,
               danceability     = ?,
               valence          = ?
           WHERE id = ?''',
        (
            transcode_result['file_path_high'],
            transcode_result['file_path_medium'],
            transcode_result['duration'],
            tempo,
            energy,
            danceability,
            valence,
            song_id
        )
    )
    conn.commit()
    conn.close()

    # ----------------------------------------------------------
    # STEP 8 — Return success response
    # ----------------------------------------------------------

    return jsonify({
        "status"    : "success",
        "song_id"   : song_id,
        "title"     : title,
        "duration"  : transcode_result['duration'],
        "transcoded": True,
        "message"   : f"'{title}' uploaded and ready to stream"
    })
🖥️ Frontend Implementation
File: templates/index.html
Action: MODIFY audio source logic only inside the existing audio card HTML. Do NOT change layout, CSS classes, control bar, sidebar, or any other element.
Find the existing audio element block in each recommendation card and replace only the audio source part with the following hybrid logic. Everything else in the card stays identical.

Existing pattern to find and replace:
HTML

<audio controls preload="metadata">
    <source src="{{ song.preview_url }}" type="audio/mp4">
    Preview not available.
</audio>
Replace with this hybrid audio block:
HTML

<div class="audio-wrapper">

    {% if song.source == 'upload' and song.is_transcoded %}
        <span class="badge badge-full">🎵 Full Track</span>
    {% elif song.source == 'upload' and not song.is_transcoded %}
        <span class="badge badge-processing">⏳ Processing...</span>
    {% else %}
        <span class="badge badge-preview">🎵 30s Preview</span>
    {% endif %}

    {% if song.source == 'upload' and song.is_transcoded %}

        <audio
            class="rec-audio-player"
            controls
            preload="metadata"
            data-song-id="{{ song.id }}"
            data-source="upload"
            data-preview-url="{{ song.preview_url or '' }}">
            <source
                src="/stream/{{ song.id }}?q=medium"
                type="audio/mpeg"
                data-high-src="/stream/{{ song.id }}?q=high">
        </audio>

        <div class="quality-toggle">
            <button
                class="btn-quality"
                data-song-id="{{ song.id }}"
                data-current-quality="medium"
                onclick="toggleQuality(this)">
                📶 Medium Quality
            </button>
        </div>

    {% elif song.source == 'upload' and not song.is_transcoded %}

        <p class="processing-text">
            This track is still being processed. Check back shortly.
        </p>

    {% else %}

        {% if song.preview_url %}
            <audio
                class="rec-audio-player"
                controls
                preload="metadata"
                data-song-id="{{ song.id }}"
                data-source="dataset"
                data-preview-url="{{ song.preview_url }}">
                <source src="{{ song.preview_url }}" type="audio/mp4">
            </audio>
        {% else %}
            <p class="no-preview-text">Preview not available.</p>
        {% endif %}

    {% endif %}

    <div class="buffer-bar-container">
        <div class="buffer-bar" data-song-id="{{ song.id }}"></div>
    </div>

</div>
File: templates/base.html
Action: ADD one script tag before the closing body tag. Do NOT change anything else.
HTML

    <!-- Enhanced audio player — streaming and queue management -->
    <script src="{{ url_for('static', filename='player.js') }}"></script>
</body>
</html>
File: static/player.js
Action: CREATE this new file. It does not exist yet.
JavaScript

/**

* player.js
* MelodAI Enhanced Audio Player and Queue Manager
*
* Responsibilities:
* Single player enforcement — only one audio plays at a time
* Auto-advance         — next song plays when current ends
* Quality toggle       — switch between high and medium streams
* Queue management     — add to queue, pop next from queue
* Buffer visualization — show buffered bytes as progress bar
* Error fallback       — if stream fails, try iTunes preview URL
* Toast notifications  — non-intrusive status messages
 */

'use strict';

// ================================================================
// SINGLE PLAYER ENFORCEMENT
// When any audio element starts playing, pause all others.
// This prevents multiple songs playing simultaneously.
// ================================================================

let currentPlayer = null;

document.addEventListener('DOMContentLoaded', function () {

    const allPlayers = document.querySelectorAll('.rec-audio-player');

    allPlayers.forEach(function (player) {

        // Pause all other players when this one starts
        player.addEventListener('play', function () {
            if (currentPlayer && currentPlayer !== player) {
                currentPlayer.pause();
            }
            currentPlayer = player;
        });

        // Auto-advance when song finishes
        player.addEventListener('ended', function () {
            handleSongEnded(player);
        });

        // Update buffer progress bar
        player.addEventListener('progress', function () {
            updateBufferProgress(player);
        });

        // Handle stream errors with iTunes fallback
        player.addEventListener('error', function (e) {
            handleStreamError(player, e);
        });

    });

});

// ================================================================
// AUTO-ADVANCE
// When a song ends, check queue first.
// If queue is empty, ask the AI recommendation engine for next.
// ================================================================

function handleSongEnded(player) {
    console.log('[Player] Song ended — checking queue');

    fetch('/queue/next')
        .then(function (response) { return response.json(); })
        .then(function (data) {

            if (data.status === 'empty' || !data.next) {
                console.log('[Player] Queue empty — fetching AI recommendation');
                fetchNextRecommendation(player);
                return;
            }

            var next = data.next;

            if (next.source === 'upload') {
                player.src = '/stream/' + next.song_id + '?q=medium';
            } else if (next.preview_url) {
                player.src = next.preview_url;
            } else {
                console.log('[Player] Next song has no playable source');
                return;
            }

            player.load();
            player.play().catch(function (e) {
                console.warn('[Player] Autoplay blocked by browser:', e);
            });

        })
        .catch(function (err) {
            console.error('[Player] Queue fetch failed:', err);
        });
}

// ================================================================
// QUALITY TOGGLE
// Switch between 320kbps high and 128kbps medium streams.
// Restores playback position after the source change.
// Only applies to uploaded songs served from /stream/ endpoint.
// ================================================================

function toggleQuality(btn) {

    var songId         = btn.dataset.songId;
    var currentQuality = btn.dataset.currentQuality;

    var player = document.querySelector(
        '.rec-audio-player[data-song-id="' + songId + '"]'
    );

    if (!player) {
        console.warn('[Quality] No player found for song_id=' + songId);
        return;
    }

    // Remember current position and playing state
    var savedTime  = player.currentTime;
    var wasPlaying = !player.paused;

    // Switch source URL to the other quality
    if (currentQuality === 'medium') {
        player.src = '/stream/' + songId + '?q=high';
        btn.dataset.currentQuality = 'high';
        btn.textContent = '📶 High Quality';
    } else {
        player.src = '/stream/' + songId + '?q=medium';
        btn.dataset.currentQuality = 'medium';
        btn.textContent = '📶 Medium Quality';
    }

    // After new source loads, restore position and resume
    player.addEventListener('canplay', function restorePosition() {
        player.currentTime = savedTime;
        if (wasPlaying) {
            player.play().catch(function (e) {
                console.warn('[Quality] Resume after switch blocked:', e);
            });
        }
        player.removeEventListener('canplay', restorePosition);
    });

    player.load();
}

// ================================================================
// ADD TO QUEUE
// Called from onclick on recommendation card queue button.
// Sends song metadata to /queue/add endpoint.
// ================================================================

function addToQueue(songId, source, previewUrl) {

    fetch('/queue/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            song_id    : songId,
            source     : source,
            preview_url: previewUrl || null
        })
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        showToast('Added to queue — ' + data.queue_length + ' songs');
    })
    .catch(function (err) {
        console.error('[Queue] Add to queue failed:', err);
        showToast('Could not add to queue');
    });

}

// ================================================================
// BUFFER PROGRESS VISUALIZATION
// Shows how many bytes of the current track are buffered.
// Finds the matching .buffer-bar element by song-id and
// sets its CSS width as a percentage of total duration.
// ================================================================

function updateBufferProgress(player) {

    if (!player.buffered || player.buffered.length === 0) {
        return;
    }

    try {
        var bufferedEnd = player.buffered.end(player.buffered.length - 1);
        var duration    = player.duration;

        if (duration && duration > 0) {
            var bufferedPercent = (bufferedEnd / duration) * 100;
            var songId          = player.dataset.songId;
            var bufferBar       = document.querySelector(
                '.buffer-bar[data-song-id="' + songId + '"]'
            );
            if (bufferBar) {
                bufferBar.style.width = bufferedPercent + '%';
            }
        }
    } catch (e) {
        // Buffered range may not exist during initial load — ignore silently
    }

}

// ================================================================
// STREAM ERROR FALLBACK
// If the /stream/ endpoint returns an error or the file is
// unavailable, fall back to the iTunes preview URL if present.
// Updates the badge to show the user they are hearing a preview.
// ================================================================

function handleStreamError(player, error) {

    var previewUrl = player.dataset.previewUrl;
    var source     = player.dataset.source;
    var songId     = player.dataset.songId;

    console.warn(
        '[Player] Stream error for source=' + source +
        ' song_id=' + songId, error
    );

    if (previewUrl && player.src !== previewUrl) {
        console.log('[Player] Falling back to iTunes preview URL');

        player.src = previewUrl;
        player.load();

        // Update badge to reflect fallback state
        var badge = document.querySelector(
            '.badge[data-song-id="' + songId + '"]'
        );
        if (badge) {
            badge.textContent = '🎵 30s Preview (fallback)';
            badge.classList.remove('badge-full');
            badge.classList.add('badge-preview');
        }

        showToast('Stream unavailable — playing 30s preview');
    } else {
        showToast('Audio unavailable for this track');
    }

}

// ================================================================
// FETCH NEXT AI RECOMMENDATION
// When queue is empty and song ends, ask the recommendation
// API for the next best song and play it automatically.
// ================================================================

function fetchNextRecommendation(player) {

    fetch('/api/recommendations?limit=1')
        .then(function (r) { return r.json(); })
        .then(function (data) {

            if (!data.songs || data.songs.length === 0) {
                console.log('[AutoRec] No recommendations returned');
                return;
            }

            var next = data.songs[0];

            if (next.source === 'upload' && next.is_transcoded) {
                player.src = '/stream/' + next.id + '?q=medium';
            } else if (next.preview_url) {
                player.src = next.preview_url;
            } else {
                console.log('[AutoRec] Next rec has no playable source');
                return;
            }

            player.load();
            player.play().catch(function (e) {
                console.warn('[AutoRec] Autoplay blocked:', e);
            });

        })
        .catch(function (err) {
            console.error('[AutoRec] Failed to fetch recommendation:', err);
        });

}

// ================================================================
// TOAST NOTIFICATION
// Small popup message at the bottom center of the screen.
// Matches the dark glassmorphism theme.
// Automatically fades out after the specified duration.
// ================================================================

function showToast(message, duration) {

    duration = duration || 2500;

    var toast = document.getElementById('melodai-toast');

    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'melodai-toast';
        toast.style.cssText = [
            'position: fixed',
            'bottom: 28px',
            'left: 50%',
            'transform: translateX(-50%)',
            'background: rgba(255, 255, 255, 0.12)',
            'backdrop-filter: blur(14px)',
            '-webkit-backdrop-filter: blur(14px)',
            'color: #ffffff',
            'padding: 10px 26px',
            'border-radius: 24px',
            'font-size: 13px',
            'font-weight: 500',
            'letter-spacing: 0.3px',
            'z-index: 9999',
            'border: 1px solid rgba(255, 255, 255, 0.18)',
            'box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3)',
            'transition: opacity 0.35s ease',
            'pointer-events: none'
        ].join(';');
        document.body.appendChild(toast);
    }

    toast.textContent = message;
    toast.style.opacity = '1';

    setTimeout(function () {
        toast.style.opacity = '0';
    }, duration);

}
File: static/styles.css
Action: APPEND only — add these classes at the very bottom of the existing file. Do NOT modify any existing CSS rules above.
CSS

/*=============================================================
   STREAMING PLAYER ADDITIONS
   Appended to existing styles.css
   Nothing above this comment has been changed
   =============================================================*/

/*Full track badge — green like Spotify*/
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    margin-bottom: 6px;
    letter-spacing: 0.3px;
    user-select: none;
}

.badge-full {
    background  : rgba(29, 185, 84, 0.18);
    color       : #1db954;
    border      : 1px solid rgba(29, 185, 84, 0.35);
}

/*Preview badge — amber warning tone*/
.badge-preview {
    background  : rgba(255, 165, 0, 0.14);
    color       : #ffa500;
    border      : 1px solid rgba(255, 165, 0, 0.28);
}

/*Processing badge — blue pulsing animation*/
.badge-processing {
    background  : rgba(100, 120, 255, 0.14);
    color       : rgba(160, 170, 255, 0.9);
    border      : 1px solid rgba(100, 120, 255, 0.28);
    animation   : melodai-pulse 1.6s ease-in-out infinite;
}

@keyframes melodai-pulse {
    0%   { opacity: 1; }
    50%  { opacity: 0.45; }
    100% { opacity: 1; }
}

/*Quality toggle button*/
.quality-toggle {
    margin-top: 5px;
}

.btn-quality {
    background      : rgba(255, 255, 255, 0.07);
    color           : rgba(255, 255, 255, 0.65);
    border          : 1px solid rgba(255, 255, 255, 0.14);
    border-radius   : 8px;
    padding         : 3px 12px;
    font-size       : 11px;
    cursor          : pointer;
    transition      : background 0.2s ease, color 0.2s ease;
    outline         : none;
}

.btn-quality:hover {
    background : rgba(255, 255, 255, 0.14);
    color      : #ffffff;
}

/*Buffer progress bar container*/
.buffer-bar-container {
    height        : 2px;
    background    : rgba(255, 255, 255, 0.08);
    border-radius : 2px;
    margin-top    : 5px;
    overflow      : hidden;
}

/*Actual buffer fill bar*/
.buffer-bar {
    height        : 100%;
    background    : rgba(255, 255, 255, 0.28);
    border-radius : 2px;
    width         : 0%;
    transition    : width 0.6s ease;
}

/*Audio wrapper spacing*/
.audio-wrapper {
    margin-top : 8px;
}

/*Processing and no-preview text messages*/
.processing-text,
.no-preview-text {
    font-size  : 12px;
    color      : rgba(255, 255, 255, 0.4);
    margin     : 6px 0;
    font-style : italic;
}
🔀 Hybrid Strategy
The platform uses a hybrid audio source strategy so that dataset songs continue working exactly as before while uploaded songs get full streaming capability.

Song Type Audio Source Duration Seeking Auto-Advance
Artist uploaded and transcoded /stream/<id>?q=medium from your server Full song 3 to 5 minutes Yes via HTTP Range Yes
Artist uploaded not yet transcoded Processing badge shown — no player None No No
Dataset song with iTunes preview URL iTunes CDN preview URL 30 seconds No Limited
Dataset song with no preview URL Text message shown None No No
Decision Tree Applied in Jinja2 Template
text

IF song.source == 'upload' AND song.is_transcoded == True
    → Render audio with src=/stream/<song_id>?q=medium
    → Show green Full Track badge
    → Show quality toggle button

ELIF song.source == 'upload' AND song.is_transcoded == False
    → Show amber Processing badge with pulse animation
    → No audio element rendered

ELIF song.preview_url is not None
    → Render audio with src=iTunes preview URL
    → Show orange 30s Preview badge

ELSE
    → Show text: Preview not available
🗺️ Implementation Phases
text

PHASE A — Backend Streaming Foundation
├── Install pydub via pip
├── Install ffmpeg at system level and verify with ffmpeg -version
├── Add os.makedirs calls to app.py startup for upload directories
├── Run all 8 ALTER TABLE SQL statements on events.db
├── Add transcode_audio() helper function to routes/artist.py
├── Modify existing upload route to call transcode_audio()
├── Add /stream/<song_id> route to app.py with Range support
├── Add play_queues dict and all four /queue/* routes to app.py
│
│   TEST PHASE A:
│   Upload a WAV file via artist dashboard
│   Check that uploads/encoded/<id>/high.mp3 was created
│   Hit /stream/1 in browser — audio should play in tab
│   Drag the browser seek bar — verify seeking works
│   Check DB: is_transcoded should be 1 after upload

PHASE B — Frontend Integration
├── Create static/player.js with full content above
├── Add player.js script tag to templates/base.html before </body>
├── Replace audio source logic in templates/index.html
│   with hybrid Jinja2 block shown above
├── Append new CSS classes to bottom of static/styles.css
│
│   TEST PHASE B:
│   Load recommendation page — uploaded songs show green badge
│   Dataset songs show orange badge
│   Play uploaded song — full song plays in browser
│   Seek to 2 minutes — jumps correctly
│   Play dataset song — 30s preview plays as before

PHASE C — Queue and Auto-Advance
├── Add Add to Queue button on recommendation cards
│   Button calls addToQueue(song_id, source, preview_url)
├── Test queue add and retrieve via /queue endpoint
├── Let an uploaded song play to completion
│   Verify next song in queue starts automatically
├── Empty queue then let song end
│   Verify fetchNextRecommendation is called
│
│   TEST PHASE C:
│   Add three songs to queue
│   Play first song to completion
│   Verify second starts automatically
│   Verify third follows
│   Verify AI fetch called when queue empties

PHASE D — Polish and Edge Cases
├── Test quality toggle mid-song — verify position is restored
├── Test stream error fallback — rename encoded file temporarily
│   Verify player falls back to iTunes URL if present
├── Test on mobile browsers — iOS Safari and Android Chrome
├── Test concurrent sessions — two browser tabs streaming
│   simultaneously should not interfere
├── Add Gunicorn workers for production: gunicorn -w 4 app:app
│   Verify streams work across multiple worker processes
│   Note: play_queues dict must move to Redis for multi-worker
📋 File Changes Summary
File Action Scope of Change
app.py MODIFY — add routes Add /stream/<id> and all /queue/* routes at bottom of file
routes/artist.py MODIFY — update upload Add transcode_audio() function and call it inside upload route
templates/index.html MODIFY — audio source only Replace <audio> source block with hybrid Jinja2 logic
templates/base.html MODIFY — add script tag Add player.js script tag before closing body tag
static/player.js CREATE — new file Full queue and player JavaScript as shown above
static/styles.css MODIFY — append only Add badge, buffer bar, and quality toggle CSS at bottom
events.db MODIFY — alter table Run 8 ALTER TABLE statements to add streaming columns
.gitignore MODIFY — add entries Add uploads/raw/ and uploads/encoded/ lines
README.md MODIFY — update deps Add pydub to pip install command and ffmpeg to prerequisites
⚠️ Important Notes for Agent
Do NOT remove or modify any existing routes in app.py — all new routes are additions only

Do NOT alter index.html layout CSS classes control bar sidebar or any element other than the audio source logic inside each recommendation card

Do NOT modify any existing columns in songs_uploaded — only add the 8 new columns via ALTER TABLE

Do NOT change any existing CSS rules in styles.css — only append new classes at the bottom after a clear comment

The transcode_audio() function must be called after the initial DB INSERT because the song_id is needed to name the encoded output folder

The /stream/<id> route must verify is_transcoded == 1 before serving — return 503 if the column is 0

The iTunes preview URL fallback must remain fully functional for all dataset songs — this is a hybrid system not a replacement

ffmpeg must be installed at system level — pydub is a Python wrapper and will raise FileNotFoundError if ffmpeg binary is not on PATH

Raw master files in uploads/raw/ must be kept permanently as backup — do not delete them after transcoding completes

stream_count is separate from play_count — play_count increments when user clicks the Play button via /event endpoint — stream_count increments when the /stream/ endpoint actually delivers bytes

The play_queues dictionary stores queues in server memory — this works for single-worker development but must be replaced with Redis for multi-worker Gunicorn production deployment

All JavaScript in player.js uses ES5 syntax (no arrow functions, no const, no let) for maximum browser compatibility including older mobile browsers
