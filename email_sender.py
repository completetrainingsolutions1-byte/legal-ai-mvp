"""
Email Sender -- sends drafted correspondence via Gmail SMTP.

SAFETY DEFAULT: EMAIL_DRY_RUN defaults to "true". Nothing is actually
sent unless you explicitly set EMAIL_DRY_RUN=false in .env. This
mirrors the MOCK_MODE pattern used elsewhere in this system -- safe by
default, real action only when deliberately enabled.

Credentials are read from environment variables only -- never hardcoded,
never typed into chat, never logged in plaintext anywhere.

SETUP (Gmail requires an "App Password", not your normal password):
1. Enable 2-Step Verification on your Google account, if not already on:
   https://myaccount.google.com/security
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Add to your local .env (never paste this into a chat):
     GMAIL_ADDRESS=youraddress@gmail.com
     GMAIL_APP_PASSWORD=the16charapppassword
     EMAIL_DRY_RUN=true
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

DRY_RUN = os.getenv("EMAIL_DRY_RUN", "true").lower() == "true"
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

EMAIL_LOG_PATH = os.path.join(os.path.dirname(__file__), "outputs", "email_send_log.jsonl")


def _log(entry):
    os.makedirs(os.path.dirname(EMAIL_LOG_PATH), exist_ok=True)
    with open(EMAIL_LOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def send_email(to_address, subject, body):
    """
    Sends an email via Gmail SMTP, or simulates it (dry run) depending
    on configuration. Always returns a result dict and always logs,
    regardless of outcome -- every attempt is auditable.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    if not to_address or "@" not in to_address:
        result = {
            "status": "skipped",
            "reason": "No valid recipient email address was provided.",
            "to": to_address, "subject": subject, "timestamp": timestamp,
        }
        _log(result)
        return result

    if DRY_RUN:
        result = {
            "status": "dry_run",
            "reason": "EMAIL_DRY_RUN is enabled -- no real email was sent.",
            "to": to_address, "subject": subject,
            "body_preview": body[:300], "timestamp": timestamp,
        }
        _log(result)
        return result

    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        result = {
            "status": "failed",
            "reason": "Gmail credentials are not configured in .env "
                      "(GMAIL_ADDRESS / GMAIL_APP_PASSWORD).",
            "to": to_address, "subject": subject, "timestamp": timestamp,
        }
        _log(result)
        return result

    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to_address, msg.as_string())

        result = {
            "status": "sent",
            "to": to_address, "subject": subject, "timestamp": timestamp,
        }
    except Exception as e:
        result = {
            "status": "failed",
            "reason": str(e),
            "to": to_address, "subject": subject, "timestamp": timestamp,
        }

    _log(result)
    return result
