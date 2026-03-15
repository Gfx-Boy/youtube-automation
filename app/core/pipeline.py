"""Main pipeline orchestrator.

Ties all 9 modules together into a single `run_pipeline()` call:
  1. Ingestion (download + local)
  2. Asset search (images if needed)
  3. Scene detection
  4. Audio analysis
  5. Clip ranking
  6. Timeline planning
  7. Text engine (baked into renderer)
  8. Rendering
  9. Save project (for re-editing later)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.project_manager import get_project_path, load_project, save_project
from app.core.schemas import RenderConfig

log = get_logger(__name__)


def run_pipeline(
    project_id: str,
    *,
    audio_path: str = "",
    source_urls: Optional[list[str]] = None,
    local_files: Optional[list[str]] = None,
    style_preset: str = "default",
    text_entries: Optional[list[dict]] = None,
    image_queries: Optional[list[str]] = None,
    preview: bool = False,
) -> Path:
    """Execute the full video generation pipeline for a project.

    Returns the path to the rendered output file.
    """
    settings = get_settings()
    project = load_project(project_id)
    proj_dir = get_project_path(project_id)

    log.info("═══ Pipeline START for project %s ═══", project_id)

    # ── 1. Ingestion ────────────────────────────────────────────────
    from app.ingestion.downloader import (
        download_urls,
        ingest_audio,
        ingest_local_files,
        extract_audio_from_video,
    )

    video_files: list[Path] = []

    if source_urls:
        log.info("Step 1a: Downloading %d URL(s)…", len(source_urls))
        downloaded = download_urls(source_urls, project_id)
        video_files.extend(downloaded)
        project.meta.source_urls.extend(source_urls)

    if local_files:
        log.info("Step 1b: Ingesting %d local file(s)…", len(local_files))
        ingested = ingest_local_files(local_files, project_id)
        video_files.extend(ingested)

    # Audio
    audio_file_path: Optional[Path] = None
    if audio_path:
        audio_file_path = ingest_audio(audio_path, project_id)
    elif video_files:
        # Extract audio from first video as fallback
        log.info("Step 1c: Extracting audio from first video…")
        audio_file_path = extract_audio_from_video(video_files[0], project_id)

    if not video_files:
        raise ValueError("No video files available. Provide URLs or local files.")
    if not audio_file_path:
        raise ValueError("No audio file available.")

    log.info("Ingestion done: %d videos, audio=%s", len(video_files), audio_file_path.name)

    # ── 2. Asset search (images) ────────────────────────────────────
    if image_queries:
        log.info("Step 2: Searching for %d image queries…", len(image_queries))
        try:
            from app.search.image_search import search_and_download
            for q in image_queries:
                search_and_download(q, project_id, num=3)
        except Exception as exc:
            log.warning("Image search failed (continuing): %s", exc)

    # ── 3. Scene detection ──────────────────────────────────────────
    log.info("Step 3: Detecting scenes…")
    from app.analysis.scene_detector import detect_scenes_batch
    all_scenes = detect_scenes_batch(video_files, project_id)
    project.scene_list = all_scenes
    log.info("Found %d total scenes.", len(all_scenes))

    # ── 4. Audio analysis ───────────────────────────────────────────
    log.info("Step 4: Analysing audio…")
    from app.analysis.audio_analyser import analyse_audio
    beat_map = analyse_audio(audio_file_path)

    # ── 5. Clip ranking ─────────────────────────────────────────────
    log.info("Step 5: Ranking %d clips…", len(all_scenes))
    from app.analysis.clip_ranker import rank_scenes
    ranked = rank_scenes(all_scenes, prompts=["cinematic", "hero shot", "dramatic"])
    project.ranked_clips = ranked

    # ── 6. Timeline planning ────────────────────────────────────────
    log.info("Step 6: Planning timeline (style=%s)…", style_preset)
    from app.planning.timeline_planner import plan_timeline
    from app.presets.styles import get_preset

    preset = get_preset(style_preset)
    render_config = RenderConfig(**{
        **RenderConfig().model_dump(),
        **preset.get("render_overrides", {}),
    })

    timeline = plan_timeline(
        ranked_clips=ranked,
        beat_map=beat_map,
        audio_file=str(audio_file_path),
        style_preset=preset.get("section_overrides"),
        text_entries=text_entries,
        render_config=render_config,
    )
    project.timeline = timeline
    project.meta.style_preset = style_preset

    # ── 7 & 8. Render ──────────────────────────────────────────────
    output_path = proj_dir / "renders" / ("preview.mp4" if preview else "output.mp4")
    log.info("Step 7–8: Rendering → %s", output_path.name)
    from app.rendering.renderer import render
    render(timeline, output_path, preview=preview)

    # ── 9. Save project ─────────────────────────────────────────────
    save_project(project)
    log.info("═══ Pipeline COMPLETE → %s ═══", output_path)

    return output_path
