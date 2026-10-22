#!/usr/bin/env python3
"""
Fetches YouTube video metadata, chapters, and full timestamped transcript.
Primary transcript source: youtube-transcript-api (manual or auto-generated captions).
Automatic fallback: Downloads audio via yt-dlp + ffmpeg and transcribes via Gemini API
when captions/subtitles are disabled or unavailable on the video.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlparse


PREFERRED_LANGUAGES = ["en", "en-US", "en-GB", "nl", "nl-BE", "de", "fr", "es"]
DEFAULT_SECTION_SECONDS = 600  # 10-minute intervals when video has no chapters


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


def discover_and_load_env() -> None:
    """Search common locations for .env files and load them."""
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    candidates = [
        Path.cwd() / ".env",
        skill_dir / ".env",
    ]
    # Also walk up to 4 parent directories from script_dir (e.g., repo root)
    for parent in list(script_dir.parents)[:5]:
        candidates.append(parent / ".env")
    for candidate in candidates:
        load_dotenv_simple(candidate)


def extract_video_id(url_or_id: str) -> str:
    """Extract the 11-character YouTube video ID from any standard YouTube URL."""
    candidate = url_or_id.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        return candidate

    parsed = urlparse(candidate)
    host = (parsed.netloc or "").lower()
    path = parsed.path or ""

    if "youtu.be" in host:
        vid = path.lstrip("/").split("/")[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            return vid

    if "youtube.com" in host or "youtube-nocookie.com" in host:
        if path == "/watch":
            qs = parse_qs(parsed.query)
            v_list = qs.get("v", [])
            if v_list and re.fullmatch(r"[A-Za-z0-9_-]{11}", v_list[0]):
                return v_list[0]
        for prefix in ("/shorts/", "/live/", "/embed/", "/v/"):
            if path.startswith(prefix):
                vid = path[len(prefix) :].split("/")[0]
                if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                    return vid

    # Fallback regex search
    match = re.search(r"(?:v=|youtu\.be/|shorts/|live/|embed/)([A-Za-z0-9_-]{11})", candidate)
    if match:
        return match.group(1)

    raise ValueError(f"Could not extract a valid 11-character YouTube video ID from: {url_or_id}")


def format_seconds(seconds: float | int) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    total = max(0, int(round(seconds)))
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def parse_timestamp_to_seconds(ts_str: str) -> float:
    """Parse MM:SS or HH:MM:SS string into seconds."""
    parts = [int(p) for p in ts_str.strip("[]() ").split(":")]
    if len(parts) == 3:
        return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    if len(parts) == 2:
        return float(parts[0] * 60 + parts[1])
    return 0.0


def fetch_metadata_ytdlp(video_id: str) -> dict:
    """Extract rich video metadata and chapters using yt-dlp without downloading video."""
    try:
        import yt_dlp  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "Missing 'yt-dlp'. Install it with: .venv/bin/pip install yt-dlp"
        ) from exc

    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(canonical_url, download=False)

    raw_date = info.get("upload_date") or ""
    if len(raw_date) == 8 and raw_date.isdigit():
        published_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    else:
        published_date = datetime.now().strftime("%Y-%m-%d")

    duration_sec = int(info.get("duration") or 0)
    raw_chapters = info.get("chapters") or []
    chapters = []
    for idx, ch in enumerate(raw_chapters, start=1):
        start_t = float(ch.get("start_time") or 0.0)
        end_t = float(ch.get("end_time") or duration_sec)
        chapters.append(
            {
                "index": idx,
                "title": ch.get("title") or f"Chapter {idx}",
                "start_seconds": int(start_t),
                "end_seconds": int(end_t),
                "start_timestamp": format_seconds(start_t),
                "end_timestamp": format_seconds(end_t),
                "timestamp_url": f"https://www.youtube.com/watch?v={video_id}&t={int(start_t)}s",
            }
        )

    return {
        "video_id": video_id,
        "url": canonical_url,
        "title": info.get("title") or f"YouTube Video {video_id}",
        "channel": info.get("channel") or info.get("uploader") or "Unknown Channel",
        "published_date": published_date,
        "duration_seconds": duration_sec,
        "duration_formatted": format_seconds(duration_sec),
        "description": info.get("description") or "",
        "chapters": chapters,
    }


def fetch_captions_transcript(video_id: str) -> tuple[list[dict], dict] | None:
    """
    Attempt to fetch subtitles using youtube-transcript-api (compatible with v0.6.x and v1.x).
    Returns (segments, source_meta) or None if captions are unavailable/disabled.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "Missing 'youtube-transcript-api'. Install with: .venv/bin/pip install youtube-transcript-api"
        ) from exc

    try:
        # Support both youtube-transcript-api >= 1.0 (instance methods) and 0.6.x (class methods)
        if hasattr(YouTubeTranscriptApi, "list_transcripts"):
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        else:
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)

        selected_transcript = None
        # 1. Try manual captions in preferred languages
        try:
            selected_transcript = transcript_list.find_manually_created_transcript(
                PREFERRED_LANGUAGES
            )
        except Exception:
            pass

        # 2. Try any manual transcript
        if selected_transcript is None:
            for tr in transcript_list:
                if not getattr(tr, "is_generated", True):
                    selected_transcript = tr
                    break

        # 3. Try auto-generated captions in preferred languages
        if selected_transcript is None:
            try:
                selected_transcript = transcript_list.find_generated_transcript(
                    PREFERRED_LANGUAGES
                )
            except Exception:
                pass

        # 4. Fallback to first available transcript in any language
        if selected_transcript is None:
            for tr in transcript_list:
                selected_transcript = tr
                break

        if selected_transcript is None:
            return None

        raw_entries = selected_transcript.fetch()
        segments: list[dict] = []
        for item in raw_entries:
            if isinstance(item, dict):
                start = float(item.get("start", 0.0))
                duration = float(item.get("duration", 0.0))
                text = str(item.get("text", "")).replace("\n", " ").strip()
            else:
                start = float(getattr(item, "start", 0.0))
                duration = float(getattr(item, "duration", 0.0))
                text = str(getattr(item, "text", "")).replace("\n", " ").strip()

            if not text:
                continue
            segments.append(
                {
                    "start_seconds": round(start, 2),
                    "duration_seconds": round(duration, 2),
                    "timestamp": format_seconds(start),
                    "timestamp_url": f"https://www.youtube.com/watch?v={video_id}&t={int(start)}s",
                    "text": text,
                }
            )

        if not segments:
            return None

        is_gen = bool(getattr(selected_transcript, "is_generated", False))
        lang = getattr(selected_transcript, "language", "Unknown")
        lang_code = getattr(selected_transcript, "language_code", "unknown")
        source_meta = {
            "method": "youtube_captions",
            "caption_type": "Auto-Generated Captions" if is_gen else "Manual Captions",
            "language": lang,
            "language_code": lang_code,
        }
        return segments, source_meta

    except Exception as exc:
        print(
            f"⚠️ Captions unavailable via youtube-transcript-api ({exc.__class__.__name__}: {exc}).",
            file=sys.stderr,
        )
        return None


