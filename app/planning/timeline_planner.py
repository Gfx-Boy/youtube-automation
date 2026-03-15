"""Module 6 — Timeline Planner.

Rule-based engine that decides:
  - which clip goes where
  - how long each clip stays
  - where transitions happen
  - which text appears
  - what effect goes on the beat

The output is a Timeline object (the project.json source of truth).
"""

from __future__ import annotations

import random
from typing import Optional

from app.core.logging import get_logger
from app.core.schemas import (
    AudioSection,
    BeatMap,
    EffectType,
    RankedClip,
    RenderConfig,
    SectionType,
    TextAnimation,
    TextLayer,
    Timeline,
    TimelineClip,
    TransitionType,
)

log = get_logger(__name__)


# ── section-based rule sets ─────────────────────────────────────────

SECTION_RULES: dict[SectionType, dict] = {
    SectionType.INTRO: {
        "cut_duration": (1.5, 3.0),
        "transitions": [TransitionType.CROSSFADE, TransitionType.FADE_BLACK],
        "effects": [EffectType.NONE],
        "text_anim": TextAnimation.BLUR_REVEAL,
    },
    SectionType.BUILDUP: {
        "cut_duration": (0.8, 1.5),
        "transitions": [TransitionType.CROSSFADE, TransitionType.CUT],
        "effects": [EffectType.NONE, EffectType.GLOW],
        "text_anim": TextAnimation.SLIDE_UP,
    },
    SectionType.DROP: {
        "cut_duration": (0.3, 0.8),
        "transitions": [TransitionType.CUT, TransitionType.FLASH],
        "effects": [EffectType.FLASH, EffectType.PUNCH_ZOOM, EffectType.SHAKE, EffectType.RGB_SPLIT],
        "text_anim": TextAnimation.BEAT_BOUNCE,
    },
    SectionType.VERSE: {
        "cut_duration": (1.0, 2.0),
        "transitions": [TransitionType.CUT, TransitionType.CROSSFADE],
        "effects": [EffectType.NONE],
        "text_anim": TextAnimation.WORD_BY_WORD,
    },
    SectionType.CHORUS: {
        "cut_duration": (0.5, 1.2),
        "transitions": [TransitionType.CUT, TransitionType.ZOOM_IN],
        "effects": [EffectType.PUNCH_ZOOM, EffectType.FLASH],
        "text_anim": TextAnimation.POP_IN,
    },
    SectionType.BRIDGE: {
        "cut_duration": (1.5, 2.5),
        "transitions": [TransitionType.CROSSFADE, TransitionType.BLUR],
        "effects": [EffectType.BLUR_PULSE, EffectType.GLOW],
        "text_anim": TextAnimation.BLUR_REVEAL,
    },
    SectionType.OUTRO: {
        "cut_duration": (2.0, 4.0),
        "transitions": [TransitionType.FADE_BLACK, TransitionType.CROSSFADE],
        "effects": [EffectType.NONE],
        "text_anim": TextAnimation.SLIDE_UP,
    },
}


# ── planner ─────────────────────────────────────────────────────────

