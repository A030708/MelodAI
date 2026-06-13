from __future__ import annotations

import os
import smtplib
import threading
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

APP_NAME = "MelodAI"
APP_URL = os.getenv("APP_URL", "http://127.0.0.1:5000")

def build_email_html(header: str, body_html: str, footer_note: str = "") -> str:
    """
    Constructs a dark-glassmorphism themed responsive HTML email template.
    Uses inline CSS styled table layouts for maximum email client compatibility.
    """
    if not footer_note:
        footer_note = f"You are receiving this because you have a registered account on {APP_NAME}."
    
    current_year = datetime.now().year
    
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{APP_NAME}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #0a0a0c; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #e1e1e6;">
  <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0a0a0c; padding: 40px 10px;">
    <tr>
      <td align="center">
        <!-- Card Container representing Glassmorphism box -->
        <table width="100%" max-width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; background-color: #121216; border: 1px solid #282832; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.65);">
          <!-- Header -->
          <tr>
            <td style="padding: 30px 40px 20px 40px; border-bottom: 1px solid #282832; text-align: left; background-image: linear-gradient(to bottom, #16161c, #121216);">
              <span style="font-size: 24px; font-weight: 800; color: #1db954; letter-spacing: -0.5px;">Melod<span style="color: #ffffff;">AI</span></span>
              <div style="font-size: 13px; color: #a1a1aa; margin-top: 4px; font-weight: 500;">{header}</div>
            </td>
          </tr>
          <!-- Content -->
          <tr>
            <td style="padding: 40px 40px; font-size: 15px; line-height: 1.6; color: #e1e1e6;">
              {body_html}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding: 30px 40px; background-color: #0e0e12; border-top: 1px solid #282832; font-size: 12px; color: #9ca3af; text-align: center; line-height: 1.5;">
              <p style="margin: 0 0 8px 0; color: #71717a;">{footer_note}</p>
              <p style="margin: 0; color: #71717a;">&copy; {current_year} {APP_NAME}. All rights reserved.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