def transcribe_via_gemini_audio_fallback(
    video_id: str, gemini_model: str = "gemini-2.5-flash"
) -> tuple[list[dict], dict]:
    """
    Fallback when a YouTube video has no captions:
    1. Downloads compressed mono audio via yt-dlp + ffmpeg into a temporary directory.
    2. Uploads audio to the Gemini Files API (`google-genai`).
    3. Generates a detailed timestamped transcript and cleans up local + remote files.
    """
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Captions are disabled on this video, and GEMINI_API_KEY is not set in .env "
            "for the audio transcription fallback."
        )

    try:
        from google import genai  # noqa: PLC0415
        import yt_dlp  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "Audio fallback requires 'google-genai' and 'yt-dlp'. "
            "Install with: .venv/bin/pip install google-genai yt-dlp"
        ) from exc

    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    print(
        "🎙️ Downloading compressed audio stream via yt-dlp + ffmpeg for Gemini transcription fallback...",
        file=sys.stderr,
    )

    with tempfile.TemporaryDirectory(prefix=f"yt_audio_{video_id}_") as tmp_dir:
        out_tmpl = str(Path(tmp_dir) / f"{video_id}.%(ext)s")
        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": out_tmpl,
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "64",
                }
            ],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([canonical_url])

        audio_files = list(Path(tmp_dir).glob(f"{video_id}.*"))
        if not audio_files:
            raise RuntimeError("Failed to download audio track via yt-dlp.")
        audio_path = audio_files[0]

        client = genai.Client(api_key=api_key)
        print(
            f"☁️ Uploading {audio_path.name} ({audio_path.stat().st_size / (1024 * 1024):.1f} MB) "
            f"to Gemini Files API...",
            file=sys.stderr,
        )
        uploaded_file = client.files.upload(file=str(audio_path))
        try:
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(3)
                uploaded_file = client.files.get(name=uploaded_file.name)
            if uploaded_file.state.name != "ACTIVE":
                raise RuntimeError(
                    f"Gemini audio file processing failed with state: {uploaded_file.state.name}"
                )

            prompt = (
                "Transcribe this audio completely and accurately. "
                "Format every single line with a timestamp in brackets at the start of the line, "
                "every 15 to 30 seconds, in the exact format:\n"
                "[MM:SS] verbatim spoken text here\n"
                "(or [HH:MM:SS] if over 1 hour). Do not summarize or skip sections."
            )
            print(f"🧠 Transcribing audio with {gemini_model}...", file=sys.stderr)
            response = client.models.generate_content(
                model=gemini_model,
                contents=[uploaded_file, prompt],
            )
            raw_text = response.text or ""
        finally:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass

    segments: list[dict] = []
    line_pattern = re.compile(r"^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[-:]?\s*(.+)$")
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = line_pattern.match(line)
        if match:
            ts_str, text = match.group(1), match.group(2).strip()
            start_sec = parse_timestamp_to_seconds(ts_str)
            segments.append(
                {
                    "start_seconds": round(start_sec, 2),
                    "duration_seconds": 20.0,
                    "timestamp": format_seconds(start_sec),
                    "timestamp_url": f"https://www.youtube.com/watch?v={video_id}&t={int(start_sec)}s",
                    "text": text,
                }
            )
        elif segments:
            segments[-1]["text"] += f" {line}"
        else:
            segments.append(
                {
                    "start_seconds": 0.0,
                    "duration_seconds": 20.0,
                    "timestamp": "00:00",
                    "timestamp_url": f"https://www.youtube.com/watch?v={video_id}&t=0s",
                    "text": line,
                }
            )

    if not segments:
        raise RuntimeError("Gemini audio fallback returned an empty transcript.")

    source_meta = {
        "method": "gemini_audio_fallback",
        "caption_type": f"Gemini Audio Transcription ({gemini_model})",
        "language": "Auto-detected",
        "language_code": "auto",
    }
    return segments, source_meta