def plan_timeline(
    ranked_clips: list[RankedClip],
    beat_map: BeatMap,
    audio_file: str,
    *,
    style_preset: Optional[dict] = None,
    text_entries: Optional[list[dict]] = None,
    render_config: Optional[RenderConfig] = None,
) -> Timeline:
    """Build a full timeline from ranked clips + audio analysis.

    Args:
        ranked_clips: clips sorted by composite score (best first).
        beat_map: output of audio analysis.
        audio_file: path to the audio file.
        style_preset: optional overrides for section rules.
        text_entries: list of {"text": ..., "time": ..., "duration": ...}.
        render_config: resolution/fps/codec.

    Returns:
        A complete Timeline ready for rendering.
    """
    rconfig = render_config or RenderConfig()
    sections = beat_map.sections or []
    beats = beat_map.beat_times or []
    duration = sections[-1].end_time if sections else 30.0

    timeline_clips: list[TimelineClip] = []
    clip_pool = list(ranked_clips)   # working copy
    cursor = 0.0  # current position on the output timeline

    for section in sections:
        rules = SECTION_RULES.get(section.section_type, SECTION_RULES[SectionType.VERSE])
        sec_start = section.start_time
        sec_end = section.end_time

        while cursor < sec_end and clip_pool:
            # Determine clip duration from section rules
            min_dur, max_dur = rules["cut_duration"]

            # Snap to nearest beat if possible
            clip_dur = _snap_duration(cursor, min_dur, max_dur, beats)

            # Don't overshoot section end
            clip_dur = min(clip_dur, sec_end - cursor)
            if clip_dur < 0.2:
                break

            # Pick best available clip
            clip = _pick_clip(clip_pool, section.section_type)

            # Choose transition
            trans = random.choice(rules["transitions"])
            trans_dur = 0.15 if trans != TransitionType.CUT else 0.0

            # Choose beat-synced effect
            effect = EffectType.NONE
            if _is_on_beat(cursor, beats, tolerance=0.1):
                effect = random.choice(rules["effects"])

            tc = TimelineClip(
                clip=clip,
                timeline_start=round(cursor, 3),
                timeline_end=round(cursor + clip_dur, 3),
                transition_in=trans,
                transition_duration=trans_dur,
                effect=effect,
            )
            timeline_clips.append(tc)
            cursor = round(cursor + clip_dur, 3)

    # ── text layers ─────────────────────────────────────────────────
    text_layers: list[TextLayer] = []
    if text_entries:
        for t in text_entries:
            sec = _section_at(t.get("time", 0), sections)
            anim = SECTION_RULES.get(sec, SECTION_RULES[SectionType.VERSE])["text_anim"]
            text_layers.append(TextLayer(
                text=t["text"],
                start_time=t.get("time", 0),
                end_time=t.get("time", 0) + t.get("duration", 2.0),
                animation=anim,
            ))

    timeline = Timeline(
        clips=timeline_clips,
        text_layers=text_layers,
        audio_file=audio_file,
        beat_map=beat_map,
        duration=round(cursor, 3),
        render_config=rconfig,
    )
    log.info("Timeline planned: %d clips, %d text layers, %.1fs duration",
             len(timeline_clips), len(text_layers), timeline.duration)
    return timeline


# ── helpers ─────────────────────────────────────────────────────────

def _snap_duration(cursor: float, min_dur: float, max_dur: float, beats: list[float]) -> float:
    """Try to make clip end on a beat."""
    target = (min_dur + max_dur) / 2
    best = target
    best_dist = float("inf")
    for b in beats:
        d = b - cursor
        if min_dur <= d <= max_dur:
            dist = abs(d - target)
            if dist < best_dist:
                best = d
                best_dist = dist
    return best


def _is_on_beat(time: float, beats: list[float], tolerance: float = 0.1) -> bool:
    return any(abs(b - time) < tolerance for b in beats)


def _pick_clip(pool: list[RankedClip], section_type: SectionType) -> RankedClip:
    """Pick the best clip for this section type, cycling through pool."""
    if not pool:
        raise ValueError("Clip pool is empty")

    # For high-energy sections, strongly prefer top-ranked clips
    if section_type in (SectionType.DROP, SectionType.CHORUS):
        idx = 0
    else:
        # Weighted random from top half
        top = max(1, len(pool) // 2)
        idx = random.randint(0, top - 1)

    clip = pool.pop(idx)
    # If pool runs out, refill from the clip (allow reuse)
    if not pool:
        pool.append(clip)
    return clip


def _section_at(time: float, sections: list[AudioSection]) -> SectionType:
    for s in sections:
        if s.start_time <= time < s.end_time:
            return s.section_type
    return SectionType.VERSE
