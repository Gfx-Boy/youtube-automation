"""Module 4 — Clip Analysis & Ranking.

Scores each detected scene on motion, brightness, contrast, sharpness,
face prominence, CLIP similarity, and (optionally) a trained aesthetic
ranker.  Outputs RankedClip objects sorted by composite score.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.schemas import ClipScore, RankedClip, SceneInfo

log = get_logger(__name__)

# ── lazy-loaded singletons ──────────────────────────────────────────
_clip_model = None
_clip_preprocess = None
_clip_tokenizer = None


def _load_clip():
    global _clip_model, _clip_preprocess, _clip_tokenizer
    if _clip_model is not None:
        return
    import open_clip
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", pretrained="laion2b_s34b_b79k"
    )
    model.eval()
    _clip_model = model
    _clip_preprocess = preprocess
    _clip_tokenizer = open_clip.get_tokenizer("ViT-B-32")
    log.info("OpenCLIP model loaded.")


# ── frame sampling ──────────────────────────────────────────────────

def _sample_frames(video_path: str, start: float, end: float, n: int = 5) -> list[np.ndarray]:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames: list[np.ndarray] = []
    timestamps = np.linspace(start, end, n + 2)[1:-1]
    for t in timestamps:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    cap.release()
    return frames


# ── low-level scorers ──────────────────────────────────────────────

def _motion_score(frames: list[np.ndarray]) -> float:
    if len(frames) < 2:
        return 0.0
    diffs = []
    for a, b in zip(frames[:-1], frames[1:]):
        ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
        gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
        diffs.append(np.mean(cv2.absdiff(ga, gb)))
    return float(np.mean(diffs))


def _brightness(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray)) / 255.0


def _contrast(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(np.std(gray)) / 128.0


def _sharpness(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(lap.var()) / 1000.0


_face_cascade = None


def _face_prominence(frame: np.ndarray) -> float:
    global _face_cascade
    if _face_cascade is None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        _face_cascade = cv2.CascadeClassifier(cascade_path)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = _face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(40, 40))
    if len(faces) == 0:
        return 0.0
    # largest face area / frame area
    areas = [w * h for (_, _, w, h) in faces]
    frame_area = frame.shape[0] * frame.shape[1]
    return max(areas) / frame_area


def _clip_similarity(frames: list[np.ndarray], prompts: list[str]) -> float:
    """Compute average CLIP similarity between frames and text prompts."""
    if not prompts or not frames:
        return 0.0
    _load_clip()
    from PIL import Image

    scores: list[float] = []
    tokens = _clip_tokenizer(prompts)

    with torch.no_grad():
        text_features = _clip_model.encode_text(tokens)
        text_features /= text_features.norm(dim=-1, keepdim=True)

        for frame in frames[:3]:  # limit for speed
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img_tensor = _clip_preprocess(img).unsqueeze(0)
            img_features = _clip_model.encode_image(img_tensor)
            img_features /= img_features.norm(dim=-1, keepdim=True)
            sim = (img_features @ text_features.T).mean().item()
            scores.append(sim)

    return float(np.mean(scores)) if scores else 0.0


# ── optional trained aesthetic ranker ───────────────────────────────

_aesthetic_model = None


def _load_aesthetic_ranker() -> bool:
    global _aesthetic_model
    if _aesthetic_model is not None:
        return True
    weight_path = get_settings().weights_dir / "aesthetic_ranker_ts.pt"  # TorchScript export from Notebook 2
    if not weight_path.exists():
        return False
    _aesthetic_model = torch.jit.load(str(weight_path), map_location="cpu")
    _aesthetic_model.eval()
    log.info("Loaded aesthetic ranker from %s", weight_path)
    return True


def _aesthetic_score(frames: list[np.ndarray]) -> float:
    if not _load_aesthetic_ranker():
        return 0.0
    from PIL import Image
    _load_clip()
    scores: list[float] = []
    with torch.no_grad():
        for frame in frames[:3]:
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img_tensor = _clip_preprocess(img).unsqueeze(0)
            emb = _clip_model.encode_image(img_tensor)
            emb /= emb.norm(dim=-1, keepdim=True)
            score = _aesthetic_model(emb).item()
            scores.append(score)
    return float(np.mean(scores)) if scores else 0.0


# ── main scoring function ──────────────────────────────────────────

def score_scene(
    scene: SceneInfo,
    prompts: Optional[list[str]] = None,
    weights: Optional[dict[str, float]] = None,
    transcript_segments: Optional[list[dict]] = None,
    keywords: Optional[list[str]] = None,
) -> ClipScore:
    """Compute all scores for a scene, returning a ClipScore.

    Args:
        scene:                The scene to score.
        prompts:              CLIP text prompts for visual similarity.
        weights:              Per-metric composite weights.
        transcript_segments:  Whisper segments for the source video
                              e.g. [{"start":1.2,"end":3.4,"text":"..."}]
        keywords:             Keywords extracted from the user's subject/prompt.
                              Used to score transcript relevance.
    """
    prompts = prompts or ["cinematic", "dramatic", "visually striking"]

    # When transcript data is available, boost its weight and reduce others slightly
    has_transcript = bool(transcript_segments and keywords)
    w = weights or (
        {
            "motion": 0.12,
            "brightness": 0.04,
            "contrast": 0.08,
            "sharpness": 0.12,
            "face_prominence": 0.09,
            "clip_similarity": 0.20,
            "aesthetic_score": 0.15,
            "transcript_score": 0.20,   # strong signal when available
        }
        if has_transcript else
        {
            "motion": 0.15,
            "brightness": 0.05,
            "contrast": 0.10,
            "sharpness": 0.15,
            "face_prominence": 0.10,
            "clip_similarity": 0.25,
            "aesthetic_score": 0.20,
            "transcript_score": 0.00,
        }
    )

    frames = _sample_frames(scene.source_file, scene.start_time, scene.end_time)
    if not frames:
        return ClipScore()

    mid = frames[len(frames) // 2]

    # Transcript score
    tscore = 0.0
    if has_transcript:
        from app.analysis.transcriber import transcript_for_range, keyword_score
        clip_text = transcript_for_range(
            transcript_segments, scene.start_time, scene.end_time
        )
        tscore = keyword_score(clip_text, keywords)

    s = ClipScore(
        motion=min(_motion_score(frames) / 30.0, 1.0),
        brightness=_brightness(mid),
        contrast=min(_contrast(mid), 1.0),
        sharpness=min(_sharpness(mid), 1.0),
        face_prominence=min(_face_prominence(mid), 1.0),
        clip_similarity=max(_clip_similarity(frames, prompts), 0.0),
        aesthetic_score=max(_aesthetic_score(frames), 0.0),
        transcript_score=tscore,
    )
    s.composite = sum(getattr(s, k, 0.0) * v for k, v in w.items())
    return s


# ── batch rank ──────────────────────────────────────────────────────

def rank_scenes(
    scenes: list[SceneInfo],
    prompts: Optional[list[str]] = None,
    weights: Optional[dict[str, float]] = None,
    top_n: Optional[int] = None,
    transcripts: Optional[dict[str, list[dict]]] = None,
    keywords: Optional[list[str]] = None,
) -> list[RankedClip]:
    """Score and rank all scenes, returning RankedClip objects.

    Args:
        transcripts: Maps source_file path → list of Whisper segments.
                     When provided, transcript_score contributes to ranking.
        keywords:    Keywords from the user's subject query.
    """
    ranked: list[RankedClip] = []
    for scene in scenes:
        segs = (transcripts or {}).get(scene.source_file)
        scores = score_scene(
            scene,
            prompts=prompts,
            weights=weights,
            transcript_segments=segs,
            keywords=keywords,
        )
        ranked.append(RankedClip(scene=scene, scores=scores))

    ranked.sort(key=lambda c: c.scores.composite, reverse=True)
    if top_n:
        ranked = ranked[:top_n]
    log.info("Ranked %d clips (top composite=%.3f, transcript used=%s)",
             len(ranked),
             ranked[0].scores.composite if ranked else 0,
             bool(transcripts))
    return ranked
