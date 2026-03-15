"""Global configuration loaded from environment / .env file."""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


_ROOT = Path(__file__).resolve().parent.parent.parent  # video_ai/


class Settings(BaseSettings):
    # ── Paths ──
    projects_dir: Path = Field(default=_ROOT / "projects")
    weights_dir: Path = Field(default=_ROOT / "weights")
    fonts_dir: Path = Field(default=_ROOT / "fonts")
    luts_dir: Path = Field(default=_ROOT / "luts")

    # ── FFmpeg ──
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    # ── Rendering defaults ──
    default_width: int = 1080
    default_height: int = 1920
    default_fps: int = 30
    default_crf: int = 18
    default_preset: str = "medium"

    # ── Database ──
    database_url: str = "sqlite+aiosqlite:///./video_ai.db"

    # ── API ──
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_config = {
        "env_file": str(_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()
