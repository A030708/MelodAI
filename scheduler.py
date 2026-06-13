from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import time
import mailer

def get_db_connection():
    import sqlite3
    from auth import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def send_weekly_artist_digests():
    """
    Called every Monday at 9:00am.
    Sends weekly stats digest to every active artist.
    """
    print('[Scheduler] Sending weekly artist digests...')

    now_ts = int(time.time())
    one_week_ago = now_ts - (7 * 86400)
    one_week_ago_dt = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()

    artists = conn.execute(
        '''SELECT a.id, a.stage_name, a.total_earnings,
                  u.email
           FROM artists a
           JOIN users u ON u.id = a.user_id
           WHERE u.is_active = 1'''
    ).fetchall()

    for artist in artists:
        artist_id = artist['id']

        # Plays this week
        week_plays = conn.execute(
            '''SELECT COUNT(*) as cnt FROM events e
               JOIN songs_uploaded su ON e.song_id = 'uploaded_' || su.id
               WHERE su.artist_id = ?
               AND e.event_type = 'play'
               AND e.ts >= ?''',
            (artist_id, one_week_ago)
        ).fetchone()['cnt']

        # Likes this week
        week_likes = conn.execute(
            '''SELECT COUNT(*) as cnt FROM events e
               JOIN songs_uploaded su ON e.song_id = 'uploaded_' || su.id
               WHERE su.artist_id = ?
               AND e.event_type = 'like'
               AND e.ts >= ?''',
            (artist_id, one_week_ago)
        ).fetchone()['cnt']

        # Earnings this week
        week_earnings = conn.execute(
            '''SELECT COALESCE(SUM(amount), 0) as total
               FROM earnings_log
               WHERE artist_id = ?
               AND timestamp >= ?''',
            (artist_id, one_week_ago_dt)
        ).fetchone()['total']

        # New followers this week
        week_followers = conn.execute(
            '''SELECT COUNT(*) as cnt FROM user_followed_artists
               WHERE artist_id = ?
               AND followed_at >= ?''',
            (artist_id, one_week_ago_dt)
        ).fetchone()['cnt']

        # Top song this week
        top_song = conn.execute(
            '''SELECT su.title, COUNT(*) as cnt
               FROM events e
               JOIN songs_uploaded su ON e.song_id = 'uploaded_' || su.id
               WHERE su.artist_id = ?
               AND e.event_type = 'play'
               AND e.ts >= ?
               GROUP BY su.id
               ORDER BY cnt DESC LIMIT 1''',
            (artist_id, one_week_ago)
        ).fetchone()

        top_song_title = top_song['title'] if top_song else 'No plays yet'

        mailer.send_artist_weekly_digest(
            to_email=artist['email'],
            stage_name=artist['stage_name'],
            week_plays=week_plays,
            week_likes=week_likes,
            week_earnings=week_earnings,
            week_followers=week_followers,
            top_song_title=top_song_title,
            total_earnings=artist['total_earnings']
        )

    conn.close()
    print('[Scheduler] Artist digests sent.')

def send_weekly_user_digests():
    """
    Called every Monday at 9:00am.
    Sends weekly listening recap to every active user.
    """
    print('[Scheduler] Sending weekly user digests...')

    now_ts = int(time.time())
    one_week_ago = now_ts - (7 * 86400)
    one_week_ago_dt = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()

    users = conn.execute(
        '''SELECT id, username, email FROM users
           WHERE role = 'user' AND is_active = 1'''
    ).fetchall()

    for user in users:
        user_id = user['id']

        week_plays = conn.execute(
            '''SELECT COUNT(*) as cnt FROM events
               WHERE user_id = ? AND event_type = 'play'
               AND ts >= ?''',
            (user_id, one_week_ago)
        ).fetchone()['cnt']

        week_likes = conn.execute(
            '''SELECT COUNT(*) as cnt FROM events
               WHERE user_id = ? AND event_type = 'like'
               AND ts >= ?''',
            (user_id, one_week_ago)
        ).fetchone()['cnt']

        followed_count = conn.execute(
            '''SELECT COUNT(*) as cnt FROM user_followed_artists
               WHERE user_id = ?''',
            (user_id,)
        ).fetchone()['cnt']

        top_genre_row = conn.execute(
            '''SELECT ui.genre FROM user_interests ui
               WHERE ui.user_id = ?
               ORDER BY ui.weight DESC LIMIT 1''',
            (user_id,)
        ).fetchone()
        top_genre = top_genre_row['genre'] if top_genre_row else 'Mixed'

        new_releases = conn.execute(
            '''SELECT COUNT(*) as cnt FROM songs_uploaded su
               JOIN user_followed_artists ufa ON ufa.artist_id = su.artist_id
               WHERE ufa.user_id = ?
               AND su.uploaded_at >= ?
               AND su.is_public = 1''',
            (user_id, one_week_ago_dt)
        ).fetchone()['cnt']

        mailer.send_user_weekly_digest(
            to_email=user['email'],
            username=user['username'],
            week_plays=week_plays,
            week_likes=week_likes,
            top_genre=top_genre,
            new_releases_count=new_releases,
            followed_artists_count=followed_count
        )

    conn.close()
    print('[Scheduler] User digests sent.')

def start_scheduler():
    """
    Start the background scheduler.
    Call this function from app.py at startup.
    """
    scheduler = BackgroundScheduler(timezone='UTC')

    # Every Monday at 9:00am UTC
    scheduler.add_job(
        send_weekly_artist_digests,
        trigger='cron',
        day_of_week='mon',
        hour=9,
        minute=0,
        id='weekly_artist_digest'
    )

    scheduler.add_job(
        send_weekly_user_digests,
        trigger='cron',
        day_of_week='mon',
        hour=9,
        minute=5,
        id='weekly_user_digest'
    )

    scheduler.start()
    print('[Scheduler] [OK] Weekly digest scheduler started.')
    return scheduler
