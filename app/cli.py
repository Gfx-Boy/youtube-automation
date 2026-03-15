"""CLI entry point — run the pipeline from the command line.

Usage:
  # Search YouTube automatically by subject (recommended):
  python -m app.cli generate --subject "andrew tate fighting" --music beat.mp3

  # Pick from your local CSV by category:
  python -m app.cli generate --music song.mp3 --category anime --preset hype_energy

  # Use explicit URLs:
  python -m app.cli generate --music song.mp3 --urls https://youtu.be/xxx

  # Other commands:
  python -m app.cli edit --project <id> --action change_font --params '{"font": "Impact"}'
  python -m app.cli render --project <id>
  python -m app.cli list
  python -m app.cli presets
  python -m app.cli serve
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from app.core.logging import setup_logging

# ── Category → preset mapping (auto-picks preset if not specified) ──
_CAT_PRESET = {
    "anime":         "hype_energy",
    "movie_villain": "dark_cinematic",
    "rap_hiphop":    "hype_energy",
    "motivational":  "smooth_emotional",
    "gaming":        "hype_energy",
    "athlete":       "hype_energy",
    "ufc_mma":       "hype_energy",
    "aesthetic_flow":"smooth_emotional",
}

VALID_CATEGORIES = list(_CAT_PRESET.keys())


def _pick_urls_from_csv(category: str, n: int) -> list[str]:
    """Return top-N URLs for a category from shorts_master_index.csv, sorted by views."""
    import csv

    # Look for CSV in a few common locations
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "shorts_master_index.csv",
        Path.home() / "Youtube Automation" / "shorts_master_index.csv",
        Path("/Users/hasanhsb/Youtube Automation/shorts_master_index.csv"),
    ]
    csv_path = next((p for p in candidates if p.exists()), None)
    if csv_path is None:
        raise FileNotFoundError(
            "shorts_master_index.csv not found. "
            "Put it in the 'Youtube Automation' folder or pass --urls manually."
        )

    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["category"].strip() == category:
                try:
                    views = int(row.get("views", 0))
                except ValueError:
                    views = 0
                rows.append((views, row["url"].strip()))

    if not rows:
        raise ValueError(f"No videos found for category '{category}' in CSV.")

    # Sort by views descending, take top N
    rows.sort(reverse=True)
    return [url for _, url in rows[:n]]


@click.group()
def cli():
    """Video AI — Automated short-form video generation."""
    setup_logging()


@cli.command()
@click.option("--music",    required=True, help="Path to your MP3 beat/track")
@click.option("--subject",  default="",   help='Natural language subject e.g. "andrew tate fighting"')
@click.option("--category", default=None,
              type=click.Choice(VALID_CATEGORIES, case_sensitive=False),
              help="Auto-pick best clips from CSV for this style category")
@click.option("--clips",    default=8,    show_default=True,
              help="How many clips to pull from CSV (used with --category)")
@click.option("--preset",   default=None, help="Style preset (auto-selected from category if omitted)")
@click.option("--name",     default="",   help="Optional project name")
@click.option("--urls",     multiple=True, help="Manual video URLs (overrides --subject and --category)")
@click.option("--files",    multiple=True, help="Local video file paths")
@click.option("--prompt",   default="",   help="Vibe description e.g. 'hype dark cinematic'")
@click.option("--preview",  is_flag=True, help="Fast lower-quality preview render")
@click.option("--no-transcribe", "skip_transcription", is_flag=True,
              help="Skip Whisper transcription (faster but less smart clip selection)")
def generate(music, subject, category, clips, preset, name, urls, files, prompt,
             preview, skip_transcription):
    """Generate a video. Give it a subject + beat — it searches, downloads & edits.

    \b
    Examples:
      # Fully automatic from subject:
      python -m app.cli generate --subject "andrew tate fighting" --music beat.mp3

      # From local CSV category:
      python -m app.cli generate --category anime --music beat.mp3

      # Supply your own URLs:
      python -m app.cli generate --urls https://youtu.be/xxx --music beat.mp3
    """
    from app.core.project_manager import create_project
    from app.core.pipeline import run_pipeline

    # ── Resolve source URLs ──────────────────────────────────────────
    source_urls = list(urls)
    active_subject = subject.strip()

    if not source_urls and not files:
        if active_subject:
            # YouTube search is handled inside the pipeline (Step 0)
            click.echo(f"Subject    : {active_subject}")
            click.echo("Will search YouTube automatically …")
        elif category:
            click.echo(f"Picking top {clips} clips for category: {category} …")
            source_urls = _pick_urls_from_csv(category, clips)
            click.echo(f"  {len(source_urls)} URLs selected")
        else:
            raise click.UsageError(
                "Provide --subject (YouTube search), --category (CSV), or --urls / --files."
            )

    # ── Resolve preset ──────────────────────────────────────────────
    resolved_preset = preset or (
        _CAT_PRESET.get(category, "default") if category else "default"
    )

    # ── Resolve project name ─────────────────────────────────────────
    project_name = name or (
        active_subject if active_subject else (f"{category} edit" if category else "my edit")
    )

    # ── Auto-fill prompt ─────────────────────────────────────────────
    resolved_prompt = prompt or active_subject or (category.replace("_", " ") if category else "")

    project = create_project(
        name=project_name,
        subject=active_subject or category or "",
        style_preset=resolved_preset,
        source_urls=source_urls,
        user_prompt=resolved_prompt,
    )
    pid = project.meta.project_id
    click.echo(f"Project ID : {pid}")
    click.echo(f"Preset     : {resolved_preset}")
    click.echo(f"Music      : {music}")

    output = run_pipeline(
        project_id=pid,
        audio_path=music,
        source_urls=source_urls if source_urls else None,
        local_files=list(files),
        style_preset=resolved_preset,
        preview=preview,
        subject=active_subject,
        use_transcription=not skip_transcription,
    )
    click.echo(f"\n✅  Done → {output}")


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
