"""Style & transition presets.

Each preset overrides the default section rules in the timeline planner
to produce a distinct editing feel.
"""

from __future__ import annotations

from app.core.schemas import (
    EffectType,
    SectionType,
    TextAnimation,
    TransitionType,
)

# ── Style presets ───────────────────────────────────────────────────

STYLE_PRESETS: dict[str, dict] = {
    "default": {
        "description": "Balanced cinematic with beat sync",
        "section_overrides": {},  # uses planner defaults
        "render_overrides": {},
    },

    "dark_cinematic": {
        "description": "Dark moody — slow cuts, smooth transitions, dramatic drops",
        "section_overrides": {
            SectionType.INTRO: {
                "cut_duration": (2.5, 4.0),
                "transitions": [TransitionType.FADE_BLACK, TransitionType.CROSSFADE],
                "effects": [EffectType.GLOW],
                "text_anim": TextAnimation.BLUR_REVEAL,
            },
            SectionType.DROP: {
                "cut_duration": (0.3, 0.6),
                "transitions": [TransitionType.FLASH, TransitionType.CUT],
                "effects": [EffectType.FLASH, EffectType.SHAKE, EffectType.RGB_SPLIT],
                "text_anim": TextAnimation.FLASH_REVEAL,
            },
            SectionType.VERSE: {
                "cut_duration": (1.5, 2.5),
                "transitions": [TransitionType.CROSSFADE],
                "effects": [EffectType.BLUR_PULSE],
                "text_anim": TextAnimation.BLUR_REVEAL,
            },
        },
        "render_overrides": {"crf": 16},
    },

    "hype_energy": {
        "description": "Fast cuts, lots of flash, punch zooms, high energy",
        "section_overrides": {
            SectionType.INTRO: {
                "cut_duration": (0.8, 1.5),
                "transitions": [TransitionType.CUT, TransitionType.FLASH],
                "effects": [EffectType.FLASH],
                "text_anim": TextAnimation.POP_IN,
            },
            SectionType.BUILDUP: {
                "cut_duration": (0.4, 0.8),
                "transitions": [TransitionType.CUT],
                "effects": [EffectType.PUNCH_ZOOM, EffectType.FLASH],
                "text_anim": TextAnimation.BEAT_BOUNCE,
            },
            SectionType.DROP: {
                "cut_duration": (0.15, 0.4),
                "transitions": [TransitionType.CUT, TransitionType.FLASH],
                "effects": [EffectType.FLASH, EffectType.PUNCH_ZOOM, EffectType.SHAKE, EffectType.RGB_SPLIT],
                "text_anim": TextAnimation.FLASH_REVEAL,
            },
            SectionType.CHORUS: {
                "cut_duration": (0.3, 0.6),
                "transitions": [TransitionType.CUT],
                "effects": [EffectType.PUNCH_ZOOM, EffectType.FLASH],
                "text_anim": TextAnimation.BEAT_BOUNCE,
            },
        },
        "render_overrides": {},
    },

    "smooth_emotional": {
        "description": "Soft, slow, emotional — ideal for sad/romantic edits",
        "section_overrides": {
            SectionType.INTRO: {
                "cut_duration": (3.0, 5.0),
                "transitions": [TransitionType.CROSSFADE, TransitionType.FADE_BLACK],
                "effects": [EffectType.NONE],
                "text_anim": TextAnimation.BLUR_REVEAL,
            },
            SectionType.VERSE: {
                "cut_duration": (2.0, 3.5),
                "transitions": [TransitionType.CROSSFADE],
                "effects": [EffectType.GLOW],
                "text_anim": TextAnimation.WORD_BY_WORD,
            },
            SectionType.DROP: {
                "cut_duration": (1.0, 2.0),
                "transitions": [TransitionType.CROSSFADE, TransitionType.BLUR],
                "effects": [EffectType.BLUR_PULSE],
                "text_anim": TextAnimation.SLIDE_UP,
            },
            SectionType.OUTRO: {
                "cut_duration": (3.0, 6.0),
                "transitions": [TransitionType.FADE_BLACK],
                "effects": [EffectType.NONE],
                "text_anim": TextAnimation.BLUR_REVEAL,
            },
        },
        "render_overrides": {"crf": 16},
    },

    "meme_edit": {
        "description": "Fast ironic edits, hard cuts, bass-boosted feel",
        "section_overrides": {
            SectionType.INTRO: {
                "cut_duration": (0.5, 1.0),
                "transitions": [TransitionType.CUT],
                "effects": [EffectType.PUNCH_ZOOM],
                "text_anim": TextAnimation.POP_IN,
            },
            SectionType.DROP: {
                "cut_duration": (0.1, 0.3),
                "transitions": [TransitionType.CUT, TransitionType.FLASH],
                "effects": [EffectType.SHAKE, EffectType.FLASH, EffectType.RGB_SPLIT, EffectType.PUNCH_ZOOM],
                "text_anim": TextAnimation.BEAT_BOUNCE,
            },
        },
        "render_overrides": {},
    },
}


def get_preset(name: str) -> dict:
    """Return a style preset by name (falls back to 'default')."""
    return STYLE_PRESETS.get(name, STYLE_PRESETS["default"])


def list_presets() -> list[dict]:
    return [
        {"name": k, "description": v["description"]}
        for k, v in STYLE_PRESETS.items()
    ]
