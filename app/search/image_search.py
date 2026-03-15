"""Module 2 — Asset / Image Search.

Uses DuckDuckGo image search — no API key or account required.
Provide the same provider interface so you can swap providers if needed.
"""

from __future__ import annotations

import abc
import hashlib
from pathlib import Path
from typing import Optional

import httpx
from duckduckgo_search import DDGS

from app.core.logging import get_logger
from app.core.project_manager import get_project_path

log = get_logger(__name__)


# ───────────────────── provider interface ───────────────────────────

class ImageSearchResult:
    def __init__(self, url: str, title: str = "", source: str = "", width: int = 0, height: int = 0):
        self.url = url
        self.title = title
        self.source = source
        self.width = width
        self.height = height


class ImageSearchProvider(abc.ABC):
    @abc.abstractmethod
    def search(self, query: str, num: int = 5) -> list[ImageSearchResult]:
        ...


# ───────────────── DuckDuckGo provider (no API key) ─────────────────

class DuckDuckGoImageSearch(ImageSearchProvider):
    """Image search via DuckDuckGo — completely free, no API key needed."""

    def search(self, query: str, num: int = 5) -> list[ImageSearchResult]:
        results: list[ImageSearchResult] = []
        try:
            with DDGS() as ddgs:
                for item in ddgs.images(
                    query,
                    max_results=num,
                    safesearch="moderate",
                ):
                    results.append(ImageSearchResult(
                        url=item.get("image", ""),
                        title=item.get("title", ""),
                        source=item.get("source", ""),
                        width=item.get("width", 0),
                        height=item.get("height", 0),
                    ))
        except Exception as exc:
            log.warning("DuckDuckGo image search failed: %s", exc)
        log.info("DDG image search '%s' → %d results", query, len(results))
        return results


# Keep the old name as an alias so nothing else in the codebase breaks
GoogleImageSearch = DuckDuckGoImageSearch


# ─────────────────── download & validate ────────────────────────────

MIN_IMAGE_SIZE = 10_000   # bytes
MAX_IMAGE_SIZE = 20_000_000
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


def download_image(
    url: str,
    project_id: str,
    subfolder: str = "images",
) -> Optional[Path]:
    """Download a single image into the project's images/ folder."""
    dest_dir = get_project_path(project_id) / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Image download failed %s — %s", url, exc)
        return None

    content_type = resp.headers.get("content-type", "")
    if not any(t in content_type for t in ALLOWED_TYPES):
        log.warning("Skipping %s — content-type %s", url, content_type)
        return None

    data = resp.content
    if not (MIN_IMAGE_SIZE <= len(data) <= MAX_IMAGE_SIZE):
        log.warning("Skipping %s — size %d bytes", url, len(data))
        return None

    ext = "jpg"
    if "png" in content_type:
        ext = "png"
    elif "webp" in content_type:
        ext = "webp"

    name_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    dest = dest_dir / f"{name_hash}.{ext}"
    dest.write_bytes(data)
    log.info("Image saved → %s", dest.name)
    return dest


# ──────────── convenience: search + download in one call ────────────

def search_and_download(
    query: str,
    project_id: str,
    provider: ImageSearchProvider | None = None,
    num: int = 5,
) -> list[Path]:
    """Search for images and download valid ones into the project."""
    prov = provider or DuckDuckGoImageSearch()
    results = prov.search(query, num=num)
    paths: list[Path] = []
    for r in results:
        p = download_image(r.url, project_id)
        if p:
            paths.append(p)
    return paths
