"""Module 1 — Ingestion.

Downloads media from URLs (via yt-dlp) or copies local files into the
project's raw_media/ folder.  Also copies/moves the audio file into
audio/.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.project_manager import get_project_path

log = get_logger(__name__)


# ── Download via yt-dlp ─────────────────────────────────────────────

def download_url(
    url: str,
    project_id: str,
    *,
    max_resolution: str = "1080",
    output_template: Optional[str] = None,
) -> Path:
    """Download a single URL into the project's raw_media/ folder."""
    dest = get_project_path(project_id) / "raw_media"
    dest.mkdir(parents=True, exist_ok=True)

    tmpl = output_template or str(dest / "%(title)s_%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", f"bestvideo[height<={max_resolution}]+bestaudio/best[height<={max_resolution}]",
        "--merge-output-format", "mp4",
        "-o", tmpl,
        "--restrict-filenames",
        url,
    ]
    log.info("Downloading %s …", url)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        log.error("yt-dlp failed: %s", result.stderr)
        raise RuntimeError(f"yt-dlp error: {result.stderr[:500]}")

    # Find the downloaded file (most recent mp4 in dest)
    mp4s = sorted(dest.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4s:
        raise FileNotFoundError("Download succeeded but no mp4 found.")
    log.info("Downloaded → %s", mp4s[0].name)
    return mp4s[0]


def download_urls(urls: list[str], project_id: str) -> list[Path]:
    """Download a batch of URLs for a project."""
    paths = []
    for url in urls:
        try:
            p = download_url(url, project_id)
            paths.append(p)
        except Exception as exc:
            log.warning("Skipping %s — %s", url, exc)
    return paths


# ── Local file ingestion ────────────────────────────────────────────

def ingest_local_file(file_path: str | Path, project_id: str) -> Path:
    """Copy a local media file into the project's raw_media/."""
    src = Path(file_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")

    dest_dir = get_project_path(project_id) / "raw_media"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    shutil.copy2(src, dest)
    log.info("Ingested local file → %s", dest.name)
    return dest


def ingest_local_files(file_paths: list[str | Path], project_id: str) -> list[Path]:
    return [ingest_local_file(f, project_id) for f in file_paths]


# ── Audio ingestion ─────────────────────────────────────────────────

def ingest_audio(audio_path: str | Path, project_id: str) -> Path:
    """Copy the audio/music file into the project's audio/ folder."""
    src = Path(audio_path)
    if not src.exists():
        raise FileNotFoundError(f"Audio file not found: {src}")

    dest_dir = get_project_path(project_id) / "audio"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    log.info("Audio ingested → %s", dest.name)
    return dest


# ── Extract audio from video ───────────────────────────────────────

def extract_audio_from_video(video_path: str | Path, project_id: str) -> Path:
    """Use FFmpeg to extract the audio track from a video file."""
    settings = get_settings()
    src = Path(video_path)
    dest_dir = get_project_path(project_id) / "audio"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (src.stem + ".wav")

    cmd = [
        settings.ffmpeg_bin,
        "-y", "-i", str(src),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "22050", "-ac", "1",
        str(dest),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    log.info("Extracted audio → %s", dest.name)
    return dest
