#!/usr/bin/env python3
"""Render deterministic 1080x1440 Xiaohongshu carousel images."""

import json
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps


CANVAS_SIZE = (1080, 1440)
SAFE_MARGIN = 72
SUPPORTED_LAYOUTS = {
    "product_focus",
    "scene_story",
    "information_card",
}
FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)


class RenderError(RuntimeError):
    pass


def load_font(size):
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size=size), candidate
        except OSError:
            continue
    raise RenderError("No usable Chinese font was found; install a Chinese font first.")


def require_image(path_value, label):
    path = Path(str(path_value or "")).expanduser()
    if not path.is_file():
        raise RenderError(f"Missing referenced image for {label}: {path}")
    try:
        return Image.open(path).convert("RGBA")
    except OSError as exc:
        raise RenderError(f"Invalid referenced image for {label}: {path}") from exc


def cover_crop(image, size):
    return ImageOps.fit(
        image,
        size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )


def contain(image, size):
    copy = image.copy()
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    return copy


def wrap_text(draw, text, font, max_width):
    paragraphs = str(text or "").splitlines() or [""]
    lines = []
    for paragraph in paragraphs:
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            candidate = current + char
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                if not current:
                    raise RenderError("Text cannot fit inside the safe area.")
                lines.append(current)
                current = char
        if current:
            lines.append(current)
    return lines


def text_block_height(lines, font, spacing):
    if not lines:
        return 0
    box = font.getbbox("国Ag")
    line_height = box[3] - box[1]
    return len(lines) * line_height + (len(lines) - 1) * spacing


def draw_text_block(draw, position, lines, font, fill, spacing):
    x, y = position
    box = font.getbbox("国Ag")
    line_height = box[3] - box[1]
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height + spacing
    return y


def add_readability_panel(canvas, top, bottom):
    overlay = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    panel = ImageDraw.Draw(overlay)
    panel.rounded_rectangle(
        (SAFE_MARGIN - 24, top - 24, CANVAS_SIZE[0] - SAFE_MARGIN + 24, bottom + 24),
        radius=24,
        fill=(255, 255, 255, 226),
    )
    canvas.alpha_composite(overlay)


def render(payload):
    layout = str(payload.get("layout") or "").strip()
    if layout not in SUPPORTED_LAYOUTS:
        raise RenderError(f"Unsupported layout: {layout}")

    try:
        background_color = ImageColor.getrgb(
            str(payload.get("background_color") or "#F7F4EE")
        )
        text_color = ImageColor.getrgb(str(payload.get("text_color") or "#191919"))
    except ValueError as exc:
        raise RenderError(f"Invalid color: {exc}") from exc

    canvas = Image.new("RGBA", CANVAS_SIZE, (*background_color, 255))
    background_path = payload.get("background_path")
    product_path = payload.get("product_path")

    if background_path:
        background = cover_crop(require_image(background_path, "background"), CANVAS_SIZE)
        canvas.alpha_composite(background)

    headline_font, font_path = load_font(74)
    body_font, _ = load_font(40)
    draw = ImageDraw.Draw(canvas)
    max_text_width = CANVAS_SIZE[0] - SAFE_MARGIN * 2
    headline_lines = wrap_text(draw, payload.get("headline", ""), headline_font, max_text_width)
    body_lines = wrap_text(draw, payload.get("body", ""), body_font, max_text_width)
    headline_height = text_block_height(headline_lines, headline_font, 14)
    body_height = text_block_height(body_lines, body_font, 14)

    if layout == "product_focus":
        if not product_path:
            raise RenderError("Missing referenced image for product.")
        product = contain(require_image(product_path, "product"), (820, 850))
        product_x = (CANVAS_SIZE[0] - product.width) // 2
        product_y = 470 + max(0, (780 - product.height) // 2)
        canvas.alpha_composite(product, (product_x, product_y))
        panel_bottom = SAFE_MARGIN + headline_height + body_height + 74
        add_readability_panel(canvas, SAFE_MARGIN, panel_bottom)
        draw = ImageDraw.Draw(canvas)
        y = draw_text_block(
            draw,
            (SAFE_MARGIN, SAFE_MARGIN),
            headline_lines,
            headline_font,
            text_color,
            14,
        )
        draw_text_block(
            draw,
            (SAFE_MARGIN, y + 34),
            body_lines,
            body_font,
            text_color,
            14,
        )
    elif layout == "scene_story":
        if not background_path:
            raise RenderError("Missing referenced image for background.")
        panel_top = 940
        panel_bottom = panel_top + headline_height + body_height + 84
        if panel_bottom > CANVAS_SIZE[1] - SAFE_MARGIN:
            raise RenderError("Text overflow in scene_story layout.")
        add_readability_panel(canvas, panel_top, panel_bottom)
        draw = ImageDraw.Draw(canvas)
        y = draw_text_block(
            draw,
            (SAFE_MARGIN, panel_top),
            headline_lines,
            headline_font,
            text_color,
            14,
        )
        draw_text_block(
            draw,
            (SAFE_MARGIN, y + 34),
            body_lines,
            body_font,
            text_color,
            14,
        )
    else:
        available_height = CANVAS_SIZE[1] - SAFE_MARGIN * 2
        total_height = headline_height + 42 + body_height
        if total_height > available_height:
            raise RenderError("Text overflow: content cannot fit inside the safe area.")
        y = SAFE_MARGIN + max(0, (available_height - total_height) // 2)
        y = draw_text_block(
            draw,
            (SAFE_MARGIN, y),
            headline_lines,
            headline_font,
            text_color,
            14,
        )
        draw_text_block(
            draw,
            (SAFE_MARGIN, y + 42),
            body_lines,
            body_font,
            text_color,
            14,
        )

    return canvas.convert("RGB"), font_path


def atomic_save(image, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=f".{output_path.stem}.",
            suffix=".png",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
        image.save(temp_path, format="PNG", optimize=True)
        os.replace(temp_path, output_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def main():
    if len(sys.argv) != 2:
        print("Usage: render_carousel.py render.json", file=sys.stderr)
        return 2
    try:
        request_path = Path(sys.argv[1]).resolve()
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RenderError("Render request must be a JSON object.")
        output_path = Path(str(payload.get("output_path") or "")).expanduser()
        if not str(output_path):
            raise RenderError("output_path is required.")
        image, font_path = render(payload)
        atomic_save(image, output_path)
        print(
            json.dumps(
                {
                    "dimensions": list(CANVAS_SIZE),
                    "font_path": font_path,
                    "output_files": [str(output_path)],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError, RenderError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
