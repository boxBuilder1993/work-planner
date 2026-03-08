"""Google Drive API wrapper for appDataFolder operations.

File names used by WorkPlanner:
  - workplanner_tasks.enc
  - workplanner_comments.enc
  - workplanner_repeating_tasks.enc
  - workplanner_salt.bin
  - workplanner_ai_state.enc  (new, for AI poller state)
"""

from __future__ import annotations

import io
import logging

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

logger = logging.getLogger(__name__)


class DriveClient:
    def __init__(self, creds: Credentials) -> None:
        self._service = build("drive", "v3", credentials=creds)

    def find_file_id(self, name: str) -> str | None:
        """Search appDataFolder for a file by name. Returns file ID or None."""
        resp = (
            self._service.files()
            .list(
                spaces="appDataFolder",
                q=f"name='{name}' and trashed=false",
                fields="files(id)",
                pageSize=1,
            )
            .execute()
        )
        files = resp.get("files", [])
        return files[0]["id"] if files else None

    def download_file(self, file_id: str) -> bytes:
        """Download raw bytes of a file by its ID."""
        request = self._service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue()

    def download_file_by_name(self, name: str) -> bytes | None:
        """Download a file from appDataFolder by name. Returns None if missing."""
        file_id = self.find_file_id(name)
        if file_id is None:
            return None
        return self.download_file(file_id)

    def upload_or_update_file(self, name: str, data: bytes) -> None:
        """Create or update a file in appDataFolder."""
        media = MediaIoBaseUpload(
            io.BytesIO(data), mimetype="application/octet-stream", resumable=False
        )
        existing_id = self.find_file_id(name)
        if existing_id:
            self._service.files().update(
                fileId=existing_id, media_body=media
            ).execute()
            logger.debug("Updated %s (id=%s)", name, existing_id)
        else:
            metadata = {"name": name, "parents": ["appDataFolder"]}
            self._service.files().create(
                body=metadata, media_body=media, fields="id"
            ).execute()
            logger.debug("Created %s", name)
