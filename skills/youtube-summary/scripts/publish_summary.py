#!/usr/bin/env python3
"""
Uploads the extensive YouTube summary to a Google Drive folder as a native Google Doc
AND appends it to an existing Master Google Doc linked to Google NotebookLM.
"""

from __future__ import annotations

import argparse
import html
import io
import json
import os
from pathlib import Path
import re
import sys


SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]

# NotebookLM allows up to 500,000 words per source document.
NOTEBOOKLM_WORD_LIMIT = 500_000
NOTEBOOKLM_WARN_THRESHOLD = 425_000


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
    """Load simple KEY=VALUE pairs from .env if not already in os.environ."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def discover_and_load_env() -> Path:
    """Search common locations for .env files and return the primary base directory."""
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    candidates = [
        Path.cwd() / ".env",
        skill_dir / ".env",
    ]
    for parent in list(script_dir.parents)[:5]:
        candidates.append(parent / ".env")
    for candidate in candidates:
        load_dotenv_simple(candidate)
    return Path.cwd()


def utf16_len(text: str) -> int:
    """Return length of string in UTF-16 code units (required by Google Docs API)."""
    return len(text.encode("utf-16-le")) // 2


def get_google_services(token_path: Path, creds_path: Path):
    """Load and auto-refresh OAuth 2.0 credentials and return (drive_service, docs_service)."""
    try:
        from google.auth.transport.requests import Request  # noqa: PLC0415
        from google.oauth2.credentials import Credentials  # noqa: PLC0415
        from googleapiclient.discovery import build  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "Missing Google API libraries. Install with:\n"
            ".venv/bin/pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib markdown"
        ) from exc

    if not token_path.exists():
        raise RuntimeError(
            f"OAuth token file not found at '{token_path}'.\n"
            f"Run setup_google_auth.py first to authenticate and generate {token_path.name}."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError(
                f"Stored OAuth token at '{token_path}' is expired and cannot be refreshed. "
                f"Re-run setup_google_auth.py."
            )

    drive_service = build("drive", "v3", credentials=creds)
    docs_service = build("docs", "v1", credentials=creds)
    return drive_service, docs_service


def markdown_to_styled_html(md_text: str, title: str) -> str:
    """Convert Markdown summary to clean HTML for Google Drive native Doc conversion."""
    try:
        import markdown  # noqa: PLC0415

        body_html = markdown.markdown(
            md_text,
            extensions=["tables", "fenced_code", "sane_lists"],
        )
    except ImportError:
        # Minimal fallback if 'markdown' package is not installed
        escaped = html.escape(md_text)
        body_html = f"<pre>{escaped}</pre>"

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: Arial, sans-serif; line-height: 1.45; color: #202124; }}
  h1 {{ color: #1a73e8; font-size: 22pt; margin-bottom: 8pt; }}
  h2 {{ color: #174ea6; font-size: 16pt; margin-top: 18pt; margin-bottom: 6pt; border-bottom: 1px solid #dadce0; }}
  h3 {{ color: #202124; font-size: 13pt; margin-top: 12pt; margin-bottom: 4pt; }}
  table {{ border-collapse: collapse; width: 100%; margin: 10pt 0; }}
  th, td {{ border: 1px solid #dadce0; padding: 6pt 8pt; text-align: left; vertical-align: top; }}
  th {{ background-color: #f1f3f4; font-weight: bold; }}
  code, pre {{ font-family: "Courier New", monospace; background-color: #f8f9fa; }}
  a {{ color: #1a73e8; text-decoration: none; }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""


def upload_standalone_doc_to_drive(
    drive_service,
    folder_id: str,
    metadata: dict,
    summary_md: str,
) -> dict:
    """
    Upload the Markdown summary as a native Google Doc in `folder_id`.
    If a document for this video_id already exists in the folder, updates it in-place.
    """
    from googleapiclient.http import MediaIoBaseUpload  # noqa: PLC0415

    video_id = metadata["video_id"]
    pub_date = metadata.get("published_date") or "Unknown-Date"
    channel = metadata.get("channel") or "YouTube"
    title = metadata.get("title") or video_id
    doc_name = f"{pub_date} - [{channel}] {title} [{video_id}]"

    html_str = markdown_to_styled_html(summary_md, doc_name)
    media = MediaIoBaseUpload(
        io.BytesIO(html_str.encode("utf-8")),
        mimetype="text/html",
        resumable=False,
    )

    # Check if a Google Doc for this video_id already exists in the target folder
    query = (
        f"'{folder_id}' in parents and "
        f"mimeType = 'application/vnd.google-apps.document' and "
        f"name contains '[{video_id}]' and trashed = false"
    )
    existing = (
        drive_service.files()
        .list(
            q=query,
            fields="files(id, name, webViewLink)",
            pageSize=5,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    )

    if existing:
        file_id = existing[0]["id"]
        updated = (
            drive_service.files()
            .update(
                fileId=file_id,
                body={"name": doc_name},
                media_body=media,
                fields="id, name, webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        return {**updated, "action": "updated"}

    file_metadata = {
        "name": doc_name,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
        "description": f"Extensive summary for YouTube video {metadata.get('url', video_id)}",
    }
    created = (
        drive_service.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink",
            supportsAllDrives=True,
        )
        .execute()
    )
    return {**created, "action": "created"}


def extract_doc_plain_text_and_end_index(doc: dict) -> tuple[str, int]:
    """Extract all plain text and the insertion index at the end of a Google Doc body."""
    content = doc.get("body", {}).get("content", [])
    if not content:
        return "", 1
    end_index = max(1, int(content[-1].get("endIndex", 2)) - 1)
    chunks: list[str] = []
    for elem in content:
        para = elem.get("paragraph")
        if not para:
            continue
        for run in para.get("elements", []):
            tr = run.get("textRun")
            if tr and "content" in tr:
                chunks.append(tr["content"])
    return "".join(chunks), end_index


def parse_inline_markdown(line: str) -> tuple[str, list[dict]]:
    """
    Parse inline Markdown (`[label](url)` and `**bold**`) from a single line.
    Returns (clean_text, inline_styles) where each style has utf16 start/end offsets
    relative to the start of `clean_text`.
    """
    token_re = re.compile(
        r"(\[\[?[^\]]+\]?\]\((https?://[^\s)]+)\)|\*\*([^*]+)\*\*)"
    )
    out_chars: list[str] = []
    styles: list[dict] = []
    curr_utf16 = 0
    last_idx = 0

    for match in token_re.finditer(line):
        prefix = line[last_idx : match.start()]
        if prefix:
            out_chars.append(prefix)
            curr_utf16 += utf16_len(prefix)

        full_token = match.group(1)
        if full_token.startswith("**"):
            inner_text = match.group(3)
            seg_len = utf16_len(inner_text)
            if seg_len > 0:
                styles.append(
                    {
                        "start": curr_utf16,
                        "end": curr_utf16 + seg_len,
                        "bold": True,
                    }
                )
            out_chars.append(inner_text)
            curr_utf16 += seg_len
        else:
            # Link token: [label](url) or [[MM:SS]](url)
            url = match.group(2)
            bracket_part = full_token[: full_token.rfind("](")]
            label = bracket_part[1:]  # strip outer leading '['
            seg_len = utf16_len(label)
            if seg_len > 0:
                styles.append(
                    {
                        "start": curr_utf16,
                        "end": curr_utf16 + seg_len,
                        "url": url,
                    }
                )
            out_chars.append(label)
            curr_utf16 += seg_len

        last_idx = match.end()

    suffix = line[last_idx:]
    if suffix:
        out_chars.append(suffix)

    return "".join(out_chars), styles


def build_master_doc_batch_requests(
    base_index: int,
    metadata: dict,
    standalone_doc_url: str,
    summary_md: str,
) -> list[dict]:
    """
    Convert the Markdown summary into an index-safe Google Docs `batchUpdate` request list:
    1. Inserts the entire clean text block at `base_index` in one `insertText` operation.
    2. Applies `updateParagraphStyle` (HEADING_1, HEADING_2, HEADING_3) and `updateTextStyle`
       (bold, clickable links) using exact UTF-16 code unit offsets.
    """
    video_id = metadata["video_id"]
    video_url = metadata.get("url") or f"https://www.youtube.com/watch?v={video_id}"
    pub_date = metadata.get("published_date") or "Unknown-Date"
    channel = metadata.get("channel") or "YouTube"
    title = metadata.get("title") or video_id

    # Prepend a clear entry separator and NotebookLM source metadata header
    header_md_lines = [
        "",
        "════════════════════════════════════════════════════════════════════════",
        f"# {title} [{video_id}]",
        f"**Channel:** {channel} | **Published:** {pub_date} | **Original Video:** [{video_url}]({video_url}) | **Standalone Google Doc:** [Open Summary Doc]({standalone_doc_url})",
        "",
    ]

    # Strip the top H1 from summary_md if present so we don't duplicate the title H1
    body_lines = summary_md.strip().splitlines()
    if body_lines and body_lines[0].startswith("# "):
        body_lines = body_lines[1:]

    all_raw_lines = header_md_lines + body_lines + [""]

    clean_lines: list[str] = []
    heading_ranges: list[tuple[int, int, str]] = []
    inline_style_ranges: list[dict] = []

    running_utf16 = 0
    in_code_block = False

    for raw_line in all_raw_lines:
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            line_text = f"    {raw_line}\n"
            clean_lines.append(line_text)
            running_utf16 += utf16_len(line_text)
            continue

        # Ignore horizontal rule or pure markdown table separator lines (`| :--- | :--- |`)
        if re.fullmatch(r"[-*_]{3,}", stripped) or re.fullmatch(
            r"\|?[\s:|-]+\|[\s:|-]*", stripped
        ):
            continue

        heading_style = None
        working_line = raw_line
        if working_line.startswith("# "):
            heading_style = "HEADING_1"
            working_line = working_line[2:].strip()
        elif working_line.startswith("## "):
            heading_style = "HEADING_2"
            working_line = working_line[3:].strip()
        elif working_line.startswith("### "):
            heading_style = "HEADING_3"
            working_line = working_line[4:].strip()
        elif working_line.startswith("#### "):
            heading_style = "HEADING_4"
            working_line = working_line[5:].strip()
        else:
            # Convert leading markdown bullets (`- ` or `* `) to clean Unicode bullets
            bullet_match = re.match(r"^(\s*)[-*]\s+(.+)$", working_line)
            if bullet_match:
                indent_spaces = len(bullet_match.group(1))
                prefix_bullet = "  " * (indent_spaces // 2) + "• "
                working_line = prefix_bullet + bullet_match.group(2)
            elif working_line.strip().startswith("|") and working_line.strip().endswith("|"):
                # Format Markdown table row cleanly as pipe-separated cells
                cells = [c.strip() for c in working_line.strip().strip("|").split("|")]
                working_line = " | ".join(cells)

        parsed_text, inline_styles = parse_inline_markdown(working_line)
        line_with_nl = parsed_text + "\n"
        line_utf16_len = utf16_len(line_with_nl)

        line_start = base_index + running_utf16
        line_end = line_start + line_utf16_len

        if heading_style and parsed_text.strip():
            heading_ranges.append((line_start, line_end, heading_style))

        for st in inline_styles:
            inline_style_ranges.append(
                {
                    **st,
                    "abs_start": line_start + st["start"],
                    "abs_end": line_start + st["end"],
                }
            )

        clean_lines.append(line_with_nl)
        running_utf16 += line_utf16_len

    full_inserted_text = "".join(clean_lines)
    if not full_inserted_text.strip():
        return []

    requests: list[dict] = [
        {
            "insertText": {
                "location": {"index": base_index},
                "text": full_inserted_text,
            }
        },
        # Reset inserted block paragraph style to NORMAL_TEXT first so it doesn't inherit previous heading
        {
            "updateParagraphStyle": {
                "range": {
                    "startIndex": base_index,
                    "endIndex": base_index + utf16_len(full_inserted_text),
                },
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                "fields": "namedStyleType",
            }
        },
    ]

    for h_start, h_end, h_style in heading_ranges:
        requests.append(
            {
                "updateParagraphStyle": {
                    "range": {"startIndex": h_start, "endIndex": h_end},
                    "paragraphStyle": {"namedStyleType": h_style},
                    "fields": "namedStyleType",
                }
            }
        )

    for st in inline_style_ranges:
        if st.get("bold"):
            requests.append(
                {
                    "updateTextStyle": {
                        "range": {
                            "startIndex": st["abs_start"],
                            "endIndex": st["abs_end"],
                        },
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                }
            )
        if st.get("url"):
            requests.append(
                {
                    "updateTextStyle": {
                        "range": {
                            "startIndex": st["abs_start"],
                            "endIndex": st["abs_end"],
                        },
                        "textStyle": {"link": {"url": st["url"]}},
                        "fields": "link",
                    }
                }
            )

    return requests


def append_to_notebooklm_master_doc(
    docs_service,
    master_doc_id: str,
    metadata: dict,
    standalone_doc_url: str,
    summary_md: str,
    force_append: bool = False,
) -> dict:
    """Append the formatted summary to the Master Google Doc synced with NotebookLM."""
    doc = docs_service.documents().get(documentId=master_doc_id).execute()
    doc_title = doc.get("title", "Master Document")
    existing_text, end_index = extract_doc_plain_text_and_end_index(doc)

    video_id = metadata["video_id"]
    existing_words = len(existing_text.split())
    added_words = len(summary_md.split())
    projected_words = existing_words + added_words

    if f"[{video_id}]" in existing_text and not force_append:
        return {
            "master_doc_id": master_doc_id,
            "master_doc_title": doc_title,
            "master_doc_url": f"https://docs.google.com/document/d/{master_doc_id}/edit",
            "action": "skipped_already_present",
            "total_words": existing_words,
        }

    requests = build_master_doc_batch_requests(
        base_index=end_index,
        metadata=metadata,
        standalone_doc_url=standalone_doc_url,
        summary_md=summary_md,
    )
    if requests:
        docs_service.documents().batchUpdate(
            documentId=master_doc_id,
            body={"requests": requests},
        ).execute()

    return {
        "master_doc_id": master_doc_id,
        "master_doc_title": doc_title,
        "master_doc_url": f"https://docs.google.com/document/d/{master_doc_id}/edit",
        "action": "appended",
        "total_words": projected_words,
    }


def main() -> int:
    ensure_venv()
    parser = argparse.ArgumentParser(
        description="Upload YouTube summary to Google Drive and append to NotebookLM Master Google Doc."
    )
    parser.add_argument(
        "--metadata",
        "-m",
        type=Path,
        required=True,
        help="Path to the metadata JSON generated by fetch_youtube.py",
    )
    parser.add_argument(
        "--summary",
        "-s",
        type=Path,
        required=True,
        help="Path to the extensive Markdown summary file",
    )
    parser.add_argument(
        "--folder-id",
        default=None,
        help="Override Google Drive folder ID (defaults to YOUTUBE_DRIVE_FOLDER_ID in .env)",
    )
    parser.add_argument(
        "--master-doc-id",
        default=None,
        help="Override NotebookLM Master Google Doc ID (defaults to YOUTUBE_MASTER_DOC_ID in .env)",
    )
    parser.add_argument(
        "--force-append",
        action="store_true",
        help="Append to Master Google Doc even if the video ID is already present",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and environment configuration without calling Google APIs",
    )
    args = parser.parse_args()

    base_dir = discover_and_load_env()

    if not args.metadata.exists():
        print(f"❌ Metadata JSON file not found: {args.metadata}", file=sys.stderr)
        return 1
    if not args.summary.exists():
        print(f"❌ Summary Markdown file not found: {args.summary}", file=sys.stderr)
        return 1

    metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
    summary_md = args.summary.read_text(encoding="utf-8").strip()
    summary_words = len(summary_md.split())

    if summary_words < 150:
        print(
            f"⚠️ Warning: Summary is very short ({summary_words} words). "
            "Ensure you generated an extensive summary following references/summary_template.md.",
            file=sys.stderr,
        )

    folder_id = args.folder_id or os.environ.get("YOUTUBE_DRIVE_FOLDER_ID", "").strip()
    master_doc_id = (
        args.master_doc_id or os.environ.get("YOUTUBE_MASTER_DOC_ID", "").strip()
    )
    skill_dir = Path(__file__).resolve().parent.parent
    raw_token = os.environ.get("GOOGLE_TOKEN_FILE", "google_token.json").strip()
    raw_creds = os.environ.get("GOOGLE_CREDENTIALS_FILE", "google_credentials.json").strip()
    token_file = Path(raw_token) if Path(raw_token).is_absolute() else (skill_dir / raw_token)
    creds_file = Path(raw_creds) if Path(raw_creds).is_absolute() else (skill_dir / raw_creds)
    if not token_file.exists() and (skill_dir / "google_token.json").exists():
        token_file = skill_dir / "google_token.json"
    if not creds_file.exists() and (skill_dir / "google_credentials.json").exists():
        creds_file = skill_dir / "google_credentials.json"

    if not folder_id:
        print(
            "❌ Missing YOUTUBE_DRIVE_FOLDER_ID in .env (or pass --folder-id).",
            file=sys.stderr,
        )
        return 1
    if not master_doc_id:
        print(
            "❌ Missing YOUTUBE_MASTER_DOC_ID in .env (or pass --master-doc-id).",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print(
            f"✅ Dry-run validation passed:\n"
            f"   • Video: {metadata.get('title')} ({metadata.get('video_id')})\n"
            f"   • Summary Word Count: {summary_words:,} words\n"
            f"   • Target Drive Folder ID: {folder_id}\n"
            f"   • Target NotebookLM Master Doc ID: {master_doc_id}\n"
            f"   • OAuth Token File: {token_file} (exists={token_file.exists()})"
        )
        return 0

    try:
        drive_service, docs_service = get_google_services(token_file, creds_file)
    except Exception as exc:
        print(f"❌ Google Authentication Error: {exc}", file=sys.stderr)
        return 1

    print("☁️ Uploading standalone Google Doc to Google Drive...", file=sys.stderr)
    try:
        drive_result = upload_standalone_doc_to_drive(
            drive_service=drive_service,
            folder_id=folder_id,
            metadata=metadata,
            summary_md=summary_md,
        )
    except Exception as exc:
        print(f"❌ Failed to upload standalone Doc to Google Drive: {exc}", file=sys.stderr)
        return 1

    standalone_url = drive_result.get(
        "webViewLink", f"https://docs.google.com/document/d/{drive_result['id']}/edit"
    )
    print(
        f"✅ Standalone Google Doc ({drive_result['action']}): {drive_result['name']}\n"
        f"   Link: {standalone_url}"
    )

    print("📓 Appending summary to NotebookLM Master Google Doc...", file=sys.stderr)
    try:
        master_result = append_to_notebooklm_master_doc(
            docs_service=docs_service,
            master_doc_id=master_doc_id,
            metadata=metadata,
            standalone_doc_url=standalone_url,
            summary_md=summary_md,
            force_append=args.force_append,
        )
    except Exception as exc:
        print(
            f"❌ Failed to append to NotebookLM Master Google Doc ({master_doc_id}): {exc}",
            file=sys.stderr,
        )
        return 1

    print(
        f"✅ NotebookLM Master Doc ({master_result['action']}): {master_result['master_doc_title']}\n"
        f"   Link: {master_result['master_doc_url']}\n"
        f"   Total Master Doc Size: ~{master_result['total_words']:,} / {NOTEBOOKLM_WORD_LIMIT:,} words"
    )

    if master_result["total_words"] >= NOTEBOOKLM_WARN_THRESHOLD:
        print(
            f"⚠️ WARNING: Master Google Doc is approaching NotebookLM's 500,000-word source limit "
            f"({master_result['total_words']:,} words). Consider creating a Volume 2 Master Doc soon.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
