from __future__ import annotations

import os
import tempfile
import sqlite3
import unittest

import werkzeug
if not hasattr(werkzeug, '__version__'):
    setattr(werkzeug, '__version__', "3.0.1")


# Create a temporary DB file to isolate testing
temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
os.close(temp_db_fd)

# Override database path in auth module before importing anything else
import auth
auth.DB_PATH = temp_db_path
auth.init_db()

# Now import routes to test
from auth import get_db
from earnings import log_earnings
from mailer import send_invite_email

class TestNotificationSystem(unittest.TestCase):
    def setUp(self):
        from app import app
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.con = sqlite3.connect(temp_db_path)
        self.con.row_factory = sqlite3.Row

    def tearDown(self):
        self.con.close()

    def test_01_user_registration_welcome(self):
        """Test user registration triggers welcome notification and welcome email."""
        # Clean users and notifications
        self.con.execute("DELETE FROM notifications")
        self.con.execute("DELETE FROM users WHERE username='test_listener'")
        self.con.commit()

        # Perform registration request
        response = self.client.post('/register', data={
            'username': 'test_listener',
            'email': 'listener@example.com',
            'password': 'Password123'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        # Check DB notifications
        user = self.con.execute("SELECT id FROM users WHERE username='test_listener'").fetchone()
        self.assertIsNotNone(user)

        notif = self.con.execute("SELECT * FROM notifications WHERE user_id=?", (user['id'],)).fetchone()
        self.assertIsNotNone(notif)
        self.assertIn("Welcome to MelodAI", notif['message'])

    def test_02_artist_onboarding(self):
        """Test admin artist creation and subsequent registration welcome notifications."""
        # Simulate admin session to pass admin check
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        # Add artist via admin dashboard
        response = self.client.post('/admin/add-artist', data={
            'stage_name': 'Test DJ',
            'email': 'dj@example.com',
            'genre': 'Electronic',
            'bio': 'A cool electronic music producer.'
        })
        self.assertEqual(response.status_code, 200)

        # Extract invite code
        artist = self.con.execute(
            "SELECT a.invite_code, a.id, a.user_id FROM artists a JOIN users u ON a.user_id=u.id WHERE a.stage_name='Test DJ'"
        ).fetchone()
        self.assertIsNotNone(artist)
        invite_code = artist['invite_code']

        # Clear session to act as registering artist
        with self.client.session_transaction() as sess:
            sess.clear()

        # Complete artist registration
        response = self.client.post('/artist/register', data={
            'code': invite_code,
            'username': 'test_dj',
            'email': 'dj@example.com',
            'password': 'CreatorPassword123'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Check notifications for the artist user
        notif = self.con.execute("SELECT * FROM notifications WHERE user_id=?", (artist['user_id'],)).fetchone()
        self.assertIsNotNone(notif)
        self.assertIn("Creator Community", notif['message'])

    def test_03_admin_moderation(self):
        """Test admin ban, activate, and song deletion triggers notifications."""
        # Log in as admin
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        # Fetch a test user
        user = self.con.execute("SELECT id FROM users WHERE username='test_listener'").fetchone()
        user_id = user['id']

        # Ban User
        response = self.client.post(f'/admin/users/{user_id}/ban', follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Verify inactive status and notification
        user_status = self.con.execute("SELECT is_active FROM users WHERE id=?", (user_id,)).fetchone()
        self.assertEqual(user_status['is_active'], 0)
        notif = self.con.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchone()
        self.assertIn("suspended", notif['message'])

        # Activate User
        response = self.client.post(f'/admin/users/{user_id}/activate', follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Verify active status and notification
        user_status = self.con.execute("SELECT is_active FROM users WHERE id=?", (user_id,)).fetchone()
        self.assertEqual(user_status['is_active'], 1)
        notif = self.con.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchone()
        self.assertIn("re-activated", notif['message'])

        # Insert a mock song to test deletion notification
        artist = self.con.execute("SELECT id, user_id FROM artists WHERE stage_name='Test DJ'").fetchone()
        cursor = self.con.execute(
            "INSERT INTO songs_uploaded (artist_id, title, file_path) VALUES (?, ?, ?)",
            (artist['id'], 'Bad Track', 'uploads/raw/dummy.mp3')
        )
        song_id = cursor.lastrowid
        self.con.commit()

        # Delete song via admin route
        response = self.client.delete(f'/admin/songs/{song_id}')
        self.assertEqual(response.status_code, 200)

        # Verify song is deleted and artist notified
        song_check = self.con.execute("SELECT * FROM songs_uploaded WHERE id=?", (song_id,)).fetchone()
        self.assertIsNone(song_check)
        artist_notif = self.con.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC", (artist['user_id'],)).fetchone()
        self.assertIn("removed by platform moderation", artist_notif['message'])

    def test_04_user_follow(self):
        """Test follow artist endpoint triggers notification to the artist."""
        user = self.con.execute("SELECT id FROM users WHERE username='test_listener'").fetchone()
        artist = self.con.execute("SELECT id, user_id FROM artists WHERE stage_name='Test DJ'").fetchone()

        # Log in as user
        with self.client.session_transaction() as sess:
            sess['user_id'] = user['id']
            sess['username'] = 'test_listener'
            sess['role'] = 'user'

        # Follow artist
        response = self.client.post(f'/user/follow/{artist["id"]}')
        self.assertEqual(response.status_code, 302)

        # Check follow record
        follow = self.con.execute(
            "SELECT 1 FROM user_followed_artists WHERE user_id=? AND artist_id=?",
            (user['id'], artist['id'])
        ).fetchone()
        self.assertIsNotNone(follow)

        # Check notification logged for artist user
        notif = self.con.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC", (artist['user_id'],)).fetchone()
        self.assertIsNotNone(notif)
        self.assertIn("test_listener started following you", notif['message'])

    def test_05_song_upload_follower_notification(self):
        """Test that song upload triggers notification to followers."""
        artist = self.con.execute("SELECT id, user_id FROM artists WHERE stage_name='Test DJ'").fetchone()

        # Log in as artist
        with self.client.session_transaction() as sess:
            sess['user_id'] = artist['user_id']
            sess['username'] = 'test_dj'
            sess['role'] = 'artist'
            sess['csrf_token'] = 'test_csrf'

        # Clear notifications for user first to check clean insert
        user = self.con.execute("SELECT id FROM users WHERE username='test_listener'").fetchone()
        self.con.execute("DELETE FROM notifications WHERE user_id=?", (user['id'],))
        self.con.commit()

        # Mock a file upload object
        from io import BytesIO
        audio_data = BytesIO(b"dummy mp3 data")
        
        response = self.client.post('/artist/upload', data={
            'csrf_token': 'test_csrf',
            'title': 'New Synthwave Beat',
            'genre': 'Synthwave',
            'audio': (audio_data, 'beat.mp3')
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)

        # Check if listener received a notification about the new song
        notif = self.con.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC", (user['id'],)).fetchone()
        self.assertIsNotNone(notif)
        self.assertIn("uploaded a new song", notif['message'])

    def test_06_earnings_milestones(self):
        """Test log_earnings milestones ($1.00 crossing)."""
        artist = self.con.execute("SELECT id, user_id FROM artists WHERE stage_name='Test DJ'").fetchone()
        
        # Clear notifications for the artist user
        self.con.execute("DELETE FROM notifications WHERE user_id=?", (artist['user_id'],))
        self.con.commit()

        # Insert song to attribute plays
        cursor = self.con.execute(
            "INSERT INTO songs_uploaded (artist_id, title, file_path) VALUES (?, ?, ?)",
            (artist['id'], 'Milestone Song', 'uploads/raw/m.mp3')
        )
        song_id = cursor.lastrowid
        assert isinstance(song_id, int)
        self.con.commit()

        # Artificially log play events until total_earnings crosses $1.00 (EARN_PER_PLAY = 0.004)
        # We need 250 plays to cross $1.00.
        with self.app.app_context():
            db_conn = get_db()
            # Mock/Set earnings to 0.992 (248 plays)
            db_conn.execute("UPDATE artists SET total_earnings = 0.992 WHERE id = ?", (artist['id'],))
            db_conn.commit()

            # Trigger 2 plays to cross 1.00
            log_earnings(db_conn, artist['id'], song_id, 'play') # -> 0.996
            log_earnings(db_conn, artist['id'], song_id, 'play') # -> 1.000 (milestone!)

            # Verify milestone notification
            notif = db_conn.execute(
                "SELECT * FROM notifications WHERE user_id=? AND message LIKE '%crossed $1.00%'",
                (artist['user_id'],)
            ).fetchone()
            self.assertIsNotNone(notif)

    def test_07_admin_broadcast(self):
        """Test admin global broadcast route sends notification to active users."""
        # Log in as admin
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['username'] = 'admin'
            sess['role'] = 'admin'

        # Delete all notifications to isolate test
        self.con.execute("DELETE FROM notifications")
        self.con.commit()

        response = self.client.post('/admin/broadcast', data={
            'subject': 'System Maintenance Info',
            'message': '<p>We will be down for 5 minutes.</p>'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Count active users
        active_users_count = self.con.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]
        
        # Count notifications generated
        notif_count = self.con.execute("SELECT COUNT(*) FROM notifications WHERE message LIKE '📢 Broadcast: System Maintenance Info'").fetchone()[0]
        
        self.assertEqual(active_users_count, notif_count)

    def test_08_weekly_digests(self):
        """Verify the Weekly Digest methods don't error out when statistics are processed."""
        # We will directly run the background worker functions to ensure they complete cleanly
        from scheduler import send_weekly_artist_digests as _send_weekly_artist_digests, send_weekly_user_digests as _send_weekly_user_digests
        
        # We just need to assert they run without raising exceptions
        try:
            _send_weekly_artist_digests()
            _send_weekly_user_digests()
            digest_ok = True
        except Exception as e:
            print(f"Digest failed with error: {e}")
            digest_ok = False

        self.assertTrue(digest_ok)

if __name__ == '__main__':
    unittest.main()
