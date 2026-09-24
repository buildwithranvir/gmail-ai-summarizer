"""
run.py - the script that runs the whole thing. Just run this file.

    python run.py               (normal run, opens browser for login if needed)
    python run.py --scheduled   (automatic run, never opens a browser)

It logs in to Gmail, reads your unread emails from the last 24 hours,
asks the AI (Groq) to summarize what matters, and emails that summary to you.
"""

import os
import sys
from datetime import datetime

from dotenv import load_dotenv

from ai_helper import GROUPS, summarize_emails, summary_to_html, summary_to_text
from gmail_helper import (
    SUMMARY_SUBJECT,
    fetch_unread_emails,
    get_gmail_service,
    get_my_email_address,
    send_email,
)

# Make sure emojis don't crash printing on Windows.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load GROQ_API_KEY and GROQ_MODEL from the .env file next to this script.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def main():
    # "--scheduled" means we're running automatically (e.g. Task Scheduler),
    # so nobody is around to log in through a browser.
    scheduled = "--scheduled" in sys.argv
    print(f"--- Run started {datetime.now():%Y-%m-%d %H:%M} ---")

    # Check settings first, so we fail early with a clear message.
    for setting in ("GROQ_API_KEY", "GROQ_MODEL"):
        if not os.getenv(setting):
            sys.exit(f"Missing {setting} in your .env file (see .env.example).")

    # 1. Log in and read the inbox.
    print("Logging in to Gmail...")
    service = get_gmail_service(allow_browser=not scheduled)

    print("Fetching unread emails from the last 24 hours...")
    emails = fetch_unread_emails(service)

    # 2. Summarize with AI (skip the AI call if there's nothing to summarize).
    if emails:
        print(f"Found {len(emails)} unread email(s). Asking the AI to summarize...\n")
        summary = summarize_emails(emails)
    else:
        print("No unread emails in the last 24 hours.\n")
        summary = {key: [] for key, _title in GROUPS}

    text = summary_to_text(summary)
    print("=" * 50)
    print("  YOUR INBOX IN 30 SECONDS")
    print("=" * 50 + "\n")
    print(text + "\n")

    # 3. Email the summary to yourself.
    today = datetime.now()
    date_text = f"{today.day} {today:%b %Y}"  # e.g. "24 Sep 2026"
    subject = f"{SUMMARY_SUBJECT} - {date_text}"

    my_address = get_my_email_address(service)
    send_email(
        service,
        to=my_address,
        subject=subject,
        text_body=text,
        html_body=summary_to_html(summary, len(emails), date_text),
    )
    print(f"Summary emailed to you: \"{subject}\"")


if __name__ == "__main__":
    main()
