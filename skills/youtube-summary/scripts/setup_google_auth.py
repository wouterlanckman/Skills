#!/usr/bin/env python3
"""
One-time setup and verification script for the youtube-summary skill:
1. Runs the OAuth 2.0 flow using `google_credentials.json` and saves `google_token.json`.
2. Verifies access to your existing Google Drive folder (`YOUTUBE_DRIVE_FOLDER_ID`)
   and existing NotebookLM Master Google Doc (`YOUTUBE_MASTER_DOC_ID`).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]


def load_dotenv_simple(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authenticate Google Drive & Docs API and verify existing Folder & Master Doc IDs."
    )
    parser.add_argument(
        "--credentials",
        type=Path,
        default=None,
        help="Path to OAuth client credentials JSON (defaults to GOOGLE_CREDENTIALS_FILE or ./google_credentials.json)",
    )
    parser.add_argument(
        "--token",
        type=Path,
        default=None,
        help="Path to output token JSON (defaults to GOOGLE_TOKEN_FILE or ./google_token.json)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8085,
        help="Local port for OAuth callback server (use SSH port forwarding -L 8085:localhost:8085 if running directly on Raspberry Pi)",
    )
    args = parser.parse_args()

    load_dotenv_simple(Path.cwd() / ".env")
    load_dotenv_simple(Path(__file__).resolve().parent.parent / ".env")

    creds_path = args.credentials or Path(
        os.environ.get("GOOGLE_CREDENTIALS_FILE", "google_credentials.json")
    )
    token_path = args.token or Path(
        os.environ.get("GOOGLE_TOKEN_FILE", "google_token.json")
    )

    try:
        from google.auth.transport.requests import Request  # noqa: PLC0415
        from google.oauth2.credentials import Credentials  # noqa: PLC0415
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: PLC0415
        from googleapiclient.discovery import build  # noqa: PLC0415
    except ImportError as exc:
        print(
            f"❌ Missing Google Auth libraries: {exc}\n"
            "Install with: .venv/bin/pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib",
            file=sys.stderr,
        )
        return 1

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing existing OAuth token...")
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                print(
                    f"❌ OAuth Client file not found at: {creds_path}\n"
                    "Download your Desktop App OAuth JSON from Google Cloud Console and save it there.",
                    file=sys.stderr,
                )
                return 1
            print(
                f"🌐 Starting OAuth 2.0 login on http://localhost:{args.port} ...\n"
                "   (Tip: If running via SSH on your Raspberry Pi, connect with: ssh -L 8085:localhost:8085 pi@<ip>)"
            )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(
                port=args.port,
                access_type="offline",
                prompt="consent",
            )
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        print(f"✅ Saved OAuth token (with refresh_token) to: {token_path.resolve()}")

    drive_service = build("drive", "v3", credentials=creds)
    docs_service = build("docs", "v1", credentials=creds)

    folder_id = os.environ.get("YOUTUBE_DRIVE_FOLDER_ID", "").strip()
    master_doc_id = os.environ.get("YOUTUBE_MASTER_DOC_ID", "").strip()

    if folder_id:
        try:
            f_meta = (
                drive_service.files()
                .get(
                    fileId=folder_id,
                    fields="id, name, mimeType, webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )
            print(
                f"✅ Verified Google Drive Folder: '{f_meta.get('name')}' ({f_meta.get('id')})\n"
                f"   URL: {f_meta.get('webViewLink')}"
            )
        except Exception as exc:
            print(
                f"❌ Could not access YOUTUBE_DRIVE_FOLDER_ID='{folder_id}': {exc}",
                file=sys.stderr,
            )
            return 1
    else:
        print("ℹ️ YOUTUBE_DRIVE_FOLDER_ID is not yet set in .env.")

    if master_doc_id:
        try:
            doc_meta = (
                docs_service.documents().get(documentId=master_doc_id).execute()
            )
            print(
                f"✅ Verified NotebookLM Master Google Doc: '{doc_meta.get('title')}' ({master_doc_id})\n"
                f"   URL: https://docs.google.com/document/d/{master_doc_id}/edit"
            )
        except Exception as exc:
            print(
                f"❌ Could not access YOUTUBE_MASTER_DOC_ID='{master_doc_id}': {exc}",
                file=sys.stderr,
            )
            return 1
    else:
        print("ℹ️ YOUTUBE_MASTER_DOC_ID is not yet set in .env.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
