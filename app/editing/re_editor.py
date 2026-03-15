"""Module 9 — Re-Editor.

Parses user edit commands and patches the project timeline without
starting from scratch.  Then triggers a re-render of only what changed
(or the full timeline if needed).

Supported edit actions:
  replace_clip      — swap a clip at a position
  change_transition — change transition type on a clip
  edit_text         — modify a text layer
  add_text          — add a new text layer
  remove_text       — remove a text layer
  change_effect     — change the effect on a clip
  set_intensity     — change effect intensity
  trim_clip         — adjust clip start/end
  change_speed      — set playback speed on a clip
  change_font       — change font on all / specific text layers
  change_style      — apply a different style preset (re-plans)
  regenerate_section — re-plan only one section
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from app.core.logging import get_logger
from app.core.schemas import (
    EditCommand,
    EffectType,
    Project,
    TextAnimation,
    TextLayer,
    TimelineClip,
    TransitionType,
)

log = get_logger(__name__)


def apply_edit(project: Project, command: EditCommand) -> Project:
    """Apply a single edit command to a project, returning the mutated project.

    The original project is deep-copied first so the caller keeps the
    original for history / undo.
    """
    p = deepcopy(project)
    action = command.action
    params = command.params
    target = command.target_id

    handler = _HANDLERS.get(action)
    if handler is None:
        raise ValueError(f"Unknown edit action: {action}")

    handler(p, target, params)

    # Record in history
    p.history.append({
        "action": action,
        "target_id": target,
        "params": params,
        "description": command.description,
        "timestamp": datetime.utcnow().isoformat(),
    })
    p.meta.updated_at = datetime.utcnow().isoformat()
    return p


def apply_edits(project: Project, commands: list[EditCommand]) -> Project:
    """Apply a sequence of edit commands."""
    p = project
    for cmd in commands:
        p = apply_edit(p, cmd)
    return p


# ── individual handlers ─────────────────────────────────────────────

def _replace_clip(p: Project, target_id: str | None, params: dict[str, Any]) -> None:
    clip_entry = _find_clip(p, target_id)
    new_clip_id = params.get("new_clip_id")
    if not new_clip_id:
        raise ValueError("replace_clip requires 'new_clip_id' in params")
    replacement = next((c for c in p.ranked_clips if c.clip_id == new_clip_id), None)
    if replacement is None:
        raise ValueError(f"Clip {new_clip_id} not found in ranked clips")
    clip_entry.clip = replacement
    log.info("Replaced clip %s → %s", target_id, new_clip_id)


def _change_transition(p: Project, target_id: str | None, params: dict[str, Any]) -> None:
    clip_entry = _find_clip(p, target_id)
    trans = params.get("transition")
    if trans:
        clip_entry.transition_in = TransitionType(trans)
    dur = params.get("duration")
    if dur is not None:
        clip_entry.transition_duration = float(dur)
    log.info("Changed transition on %s → %s", target_id, trans)


def _edit_text(p: Project, target_id: str | None, params: dict[str, Any]) -> None:
    layer = _find_text(p, target_id)
    for key in ("text", "font", "font_size", "color", "stroke_color",
                "stroke_width", "position", "x", "y", "start_time",
                "end_time"):
        if key in params:
            setattr(layer, key, params[key])
    if "animation" in params:
        layer.animation = TextAnimation(params["animation"])
    log.info("Edited text layer %s", target_id)


def _add_text(p: Project, _target_id: str | None, params: dict[str, Any]) -> None:
    layer = TextLayer(**params)
    p.timeline.text_layers.append(layer)
    log.info("Added text layer %s", layer.layer_id)


def _remove_text(p: Project, target_id: str | None, _params: dict[str, Any]) -> None:
    p.timeline.text_layers = [
        tl for tl in p.timeline.text_layers if tl.layer_id != target_id
    ]
    log.info("Removed text layer %s", target_id)


def _change_effect(p: Project, target_id: str | None, params: dict[str, Any]) -> None:
    clip_entry = _find_clip(p, target_id)
    effect = params.get("effect")
    if effect:
        clip_entry.effect = EffectType(effect)
    log.info("Changed effect on %s → %s", target_id, effect)


def _set_intensity(p: Project, target_id: str | None, params: dict[str, Any]) -> None:
    clip_entry = _find_clip(p, target_id)
    clip_entry.effect_intensity = float(params.get("intensity", 1.0))
    log.info("Set intensity on %s → %.2f", target_id, clip_entry.effect_intensity)


def _trim_clip(p: Project, target_id: str | None, params: dict[str, Any]) -> None:
    clip_entry = _find_clip(p, target_id)
    if "start" in params:
        clip_entry.timeline_start = float(params["start"])
    if "end" in params:
        clip_entry.timeline_end = float(params["end"])
    log.info("Trimmed clip %s", target_id)


def _change_speed(p: Project, target_id: str | None, params: dict[str, Any]) -> None:
    clip_entry = _find_clip(p, target_id)
    clip_entry.speed = float(params.get("speed", 1.0))
    log.info("Changed speed on %s → %.2f", target_id, clip_entry.speed)


def _change_font(p: Project, _target_id: str | None, params: dict[str, Any]) -> None:
    font = params.get("font", "Arial")
    size = params.get("font_size")
    for tl in p.timeline.text_layers:
        tl.font = font
        if size:
            tl.font_size = int(size)
    log.info("Changed font → %s", font)


# ── lookup helpers ──────────────────────────────────────────────────

def _find_clip(p: Project, target_id: str | None) -> TimelineClip:
    for tc in p.timeline.clips:
        if tc.entry_id == target_id:
            return tc
    raise ValueError(f"Timeline clip {target_id} not found")


def _find_text(p: Project, target_id: str | None) -> TextLayer:
    for tl in p.timeline.text_layers:
        if tl.layer_id == target_id:
            return tl
    raise ValueError(f"Text layer {target_id} not found")


# ── handler registry ────────────────────────────────────────────────

_HANDLERS = {
    "replace_clip": _replace_clip,
    "change_transition": _change_transition,
    "edit_text": _edit_text,
    "add_text": _add_text,
    "remove_text": _remove_text,
    "change_effect": _change_effect,
    "set_intensity": _set_intensity,
    "trim_clip": _trim_clip,
    "change_speed": _change_speed,
    "change_font": _change_font,
}
