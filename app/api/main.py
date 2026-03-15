"""FastAPI application — REST API for the video generation pipeline.

Endpoints:
  POST /projects            — create a new project
  GET  /projects            — list all projects
  GET  /projects/{id}       — get project details
  POST /projects/{id}/generate — run the full pipeline
  POST /projects/{id}/edit  — apply edit commands
  POST /projects/{id}/render — re-render from timeline
  GET  /presets             — list available style presets
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import setup_logging, get_logger
from app.core.project_manager import (
    create_project,
    list_projects,
    load_project,
    save_project,
)
from app.core.schemas import EditCommand, Project, RenderConfig
from app.presets.styles import list_presets

setup_logging()
log = get_logger(__name__)

app = FastAPI(
    title="Video AI",
    description="Automated short-form video generation system",
    version="0.1.0",
)


# ── Request / response models ──────────────────────────────────────

class CreateProjectReq(BaseModel):
    name: str
    subject: str = ""
    style_preset: str = "default"
    source_urls: list[str] = Field(default_factory=list)
    local_files: list[str] = Field(default_factory=list)
    audio_path: str = ""
    user_prompt: str = ""
    text_entries: list[dict] = Field(default_factory=list)


class EditReq(BaseModel):
    commands: list[EditCommand]


class GenerateReq(BaseModel):
    audio_path: str = ""
    source_urls: list[str] = Field(default_factory=list)
    local_files: list[str] = Field(default_factory=list)
    style_preset: str = "default"
    subject: str = ""
    user_prompt: str = ""
    text_entries: list[dict] = Field(default_factory=list)
    preview: bool = False


class StatusResp(BaseModel):
    status: str
    message: str = ""
    project_id: str = ""


# ── Endpoints ──────────────────────────────────────────────────────

@app.get("/presets")
def api_list_presets():
    return list_presets()


@app.get("/projects")
def api_list_projects():
    return list_projects()


@app.post("/projects", response_model=StatusResp)
def api_create_project(req: CreateProjectReq):
    project = create_project(
        name=req.name,
        subject=req.subject,
        style_preset=req.style_preset,
        source_urls=req.source_urls,
        user_prompt=req.user_prompt,
    )
    return StatusResp(
        status="created",
        project_id=project.meta.project_id,
        message=f"Project '{req.name}' created.",
    )


@app.get("/projects/{project_id}")
def api_get_project(project_id: str):
    try:
        project = load_project(project_id)
        return project.model_dump()
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")


@app.post("/projects/{project_id}/generate", response_model=StatusResp)
def api_generate(project_id: str, req: GenerateReq, bg: BackgroundTasks):
    """Kick off the full pipeline in the background."""
    try:
        load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")

    # Import here to avoid circular + heavy imports at startup
    from app.core.pipeline import run_pipeline

    bg.add_task(
        run_pipeline,
        project_id=project_id,
        audio_path=req.audio_path,
        source_urls=req.source_urls,
        local_files=req.local_files,
        style_preset=req.style_preset,
        text_entries=req.text_entries,
        preview=req.preview,
    )
    return StatusResp(
        status="started",
        project_id=project_id,
        message="Pipeline started in background.",
    )


@app.post("/projects/{project_id}/edit", response_model=StatusResp)
def api_edit(project_id: str, req: EditReq):
    """Apply edit commands and re-render."""
    try:
        project = load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")

    from app.editing.re_editor import apply_edits

    project = apply_edits(project, req.commands)
    save_project(project)
    return StatusResp(
        status="edited",
        project_id=project_id,
        message=f"Applied {len(req.commands)} edit(s). Re-render when ready.",
    )


@app.post("/projects/{project_id}/render", response_model=StatusResp)
def api_render(project_id: str, preview: bool = False, bg: BackgroundTasks = None):
    """Re-render the current timeline."""
    try:
        project = load_project(project_id)
    except FileNotFoundError:
        raise HTTPException(404, "Project not found")

    from app.rendering.renderer import render
    from app.core.project_manager import get_project_path

    output = get_project_path(project_id) / "renders" / "output.mp4"

    if bg:
        bg.add_task(render, project.timeline, output, preview=preview)
        return StatusResp(status="started", project_id=project_id, message="Render started.")
    else:
        render(project.timeline, output, preview=preview)
        return StatusResp(status="done", project_id=project_id, message=f"Rendered → {output}")
