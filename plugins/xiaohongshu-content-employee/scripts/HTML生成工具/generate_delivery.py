#!/usr/bin/env python3
"""Generate a standalone Xiaohongshu content delivery page from JSON."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List


REQUIRED_SECTIONS = (
    "content_digest",
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
ALLOWED_TOP_LEVEL_FIELDS = frozenset(REQUIRED_SECTIONS)
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|credential|password|secret|token|"
    r"request|response|debug|trace|log|screenshot|test[_-]?report|"
    r"development[_-]?plan)"
)
LOCAL_PATH_PATTERN = re.compile(
    r"(?i)(?:^|[\s\"'])("
    + re.escape("file:" + "//")
    + "|"
    + re.escape("~" + "/")
    + r"|/(?:"
    + "|".join(("Users", "home", "tmp", "var/folders"))
    + r")/|[A-Z]:[\\/])"
)
PROVIDER_NAMES = {
    "thinkai-image-2": "ThinkAI Image 2",
    "thinkai-nano": "ThinkAI Nano",
    "seedream": "火山引擎 Seedream",
    "openai-gpt-image": "OpenAI GPT Image",
    "google-nano-banana": "Google Nano Banana",
    "custom": "其他渠道",
}

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


def find_sensitive_key(value: Any, path: tuple[str, ...] = ()) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key)
            current = (*path, normalized)
            if SENSITIVE_KEY_PATTERN.search(normalized):
                return ".".join(current)
            found = find_sensitive_key(item, current)
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = find_sensitive_key(item, (*path, str(index)))
            if found:
                return found
    return None


def find_local_path(value: Any, path: tuple[str, ...] = ()) -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            found = find_local_path(item, (*path, str(key)))
            if found:
                return found
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found = find_local_path(item, (*path, str(index)))
            if found:
                return found
    elif isinstance(value, str) and LOCAL_PATH_PATTERN.search(value):
        return ".".join(path)
    return None


def validate_payload(payload: Any, source_dir: Path) -> None:
    root = require_mapping(payload, "delivery payload")
    unknown = sorted(set(root) - ALLOWED_TOP_LEVEL_FIELDS)
    if unknown:
        raise DeliveryError("unknown delivery fields: " + ", ".join(unknown))
    sensitive_key = find_sensitive_key(root)
    if sensitive_key:
        raise DeliveryError(f"sensitive field is not allowed: {sensitive_key}")
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

    content_digest = root.get("content_digest")
    if not isinstance(content_digest, str) or not re.fullmatch(
        r"[0-9a-f]{64}", content_digest
    ):
        raise DeliveryError("content_digest must be a lowercase SHA-256 digest")

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
        if image.get("source_type") == "ai_generated":
            provider = str(image.get("provider") or "").strip()
            model = str(image.get("model") or "").strip()
            if not provider:
                raise DeliveryError(f"images[{index}] ai_generated requires provider")
            if not model:
                raise DeliveryError(f"images[{index}] ai_generated requires model")
            width = image.get("width")
            height = image.get("height")
            if (
                not isinstance(width, int)
                or not isinstance(height, int)
                or width <= 0
                or height <= 0
                or width * 4 != height * 3
            ):
                raise DeliveryError(
                    f"images[{index}] ai_generated must use a 3:4 portrait ratio"
                )

    for index, page in enumerate(require_mapping_items(root["carousel"], "carousel")):
        image_id = str(page.get("image_id", "")).strip()
        if image_id and image_id not in image_ids:
            raise DeliveryError(
                f"carousel[{index}] references unknown image id: {image_id}"
            )

    local_path = find_local_path(root)
    if local_path:
        raise DeliveryError(f"local machine path is not allowed: {local_path}")


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


def relative_image_src(
    image: Dict[str, Any], source_dir: Path, output_dir: Path
) -> str:
    absolute = (source_dir / str(image["path"])).resolve()
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
) -> str:
    pages = list(carousel_pages)
    items = []
    for index, image in enumerate(images):
        src = relative_image_src(image, source_dir, output_dir)
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
) -> tuple[str, str]:
    slides = []
    dots = []
    for index, page in enumerate(carousel_pages):
        image = images_by_id.get(str(page.get("image_id", "")))
        if not image:
            continue
        src = relative_image_src(image, source_dir, output_dir)
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
        carousel_pages, images_by_id, source_dir, output_dir
    )
    if not slides and image_list:
        fallback = image_list[0]
        fallback_src = relative_image_src(fallback, source_dir, output_dir)
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
        relative_image_src(cover_image, source_dir, output_dir)
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
    images: Iterable[Dict[str, Any]], source_dir: Path, output_dir: Path
) -> str:
    items = []
    for image in images:
        src = relative_image_src(image, source_dir, output_dir)
        provider_detail = ""
        if image.get("source_type") == "ai_generated":
            provider_id = str(image.get("provider") or "")
            provider_name = PROVIDER_NAMES.get(provider_id, provider_id)
            provider_detail = (
                f'<p class="muted">渠道：{escape(provider_name)} · '
                f'模型：{escape(image.get("model"))} · '
                f'{escape(image.get("width"))}×{escape(image.get("height"))}</p>'
            )
        items.append(
            '<article class="item">'
            f"<h3>{escape(image.get('id'))}</h3>"
            f'<img class="image-preview" src="{escape(src)}" '
            f'alt="{escape(image.get("usage") or image.get("id"))}">'
            f"<p>{escape(image.get('usage'))}</p>"
            f'<p class="muted">来源：{escape(image.get("source"))}</p>'
            f"{provider_detail}"
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


def render_content(payload: Dict[str, Any], source_dir: Path, output_dir: Path) -> str:
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
        images, payload["carousel"], source_dir, output_dir
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
    )

    return f"""
  <main class="shell">
    <header class="topbar">
      <div>
        <span class="eyebrow">小红书内容交付</span>
        <h1>{escape(project.get("name"))}</h1>
        <div class="meta">{escape(project.get("goal"))} · {escape(project.get("generated_at"))}</div>
      </div>
      <div class="status status-pass">READY</div>
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
        <section class="section"><h2>图片使用方案</h2><div class="stack">{render_images(images, source_dir, output_dir)}</div></section>
        <section class="section"><h2>证据台账</h2><div class="stack">{render_evidence(payload["evidence"])}</div></section>
      </div>
    </details>
  </main>
"""


def generate(source: Path, output: Path) -> None:
    package_root = PACKAGE_ROOT.resolve()
    resolved_output = output.resolve()
    if resolved_output == package_root or package_root in resolved_output.parents:
        raise DeliveryError("HTML output cannot be inside the plugin package")
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
