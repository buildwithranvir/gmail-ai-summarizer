"""
gmail_helper.py - Everything that talks to Gmail lives here.

- get_gmail_service(): logs you in to Google and returns a Gmail "service"
- fetch_unread_emails(): gets your unread emails from the last 24 hours
- get_my_email_address(): finds out which Gmail address you logged in with
- send_email(): sends an email (the summary) from your Gmail
"""

import base64
import html
import os
import re
import time
from email.message import EmailMessage

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# What we ask Google permission to do:
#   gmail.readonly -> read your emails (can't delete or change anything)
#   gmail.send     -> send an email (the summary, to yourself)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# Always look for files next to this script, even if it's run from
# another folder (important later, when it runs automatically every morning).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")  # your app's ID card
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")  # your saved login

MAX_EMAILS = 50  # never process more than this many emails
MAX_BODY_CHARS = 1500  # cut long email bodies down to this many characters

# Subject of the summary email we send. We also use it to make sure
# tomorrow's run doesn't summarize today's summary!
SUMMARY_SUBJECT = "Your inbox in 30 seconds"


def get_gmail_service(allow_browser=True):
    """Log in to Gmail and return a service object we can use to call the API.

    allow_browser=False is for scheduled runs: nobody is at the computer to
    click through the login page, so we stop with a clear error instead of
    waiting forever.
    """
    creds = None

    # 1. If we've logged in before, reuse the saved login (token.json).
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # 2. If the saved login is expired, try to refresh it silently.
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            # Happens when Google revokes the login (e.g. after 7 days in
            # "Testing" mode). We just log in again from scratch.
            print("Your saved Google login expired.")
            creds = None

    # 3. No valid login? Open the browser and ask you to sign in.
    if not creds or not creds.valid:
        if not allow_browser:
            raise RuntimeError(
                "Google login needed, but this is a scheduled run so no browser "
                "can be opened. Run 'python main.py' by hand once to log in again."
            )
        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(
                "credentials.json not found. Download it from Google Cloud "
                "and put it in the project folder (see README)."
            )
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)

    # 4. Save the login so next time there's no browser pop-up.
    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_unread_emails(service):
    """Return a list of unread emails from the last 24 hours (max MAX_EMAILS).

    Each email is a dict: {"sender", "subject", "date", "body"}
    """
    # Gmail search query, same as typing it in the Gmail search bar.
    # "after:" takes a Unix timestamp, so this means "the last 24 hours".
    # The "-subject:" part skips our own summary emails.
    one_day_ago = int(time.time()) - 24 * 60 * 60
    query = f'is:unread after:{one_day_ago} -subject:"{SUMMARY_SUBJECT}"'

    # Step 1: get the IDs of matching emails (newest first).
    result = service.users().messages().list(
        userId="me", q=query, maxResults=MAX_EMAILS
    ).execute()
    message_ids = [m["id"] for m in result.get("messages", [])]

    # Step 2: download each email and pull out the parts we care about.
    emails = []
    for message_id in message_ids:
        message = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()

        headers = message["payload"].get("headers", [])
        body = _get_body_text(message["payload"]) or message.get("snippet", "")

        emails.append({
            "sender": _get_header(headers, "From"),
            "subject": _get_header(headers, "Subject") or "(no subject)",
            "date": _get_header(headers, "Date"),
            "body": _truncate(body, MAX_BODY_CHARS),
        })

    return emails


def get_my_email_address(service):
    """Ask Gmail which address we're logged in as."""
    profile = service.users().getProfile(userId="me").execute()
    return profile["emailAddress"]


def send_email(service, to, subject, text_body, html_body):
    """Send an email from your Gmail.

    We include both a plain-text and an HTML version. Email apps show the
    HTML one, and fall back to plain text if they can't display HTML.
    """
    message = EmailMessage()
    message["To"] = to
    message["From"] = to
    message["Subject"] = subject
    message.set_content(text_body)  # plain-text version
    message.add_alternative(html_body, subtype="html")  # pretty version

    # The Gmail API wants the whole email as URL-safe base64 text.
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


# ---------- Small helper functions (used only inside this file) ----------

def _get_header(headers, name):
    """Find one header (like 'From' or 'Subject') in the email's header list."""
    for header in headers:
        if header["name"].lower() == name.lower():
            return header["value"]
    return ""


def _get_body_text(payload):
    """Get readable text out of an email.

    Emails are often split into nested "parts" (plain text, HTML, attachments).
    We prefer the plain-text version; if there isn't one, we strip the HTML.
    """
    found = {}
    _collect_text_parts(payload, found)

    if "text/plain" in found:
        return _clean_whitespace(found["text/plain"])
    if "text/html" in found:
        return _html_to_text(found["text/html"])
    return ""


def _collect_text_parts(payload, found):
    """Walk through all the parts of an email and remember the first
    plain-text and first HTML part we see."""
    mime_type = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")

    if data and mime_type in ("text/plain", "text/html") and mime_type not in found:
        found[mime_type] = _decode_base64(data)

    for part in payload.get("parts", []):
        _collect_text_parts(part, found)


def _decode_base64(data):
    """Gmail sends email text encoded as 'URL-safe base64'. Turn it back into text."""
    padded = data + "=" * (-len(data) % 4)  # add missing padding
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _html_to_text(raw_html):
    """Very simple HTML -> text: drop styles/scripts, remove tags, fix &amp; etc."""
    text = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return _clean_whitespace(html.unescape(text))


def _clean_whitespace(text):
    """Collapse runs of spaces/newlines into single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def _truncate(text, max_chars):
    """Cut text to max_chars, adding '...' if it was longer."""
    return text if len(text) <= max_chars else text[:max_chars] + "..."
