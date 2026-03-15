"""Module 7 — Text Engine.

Generates text overlay assets (styled PNGs or FFmpeg drawtext commands)
for animated captions, title cards, hook text, and lyric phrases.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.schemas import TextLayer

log = get_logger(__name__)

# ── font cache ──────────────────────────────────────────────────────

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _get_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _font_cache:
        fonts_dir = get_settings().fonts_dir
        local = fonts_dir / f"{name}.ttf"
        if local.exists():
            _font_cache[key] = ImageFont.truetype(str(local), size)
        else:
            try:
                _font_cache[key] = ImageFont.truetype(name, size)
            except OSError:
                log.warning("Font '%s' not found, using default", name)
                _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]


# ── static text render (PNG) ────────────────────────────────────────

def render_text_image(
    layer: TextLayer,
    width: int = 1080,
    height: int = 1920,
    output_path: Optional[Path] = None,
) -> Image.Image:
    """Render a single text layer to a transparent RGBA image."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _get_font(layer.font, layer.font_size)

    # Measure text
    bbox = draw.textbbox((0, 0), layer.text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    # Position
    if layer.x is not None and layer.y is not None:
        x, y = layer.x, layer.y
    elif layer.position == "top":
        x = (width - tw) // 2
        y = int(height * 0.08) if layer.safe_area else 20
    elif layer.position == "bottom":
        x = (width - tw) // 2
        y = int(height * 0.85) if layer.safe_area else height - th - 20
    else:  # center
        x = (width - tw) // 2
        y = (height - th) // 2

    # Stroke / outline
    if layer.stroke_width > 0:
        for dx in range(-layer.stroke_width, layer.stroke_width + 1):
            for dy in range(-layer.stroke_width, layer.stroke_width + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), layer.text, font=font, fill=layer.stroke_color)

    # Shadow
    if layer.shadow:
        shadow_offset = max(2, layer.font_size // 20)
        draw.text((x + shadow_offset, y + shadow_offset), layer.text, font=font, fill="#00000080")

    # Main text
    draw.text((x, y), layer.text, font=font, fill=layer.color)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), "PNG")
        log.info("Text image saved → %s", output_path.name)

    return img


# ── FFmpeg drawtext filter generation ───────────────────────────────

_FFMPEG_ANIM_MAP = {
    "none": "",
    "pop_in": "fontsize='if(lt(t-{start},0.15),{sz}*(t-{start})/0.15,{sz})'",
    "slide_up": "y='if(lt(t-{start},0.3),h-(h-{y})*(t-{start})/0.3,{y})'",
    "blur_reveal": "alpha='if(lt(t-{start},0.3),(t-{start})/0.3,1)'",
    "flash_reveal": "alpha='if(lt(t-{start},0.05),1,if(lt(t-{start},0.15),0.3,1))'",
    "beat_bounce": "fontsize='{sz}+10*sin(2*PI*4*(t-{start}))*exp(-3*(t-{start}))'",
    "word_by_word": "alpha='if(lt(t-{start},0.5),(t-{start})/0.5,1)'",
}


def build_drawtext_filter(
    layer: TextLayer,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Build an FFmpeg drawtext filter string for a text layer."""
    settings = get_settings()
    fonts_dir = settings.fonts_dir
    font_file = fonts_dir / f"{layer.font}.ttf"
    fontfile_arg = f"fontfile='{font_file}'" if font_file.exists() else ""

    # Escape special chars for FFmpeg
    escaped = layer.text.replace("'", "'\\''").replace(":", "\\:")

    # Position
    if layer.x is not None and layer.y is not None:
        x_expr = str(layer.x)
        y_expr = str(layer.y)
    elif layer.position == "top":
        x_expr = "(w-text_w)/2"
        y_expr = str(int(height * 0.08))
    elif layer.position == "bottom":
        x_expr = "(w-text_w)/2"
        y_expr = str(int(height * 0.85))
    else:
        x_expr = "(w-text_w)/2"
        y_expr = "(h-text_h)/2"

    # Resolve animation expression first so we know which base values it overrides
    anim_key = layer.animation.value if layer.animation else "none"
    anim_tmpl = _FFMPEG_ANIM_MAP.get(anim_key, "")
    anim_str = ""
    if anim_tmpl:
        anim_str = anim_tmpl.format(
            start=layer.start_time,
            sz=layer.font_size,
            y=y_expr,
        )
    # pop_in / beat_bounce override fontsize; slide_up overrides y
    anim_overrides_fontsize = anim_str.startswith("fontsize=")
    anim_overrides_y = anim_str.startswith("y=")

    parts = [
        f"drawtext=text='{escaped}'",
        fontfile_arg,
        "" if anim_overrides_fontsize else f"fontsize={layer.font_size}",
        f"fontcolor={layer.color}",
        f"borderw={layer.stroke_width}",
        f"bordercolor={layer.stroke_color}",
        f"x={x_expr}",
        "" if anim_overrides_y else f"y={y_expr}",
        f"enable='between(t,{layer.start_time},{layer.end_time})'",
        anim_str,
    ]

    # Filter out empty parts
    return ":".join(p for p in parts if p)
