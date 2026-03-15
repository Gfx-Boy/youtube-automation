"""Pydantic schemas — the data contracts for the entire pipeline.

These schemas define:
 - Project metadata
 - Timeline (the source of truth for every edit)
 - Clip / scene / beat / text layer descriptors
 - Render config
 - Edit commands (for re-editing)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


# ───────────────────────────── helpers ──────────────────────────────

def _uid() -> str:
    return uuid.uuid4().hex[:12]


# ───────────────────────────── enums ────────────────────────────────

class TransitionType(str, Enum):
    CUT = "cut"
    CROSSFADE = "crossfade"
    FADE_BLACK = "fade_black"
    FADE_WHITE = "fade_white"
    WIPE_LEFT = "wipe_left"
    WIPE_RIGHT = "wipe_right"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    BLUR = "blur"
    FLASH = "flash"
    GLITCH = "glitch"


class TextAnimation(str, Enum):
    NONE = "none"
    POP_IN = "pop_in"
    BLUR_REVEAL = "blur_reveal"
    SLIDE_UP = "slide_up"
    WORD_BY_WORD = "word_by_word"
    BEAT_BOUNCE = "beat_bounce"
    FLASH_REVEAL = "flash_reveal"


class EffectType(str, Enum):
    NONE = "none"
    FLASH = "flash"
    PUNCH_ZOOM = "punch_zoom"
    SHAKE = "shake"
    BLUR_PULSE = "blur_pulse"
    GLOW = "glow"
    SPEED_RAMP = "speed_ramp"
    RGB_SPLIT = "rgb_split"


class ClipSourceType(str, Enum):
    VIDEO = "video"
    IMAGE = "image"


class SectionType(str, Enum):
    INTRO = "intro"
    BUILDUP = "buildup"
    DROP = "drop"
    VERSE = "verse"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    OUTRO = "outro"


# ───────────────────────── scene / clip ─────────────────────────────

class SceneInfo(BaseModel):
    scene_id: str = Field(default_factory=_uid)
    source_file: str
    start_time: float
    end_time: float
    duration: float
    thumbnail_path: Optional[str] = None
    sample_frames: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClipScore(BaseModel):
    motion: float = 0.0
    brightness: float = 0.0
    contrast: float = 0.0
    sharpness: float = 0.0
    face_prominence: float = 0.0
    clip_similarity: float = 0.0       # CLIP score vs prompt
    aesthetic_score: float = 0.0        # from trained ranker
    composite: float = 0.0             # weighted total


class RankedClip(BaseModel):
    clip_id: str = Field(default_factory=_uid)
    scene: SceneInfo
    scores: ClipScore = Field(default_factory=ClipScore)
    source_type: ClipSourceType = ClipSourceType.VIDEO
    tags: list[str] = Field(default_factory=list)


# ─────────────────────────── audio ──────────────────────────────────

class BeatMap(BaseModel):
    bpm: float
    beat_times: list[float] = Field(default_factory=list)
    onset_times: list[float] = Field(default_factory=list)
    energy_curve: list[float] = Field(default_factory=list)
    drop_candidates: list[float] = Field(default_factory=list)
    sections: list[AudioSection] = Field(default_factory=list)


class AudioSection(BaseModel):
    section_type: SectionType
    start_time: float
    end_time: float


# forward-ref fix (BeatMap references AudioSection)
BeatMap.model_rebuild()


# ──────────────────────── text layer ────────────────────────────────

class TextLayer(BaseModel):
    layer_id: str = Field(default_factory=_uid)
    text: str
    start_time: float
    end_time: float
    font: str = "Arial"
    font_size: int = 64
    color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: int = 2
    shadow: bool = True
    position: str = "center"          # center | top | bottom | custom x,y
    x: Optional[int] = None
    y: Optional[int] = None
    animation: TextAnimation = TextAnimation.NONE
    safe_area: bool = True            # respect 9:16 safe margins


# ──────────────────── timeline entry ────────────────────────────────

class TimelineClip(BaseModel):
    entry_id: str = Field(default_factory=_uid)
    clip: RankedClip
    timeline_start: float             # position on output timeline (seconds)
    timeline_end: float
    speed: float = 1.0
    crop: Optional[dict[str, int]] = None   # {x, y, w, h}
    transition_in: TransitionType = TransitionType.CUT
    transition_duration: float = 0.0
    effect: EffectType = EffectType.NONE
    effect_intensity: float = 1.0
    lut: Optional[str] = None


# ──────────────────── render config ─────────────────────────────────

class RenderConfig(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 30
    crf: int = 18
    preset: str = "medium"
    codec: str = "libx264"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    pixel_format: str = "yuv420p"


# ────────────────────── full timeline ───────────────────────────────

class Timeline(BaseModel):
    clips: list[TimelineClip] = Field(default_factory=list)
    text_layers: list[TextLayer] = Field(default_factory=list)
    audio_file: str = ""
    beat_map: Optional[BeatMap] = None
    duration: float = 0.0
    render_config: RenderConfig = Field(default_factory=RenderConfig)


# ──────────────────── project metadata ──────────────────────────────

class ProjectMeta(BaseModel):
    project_id: str = Field(default_factory=_uid)
    name: str = ""
    subject: str = ""
    style_preset: str = "default"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    version: int = 1
    source_urls: list[str] = Field(default_factory=list)
    local_assets: list[str] = Field(default_factory=list)
    user_prompt: str = ""
    notes: str = ""


# ────────────────────── full project ────────────────────────────────

class Project(BaseModel):
    meta: ProjectMeta = Field(default_factory=ProjectMeta)
    timeline: Timeline = Field(default_factory=Timeline)
    scene_list: list[SceneInfo] = Field(default_factory=list)
    ranked_clips: list[RankedClip] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)


# ────────────────── edit commands (re-editor) ───────────────────────

class EditCommand(BaseModel):
    action: str                        # replace_clip | change_transition | edit_text | ...
    target_id: Optional[str] = None    # entry_id or layer_id
    params: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
