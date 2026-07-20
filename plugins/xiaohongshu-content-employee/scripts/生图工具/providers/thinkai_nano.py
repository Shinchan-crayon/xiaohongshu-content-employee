"""ThinkAI Nano Banana 2 图片生成适配器。"""

import base64
import binascii
import re
from typing import Any

from providers.base import provider_config, require_text
from provider_registry import resolve_model


SUPPORTED_SIZES = {"1K", "2K", "4K"}
ASPECT_RATIO_PATTERN = re.compile(r"^\d+:\d+$")


def load_config(raw_config: dict, provider_spec: dict) -> dict:
    saved = provider_config(raw_config, "thinkai-nano")
    api_key = require_text(saved.get("api_key"), "ThinkAI Nano API Key")
    alias = str(
        saved.get("model_alias") or provider_spec["recommended_model"]
    ).strip().lower()
    return {
        "provider": "thinkai-nano",
        "provider_name": provider_spec["name"],
        "base_url": provider_spec["base_url"],
        "model": resolve_model("thinkai-nano", alias),
        "api_key": api_key,
    }


def normalize_size(raw_size, provider_spec: dict) -> str:
    value = str(raw_size or provider_spec["default_size"]).strip()
    if "@" in value:
        aspect_ratio, image_size = value.split("@", 1)
    else:
        aspect_ratio, image_size = "1:1", value
    aspect_ratio = aspect_ratio.strip()
    image_size = image_size.strip().upper()
    if not ASPECT_RATIO_PATTERN.fullmatch(aspect_ratio):
        raise ValueError("ThinkAI Nano 比例必须使用 16:9、1:1 等格式。")
    if image_size not in SUPPORTED_SIZES:
        raise ValueError("ThinkAI Nano 尺寸只能是 1K、2K 或 4K。")
    return f"{aspect_ratio}@{image_size}"


def build_request(config: dict, prompt: str, size: str, quality: str) -> dict:
    del quality
    aspect_ratio, image_size = normalize_size(
        size,
        {"default_size": "1:1@1K"},
    ).split("@", 1)
    return {
        "url": (
            f"{config['base_url']}/models/"
            f"{config['model']}:generateContent"
        ),
        "headers": {
            "Authorization": f"Bearer {config['api_key']}",
            "x-goog-api-key": config["api_key"],
            "Content-Type": "application/json",
            "User-Agent": "Xiaohongshu-Content-Employee/2.0.1",
        },
        "body": {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE", "TEXT"],
                "imageConfig": {
                    "aspectRatio": aspect_ratio,
                    "imageSize": image_size,
                },
            },
        },
    }


def _find_inline_image(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("inlineData", "inline_data"):
            inline = value.get(key)
            if isinstance(inline, dict):
                data = inline.get("data")
                if isinstance(data, str) and data:
                    return data
        for child in value.values():
            try:
                return _find_inline_image(child)
            except LookupError:
                continue
    elif isinstance(value, list):
        for child in value:
            try:
                return _find_inline_image(child)
            except LookupError:
                continue
    raise LookupError


def extract_image_source(response_json: dict):
    try:
        encoded = _find_inline_image(response_json)
        base64.b64decode(encoded, validate=True)
    except LookupError as exc:
        raise RuntimeError("ThinkAI Nano 响应未包含内嵌图片数据。") from exc
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("ThinkAI Nano 返回的图片 Base64 数据无效。") from exc
    return "base64", encoded
