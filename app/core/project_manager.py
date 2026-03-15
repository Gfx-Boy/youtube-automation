"""Project manager — create, load, save, and version projects.

The project.json is the single source of truth.  Every render, every
re-edit reads from and writes back to this file.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.schemas import Project, ProjectMeta


def _project_dir(project_id: str) -> Path:
    return get_settings().projects_dir / project_id


def _ensure_subdirs(root: Path) -> None:
    for sub in ("inputs", "raw_media", "scenes", "images", "audio", "cache", "renders"):
        (root / sub).mkdir(parents=True, exist_ok=True)


# ── create ──────────────────────────────────────────────────────────

def create_project(
    name: str,
    subject: str = "",
    style_preset: str = "default",
    source_urls: Optional[list[str]] = None,
    user_prompt: str = "",
) -> Project:
    meta = ProjectMeta(
        name=name,
        subject=subject,
        style_preset=style_preset,
        source_urls=source_urls or [],
        user_prompt=user_prompt,
    )
    project = Project(meta=meta)
    root = _project_dir(meta.project_id)
    _ensure_subdirs(root)
    save_project(project)
    return project


# ── save / load ─────────────────────────────────────────────────────

def save_project(project: Project) -> Path:
    project.meta.updated_at = datetime.utcnow().isoformat()
    root = _project_dir(project.meta.project_id)
    root.mkdir(parents=True, exist_ok=True)

    path = root / "project.json"

    # keep one backup before overwriting
    if path.exists():
        backup = root / f"project_v{project.meta.version}.json"
        shutil.copy2(path, backup)
        project.meta.version += 1

    path.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_project(project_id: str) -> Project:
    path = _project_dir(project_id) / "project.json"
    if not path.exists():
        raise FileNotFoundError(f"No project found at {path}")
    data = json.loads(path.read_text("utf-8"))
    return Project.model_validate(data)


def list_projects() -> list[dict]:
    projects_root = get_settings().projects_dir
    results = []
    if not projects_root.exists():
        return results
    for d in sorted(projects_root.iterdir()):
        pj = d / "project.json"
        if pj.exists():
            data = json.loads(pj.read_text("utf-8"))
            results.append({
                "project_id": d.name,
                "name": data.get("meta", {}).get("name", ""),
                "updated_at": data.get("meta", {}).get("updated_at", ""),
            })
    return results


def get_project_path(project_id: str) -> Path:
    return _project_dir(project_id)
