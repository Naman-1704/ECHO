from datetime import datetime, timedelta

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest

from app.config import settings

CLIENT_CONFIG = {
    "web": {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [settings.google_redirect_uri],
    }
}


def get_auth_url() -> str:
    """Step 1 of OAuth: build the URL we redirect the user to for consent."""
    flow = Flow.from_client_config(
        CLIENT_CONFIG, scopes=settings.google_scopes, redirect_uri=settings.google_redirect_uri
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",       # needed to get a refresh_token
        include_granted_scopes="true",
        prompt="consent",            # forces refresh_token on every login during dev/testing
    )
    return auth_url


def exchange_code_for_credentials(code: str) -> Credentials:
    """Step 2 of OAuth: exchange the ?code= from the callback for real tokens."""
    flow = Flow.from_client_config(
        CLIENT_CONFIG, scopes=settings.google_scopes, redirect_uri=settings.google_redirect_uri
    )
    flow.fetch_token(code=code)
    return flow.credentials


def credentials_from_stored_tokens(access_token: str, refresh_token: str) -> Credentials:
    """Rebuild a Credentials object from what we saved in the DB, refreshing if expired."""
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=settings.google_scopes,
    )
    if not creds.valid:
        creds.refresh(GoogleRequest())
    return creds


def expiry_from_credentials(creds: Credentials) -> datetime:
    return creds.expiry or (datetime.utcnow() + timedelta(hours=1))
