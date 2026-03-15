"""Module 3 — Scene Detection.

Uses PySceneDetect to split source videos into individual shots,
saving metadata + thumbnail per scene.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import cv2

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.schemas import SceneInfo
from app.core.project_manager import get_project_path

log = get_logger(__name__)


def detect_scenes(
    video_path: str | Path,
    project_id: str,
    *,
    threshold: float = 27.0,
    min_scene_len: float = 0.5,
) -> list[SceneInfo]:
    """Detect scene boundaries in a video using PySceneDetect.

    Returns a list of SceneInfo objects with timestamps and thumbnails.
    """
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector

    video_path = Path(video_path)
    scenes_dir = get_project_path(project_id) / "scenes" / video_path.stem
    scenes_dir.mkdir(parents=True, exist_ok=True)

    log.info("Detecting scenes in %s (threshold=%.1f) …", video_path.name, threshold)

    video = open_video(str(video_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold, min_scene_len=int(min_scene_len * video.frame_rate)))
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()

    results: list[SceneInfo] = []
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    for i, (start, end) in enumerate(scene_list):
        start_sec = start.get_seconds()
        end_sec = end.get_seconds()
        duration = end_sec - start_sec

        # Save a thumbnail from the middle of the scene
        mid_frame = int(((start_sec + end_sec) / 2) * fps)
        thumb_path = scenes_dir / f"scene_{i:04d}.jpg"
        cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
        ret, frame = cap.read()
        if ret:
            cv2.imwrite(str(thumb_path), frame)

        scene = SceneInfo(
            source_file=str(video_path),
            start_time=start_sec,
            end_time=end_sec,
            duration=duration,
            thumbnail_path=str(thumb_path) if thumb_path.exists() else None,
            metadata={"scene_index": i, "fps": fps},
        )
        results.append(scene)

    cap.release()
    log.info("Found %d scenes in %s", len(results), video_path.name)
    return results


def detect_scenes_batch(
    video_paths: list[Path],
    project_id: str,
    **kwargs,
) -> list[SceneInfo]:
    """Run scene detection on multiple videos."""
    all_scenes: list[SceneInfo] = []
    for vp in video_paths:
        scenes = detect_scenes(vp, project_id, **kwargs)
        all_scenes.extend(scenes)
    return all_scenes
