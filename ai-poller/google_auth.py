"""OAuth2 installed-app flow for Google Drive access.

Requires a Desktop OAuth client ID from the same Google Cloud project
that the Android/Web apps use (project 887974376217). Download as
credentials.json into the ai-poller/ directory.

First run opens a browser for consent and saves a refresh token to token.json.
Subsequent runs reuse the cached token and auto-refresh.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.appdata"]

_DIR = Path(__file__).parent
_CREDENTIALS_FILE = _DIR / "credentials.json"
_TOKEN_FILE = _DIR / "token.json"


def authenticate() -> Credentials:
    """Return valid Google OAuth2 credentials, prompting login if needed."""
    creds: Credentials | None = None

    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not _CREDENTIALS_FILE.exists():
            raise FileNotFoundError(
                f"Missing {_CREDENTIALS_FILE}. Download a Desktop OAuth client ID "
                "from Google Cloud Console and save it as credentials.json."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(_CREDENTIALS_FILE), SCOPES
        )
        creds = flow.run_local_server(port=0)

    # Save for next run
    _TOKEN_FILE.write_text(creds.to_json())
    return creds
