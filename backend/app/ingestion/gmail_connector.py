import base64
from datetime import datetime
from email.utils import parsedate_to_datetime

from googleapiclient.discovery import build

from app.auth.google_oauth import credentials_from_stored_tokens


def _get_service(access_token: str, refresh_token: str):
    creds = credentials_from_stored_tokens(access_token, refresh_token)
    return build("gmail", "v1", credentials=creds)


def _extract_body(payload: dict) -> str:
    """Gmail messages are nested MIME parts; walk them to find the plain-text body."""
    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")

    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return ""


def fetch_messages(access_token: str, refresh_token: str, max_results: int = 10, page_token: str | None = None):
    """
    Pulls a page of messages (metadata + parsed body). For an MVP, start with
    max_results=50 and a manual "sync more" trigger rather than pulling everything at once.
    """
    service = _get_service(access_token, refresh_token)

    resp = service.users().messages().list(
        userId="me", maxResults=max_results, pageToken=page_token
    ).execute()

    message_ids = [m["id"] for m in resp.get("messages", [])]
    next_page_token = resp.get("nextPageToken")

    results = []
    for mid in message_ids:
        msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        body = _extract_body(msg["payload"])

        try:
            item_date = parsedate_to_datetime(headers.get("Date", ""))
        except Exception:
            item_date = datetime.utcnow()

        results.append({
            "source_id": mid,
            "subject_or_title": headers.get("Subject", "(no subject)"),
            "participants": {
                "from": headers.get("From"),
                "to": headers.get("To", "").split(",") if headers.get("To") else [],
            },
            "raw_text": body or msg.get("snippet", ""),
            "item_date": item_date,
        })

    return results, next_page_token


def get_current_history_id(access_token: str, refresh_token: str) -> str:
    """Used to set up incremental sync going forward (call once after first full pull)."""
    service = _get_service(access_token, refresh_token)
    profile = service.users().getProfile(userId="me").execute()
    return profile["historyId"]
