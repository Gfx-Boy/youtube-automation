"""CLI entry point — run the pipeline from the command line.

Usage:
  python -m app.cli generate --name "My Edit" --audio song.mp3 --urls "https://..." --style dark_cinematic
  python -m app.cli edit --project <id> --action change_font --params '{"font": "Impact"}'
  python -m app.cli render --project <id>
  python -m app.cli list
  python -m app.cli presets
  python -m app.cli serve
"""

from __future__ import annotations

import json
import sys

import click

from app.core.logging import setup_logging


@click.group()
def cli():
    """Video AI — Automated short-form video generation."""
    setup_logging()


@cli.command()
@click.option("--name", required=True, help="Project name")
@click.option("--audio", default="", help="Path to audio/music file")
@click.option("--urls", default="", help="Comma-separated video URLs")
@click.option("--files", default="", help="Comma-separated local video paths")
@click.option("--style", default="default", help="Style preset name")
@click.option("--subject", default="", help="Subject/theme")
@click.option("--prompt", default="", help="User prompt/instruction")
@click.option("--images", default="", help="Comma-separated image search queries")
@click.option("--preview", is_flag=True, help="Fast preview render")
def generate(name, audio, urls, files, style, subject, prompt, images, preview):
    """Create a new project and run the full pipeline."""
    from app.core.project_manager import create_project
    from app.core.pipeline import run_pipeline

    project = create_project(
        name=name,
        subject=subject,
        style_preset=style,
        source_urls=[u.strip() for u in urls.split(",") if u.strip()],
        user_prompt=prompt,
    )
    pid = project.meta.project_id
    click.echo(f"Created project: {pid}")

    output = run_pipeline(
        project_id=pid,
        audio_path=audio,
        source_urls=[u.strip() for u in urls.split(",") if u.strip()],
        local_files=[f.strip() for f in files.split(",") if f.strip()],
        style_preset=style,
        image_queries=[q.strip() for q in images.split(",") if q.strip()] or None,
        preview=preview,
    )
    click.echo(f"Done → {output}")


@cli.command()
@click.option("--project", required=True, help="Project ID")
@click.option("--action", required=True, help="Edit action name")
@click.option("--target", default=None, help="Target clip/layer ID")
@click.option("--params", default="{}", help="JSON params")
def edit(project, action, target, params):
    """Apply an edit command to an existing project."""
    from app.core.project_manager import load_project, save_project
    from app.core.schemas import EditCommand
    from app.editing.re_editor import apply_edit

    proj = load_project(project)
    cmd = EditCommand(
        action=action,
        target_id=target,
        params=json.loads(params),
    )
    proj = apply_edit(proj, cmd)
    save_project(proj)
    click.echo(f"Edit applied: {action}")


@cli.command()
@click.option("--project", required=True, help="Project ID")
@click.option("--preview", is_flag=True, help="Fast preview render")
def render(project, preview):
    """Re-render an existing project's timeline."""
    from app.core.project_manager import load_project, get_project_path
    from app.rendering.renderer import render as do_render

    proj = load_project(project)
    output = get_project_path(project) / "renders" / ("preview.mp4" if preview else "output.mp4")
    do_render(proj.timeline, output, preview=preview)
    click.echo(f"Rendered → {output}")


@cli.command("list")
def list_cmd():
    """List all projects."""
    from app.core.project_manager import list_projects
    projects = list_projects()
    if not projects:
        click.echo("No projects found.")
        return
    for p in projects:
        click.echo(f"  {p['project_id']}  {p['name']}  ({p['updated_at']})")


@cli.command()
def presets():
    """List available style presets."""
    from app.presets.styles import list_presets
    for p in list_presets():
        click.echo(f"  {p['name']:20s}  {p['description']}")


@cli.command()
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=8000, type=int)
def serve(host, port):
    """Start the FastAPI server."""
    import uvicorn
    uvicorn.run("app.api.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    cli()
