"""
Google Drive connector. Produces the same item dicts as gmail_connector, so everything
downstream (privacy filter, chunking, embedding, extraction, graph) is shared.

Supported: Google Docs and Slides (exported as plain text), and plain-text / Markdown
files. Sheets, PDFs and Office files are skipped for now (they need dedicated parsers).
The Drive owner/last editor become the item's "from" so authors show up in the graph.
"""
from __future__ import annotations

from datetime import datetime

from googleapiclient.discovery import build

from app.auth.google_oauth import credentials_from_stored_tokens
from app.utils.dates import to_naive_utc

GOOGLE_EXPORTABLE = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
}
PLAIN_DOWNLOADABLE = {"text/plain", "text/markdown", "text/x-markdown"}
MAX_TEXT_CHARS = 200_000          # a single doc this large is almost certainly not a handover doc
MAX_DOWNLOAD_BYTES = 2_000_000

_MIME_QUERY = " or ".join(
    f"mimeType='{m}'" for m in [*GOOGLE_EXPORTABLE, *sorted(PLAIN_DOWNLOADABLE)]
)
QUERY = f"trashed = false and ({_MIME_QUERY})"
FIELDS = ("nextPageToken, files(id, name, mimeType, modifiedTime, size, "
          "owners(displayName, emailAddress), lastModifyingUser(displayName, emailAddress))")


def _get_service(access_token: str, refresh_token: str):
    creds = credentials_from_stored_tokens(access_token, refresh_token)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return to_naive_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _person(entry: dict | None) -> str | None:
    if not entry or not entry.get("emailAddress"):
        return None
    name = entry.get("displayName") or ""
    return f"{name} <{entry['emailAddress']}>" if name else entry["emailAddress"]


def _read_text(service, f: dict) -> str:
    mime = f["mimeType"]
    if mime in GOOGLE_EXPORTABLE:
        data = service.files().export(fileId=f["id"], mimeType=GOOGLE_EXPORTABLE[mime]).execute()
    else:
        if int(f.get("size") or 0) > MAX_DOWNLOAD_BYTES:
            return ""
        data = service.files().get_media(fileId=f["id"]).execute()
    text = data.decode("utf-8", errors="ignore") if isinstance(data, (bytes, bytearray)) else str(data or "")
    return text.lstrip("﻿").strip()[:MAX_TEXT_CHARS]


def fetch_files(access_token: str, refresh_token: str, max_results: int = 25,
                page_token: str | None = None, service=None):
    """Returns (items, next_page_token). `service` is injectable for tests."""
    service = service or _get_service(access_token, refresh_token)
    resp = service.files().list(
        q=QUERY, pageSize=max_results, pageToken=page_token, orderBy="modifiedTime desc",
        fields=FIELDS, spaces="drive",
    ).execute()

    items = []
    for f in resp.get("files", []):
        try:
            text = _read_text(service, f)
        except Exception:        # one unreadable/forbidden file must not abort the whole sync
            continue
        if not text:
            continue
        owner = _person((f.get("owners") or [None])[0]) or _person(f.get("lastModifyingUser"))
        editor = _person(f.get("lastModifyingUser"))
        items.append({
            "source_id": f["id"],
            "subject_or_title": f.get("name") or "(untitled)",
            "participants": {"from": owner, "to": [editor] if editor and editor != owner else []},
            "raw_text": text,
            "item_date": _parse_time(f.get("modifiedTime")),
        })
    return items, resp.get("nextPageToken")
