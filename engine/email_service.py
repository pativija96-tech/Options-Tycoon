"""
Options Tycoon — Email Service (Resend)

Sends welcome and weekly reminder emails via Resend API.
Free tier: 100 emails/day, 3000/month.

Environment variables:
- RESEND_API_KEY: API key from resend.com
"""

import os
import logging
import httpx

logger = logging.getLogger("options_tycoon.email")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
APP_URL = os.environ.get("APP_URL", "https://web-production-90d8.up.railway.app")
EMAIL_FROM = "Options Tycoon <notifications@options-tycoon.com>"


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email via Resend API. Returns True if successful."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set. Skipping email send.")
        return False

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": EMAIL_FROM,
                "to": [to_email],
                "subject": subject,
                "html": html_body,
            },
            timeout=10,
        )

        if response.status_code == 200:
            logger.info(f"Email sent to {to_email}: {subject}")
            return True
        else:
            logger.error(f"Resend API error {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def send_weekly_reminder(user_name: str, user_email: str, dna_score: int = None, days_since_upload: int = 7):
    """Send the weekly upload reminder email."""
    subject = f"Your Trader DNA — Time for this week's check-in"

    score_text = ""
    if dna_score is not None:
        score_text = f"<p style='font-size:2rem;font-weight:900;color:#ff3d71;font-family:monospace;'>{dna_score}/100</p><p style='color:#8899aa;'>Your last DNA Score</p>"

    html = f"""
    <div style="max-width:520px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e14;color:#e8edf3;padding:40px 32px;border-radius:16px;">
        <div style="margin-bottom:24px;">
            <span style="font-size:1.2rem;font-weight:800;">Options<span style="color:#00e676;">Tycoon</span></span>
        </div>
        
        <h1 style="font-size:1.4rem;font-weight:700;margin-bottom:16px;">Hey {user_name.split(' ')[0] if user_name else 'Trader'},</h1>
        
        <p style="color:#8899aa;line-height:1.7;margin-bottom:20px;">
            It's been {days_since_upload} days since your last upload. Your behavioral patterns may have changed — upload this week's trades to see if your score improved.
        </p>
        
        {score_text}
        
        <div style="margin:28px 0;">
            <a href="{APP_URL}/static/upload-free.html" style="display:inline-block;padding:14px 32px;background:#00e676;color:#000;font-weight:800;font-size:0.95rem;border-radius:8px;text-decoration:none;">
                Upload This Week's Trades →
            </a>
        </div>
        
        <div style="margin-top:32px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.06);">
            <p style="font-size:0.75rem;color:#4a5b6e;line-height:1.6;">
                You're receiving this because you signed up for Options Tycoon.<br>
                <a href="{APP_URL}/static/dashboard.html" style="color:#4a5b6e;">Go to Dashboard</a> · 
                <a href="{APP_URL}/static/privacy.html" style="color:#4a5b6e;">Privacy Policy</a>
            </p>
            <p style="font-size:0.65rem;color:#4a5b6e;margin-top:8px;">
                ⚠️ Not financial advice. Behavioral observations from your own data only.
            </p>
        </div>
    </div>
    """

    return send_email(user_email, subject, html)


def send_welcome_email(user_name: str, user_email: str):
    """Send welcome email after first sign-up."""
    subject = "Welcome to Options Tycoon — Your DNA Report awaits"

    html = f"""
    <div style="max-width:520px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0e14;color:#e8edf3;padding:40px 32px;border-radius:16px;">
        <div style="margin-bottom:24px;">
            <span style="font-size:1.2rem;font-weight:800;">Options<span style="color:#00e676;">Tycoon</span></span>
        </div>
        
        <h1 style="font-size:1.4rem;font-weight:700;margin-bottom:16px;">Welcome, {user_name.split(' ')[0] if user_name else 'Trader'}! 🧬</h1>
        
        <p style="color:#8899aa;line-height:1.7;margin-bottom:20px;">
            Your account is set up. Here's how to get your Trader DNA Score:
        </p>
        
        <div style="margin-bottom:20px;padding:16px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:8px;">
            <p style="color:#e8edf3;font-size:0.9rem;line-height:1.8;">
                📤 <strong>Upload</strong> your broker CSV (Zerodha, Groww, Angel One)<br>
                🧠 <strong>Get</strong> your Trader DNA Score + behavioral patterns<br>
                📈 <strong>Track</strong> improvement by uploading weekly<br>
                🎯 <strong>Fix One Thing</strong> each week to improve discipline
            </p>
        </div>
        
        <div style="margin:28px 0;">
            <a href="{APP_URL}/static/upload-free.html" style="display:inline-block;padding:14px 32px;background:#00e676;color:#000;font-weight:800;font-size:0.95rem;border-radius:8px;text-decoration:none;">
                Upload Your First CSV →
            </a>
        </div>
        
        <p style="color:#4a5b6e;font-size:0.8rem;line-height:1.6;">
            Your data is private and encrypted. We never access your broker account. Delete anytime from your Dashboard.
        </p>
        
        <div style="margin-top:32px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.06);">
            <p style="font-size:0.7rem;color:#4a5b6e;">
                ⚠️ Not financial advice. Not SEBI registered. Behavioral observations only.
            </p>
        </div>
    </div>
    """

    return send_email(user_email, subject, html)
