"""
run.py - the script that runs the whole thing. Just run this file.

    python run.py               (normal run, opens browser for login if needed)
    python run.py --scheduled   (automatic run, see below)

It logs in to Gmail, reads your unread emails from the last 24 hours,
asks the AI (Groq) to summarize what matters, and emails that summary to you.

In --scheduled mode (used by the Windows task that run_daily.bat sets up):
- it never opens a browser, since nobody is around to log in
- it only sends a summary if the last one was sent 20 or more hours ago,
  so logging in or unlocking the laptop several times a day is harmless
- everything it prints goes to summary_log.txt instead of the screen
"""

import os
import subprocess
import sys
import time
from datetime import datetime

# The packages this project needs are installed inside the venv/ folder.
# If this file is started with your normal Python instead (for example with
# VS Code's Run button), restart it using the project's own venv Python.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(BASE_DIR, "venv")
VENV_PYTHON = os.path.join(
    VENV_DIR, "Scripts" if os.name == "nt" else "bin", "python.exe" if os.name == "nt" else "python"
)
if os.path.exists(VENV_PYTHON) and os.path.normcase(sys.prefix) != os.path.normcase(VENV_DIR):
    sys.exit(subprocess.call([VENV_PYTHON, os.path.abspath(__file__), *sys.argv[1:]]))

from dotenv import load_dotenv

from ai_helper import GROUPS, summarize_emails, summary_to_html, summary_to_text
from gmail_helper import (
    SUMMARY_SUBJECT,
    fetch_unread_emails,
    get_gmail_service,
    get_my_email_address,
    send_email,
)

LOG_FILE = os.path.join(BASE_DIR, "summary_log.txt")
LAST_RUN_FILE = os.path.join(BASE_DIR, "last_run.txt")  # when the last summary was sent
HOURS_BETWEEN_RUNS = 20

# "--scheduled" means we're running automatically from the Windows task.
SCHEDULED = "--scheduled" in sys.argv


def hours_since_last_run():
    """How many hours ago the last summary was sent (None if never)."""
    try:
        with open(LAST_RUN_FILE) as file:
            last_run = float(file.read().strip())
    except (OSError, ValueError):
        return None
    return (time.time() - last_run) / 3600


def remember_this_run():
    """Save the current time as 'the last summary was sent now'."""
    with open(LAST_RUN_FILE, "w") as file:
        file.write(str(time.time()))


if SCHEDULED:
    # Sent a summary less than 20 hours ago? Then there's nothing to do yet.
    hours = hours_since_last_run()
    if hours is not None and hours < HOURS_BETWEEN_RUNS:
        sys.exit(0)

    # Nobody is watching the screen, so write everything (errors too) to the log.
    log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
else:
    # Make sure special characters don't crash printing on Windows.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Load GROQ_API_KEY and GROQ_MODEL from the .env file next to this script.
load_dotenv(os.path.join(BASE_DIR, ".env"))


def main():
    print(f"--- Run started {datetime.now():%Y-%m-%d %H:%M} ---")

    # Check settings first, so we fail early with a clear message.
    for setting in ("GROQ_API_KEY", "GROQ_MODEL"):
        if not os.getenv(setting):
            sys.exit(f"Missing {setting} in your .env file (see .env.example).")

    # 1. Log in and read the inbox.
    print("Logging in to Gmail...")
    service = get_gmail_service(allow_browser=not SCHEDULED)

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

    # Only remember the run once the email is actually sent. If something
    # failed (no internet yet, expired login), the next trigger tries again.
    remember_this_run()


if __name__ == "__main__":
    main()
