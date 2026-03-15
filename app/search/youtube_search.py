"""YouTube search via yt-dlp — no API key, no account needed.

Uses yt-dlp's built-in ytsearchN: syntax which queries YouTube
directly without any official API.
"""

from __future__ import annotations

import json
import subprocess
from app.core.logging import get_logger

log = get_logger(__name__)


def search_youtube(
    query: str,
    max_results: int = 8,
    max_duration: int = 180,     # seconds — 180 = 3 min, keeps Shorts-style content
    append_shorts: bool = True,  # append "shorts" to bias toward vertical content
) -> list[str]:
    """Search YouTube and return video URLs matching the query.

    Args:
        query:         Natural language search e.g. "andrew tate fighting"
        max_results:   How many video URLs to return
        max_duration:  Skip videos longer than this (seconds)
        append_shorts: Append ' shorts' to the query to bias toward Shorts

    Returns:
        List of YouTube video URLs, ordered by relevance.
    """
    search_query_text = f"{query} shorts" if append_shorts else query
    yt_search = f"ytsearch{max_results * 3}:{search_query_text}"  # over-fetch then filter

    cmd = [
        "yt-dlp",
        "--quiet",
        "--flat-playlist",
        "--dump-json",
        "--no-playlist",
        yt_search,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        log.warning("YouTube search timed out for: %s", query)
        return []
    except FileNotFoundError:
        log.error("yt-dlp not found — run: pip install yt-dlp")
        return []

    urls: list[str] = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        vid_url = data.get("url") or data.get("webpage_url") or ""
        if not vid_url:
            continue

        # Filter by duration if available
        duration = data.get("duration") or 9999
        if duration > max_duration:
            continue

        urls.append(vid_url)
        if len(urls) >= max_results:
            break

    log.info("YouTube search '%s' → %d URLs found", query, len(urls))
    return urls
