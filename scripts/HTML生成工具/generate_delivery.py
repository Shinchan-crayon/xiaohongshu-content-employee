#!/usr/bin/env python3
"""Generate a standalone Xiaohongshu content delivery page from JSON."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


REQUIRED_SECTIONS = (
    "project",
    "evidence",
    "topics",
    "titles",
    "post",
    "tags",
    "cover",
    "carousel",
    "images",
    "review",
)
APPROVED_REVIEW_STATUSES = {"PASS", "PASS_WITH_NOTES"}

SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parents[1]
TEMPLATE_DIR = PACKAGE_ROOT / "templates" / "HTML交付模板"


class DeliveryError(ValueError):
    pass


def escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def require_mapping(value: Any, name: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise DeliveryError(f"{name} must be an object")
    return value


def require_list(value: Any, name: str) -> List[Any]:
    if not isinstance(value, list):
        raise DeliveryError(f"{name} must be an array")
    return value


def require_mapping_items(value: Any, name: str) -> List[Dict[str, Any]]:
    items = require_list(value, name)
    return [
        require_mapping(item, f"{name}[{index}]")
        for index, item in enumerate(items)
    ]


def validate_payload(payload: Any, source_dir: Path) -> None:
    root = require_mapping(payload, "delivery payload")
    missing = [key for key in REQUIRED_SECTIONS if key not in root]
    if missing:
        raise DeliveryError(
            "missing required sections: " + ", ".join(sorted(missing))
        )

    require_mapping(root["project"], "project")
    require_mapping_items(root["evidence"], "evidence")
    require_mapping_items(root["topics"], "topics")
    titles = require_mapping_items(root["titles"], "titles")
    for index, title in enumerate(titles):
        if not isinstance(title.get("text"), str):
            raise DeliveryError(f"titles[{index}].text must be a string")

    post = require_mapping(root["post"], "post")
    body = require_list(post.get("body", []), "post.body")
    for index, paragraph in enumerate(body):
        if not isinstance(paragraph, str):
            raise DeliveryError(f"post.body[{index}] must be a string")

    tags = require_list(root["tags"], "tags")
    for index, tag in enumerate(tags):
        if not isinstance(tag, str):
            raise DeliveryError(f"tags[{index}] must be a string")

    require_mapping(root["cover"], "cover")

    review = require_mapping(root["review"], "review")
    review_status = review.get("status")
    if review_status not in APPROVED_REVIEW_STATUSES:
        raise DeliveryError(
            "review status must be PASS or PASS_WITH_NOTES"
        )

    require_mapping_items(review.get("checks", []), "review.checks")

    images = require_mapping_items(root["images"], "images")
    image_ids = set()
    for index, image in enumerate(images):
        image_id = str(image.get("id", "")).strip()
        image_path = str(image.get("path", "")).strip()
        if not image_id or not image_path:
            raise DeliveryError(f"images[{index}] requires id and path")
        if image_id in image_ids:
            raise DeliveryError(f"duplicate image id: {image_id}")
        image_ids.add(image_id)
        candidate = (source_dir / image_path).resolve()
        if not candidate.is_file():
            raise DeliveryError(f"missing image: {image_path}")

    for index, page in enumerate(require_mapping_items(root["carousel"], "carousel")):
        image_id = str(page.get("image_id", "")).strip()
        if image_id and image_id not in image_ids:
            raise DeliveryError(
                f"carousel[{index}] references unknown image id: {image_id}"
            )


def status_class(status: Any) -> str:
    normalized = str(status or "").upper()
    if normalized == "PASS":
        return "status-pass"
    if normalized in {"WARN", "PASS_WITH_NOTES"}:
        return "status-warn"
    return "status-fail"


def render_copy_block(block_id: str, content: str) -> str:
    return (
        '<div class="copy-row">'
        f'<div class="copy-source" id="{escape(block_id)}">{content}</div>'
        f'<button class="copy-btn" type="button" data-copy-target="{escape(block_id)}" '
        'title="复制内容">复制</button>'
        "</div>"
    )


def render_topics(topics: Iterable[Dict[str, Any]]) -> str:
    items = []
    for topic in topics:
        items.append(
            '<article class="item">'
            f"<h3>{escape(topic.get('title'))}</h3>"
            f"<p>{escape(topic.get('reason') or topic.get('angle'))}</p>"
            "</article>"
        )
    return "".join(items)


def render_titles(titles: Iterable[Dict[str, Any]]) -> str:
    items = []
    for index, title in enumerate(titles, 1):
        recommended = bool(title.get("recommended"))
        classes = "item recommended" if recommended else "item"
        badge = '<span class="tag">推荐</span> ' if recommended else ""
        items.append(
            f'<article class="{classes}">'
            + render_copy_block(
                f"title-{index}", f"{badge}{escape(title.get('text'))}"
            )
            + "</article>"
        )
    return "".join(items)


def render_post(post: Dict[str, Any]) -> str:
    body = require_list(post.get("body", []), "post.body")
    parts = [f"<p><strong>{escape(post.get('hook'))}</strong></p>"]
    parts.extend(f"<p>{escape(paragraph)}</p>" for paragraph in body)
    if post.get("cta"):
        parts.append(f"<p>{escape(post.get('cta'))}</p>")
    return render_copy_block("post-copy", "".join(parts))


def render_carousel(
    pages: Iterable[Dict[str, Any]], images_by_id: Dict[str, Dict[str, Any]]
) -> str:
    items = []
    for index, page in enumerate(pages, 1):
        image = images_by_id.get(str(page.get("image_id", "")))
        image_note = (
            f'<p class="muted">图片：{escape(image.get("usage"))}</p>' if image else ""
        )
        content = (
            f'<div class="page-number">第 {escape(page.get("page", index))} 页</div>'
            f"<h3>{escape(page.get('headline'))}</h3>"
            f"<p>{escape(page.get('body'))}</p>"
            f"{image_note}"
        )
        items.append(
            '<article class="item">'
            + render_copy_block(f"carousel-{index}", content)
            + "</article>"
        )
    return "".join(items)


def render_images(
    images: Iterable[Dict[str, Any]], source_dir: Path, output_dir: Path
) -> str:
    items = []
    for image in images:
        absolute = (source_dir / str(image["path"])).resolve()
        relative = os.path.relpath(str(absolute), str(output_dir))
        src = Path(relative).as_posix()
        items.append(
            '<article class="item">'
            f"<h3>{escape(image.get('id'))}</h3>"
            f'<img class="image-preview" src="{escape(src)}" '
            f'alt="{escape(image.get("usage") or image.get("id"))}">'
            f"<p>{escape(image.get('usage'))}</p>"
            f'<p class="muted">来源：{escape(image.get("source"))}</p>'
            '<div class="actions">'
            f'<a class="image-link" href="{escape(src)}" target="_blank" rel="noopener">预览</a>'
            f'<a class="image-link" href="{escape(src)}" download>下载</a>'
            "</div>"
            "</article>"
        )
    return "".join(items)


def render_evidence(evidence: Iterable[Dict[str, Any]]) -> str:
    items = []
    for entry in evidence:
        items.append(
            '<article class="item">'
            f'<span class="evidence-label">{escape(entry.get("label"))}</span>'
            f"<p>{escape(entry.get('claim'))}</p>"
            f'<p class="muted">来源：{escape(entry.get("source"))}</p>'
            "</article>"
        )
    return "".join(items)


def render_review(review: Dict[str, Any]) -> str:
    rows = []
    for check in require_list(review.get("checks", []), "review.checks"):
        rows.append(
            "<tr>"
            f"<td>{escape(check.get('name'))}</td>"
            f'<td class="{status_class(check.get("status"))}">{escape(check.get("status"))}</td>'
            f"<td>{escape(check.get('notes') or check.get('findings'))}</td>"
            "</tr>"
        )
    return (
        '<table class="review-table">'
        "<thead><tr><th>检查项</th><th>状态</th><th>说明</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def render_content(payload: Dict[str, Any], source_dir: Path, output_dir: Path) -> str:
    project = require_mapping(payload["project"], "project")
    post = require_mapping(payload["post"], "post")
    cover = require_mapping(payload["cover"], "cover")
    review = require_mapping(payload["review"], "review")
    images = require_list(payload["images"], "images")
    images_by_id = {str(item["id"]): item for item in images}
    tags = " ".join(f'<span class="tag">#{escape(tag)}</span>' for tag in payload["tags"])
    cover_content = (
        f"<h3>{escape(cover.get('headline'))}</h3>"
        f"<p>{escape(cover.get('subheadline'))}</p>"
    )

    return f"""
  <main class="shell">
    <header class="topbar">
      <div>
        <h1>{escape(project.get("name"))}</h1>
        <div class="meta">{escape(project.get("goal"))} · {escape(project.get("generated_at"))}</div>
      </div>
      <div class="status {status_class(review.get("status"))}">{escape(review.get("status"))}</div>
    </header>
    <div class="layout">
      <div>
        <section class="section"><h2>推荐选题</h2><div class="stack">{render_topics(payload["topics"])}</div></section>
        <section class="section"><h2>标题候选</h2><div class="stack">{render_titles(payload["titles"])}</div></section>
        <section class="section"><h2>小红书正文</h2>{render_post(post)}</section>
        <section class="section"><h2>标签</h2><div class="tags" id="tags-copy">{tags}</div><button class="copy-btn" type="button" data-copy-target="tags-copy">复制</button></section>
        <section class="section"><h2>封面文案</h2>{render_copy_block("cover-copy", cover_content)}</section>
        <section class="section"><h2>轮播图逐页脚本</h2><div class="carousel">{render_carousel(payload["carousel"], images_by_id)}</div></section>
      </div>
      <aside class="sidebar">
        <section class="section"><h2>图片使用方案</h2><div class="stack">{render_images(images, source_dir, output_dir)}</div></section>
        <section class="section"><h2>证据台账</h2><div class="stack">{render_evidence(payload["evidence"])}</div></section>
        <section class="section"><h2>内容审核结果</h2>{render_review(review)}</section>
      </aside>
    </div>
  </main>
"""


def generate(source: Path, output: Path) -> None:
    payload = json.loads(source.read_text(encoding="utf-8"))
    validate_payload(payload, source.parent)
    template = (TEMPLATE_DIR / "delivery.html").read_text(encoding="utf-8")
    style = (TEMPLATE_DIR / "delivery.css").read_text(encoding="utf-8")
    script = (TEMPLATE_DIR / "delivery.js").read_text(encoding="utf-8")
    project = require_mapping(payload["project"], "project")
    rendered = (
        template.replace("{{TITLE}}", escape(project.get("name", "内容交付")))
        .replace("{{STYLE}}", style)
        .replace(
            "{{CONTENT}}",
            render_content(payload, source.parent, output.parent.resolve()),
        )
        .replace("{{SCRIPT}}", script)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path)
    parser.add_argument("output_html", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        generate(args.input_json.resolve(), args.output_html.resolve())
    except (OSError, json.JSONDecodeError, DeliveryError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(args.output_html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
