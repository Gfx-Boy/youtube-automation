"""Speech transcription using OpenAI Whisper — runs 100% locally, no API key.

Whisper auto-detects language, timestamps every word segment, and runs 
on CPU (slow but works) or MPS/CUDA (fast).

Model sizes and tradeoffs:
  tiny   — fastest, lowest accuracy  (~75 MB)
  base   — good balance, recommended (~145 MB)
  small  — better accuracy           (~465 MB)
  medium — high accuracy             (~1.5 GB)
"""

from __future__ import annotations

from pathlib import Path

from app.core.logging import get_logger

log = get_logger(__name__)

# ── lazy-loaded singleton ────────────────────────────────────────────
_model = None
_loaded_size: str | None = None


def _load_model(size: str = "base"):
    global _model, _loaded_size
    if _model is not None and _loaded_size == size:
        return _model
    import whisper
    log.info("Loading Whisper '%s' model (first run downloads ~145 MB) …", size)
    _model = whisper.load_model(size)
    _loaded_size = size
    log.info("Whisper ready.")
    return _model


# ── main transcription function ──────────────────────────────────────

def transcribe_video(
    video_path: str | Path,
    model_size: str = "base",
) -> list[dict]:
    """Transcribe a video or audio file.

    Returns a list of segment dicts:
        [{"start": 1.2, "end": 3.8, "text": "you have to be a winner"}, ...]

    Each segment maps to a timestamp range in the video.
    """
    path = str(video_path)
    log.info("Transcribing: %s …", Path(path).name)

    model = _load_model(model_size)

    result = model.transcribe(
        path,
        verbose=False,
        fp16=False,   # fp16=True only if CUDA available — avoids MPS errors
        language=None,  # auto-detect
    )

    segments = [
        {
            "start": float(s["start"]),
            "end":   float(s["end"]),
            "text":  s["text"].strip(),
        }
        for s in result.get("segments", [])
    ]

    log.info("  %s → %d segments (lang=%s)",
             Path(path).name, len(segments), result.get("language", "?"))
    return segments


# ── helpers ─────────────────────────────────────────────────────────

def transcript_for_range(
    segments: list[dict],
    start: float,
    end: float,
) -> str:
    """Return all transcript text that overlaps with time range [start, end]."""
    texts = [
        s["text"] for s in segments
        if s["end"] >= start and s["start"] <= end
    ]
    return " ".join(texts).strip()


_STOP_WORDS = {
    "a","an","the","and","or","but","in","on","at","to","for","of",
    "with","by","is","are","was","were","be","been","this","that","it",
    "he","she","they","we","you","i","my","his","her","their","our",
    "what","when","where","how","not","no","so","if","just","like",
    "clips","edit","video","short","shorts","best","moments","compilation",
}

def extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from a free-text subject description."""
    words = text.lower().replace("-", " ").split()
    return [w.strip(".,!?") for w in words if w not in _STOP_WORDS and len(w) > 2]


def keyword_score(transcript_text: str, keywords: list[str]) -> float:
    """Score 0.0–1.0: how many keywords appear in the transcript text."""
    if not keywords or not transcript_text:
        return 0.0
    lower = transcript_text.lower()
    hits = sum(1 for kw in keywords if kw in lower)
    return min(hits / len(keywords), 1.0)
