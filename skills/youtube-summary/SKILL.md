---
name: youtube-summary
description: >-
  Takes a YouTube URL, extracts its full transcript and metadata (with automatic Gemini
  audio transcription fallback if captions are missing), generates an extensive,
  in-depth English summary (not just a high-level overview), uploads it as a native
  Google Doc to a configured Google Drive folder, and appends it to a Master Google Doc
  synced with a Gemini NotebookLM notebook. Use this skill whenever the user shares a
  YouTube link and asks to summarize it, save it to Drive, or add it to their notebook.
---

# YouTube Extensive Summarizer & NotebookLM Publisher Skill

This skill guides you through extracting the full content of a YouTube video, generating a comprehensive, deep-dive summary in **English**, uploading it to Google Drive as a standalone Google Doc, and appending it to a Master Google Doc linked to **Google NotebookLM**.

## References

Before drafting the summary, always read:
1. [Extensive Summary Template & Guidelines](./references/summary_template.md) — Structure, depth requirements, timestamp formatting, and section-by-section synthesis rules.

## Prerequisites & Environment

The helper scripts automatically load environment variables from `.env` in the current working directory, the skill directory (`~/.gemini/config/skills/youtube-summary/.env`), or parent project root:
- `YOUTUBE_DRIVE_FOLDER_ID`: Existing Google Drive Folder ID where standalone video summaries are uploaded.
- `YOUTUBE_MASTER_DOC_ID`: Existing Google Doc ID linked as a source in your NotebookLM notebook.
- `GOOGLE_CREDENTIALS_FILE`: Path to OAuth 2.0 `google_credentials.json` (defaults to `google_credentials.json`).
- `GOOGLE_TOKEN_FILE`: Path to OAuth 2.0 `google_token.json` (defaults to `google_token.json`).
- `GEMINI_API_KEY`: Used only as an automatic fallback when a video has no manual or auto-generated subtitles.

---

## Step-by-Step Workflow

### Step 1: Extract Video Metadata, Chapters & Transcript
1. Create `temp_workspace/` if it does not exist.
2. Run [fetch_youtube.py](./scripts/fetch_youtube.py) with the provided YouTube URL (use `.venv/bin/python` if a project virtualenv is active, otherwise `python3`):
   ```bash
   python3 ~/.gemini/config/skills/youtube-summary/scripts/fetch_youtube.py "<YOUTUBE_URL>" --output temp_workspace/yt_data.json
   ```
3. Inspect the script output:
   - By default, it fetches metadata and chapters via `yt-dlp` and retrieves the transcript via `youtube-transcript-api`.
   - If captions are disabled on the video, the script automatically falls back to downloading the audio track (`yt-dlp` + `ffmpeg`) and transcribing it via the Gemini API (`GEMINI_API_KEY`).
4. Read `temp_workspace/yt_data.json` to inspect the metadata, chapters/sections, and full timestamped transcript.

### Step 2: Generate an Extensive Summary in English
1. Read [references/summary_template.md](./references/summary_template.md) and follow every instruction strictly.
2. **Language Requirement**: Always write the summary in **English**, even if the original video and transcript are in Dutch or another language.
3. **Depth Requirement**: Do **NOT** produce a short or high-level summary. You must process every chapter/time-block of the transcript and retain:
   - Specific arguments, reasoning chains, and nuances
   - Concrete examples, case studies, statistics, and numbers mentioned
   - Tools, libraries, books, frameworks, or commands discussed
   - Direct or closely paraphrased notable quotes with clickable `[MM:SS](https://www.youtube.com/watch?v=<VIDEO_ID>&t=<SECONDS>s)` links
4. Save the complete Markdown summary to `temp_workspace/summary_<video_id>.md`.

### Step 3 & Step 4: Upload to Google Drive & Append to NotebookLM Master Doc
1. Validate the files first using `--dry-run`:
   ```bash
   python3 ~/.gemini/config/skills/youtube-summary/scripts/publish_summary.py \
     --metadata temp_workspace/yt_data.json \
     --summary temp_workspace/summary_<video_id>.md \
     --dry-run
   ```
2. Publish the summary to Google Drive and append it to the Master Google Doc:
   ```bash
   python3 ~/.gemini/config/skills/youtube-summary/scripts/publish_summary.py \
     --metadata temp_workspace/yt_data.json \
     --summary temp_workspace/summary_<video_id>.md
   ```
3. Verify the output:
   - Confirm that the standalone Google Doc was created (or updated) inside `YOUTUBE_DRIVE_FOLDER_ID`.
   - Confirm that the summary was appended to the Master Google Doc (`YOUTUBE_MASTER_DOC_ID`).
   - Check if any warning was printed regarding NotebookLM's 500,000-word source limit.

### Step 5: Report & Clean Up
1. Present a concise confirmation to the user including:
   - The **Executive Overview** of the video
   - Clickable link to the **Standalone Google Doc** in Google Drive
   - Clickable link to the **NotebookLM Master Google Doc** (reminding the user they can click *"Sync with Google Drive"* in NotebookLM to pull the new summary in one click)
2. Remove temporary files in `temp_workspace/` (`yt_data.json` and `summary_<video_id>.md`) once publishing succeeds.
