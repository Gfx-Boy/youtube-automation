"""Module 8 — Renderer.

Turns a Timeline into the final mp4 using FFmpeg.

Handles:
  - clip trimming & concatenation
  - 9:16 crop/scale/reframe
  - transitions (crossfade, fade, flash, wipe, zoom, blur, glitch)
  - beat-synced effects (flash, punch zoom, shake, blur pulse, glow, speed ramp, rgb split)
  - text overlays via drawtext filters
  - audio mux
  - final export
"""

from __future__ import annotations

import subprocess
import shlex
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.schemas import (
    EffectType,
    Timeline,
    TimelineClip,
    TransitionType,
)
from app.rendering.text_engine import build_drawtext_filter

log = get_logger(__name__)


def render(
    timeline: Timeline,
    output_path: str | Path,
    *,
    preview: bool = False,
) -> Path:
    """Render a full Timeline to an mp4.

    Strategy:
      1. Build per-clip input entries
      2. Build the filter graph (trim → scale → effects → concat → text → audio)
      3. Run FFmpeg
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    rc = timeline.render_config
    w, h = rc.width, rc.height

    if not timeline.clips:
        raise ValueError("Timeline has no clips to render.")

    # ── 1. build input list & per-clip filter chains ────────────────
    inputs: list[str] = []
    filter_parts: list[str] = []
    concat_inputs: list[str] = []

    for i, tc in enumerate(timeline.clips):
        src = tc.clip.scene.source_file
        inputs.extend(["-i", src])

        # trim
        ss = tc.clip.scene.start_time
        dur = tc.timeline_end - tc.timeline_start
        # Speed adjustment
        speed = tc.speed if tc.speed and tc.speed > 0 else 1.0

        chain = []
        # Trim
        chain.append(f"[{i}:v]trim=start={ss}:duration={dur / speed},setpts=PTS-STARTPTS")
        # Scale/crop to 9:16
        chain.append(f"scale={w}:{h}:force_original_aspect_ratio=increase")
        chain.append(f"crop={w}:{h}")
        # Speed
        if speed != 1.0:
            chain.append(f"setpts={1/speed}*PTS")
        # Effects
        effect_filter = _effect_filter(tc, w, h)
        if effect_filter:
            chain.append(effect_filter)

        label = f"v{i}"
        filter_parts.append(",".join(chain) + f"[{label}]")
        concat_inputs.append(f"[{label}]")

    # ── 2. transitions (simple concat for MVP, crossfade between pairs) ──
    n = len(timeline.clips)
    if n == 1:
        final_video = concat_inputs[0]
    else:
        # Use xfade for transitions between consecutive clips
        current = concat_inputs[0]
        offset = 0.0
        for i in range(1, n):
            tc = timeline.clips[i]
            dur_prev = timeline.clips[i-1].timeline_end - timeline.clips[i-1].timeline_start
            offset += dur_prev - tc.transition_duration

            xfade_type = _xfade_name(tc.transition_in)
            td = max(tc.transition_duration, 0.05)
            out_label = f"xf{i}"
            filter_parts.append(
                f"{current}{concat_inputs[i]}"
                f"xfade=transition={xfade_type}:duration={td}:offset={offset:.3f}"
                f"[{out_label}]"
            )
            current = f"[{out_label}]"
        final_video = current

    # ── 3. text overlays ────────────────────────────────────────────
    text_label = final_video
    for j, tl in enumerate(timeline.text_layers):
        dt_filter = build_drawtext_filter(tl, w, h)
        out = f"txt{j}"
        filter_parts.append(f"{text_label}{dt_filter}[{out}]")
        text_label = f"[{out}]"

    final_video = text_label

    # ── 4. audio input ──────────────────────────────────────────────
    audio_idx = len(timeline.clips)
    if timeline.audio_file:
        inputs.extend(["-i", timeline.audio_file])

    # ── 5. assemble command ─────────────────────────────────────────
    filter_complex = ";\n".join(filter_parts)

    cmd = [settings.ffmpeg_bin, "-y"]
    cmd.extend(inputs)
    cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(["-map", final_video])  # keep brackets — required for filter_complex output labels

    if timeline.audio_file:
        cmd.extend([
            "-map", f"{audio_idx}:a",
            "-shortest",
        ])

    cmd.extend([
        "-c:v", rc.codec,
        "-preset", "ultrafast" if preview else rc.preset,
        "-crf", str(rc.crf + 5 if preview else rc.crf),
        "-pix_fmt", rc.pixel_format,
        "-c:a", rc.audio_codec,
        "-b:a", rc.audio_bitrate,
        str(output_path),
    ])

    log.info("Rendering → %s (%s mode)", output_path.name, "preview" if preview else "final")
    log.info("FFmpeg cmd: %s", " ".join(shlex.quote(c) for c in cmd))

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        log.error("FFmpeg error:\n%s", result.stderr[-2000:])
        raise RuntimeError(f"FFmpeg render failed: {result.stderr[-500:]}")

    log.info("Render complete → %s (%.1f MB)",
             output_path.name, output_path.stat().st_size / 1_048_576)
    return output_path


# ── effect filters ──────────────────────────────────────────────────

def _effect_filter(tc: TimelineClip, w: int, h: int) -> str:
    """Return an FFmpeg filter string for the clip's assigned effect."""
    e = tc.effect
    intensity = tc.effect_intensity

    if e == EffectType.FLASH:
        return f"eq=brightness={0.3 * intensity}"  # eq has no duration param
    elif e == EffectType.PUNCH_ZOOM:
        z = 1.0 + 0.15 * intensity
        return f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}"
    elif e == EffectType.SHAKE:
        amp = int(5 * intensity)
        return f"crop=w=iw-{amp*2}:h=ih-{amp*2}:x='random(1)*{amp}':y='random(2)*{amp}',scale={w}:{h}"
    elif e == EffectType.BLUR_PULSE:
        return f"boxblur=luma_radius=3:luma_power=1:enable='lt(mod(t,0.5),0.15)'"
    elif e == EffectType.GLOW:
        return "unsharp=5:5:1.5:5:5:0.0"
    elif e == EffectType.SPEED_RAMP:
        return f"setpts={0.5/intensity}*PTS"
    elif e == EffectType.RGB_SPLIT:
        # rgbashift shifts R and B channels horizontally — single stream, no splitting needed
        shift = max(2, int(5 * intensity))
        return f"rgbashift=rh={shift}:bh=-{shift}"
    return ""


def _xfade_name(t: TransitionType) -> str:
    """Map our TransitionType to FFmpeg xfade transition names."""
    mapping = {
        TransitionType.CUT: "fade",
        TransitionType.CROSSFADE: "fade",
        TransitionType.FADE_BLACK: "fadeblack",
        TransitionType.FADE_WHITE: "fadewhite",
        TransitionType.WIPE_LEFT: "wipeleft",
        TransitionType.WIPE_RIGHT: "wiperight",
        TransitionType.ZOOM_IN: "circlecrop",
        TransitionType.ZOOM_OUT: "circlecrop",
        TransitionType.BLUR: "smoothleft",
        TransitionType.FLASH: "fadewhite",
        TransitionType.GLITCH: "pixelize",
    }
    return mapping.get(t, "fade")
