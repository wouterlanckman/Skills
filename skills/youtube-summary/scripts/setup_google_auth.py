#!/usr/bin/env python3
"""
One-time setup and verification script for the youtube-summary skill:
1. Generates `google_token.json` from `google_credentials.json` via OAuth 2.0.
   Works seamlessly on a headless Raspberry Pi over SSH (copy-paste redirect URL)
   or locally with a browser (--local-server).
2. Verifies access to your existing Google Drive folder (`YOUTUBE_DRIVE_FOLDER_ID`)
   and existing NotebookLM Master Google Doc (`YOUTUBE_MASTER_DOC_ID`).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse


SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]


def ensure_venv() -> None:
    """Automatically re-exec inside the skill or repo .venv if invoked with system python."""
    if os.environ.get("_AGY_VENV_ACTIVE") == "1":
        return
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    repo_dir = skill_dir.parent.parent
    for candidate_venv in (skill_dir / ".venv", repo_dir / ".venv", Path.cwd() / ".venv"):
        venv_python = candidate_venv / "bin" / "python"
        if venv_python.is_file() and os.access(venv_python, os.X_OK):
            if Path(sys.prefix).resolve() != candidate_venv.resolve():
                os.environ["_AGY_VENV_ACTIVE"] = "1"
                os.execv(str(venv_python), [str(venv_python), *sys.argv])
            return


def load_dotenv_simple(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def run_ssh_copy_paste_oauth(flow, port: int):
    """
    Headless-friendly OAuth flow for Raspberry Pi over SSH:
    Prints the Google login URL, lets the user approve in any browser, and accepts
    either the redirected `http://localhost:8085/?...` URL or the raw `code=` parameter.
    """
    redirect_uri = f"http://localhost:{port}/"
    flow.redirect_uri = redirect_uri
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    print("\n" + "=" * 76)
    print("🔐 GOOGLE OAUTH 2.0 SETUP (HEADLESS / SSH MODE)")
    print("=" * 76)
    print("\n1️⃣  Open this link in your browser on your PC/phone:\n")
    print(f"    {auth_url}\n")
    print("2️⃣  Log in with your Google account and click 'Continue' / 'Allow'.")
    print(
        f"3️⃣  Your browser will redirect to http://localhost:{port}/... and may show\n"
        "    'This site can’t be reached' — THAT IS NORMAL!\n"
        "    Simply copy the ENTIRE address bar URL from your browser and paste it below.\n"
    )
    user_input = input("📋 Paste the redirected localhost URL (or code) here: ").strip()

    if user_input.startswith("http://") or user_input.startswith("https://"):
        parsed = urlparse(user_input)
        qs = parse_qs(parsed.query)
        code_list = qs.get("code")
        if not code_list:
            raise ValueError(
                "No '?code=...' parameter found in the URL you pasted. "
                "Make sure you copied the full URL from the browser's address bar after clicking Allow."
            )
        code = code_list[0]
    else:
        code = user_input

    flow.fetch_token(code=code)
    return flow.credentials


def main() -> int:
    ensure_venv()
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
        help="Redirect port (default: 8085)",
    )
    parser.add_argument(
        "--local-server",
        action="store_true",
        help="Use a local callback webserver instead of the SSH copy-paste flow",
    )
    args = parser.parse_args()

    skill_dir = Path(__file__).resolve().parent.parent
    load_dotenv_simple(Path.cwd() / ".env")
    load_dotenv_simple(skill_dir / ".env")

    raw_creds = os.environ.get("GOOGLE_CREDENTIALS_FILE", "google_credentials.json").strip()
    raw_token = os.environ.get("GOOGLE_TOKEN_FILE", "google_token.json").strip()
    default_creds = Path(raw_creds) if Path(raw_creds).is_absolute() else (skill_dir / raw_creds)
    default_token = Path(raw_token) if Path(raw_token).is_absolute() else (skill_dir / raw_token)
    if not default_creds.exists() and (skill_dir / "google_credentials.json").exists():
        default_creds = skill_dir / "google_credentials.json"
    creds_path = args.credentials or default_creds
    token_path = args.token or default_token

    from google.auth.transport.requests import Request  # noqa: PLC0415
    from google.oauth2.credentials import Credentials  # noqa: PLC0415
    from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: PLC0415
    from googleapiclient.discovery import build  # noqa: PLC0415

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
                    "Save your downloaded Desktop App OAuth JSON there first.",
                    file=sys.stderr,
                )
                return 1
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            if args.local_server:
                creds = flow.run_local_server(
                    port=args.port,
                    access_type="offline",
                    prompt="consent",
                )
            else:
                creds = run_ssh_copy_paste_oauth(flow, port=args.port)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        print(f"\n✅ Saved OAuth token (with refresh_token) to: {token_path.resolve()}")

    drive_service = build("drive", "v3", credentials=creds)
    docs_service = build("docs", "v1", credentials=creds)

    folder_id = os.environ.get("YOUTUBE_DRIVE_FOLDER_ID", "").strip()
    master_doc_id = os.environ.get("YOUTUBE_MASTER_DOC_ID", "").strip()

    if folder_id and folder_id != "your_drive_folder_id_here":
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

    if master_doc_id and master_doc_id != "your_master_google_doc_id_here":
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