def build_sections(
    video_id: str, duration_seconds: int, chapters: list[dict], segments: list[dict]
) -> list[dict]:
    """
    Group transcript segments into creator-defined chapters, or 10-minute intervals
    if the video does not define chapters.
    """
    max_seg_time = int(segments[-1]["start_seconds"] + 30) if segments else 0
    total_duration = max(duration_seconds, max_seg_time, 1)

    if chapters:
        boundaries = chapters
    else:
        boundaries = []
        idx = 1
        for start_t in range(0, total_duration, DEFAULT_SECTION_SECONDS):
            end_t = min(start_t + DEFAULT_SECTION_SECONDS, total_duration)
            boundaries.append(
                {
                    "index": idx,
                    "title": f"Section {idx} ({format_seconds(start_t)} – {format_seconds(end_t)})",
                    "start_seconds": start_t,
                    "end_seconds": end_t,
                    "start_timestamp": format_seconds(start_t),
                    "end_timestamp": format_seconds(end_t),
                    "timestamp_url": f"https://www.youtube.com/watch?v={video_id}&t={start_t}s",
                }
            )
            idx += 1

    sections: list[dict] = []
    for b in boundaries:
        s_start = b["start_seconds"]
        s_end = b["end_seconds"]
        sec_segments = [
            seg
            for seg in segments
            if s_start <= seg["start_seconds"] < s_end
            or (b["index"] == len(boundaries) and seg["start_seconds"] >= s_start)
        ]
        formatted_lines = [f"[{seg['timestamp']}] {seg['text']}" for seg in sec_segments]
        sections.append(
            {
                **b,
                "segment_count": len(sec_segments),
                "transcript_text": "\n".join(formatted_lines),
            }
        )
    return sections


def main() -> int:
    ensure_venv()
    parser = argparse.ArgumentParser(
        description="Fetch YouTube metadata, chapters, and timestamped transcript."
    )
    parser.add_argument("youtube_url", help="YouTube video URL or 11-char video ID")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output JSON file path (defaults to temp_workspace/yt_<video_id>.json)",
    )
    parser.add_argument(
        "--force-audio-fallback",
        action="store_true",
        help="Skip caption lookup and transcribe audio via yt-dlp + Gemini API",
    )
    parser.add_argument(
        "--gemini-model",
        default="gemini-2.5-flash",
        help="Gemini model to use when audio transcription fallback is triggered",
    )
    args = parser.parse_args()

    discover_and_load_env()

    try:
        video_id = extract_video_id(args.youtube_url)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    output_path = args.output or (Path("temp_workspace") / f"yt_{video_id}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Fetching metadata for YouTube video ID: {video_id}...", file=sys.stderr)
    try:
        metadata = fetch_metadata_ytdlp(video_id)
    except Exception as exc:
        print(f"❌ Failed to fetch metadata via yt-dlp: {exc}", file=sys.stderr)
        return 1

    result = None
    if not args.force_audio_fallback:
        print("📝 Fetching captions via youtube-transcript-api...", file=sys.stderr)
        result = fetch_captions_transcript(video_id)

    if result is None:
        try:
            segments, source_meta = transcribe_via_gemini_audio_fallback(
                video_id, gemini_model=args.gemini_model
            )
        except Exception as exc:
            print(f"❌ Transcript extraction failed: {exc}", file=sys.stderr)
            return 1
    else:
        segments, source_meta = result

    sections = build_sections(
        video_id=video_id,
        duration_seconds=metadata["duration_seconds"],
        chapters=metadata["chapters"],
        segments=segments,
    )

    full_transcript_text = "\n".join(
        f"[{seg['timestamp']}] {seg['text']}" for seg in segments
    )
    word_count = len(full_transcript_text.split())

    payload = {
        **metadata,
        "transcript_source": source_meta,
        "transcript_stats": {
            "segment_count": len(segments),
            "section_count": len(sections),
            "word_count": word_count,
        },
        "sections": sections,
        "full_transcript": full_transcript_text,
    }

    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"✅ Saved YouTube data to {output_path}\n"
        f"   • Title: {metadata['title']}\n"
        f"   • Channel: {metadata['channel']} ({metadata['duration_formatted']})\n"
        f"   • Source: {source_meta['caption_type']} ({source_meta['language']})\n"
        f"   • Sections: {len(sections)} | Segments: {len(segments)} | Words: {word_count:,}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
