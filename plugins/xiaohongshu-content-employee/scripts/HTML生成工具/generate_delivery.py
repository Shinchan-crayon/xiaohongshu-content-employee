#!/usr/bin/env python3
"""Generate a standalone Xiaohongshu content delivery page from JSON."""

from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import os
import re
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
)

SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parents[1]
TEMPLATE_DIR = PACKAGE_ROOT / "templates" / "HTML交付模板"
WORKFLOW_RUNTIME_DIR = SCRIPT_DIR.parent / "工作流工具"
if str(WORKFLOW_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_RUNTIME_DIR))

from workflow_runtime import (  # noqa: E402
    finish_stage,
    load_runtime,
    start_stage,
    transition,
    utc_now,
    write_run_log,
    write_artifact,
)


class DeliveryError(ValueError):
    pass


def load_delivery_inputs(
    run_dir: Path,
    content_path: Path,
) -> tuple[dict, dict, dict, dict]:
    run_dir = Path(run_dir).expanduser().resolve()
    expected_content_path = (run_dir / "content.json").resolve()
    if Path(content_path).expanduser().resolve() != expected_content_path:
        raise DeliveryError("Deliver Executor 只能读取 run_dir/content.json。")
    visual_path = run_dir / "visual.json"
    generation_path = run_dir / "generation.json"
    if not generation_path.is_file():
        raise DeliveryError("run_dir 缺少 generation.json，不能生成 HTML。")
    if not expected_content_path.is_file():
        raise DeliveryError("run_dir 缺少 content.json，不能生成 HTML。")
    if not visual_path.is_file():
        raise DeliveryError("run_dir 缺少 visual.json，不能生成 HTML。")
    try:
        runtime = load_runtime(run_dir)
        content = json.loads(expected_content_path.read_text(encoding="utf-8"))
        visual = json.loads(visual_path.read_text(encoding="utf-8"))
        generation = json.loads(generation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise DeliveryError(f"无法读取 Deliver Executor 输入：{error}") from error

    for artifact_name, payload in (
        ("content.json", content),
        ("visual.json", visual),
        ("generation.json", generation),
    ):
        if not isinstance(payload, dict):
            raise DeliveryError(f"{artifact_name} 必须是 JSON 对象。")
        if payload.get("schema_version") != 1:
            raise DeliveryError(f"{artifact_name}.schema_version 必须是 1。")
        if payload.get("run_id") != runtime["run_id"]:
            raise DeliveryError(f"{artifact_name}.run_id 与当前运行不匹配。")
    if runtime["stage"] != "producing":
        raise DeliveryError(
            f"Deliver Executor 只能在 producing 阶段启动，实际为 {runtime['stage']}。"
        )
    if generation.get("status") != "complete":
        raise DeliveryError(
            "generation.json.status 必须是 complete，禁止部分交付。"
        )
    return runtime, content, visual, generation


def complete_delivery(
    run_dir: Path,
    output: Path,
    runtime_log: Path,
) -> Path:
    resolved_output = Path(output).expanduser().resolve()
    if not resolved_output.is_file():
        raise DeliveryError("HTML 文件不存在，不能完成工作流。")
    resolved_log = Path(runtime_log).expanduser().resolve()
    if not resolved_log.is_file():
        raise DeliveryError("运行日志不存在，不能完成工作流。")
    try:
        runtime = load_runtime(run_dir)
        delivery_path = write_artifact(
            run_dir,
            "delivery.json",
            {
                "schema_version": 1,
                "run_id": runtime["run_id"],
                "html_path": str(resolved_output),
                "runtime_log_path": str(resolved_log),
                "generation_status": "complete",
                "completed_at": utc_now(),
            },
        )
        finish_stage(
            run_dir,
            "deliver-executor",
            [delivery_path],
            {
                "token_count": 0,
                "model_calls": 0,
                "tool_calls": 2,
                "retries": 0,
                "paid_requests": 0,
                "cost_amount": None,
                "cost_currency": None,
                "cost_status": "unavailable",
            },
        )
        transition(run_dir, "delivered")
        transition(run_dir, "completed")
        return delivery_path
    except (OSError, ValueError) as error:
        raise DeliveryError(f"无法完成 HTML 交付：{error}") from error


def require_text(value: Any, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise DeliveryError(f"{name} must be a non-empty string")
    return normalized


INTERNAL_COPY_FIELDS = (
    "briefing",
    "claim",
    "claims",
    "claim_id",
    "claim_ids",
    "post_claim_ids",
    "selling_point_ids",
    "post_selling_point_ids",
    "source_claim_ids",
    "locked_wording",
    "must_use",
    "forbidden_expansions",
    "information_task",
    "product_identity",
)
INTERNAL_COPY_PHRASES = (
    "先锁定产品身份",
    "官方页面标题",
    "来源台账",
    "事实边界",
    "不可改写事实",
    "claim_ids",
    "post_claim_ids",
    "fact_check",
    "material_record",
    "workflow runtime",
    "stage transition",
)
INTERNAL_COPY_ERROR = (
    "最终文案仍包含内部 briefing/审核字段，请先转写为小红书成稿。"
)


def require_final_copy(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise DeliveryError(
            f"{INTERNAL_COPY_ERROR}{name} 必须是最终正文字符串。"
        )
    normalized = value.strip()
    if not normalized:
        raise DeliveryError(f"{name} must be a non-empty string")
    field_pattern = "|".join(re.escape(field) for field in INTERNAL_COPY_FIELDS)
    if re.search(
        rf"(?im)^\s*[\"']?(?:{field_pattern})[\"']?\s*[:：=]",
        normalized,
    ) or re.search(
        rf"[{{,]\s*[\"'](?:{field_pattern})[\"']\s*:",
        normalized,
    ):
        raise DeliveryError(INTERNAL_COPY_ERROR)
    folded = normalized.casefold()
    if any(phrase.casefold() in folded for phrase in INTERNAL_COPY_PHRASES):
        raise DeliveryError(INTERNAL_COPY_ERROR)
    return normalized


def split_copy(value: str) -> tuple[str, List[str]]:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if not lines:
        return "", []
    return lines[0], lines[1:]


def latest_generation_items(items: Any) -> Dict[str, Dict[str, Any]]:
    latest = {}
    for index, value in enumerate(require_list(items, "generation.json.items")):
        item = require_mapping(value, f"generation.json.items[{index}]")
        page_id = require_text(
            item.get("page_id"),
            f"generation.json.items[{index}].page_id",
        )
        attempt = item.get("attempt")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise DeliveryError(
                f"generation.json.items[{index}].attempt must be a positive integer"
            )
        previous = latest.get(page_id)
        if previous is None or attempt > previous["attempt"]:
            latest[page_id] = item
    return latest


def build_delivery_payload(
    content: Dict[str, Any],
    visual: Dict[str, Any],
    generation: Dict[str, Any],
) -> tuple[Dict[str, Any], Path]:
    required_content_fields = (
        "titles",
        "post",
        "post_selling_point_ids",
        "post_claim_ids",
        "carousel_blocks",
    )
    missing = [field for field in required_content_fields if field not in content]
    if missing:
        raise DeliveryError(
            "content.json missing required sections: " + ", ".join(missing)
        )

    raw_titles = require_list(content["titles"], "content.json.titles")
    titles = []
    for index, value in enumerate(raw_titles):
        title_text = require_final_copy(
            value,
            f"content.json.titles[{index}]",
        )
        titles.append(
            {
                "text": title_text,
                "recommended": index == 0,
            }
        )
    if len(titles) < 5:
        raise DeliveryError("content.json.titles 至少需要 5 个候选标题")

    post_text = require_final_copy(content["post"], "content.json.post")
    hook, body = split_copy(post_text)
    carousel_blocks = require_mapping_items(
        content["carousel_blocks"],
        "content.json.carousel_blocks",
    )
    block_by_id = {}
    for index, block in enumerate(carousel_blocks):
        block_id = require_text(
            block.get("id"),
            f"content.json.carousel_blocks[{index}].id",
        )
        block_by_id[block_id] = block

    visual_pages = require_mapping_items(
        visual.get("pages"),
        "visual.json.pages",
    )
    generation_items = latest_generation_items(generation.get("items"))
    page_ids = [
        require_text(page.get("id"), f"visual.json.pages[{index}].id")
        for index, page in enumerate(visual_pages)
    ]
    if set(generation_items) != set(page_ids):
        raise DeliveryError(
            "generation.json must contain one latest request for every visual page"
        )
    incomplete = [
        page_id
        for page_id in page_ids
        if generation_items[page_id].get("request_status") != "complete"
    ]
    if incomplete:
        raise DeliveryError(
            "generation.json latest requests must all be complete: "
            + ", ".join(incomplete)
        )

    source_dir = Path(
        str(generation.get("output_root") or "")
    ).expanduser().resolve()
    if not str(generation.get("output_root") or "").strip():
        raise DeliveryError("generation.json.output_root must be recorded")

    carousel = []
    images = []
    for index, page in enumerate(visual_pages):
        page_id = page_ids[index]
        block = block_by_id.get(page_id, {})
        copy_text = require_final_copy(
            block.get("text") or page.get("information_task") or page_id,
            f"content.json.carousel_blocks[{page_id}].text",
        )
        headline, page_body = split_copy(copy_text)
        if not headline:
            headline = page_id
        item = generation_items[page_id]
        image_path = require_text(
            item.get("path"),
            f"generation.json.items[{page_id}].path",
        )
        carousel.append(
            {
                "page": index + 1,
                "headline": headline,
                "body": "\n".join(page_body),
                "image_id": page_id,
            }
        )
        images.append(
            {
                "id": page_id,
                "path": image_path,
                "usage": require_text(
                    page.get("information_task") or headline,
                    f"visual.json.pages[{index}].information_task",
                ),
                "source": "已批准 Prompt 的生成图片",
                "source_type": "ai_generated",
            }
        )

    tags = [
        value
        for value in re.findall(r"#([^\s#]+)", post_text)
        if value.strip()
    ]
    payload = {
        "project": {
            "name": titles[0]["text"],
            "goal": "小红书内容与轮播图交付",
            "generated_at": "",
        },
        "evidence": [],
        "topics": [
            {
                "title": carousel[0]["headline"] if carousel else titles[0]["text"],
                "reason": "已选定内容主题",
            }
        ],
        "titles": titles,
        "post": {
            "hook": hook,
            "body": body,
            "cta": "",
        },
        "tags": tags,
        "cover": {
            "headline": titles[0]["text"],
            "subheadline": carousel[0]["headline"] if carousel else "",
            "image_id": page_ids[0] if page_ids else "",
        },
        "carousel": carousel,
        "images": images,
    }
    return payload, source_dir


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
        raw_path = Path(image_path).expanduser()
        if raw_path.is_absolute():
            raise DeliveryError(f"images[{index}].path must be relative")
        source_root = source_dir.resolve()
        candidate = (source_root / raw_path).resolve()
        if candidate != source_root and source_root not in candidate.parents:
            raise DeliveryError(
                f"images[{index}].path points outside delivery source"
            )
        if not candidate.is_file():
            raise DeliveryError(f"missing image: {image_path}")
    for index, page in enumerate(require_mapping_items(root["carousel"], "carousel")):
        image_id = str(page.get("image_id", "")).strip()
        if image_id and image_id not in image_ids:
            raise DeliveryError(
                f"carousel[{index}] references unknown image id: {image_id}"
            )

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


def image_src(
    image: Dict[str, Any],
    source_dir: Path,
    output_dir: Path,
    embed_images: bool,
) -> str:
    absolute = (source_dir / str(image["path"])).resolve()
    if embed_images:
        media_type = mimetypes.guess_type(absolute.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(absolute.read_bytes()).decode("ascii")
        return f"data:{media_type};base64,{encoded}"
    relative = os.path.relpath(str(absolute), str(output_dir))
    return Path(relative).as_posix()


def render_title_options(titles: Iterable[Dict[str, Any]]) -> str:
    title_list = list(titles)
    active_index = next(
        (index for index, title in enumerate(title_list) if title.get("recommended")),
        0,
    )
    items = []
    for index, title in enumerate(title_list):
        is_active = index == active_index
        recommended = bool(title.get("recommended"))
        classes = "title-option is-active" if is_active else "title-option"
        badge = '<span class="recommend-label">推荐</span>' if recommended else ""
        items.append(
            '<div class="title-choice">'
            f'<button class="{classes}" type="button" '
            f'data-title-text="{escape(title.get("text"))}" '
            f'aria-pressed="{"true" if is_active else "false"}">'
            f'{badge}<span class="title-input" data-title-editor '
            f'contenteditable="true" role="textbox" aria-multiline="false" '
            f'aria-label="候选标题 {index + 1}">{escape(title.get("text"))}</span>'
            "</button>"
            f'<button class="icon-btn title-copy" type="button" '
            f'data-copy-text="{escape(title.get("text"))}" title="复制标题" '
            f'aria-label="复制标题 {index + 1}">⧉</button>'
            "</div>"
        )
    return "".join(items)


def render_image_editor(
    images: Iterable[Dict[str, Any]],
    carousel_pages: Iterable[Dict[str, Any]],
    source_dir: Path,
    output_dir: Path,
    embed_images: bool,
) -> str:
    pages = list(carousel_pages)
    items = []
    for index, image in enumerate(images):
        src = image_src(image, source_dir, output_dir, embed_images)
        image_id = str(image.get("id", ""))
        slide_index = next(
            (
                page_index
                for page_index, page in enumerate(pages)
                if str(page.get("image_id", "")) == image_id
            ),
            0,
        )
        classes = "image-thumb is-active" if index == 0 else "image-thumb"
        items.append(
            f'<button class="{classes}" type="button" '
            f'data-editor-slide-index="{slide_index}" '
            f'data-editor-image="{escape(image_id)}" '
            f'title="查看{escape(image.get("usage") or image_id)}">'
            f'<img src="{escape(src)}" alt="{escape(image.get("usage") or image_id)}">'
            f'<span>{index + 1}</span>'
            "</button>"
        )
    return "".join(items)


def render_post_editor(post: Dict[str, Any], tags: Iterable[str]) -> str:
    body = require_list(post.get("body", []), "post.body")
    parts = [f'<p class="post-hook">{escape(post.get("hook"))}</p>']
    parts.extend(f"<p>{escape(paragraph)}</p>" for paragraph in body)
    if post.get("cta"):
        parts.append(f'<p class="post-cta">{escape(post.get("cta"))}</p>')
    tag_markup = " ".join(
        f'<span class="editor-tag">#{escape(tag)}</span>' for tag in tags
    )
    return (
        '<div class="post-copy copy-source" id="post-copy">'
        '<div class="post-content" data-post-editor contenteditable="true" '
        'role="textbox" aria-multiline="true" aria-label="小红书正文">'
        f"{''.join(parts)}"
        "</div>"
        f'<div class="editor-tags" id="tags-copy">{tag_markup}</div>'
        "</div>"
    )


def render_preview_slides(
    carousel_pages: Iterable[Dict[str, Any]],
    images_by_id: Dict[str, Dict[str, Any]],
    source_dir: Path,
    output_dir: Path,
    embed_images: bool,
) -> tuple[str, str]:
    slides = []
    dots = []
    for index, page in enumerate(carousel_pages):
        image = images_by_id.get(str(page.get("image_id", "")))
        if not image:
            continue
        src = image_src(image, source_dir, output_dir, embed_images)
        slide_number = len(slides) + 1
        classes = "preview-slide is-active" if not slides else "preview-slide"
        slides.append(
            f'<figure class="{classes}" data-slide-index="{slide_number}">'
            f'<img src="{escape(src)}" alt="{escape(page.get("headline") or image.get("usage"))}">'
            f'<figcaption>{escape(page.get("headline"))}</figcaption>'
            "</figure>"
        )
        dot_classes = "preview-dot is-active" if slide_number == 1 else "preview-dot"
        dots.append(
            f'<button class="{dot_classes}" type="button" '
            f'data-carousel-dot="{slide_number}" '
            f'aria-label="查看第 {slide_number} 张图片"></button>'
        )
    return "".join(slides), "".join(dots)


def render_phone_preview(
    project: Dict[str, Any],
    titles: Iterable[Dict[str, Any]],
    post: Dict[str, Any],
    cover: Dict[str, Any],
    carousel_pages: Iterable[Dict[str, Any]],
    images: Iterable[Dict[str, Any]],
    source_dir: Path,
    output_dir: Path,
    embed_images: bool,
) -> str:
    title_list = list(titles)
    active_title = next(
        (
            str(title.get("text", ""))
            for title in title_list
            if title.get("recommended")
        ),
        str(title_list[0].get("text", "")) if title_list else "",
    )
    image_list = list(images)
    images_by_id = {str(image.get("id")): image for image in image_list}
    slides, dots = render_preview_slides(
        carousel_pages,
        images_by_id,
        source_dir,
        output_dir,
        embed_images,
    )
    if not slides and image_list:
        fallback = image_list[0]
        fallback_src = image_src(
            fallback,
            source_dir,
            output_dir,
            embed_images,
        )
        slides = (
            '<figure class="preview-slide is-active" data-slide-index="1">'
            f'<img src="{escape(fallback_src)}" alt="{escape(fallback.get("usage"))}">'
            "</figure>"
        )
        dots = (
            '<button class="preview-dot is-active" type="button" '
            'data-carousel-dot="1" aria-label="查看第 1 张图片"></button>'
        )

    cover_image = images_by_id.get(str(cover.get("image_id", "")))
    if not cover_image:
        first_page = next(iter(carousel_pages), {})
        cover_image = images_by_id.get(str(first_page.get("image_id", "")))
    if not cover_image and image_list:
        cover_image = image_list[0]
    cover_src = (
        image_src(
            cover_image,
            source_dir,
            output_dir,
            embed_images,
        )
        if cover_image
        else ""
    )
    preview_body = " ".join(
        [
            str(post.get("hook") or ""),
            *[str(item) for item in require_list(post.get("body", []), "post.body")],
        ]
    ).strip()
    account_name = str(project.get("account_name") or "内容创作者")
    cover_image_markup = (
        f'<img src="{escape(cover_src)}" alt="{escape(cover.get("headline"))}">'
        if cover_src
        else '<div class="cover-placeholder">暂无封面</div>'
    )

    return f"""
      <aside class="preview-pane" aria-label="发布效果预览">
        <div class="preview-tabs" role="tablist" aria-label="预览模式">
          <button class="preview-tab is-active" type="button" role="tab"
            aria-selected="true" data-preview-tab="note">笔记预览</button>
          <button class="preview-tab" type="button" role="tab"
            aria-selected="false" data-preview-tab="cover">封面预览</button>
        </div>
        <div class="phone-stage" data-preview-scale-stage>
          <div class="phone-frame" data-preview-scale-target>
            <div class="phone-status"><strong>9:41</strong><span>● ● ▰</span></div>
            <section class="preview-panel is-active" data-preview-panel="note">
              <div class="note-header">
                <span class="back-mark">‹</span>
                <span class="account-avatar">小</span>
                <strong>{escape(account_name)}</strong>
                <span class="follow-button">关注</span>
                <span class="share-mark">⌁</span>
              </div>
              <div class="phone-carousel">
                <div class="preview-slides">{slides}</div>
                <button class="carousel-arrow carousel-prev" type="button"
                  data-carousel-direction="prev" aria-label="上一张">‹</button>
                <button class="carousel-arrow carousel-next" type="button"
                  data-carousel-direction="next" aria-label="下一张">›</button>
                <span class="slide-count"><b data-current-slide>1</b>/<span data-slide-total>1</span></span>
              </div>
              <div class="preview-dots">{dots}</div>
              <div class="note-copy">
                <strong data-preview-title>{escape(active_title)}</strong>
                <p data-preview-body>{escape(preview_body)}</p>
                <span class="note-time">编辑于 刚刚</span>
              </div>
              <div class="note-actions">
                <span>说点什么...</span><b>♡</b><b>☆</b><b>◌</b>
              </div>
            </section>
            <section class="preview-panel cover-panel" data-preview-panel="cover" hidden>
              <div class="discover-header">
                <span>☰</span><strong>发现</strong><span>⌕</span>
              </div>
              <div class="discover-tabs"><b>推荐</b><span>直播</span><span>穿搭</span><span>旅行</span></div>
              <div class="cover-grid">
                <article class="cover-result is-selected">
                  {cover_image_markup}
                  <strong data-preview-title>{escape(active_title)}</strong>
                  <small>{escape(account_name)}　♡ 0</small>
                </article>
                <article class="cover-result placeholder-result"><div></div><strong>更多内容</strong><small>用户　♡ 0</small></article>
                <article class="cover-result placeholder-result"><div></div><strong>相关笔记</strong><small>用户　♡ 0</small></article>
                <article class="cover-result placeholder-result"><div></div><strong>发现更多</strong><small>用户　♡ 0</small></article>
              </div>
              <div class="discover-nav"><span>首页</span><span>市集</span><b>＋</b><span>消息</span><span>我</span></div>
            </section>
          </div>
        </div>
      </aside>
"""


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
    images: Iterable[Dict[str, Any]],
    source_dir: Path,
    output_dir: Path,
    embed_images: bool,
) -> str:
    items = []
    for image in images:
        src = image_src(image, source_dir, output_dir, embed_images)
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


def render_content(
    payload: Dict[str, Any],
    source_dir: Path,
    output_dir: Path,
    embed_images: bool,
) -> str:
    project = require_mapping(payload["project"], "project")
    post = require_mapping(payload["post"], "post")
    cover = require_mapping(payload["cover"], "cover")
    images = require_list(payload["images"], "images")
    images_by_id = {str(item["id"]): item for item in images}
    cover_content = (
        f"<h3>{escape(cover.get('headline'))}</h3>"
        f"<p>{escape(cover.get('subheadline'))}</p>"
    )
    title_options = render_title_options(payload["titles"])
    image_editor = render_image_editor(
        images,
        payload["carousel"],
        source_dir,
        output_dir,
        embed_images,
    )
    phone_preview = render_phone_preview(
        project,
        payload["titles"],
        post,
        cover,
        payload["carousel"],
        images,
        source_dir,
        output_dir,
        embed_images,
    )

    return f"""
  <main class="shell">
    <header class="topbar">
      <div>
        <span class="eyebrow">小红书内容交付</span>
        <h1>{escape(project.get("name"))}</h1>
        <div class="meta">{escape(project.get("goal"))} · {escape(project.get("generated_at"))}</div>
      </div>
    </header>
    <div class="publish-workspace">
      <div class="editor-pane">
        <section class="editor-section image-editor">
          <div class="section-heading">
            <div><h2>图片</h2><span>{len(images)} 张</span></div>
            <span class="section-note">点击图片可同步查看笔记预览</span>
          </div>
          <div class="image-strip">{image_editor}</div>
        </section>
        <section class="editor-section title-editor">
          <div class="section-heading">
            <div><h2>标题</h2><span>{len(payload["titles"])} 个候选</span></div>
            <span class="section-note">选择后同步到右侧预览</span>
          </div>
          <div class="title-options" role="listbox" aria-label="候选标题">
            {title_options}
          </div>
        </section>
        <section class="editor-section post-editor">
          <div class="section-heading">
            <div><h2>正文</h2></div>
            <button class="copy-btn" type="button" data-copy-target="post-copy">复制正文</button>
          </div>
          {render_post_editor(post, payload["tags"])}
        </section>
      </div>
      {phone_preview}
    </div>
    <details class="delivery-details">
      <summary>查看交付详情</summary>
      <div class="details-grid">
        <section class="section"><h2>推荐选题</h2><div class="stack">{render_topics(payload["topics"])}</div></section>
        <section class="section"><h2>封面文案</h2>{render_copy_block("cover-copy", cover_content)}</section>
        <section class="section details-wide"><h2>轮播图逐页脚本</h2><div class="carousel">{render_carousel(payload["carousel"], images_by_id)}</div></section>
        <section class="section"><h2>图片使用方案</h2><div class="stack">{render_images(images, source_dir, output_dir, embed_images)}</div></section>
      </div>
    </details>
  </main>
"""


def generate(
    payload: Dict[str, Any],
    source_dir: Path,
    output: Path,
    embed_images: bool = True,
) -> None:
    package_root = PACKAGE_ROOT.resolve()
    resolved_output = output.resolve()
    if resolved_output == package_root or package_root in resolved_output.parents:
        raise DeliveryError("HTML output cannot be inside the plugin package")
    resolved_source_dir = Path(source_dir).expanduser().resolve()
    validate_payload(payload, resolved_source_dir)
    template = (TEMPLATE_DIR / "delivery.html").read_text(encoding="utf-8")
    style = (TEMPLATE_DIR / "delivery.css").read_text(encoding="utf-8")
    script = (TEMPLATE_DIR / "delivery.js").read_text(encoding="utf-8")
    project = require_mapping(payload["project"], "project")
    rendered = (
        template.replace("{{TITLE}}", escape(project.get("name", "内容交付")))
        .replace("{{STYLE}}", style)
        .replace(
            "{{CONTENT}}",
            render_content(
                payload,
                resolved_source_dir,
                resolved_output.parent,
                embed_images,
            ),
        )
        .replace("{{SCRIPT}}", script)
    )
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(rendered, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path)
    parser.add_argument("output_html", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    image_mode = parser.add_mutually_exclusive_group()
    image_mode.add_argument(
        "--embed-images",
        dest="embed_images",
        action="store_true",
        help="把生成图片嵌入 HTML，便于单文件交付（默认）",
    )
    image_mode.add_argument(
        "--link-images",
        dest="embed_images",
        action="store_false",
        help="保留相对图片路径，不嵌入图片",
    )
    parser.set_defaults(embed_images=True)
    parser.add_argument(
        "--run-log",
        action="store_true",
        help="兼容参数；独立运行日志已默认生成",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_dir = args.run_dir.expanduser().resolve()
        output = args.output_html.expanduser().resolve()
        _runtime, content, visual, generation = load_delivery_inputs(
            run_dir,
            args.input_json,
        )
        start_stage(
            run_dir,
            "deliver-executor",
            [],
            [
                run_dir / "content.json",
                run_dir / "visual.json",
                run_dir / "generation.json",
            ],
        )
        payload, source_dir = build_delivery_payload(
            content,
            visual,
            generation,
        )
        generate(
            payload,
            source_dir,
            output,
            embed_images=args.embed_images,
        )
        runtime_log = output.with_suffix(".run-log.md")
        write_run_log(run_dir, runtime_log)
        complete_delivery(
            run_dir,
            output,
            runtime_log,
        )
        # 完成状态迁移后覆盖一次，使交付日志展示最终 completed 状态。
        write_run_log(run_dir, runtime_log)
    except (OSError, json.JSONDecodeError, DeliveryError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    result = {
        "delivery_html": str(output),
        "runtime_log": str(runtime_log),
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