def _send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Internal synchronous email dispatch worker with logging to email_logs table."""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_from = os.getenv("SMTP_FROM", "noreply@musicapp.com")

    if not smtp_user or not smtp_pass:
        print(f"[mailer] SMTP not configured. Simulating email to {to_email}. Subject: '{subject}'")
        # Log simulated sent email to table
        try:
            import sqlite3
            from auth import DB_PATH
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                '''INSERT INTO email_logs
                   (to_email, subject, email_type, status)
                   VALUES (?, ?, ?, ?)''',
                (to_email, subject, 'notification', 'sent')
            )
            conn.commit()
            conn.close()
        except Exception as log_err:
            print(f'[Mailer] Log error: {log_err}')
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to_email

    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"[mailer] Email sent successfully to {to_email} with subject: '{subject}'")
        
        # Log to email_logs on success
        try:
            import sqlite3
            from auth import DB_PATH
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                '''INSERT INTO email_logs
                   (to_email, subject, email_type, status)
                   VALUES (?, ?, ?, ?)''',
                (to_email, subject, 'notification', 'sent')
            )
            conn.commit()
            conn.close()
        except Exception as log_err:
            print(f'[Mailer] Log error: {log_err}')
        return True
    except Exception as e:
        print(f"[mailer] Failed to send email to {to_email}: {e}")
        
        # Log to email_logs on failure
        try:
            import sqlite3
            from auth import DB_PATH
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                '''INSERT INTO email_logs
                   (to_email, subject, email_type, status)
                   VALUES (?, ?, ?, ?)''',
                (to_email, subject, 'notification', 'failed')
            )
            conn.commit()
            conn.close()
        except Exception as log_err:
            print(f'[Mailer] Log error: {log_err}')
        return False

def send_async(to_email: str, subject: str, html_content: str) -> None:
    """Spawns a background thread to send an email without blocking the request thread."""
    t = threading.Thread(target=_send_email, args=(to_email, subject, html_content))
    t.daemon = True
    t.start()

# 1. Welcome User
def send_welcome_user(to_email: str, username: str) -> None:
    subject = f"Welcome to {APP_NAME}! 🎵"
    body = f"""
    <h2 style="color: #ffffff; font-size: 20px; margin-top: 0; font-weight: 700;">Hey {username}, welcome to {APP_NAME}!</h2>
    <p>We're thrilled to have you join our platform. {APP_NAME} brings you closer to independent artists through real-time AI-powered recommendations.</p>
    <p>To start your journey, like or play tracks. Our recommendation engine adapts to your taste dynamically with every click!</p>
    <p style="text-align: center; margin: 35px 0 20px 0;">
      <a href="{APP_URL}/" style="background-color: #1db954; color: #000000; padding: 14px 32px; border-radius: 24px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block;">Explore Recommendations</a>
    </p>
    """
    html = build_email_html("Account Creation Successful", body)
    send_async(to_email, subject, html)

# 2. Welcome Artist
def send_welcome_artist(to_email: str, stage_name: str) -> None:
    subject = f"Welcome to the {APP_NAME} Creator Community! 🎤"
    body = f"""
    <h2 style="color: #ffffff; font-size: 20px; margin-top: 0; font-weight: 700;">Welcome, {stage_name}!</h2>
    <p>Your artist profile on {APP_NAME} is fully registered. You are now ready to connect with listeners and monetize your craft.</p>
    <p>Log in to your artist portal to upload your tracks, organize albums, post fan updates, and track your listener analytics.</p>
    <p style="text-align: center; margin: 35px 0 20px 0;">
      <a href="{APP_URL}/artist/dashboard" style="background-color: #1db954; color: #000000; padding: 14px 32px; border-radius: 24px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block;">Go to Creator Dashboard</a>
    </p>
    """
    html = build_email_html("Artist Registration Confirmed", body)
    send_async(to_email, subject, html)

# 3. Invite Code (Artist Invite)
def send_invite_code(to_email: str, artist_name: str, invite_code: str) -> bool:
    subject = f"Invitation: Join {APP_NAME} as a Creator!"
    body = f"""
    <h2 style="color: #ffffff; font-size: 20px; margin-top: 0; font-weight: 700;">Hello {artist_name},</h2>
    <p>You have been invited by the platform administration to register as a creator on {APP_NAME}.</p>
    <p>Your unique registration invite code is:</p>
    <div style="background-color: #1b1b22; border: 1px solid #2d2d3d; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center;">
      <span style="font-family: monospace; font-size: 20px; font-weight: 700; color: #1db954; letter-spacing: 1.5px;">{invite_code}</span>
    </div>
    <p>Use the link below to complete your sign-up process:</p>
    <p style="text-align: center; margin: 35px 0 20px 0;">
      <a href="{APP_URL}/artist/register?code={invite_code}" style="background-color: #1db954; color: #000000; padding: 14px 32px; border-radius: 24px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block;">Accept Invitation</a>
    </p>
    <p style="font-size: 13px; color: #71717a; margin-top: 20px;">This code is valid for single-use registration only.</p>
    """
    html = build_email_html("Exclusive Artist Invitation", body)
    
    # Needs to return bool to maintain legacy signature of send_invite_email
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    if not smtp_user or not smtp_pass:
        print(f"[mailer] SMTP not configured. Invite code for {artist_name}: {invite_code}")
        # Log simulated sent email to table
        try:
            import sqlite3
            from auth import DB_PATH
            conn = sqlite3.connect(DB_PATH)
            conn.execute(
                '''INSERT INTO email_logs
                   (to_email, subject, email_type, status)
                   VALUES (?, ?, ?, ?)''',
                (to_email, subject, 'notification', 'sent')
            )
            conn.commit()
            conn.close()
        except Exception as log_err:
            print(f'[Mailer] Log error: {log_err}')
        return False
        
    send_async(to_email, subject, html)
    return True

# Keep backward compatibility with admin.py imports
send_invite_email = send_invite_code

# 4. New Song -> Followers
def send_new_song_to_follower(to_email: str, follower_username: str, artist_name: str, song_title: str, song_id: int, genre: str) -> None:
    subject = f"New Music Alert: {artist_name} - '{song_title}'!"
    body = f"""
    <p>Hi {follower_username},</p>
    <p>An artist you follow, <strong style="color: #ffffff;">{artist_name}</strong>, just dropped a new track on {APP_NAME} ({genre}):</p>
    <div style="background-color: #1b1b22; border: 1px solid #282832; border-radius: 12px; padding: 24px; margin: 20px 0; text-align: center;">
      <div style="font-size: 20px; font-weight: 700; color: #ffffff; margin-bottom: 6px;">{song_title}</div>
      <div style="font-size: 14px; color: #1db954; font-weight: 600;">by {artist_name}</div>
    </div>
    <p>Stream it now to support the artist and tune your recommendations!</p>
    <p style="text-align: center; margin: 35px 0 20px 0;">
      <a href="{APP_URL}/" style="background-color: #1db954; color: #000000; padding: 14px 32px; border-radius: 24px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block;">Listen Now</a>
    </p>
    """
    html = build_email_html("New Release from Followed Artist", body)
    send_async(to_email, subject, html)

# Single background thread loop for sending batch follower updates to avoid spawning hundreds of threads
def send_new_song_to_followers_batch(followers, artist_name, song_title, song_id, genre):
    def notify_followers_thread(followers, artist_name, song_title, song_id, genre):
        for follower in followers:
            subject = f'New from {artist_name}: {song_title}'
            body = f"""
            <p>Hi {follower['username']},</p>
            <p>An artist you follow, <strong style="color: #ffffff;">{artist_name}</strong>, just dropped a new track on {APP_NAME} ({genre}):</p>
            <div style="background-color: #1b1b22; border: 1px solid #282832; border-radius: 12px; padding: 24px; margin: 20px 0; text-align: center;">
              <div style="font-size: 20px; font-weight: 700; color: #ffffff; margin-bottom: 6px;">{song_title}</div>
              <div style="font-size: 14px; color: #1db954; font-weight: 600;">by {artist_name}</div>
            </div>
            <p>Stream it now to support the artist and tune your recommendations!</p>
            <p style="text-align: center; margin: 35px 0 20px 0;">
              <a href="{APP_URL}/" style="background-color: #1db954; color: #000000; padding: 14px 32px; border-radius: 24px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block;">Listen Now</a>
            </p>
            """
            html = build_email_html("New Release from Followed Artist", body)
            _send_email(follower['email'], subject, html)

    threading.Thread(
        target=notify_followers_thread,
        args=(followers, artist_name, song_title, song_id, genre),
        daemon=True
    ).start()

# 5. Earnings Milestone
def send_earnings_milestone(to_email: str, artist_name: str, milestone_amount: float, total_earnings: float) -> None:
    subject = f"Congratulations! Crossed the ${milestone_amount:.2f} Milestone! 💰"
    body = f"""
    <h2 style="color: #ffffff; font-size: 20px; margin-top: 0; font-weight: 700;">Fantastic Work, {artist_name}!</h2>
    <p>Your tracks are streaming across the platform, and you've officially crossed the **${milestone_amount:.2f}** earnings milestone!</p>
    <p>Your current all-time revenue is now <strong style="color: #1db954; font-size: 18px;">${total_earnings:.3f}</strong>.</p>
    <p>Keep the uploads coming and continue connecting with your audience!</p>
    <p style="text-align: center; margin: 35px 0 20px 0;">
      <a href="{APP_URL}/artist/dashboard" style="background-color: #1db954; color: #000000; padding: 14px 32px; border-radius: 24px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block;">View Earnings Reports</a>
    </p>
    """
    html = build_email_html("Earnings Milestone Cleared", body)
    send_async(to_email, subject, html)

# 6. New Follower
def send_new_follower(to_email: str, artist_name: str, follower_username: str, follower_count: int = 0) -> None:
    subject = "You gained a new follower! 👥"
    count_text = f" You now have a total of {follower_count} followers." if follower_count > 0 else ""
    body = f"""
    <p>Hi {artist_name},</p>
    <p>Great news! <strong style="color: #ffffff;">{follower_username}</strong> has started following you on {APP_NAME}.{count_text}</p>
    <p>Followers will receive notifications in their feed and email alerts whenever you publish new tracks or release announcements.</p>
    <p style="text-align: center; margin: 35px 0 20px 0;">
      <a href="{APP_URL}/artist/dashboard" style="background-color: #1db954; color: #000000; padding: 14px 32px; border-radius: 24px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block;">Go to Dashboard</a>
    </p>
    """
    html = build_email_html("Fanbase Growing", body)
    send_async(to_email, subject, html)

# 7. Weekly Artist Digest (Legacy name for safety, maps to the required scheduler calls)
def send_artist_weekly_digest(to_email: str, stage_name: str, week_plays: int, week_likes: int, week_earnings: float, week_followers: int, top_song_title: str, total_earnings: float) -> None:
    subject = "Your MelodAI Creator Weekly Summary 📈"
    body = f"""
    <h2 style="color: #ffffff; font-size: 20px; margin-top: 0; font-weight: 700;">Weekly Performance Digest</h2>
    <p>Hi {stage_name}, here is a snapshot of your audience interaction and earnings over the last 7 days:</p>
    <table width="100%" cellpadding="12" cellspacing="0" border="0" style="background-color: #121216; border: 1px solid #282832; border-radius: 12px; margin: 25px 0;">
      <tr style="border-bottom: 1px solid #282832;">
        <td style="color: #a1a1aa; font-size: 14px;">Streams (Plays) This Week</td>
        <td style="color: #ffffff; font-size: 16px; font-weight: 700; text-align: right;">{week_plays}</td>
      </tr>
      <tr style="border-bottom: 1px solid #282832;">
        <td style="color: #a1a1aa; font-size: 14px;">Likes Received This Week</td>
        <td style="color: #ffffff; font-size: 16px; font-weight: 700; text-align: right;">{week_likes}</td>
      </tr>
      <tr style="border-bottom: 1px solid #282832;">
        <td style="color: #a1a1aa; font-size: 14px;">New Followers This Week</td>
        <td style="color: #ffffff; font-size: 16px; font-weight: 700; text-align: right;">{week_followers}</td>
      </tr>
      <tr style="border-bottom: 1px solid #282832;">
        <td style="color: #a1a1aa; font-size: 14px;">Top Song This Week</td>
        <td style="color: #ffffff; font-size: 16px; font-weight: 700; text-align: right;">{top_song_title}</td>
      </tr>
      <tr style="border-bottom: 1px solid #282832;">
        <td style="color: #a1a1aa; font-size: 14px;">Weekly Earnings</td>
        <td style="color: #1db954; font-size: 16px; font-weight: 700; text-align: right;">${week_earnings:.3f}</td>
      </tr>
      <tr>
        <td style="color: #a1a1aa; font-size: 14px;">Total Earnings All-Time</td>
        <td style="color: #1db954; font-size: 16px; font-weight: 700; text-align: right;">${total_earnings:.3f}</td>
      </tr>
    </table>
    <p style="text-align: center; margin: 35px 0 20px 0;">
      <a href="{APP_URL}/artist/dashboard" style="background-color: #1db954; color: #000000; padding: 14px 32px; border-radius: 24px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block;">Analyze Traffic Stats</a>
    </p>
    """
    html = build_email_html("Your Weekly Stats", body)
    send_async(to_email, subject, html)

# Legacy alias
send_weekly_artist_digest = send_artist_weekly_digest

# 8. Weekly User Digest
def send_user_weekly_digest(to_email: str, username: str, week_plays: int, week_likes: int, top_genre: str, new_releases_count: int, followed_artists_count: int) -> None:
    subject = "Your Weekly Mix on MelodAI 🎧"
    body = f"""
    <h2 style="color: #ffffff; font-size: 20px; margin-top: 0; font-weight: 700;">Your Weekly Listening Recap</h2>
    <p>Hi {username}, here is a snapshot of your musical journey over the last 7 days:</p>
    <table width="100%" cellpadding="12" cellspacing="0" border="0" style="background-color: #121216; border: 1px solid #282832; border-radius: 12px; margin: 25px 0;">
      <tr style="border-bottom: 1px solid #282832;">
        <td style="color: #a1a1aa; font-size: 14px;">Songs Played</td>
        <td style="color: #ffffff; font-size: 16px; font-weight: 700; text-align: right;">{week_plays}</td>
      </tr>
      <tr style="border-bottom: 1px solid #282832;">
        <td style="color: #a1a1aa; font-size: 14px;">Songs Liked</td>
        <td style="color: #ffffff; font-size: 16px; font-weight: 700; text-align: right;">{week_likes}</td>
      </tr>
      <tr style="border-bottom: 1px solid #282832;">
        <td style="color: #a1a1aa; font-size: 14px;">Top Genre</td>
        <td style="color: #1db954; font-size: 16px; font-weight: 700; text-align: right;">{top_genre}</td>
      </tr>
      <tr style="border-bottom: 1px solid #282832;">
        <td style="color: #a1a1aa; font-size: 14px;">Followed Artists</td>
        <td style="color: #ffffff; font-size: 16px; font-weight: 700; text-align: right;">{followed_artists_count}</td>
      </tr>
      <tr>
        <td style="color: #a1a1aa; font-size: 14px;">New Releases from Followed Artists</td>
        <td style="color: #ffffff; font-size: 16px; font-weight: 700; text-align: right;">{new_releases_count}</td>
      </tr>
    </table>
    <p style="text-align: center; margin: 35px 0 20px 0;">
      <a href="{APP_URL}/" style="background-color: #1db954; color: #000000; padding: 14px 32px; border-radius: 24px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block;">Open Recommendations</a>
    </p>
    """
    html = build_email_html("Your Weekly Music Mix", body)
    send_async(to_email, subject, html)

# Legacy alias
send_weekly_user_digest = send_user_weekly_digest

# 9. Song Status
def send_song_status(to_email: str, artist_name: str, song_title: str, status: str, reason: str | None = None) -> None:
    subject = f"Song Status Notification: '{song_title}'"
    status_text = status.upper()
    status_color = "#ef4444" if status == "removed" else "#1db954"
    reason_html = f"<p><strong>Reason:</strong> {reason}</p>" if reason else ""
    
    body = f"""
    <p>Hi {artist_name},</p>
    <p>We are notifying you about the status of your uploaded song: <strong style="color: #ffffff;">{song_title}</strong>.</p>
    <p>Its status has been updated to: <strong style="color: {status_color}; font-weight: 700;">{status_text}</strong></p>
    {reason_html}
    {"<p>If you believe this action was taken in error or want details, please contact platform administrators.</p>" if status == "removed" else "<p>Your track is fully approved and streaming live to the platform.</p>"}
    """
    html = build_email_html("Music Moderation Update", body)
    send_async(to_email, subject, html)

# 10. Account Banned
def send_account_banned(to_email: str, username: str) -> None:
    subject = "Important: MelodAI Account Suspended"
    body = f"""
    <h2 style="color: #ef4444; font-size: 20px; margin-top: 0; font-weight: 700;">Account Suspension</h2>
    <p>Hello {username},</p>
    <p>We are writing to inform you that your {APP_NAME} account has been suspended by the administrator due to a violation of platform guidelines.</p>
    <p>Consequently, you will be unable to log in, upload music, or access details under this profile.</p>
    """
    html = build_email_html("Account Status Restricted", body)
    send_async(to_email, subject, html)

# 11. Account Activated
def send_account_activated(to_email: str, username: str) -> None:
    subject = "MelodAI Account Re-Activated! 🎉"
    body = f"""
    <h2 style="color: #1db954; font-size: 20px; margin-top: 0; font-weight: 700;">Account Re-Activated</h2>
    <p>Hello {username},</p>
    <p>Good news! Your {APP_NAME} account has been re-activated by our administrators.</p>
    <p>You can now log in to the dashboard and resume your activities normally.</p>
    <p style="text-align: center; margin: 35px 0 20px 0;">
      <a href="{APP_URL}/login" style="background-color: #1db954; color: #000000; padding: 14px 32px; border-radius: 24px; font-weight: 700; font-size: 15px; text-decoration: none; display: inline-block;">Log In Now</a>
    </p>
    """
    html = build_email_html("Account Access Restored", body)
    send_async(to_email, subject, html)

# 12. Password Reset
def send_password_reset(to_email: str, username: str) -> None:
    subject = f"Reset Your {APP_NAME} Password"
    body = f"""
    <p>Hello {username},</p>
    <p>A request was received to reset the password linked to your {APP_NAME} profile.</p>
    <p>Since self-service password reset is in development, please reach out to support or reply to this email for assistance.</p>
    """
    html = build_email_html("Credentials Reset Notice", body)
    send_async(to_email, subject, html)

# 13. Admin Broadcast
def send_admin_broadcast(to_email: str, username: str, subject_line: str, announcement_html: str) -> None:
    """
    Sent to: All users and artists (called in a loop)
    Trigger: Admin submits broadcast form at /admin/broadcast
    """
    body = f"""
    <p>Hi <strong style="color:#ffffff;">{username}</strong>,</p>
    <p>You have a message from the {APP_NAME} team:</p>
    <div style="background:rgba(255,255,255,0.06);
                border-radius:12px;padding:20px;margin:20px 0;
                border: 1px solid rgba(255,255,255,0.1);
                border-left:4px solid #1db954;">
      {announcement_html}
    </div>
    <p style="text-align:center;margin-top:24px;">
      <a href="{APP_URL}/"
         style="background:#1db954;color:#000000;padding:14px 32px;
                border-radius:24px;font-weight:700;font-size:15px;
                text-decoration:none;display:inline-block;">
        Open {APP_NAME}
      </a>
    </p>
    """
    html = build_email_html(
        header=f'📢 Message from {APP_NAME}',
        body_html=body,
        footer_note=f'This is an official announcement from the {APP_NAME} team.'
    )
    send_async(to_email, subject_line, html)
