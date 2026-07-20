"""火山引擎方舟图片生成适配器。"""

from __future__ import annotations

import json
from typing import Tuple

from provider_registry import resolve_model
from providers.base import provider_config, require_text


DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
SIZE_ALIASES = {
    "1k": "1K",
    "2k": "2K",
    "4k": "4K",
}


def load_config(raw_config: dict, provider_spec: dict = None) -> dict:
    if provider_spec is None:
        provider_spec = {
            "name": "火山引擎 Seedream",
            "base_url": DEFAULT_BASE_URL,
            "recommended_model": "recommended",
            "models": {},
            "default_size": "2k",
        }
    providers = raw_config.get("providers")
    saved = providers.get("seedream") if isinstance(providers, dict) else None
    if not isinstance(saved, dict):
        saved = raw_config.get("seedream")
    if not isinstance(saved, dict):
        raise RuntimeError("未配置火山引擎 Seedream。请先选择并配置生图模型。")
    base_url = provider_spec["base_url"]
    legacy_base_url = str(saved.get("base_url") or base_url).rstrip("/")
    if legacy_base_url != base_url:
        raise RuntimeError("火山引擎 API 地址与当前适配器契约不一致，请重新配置。")
    legacy_model = str(saved.get("model") or "").strip()
    if legacy_model:
        model = legacy_model
    else:
        alias = str(saved.get("model_alias") or provider_spec["recommended_model"]).strip()
        model = resolve_model("seedream", alias)

    return {
        "provider": "seedream",
        "provider_name": provider_spec["name"],
        "base_url": base_url,
        "model": model,
        "api_key": require_text(saved.get("api_key"), "火山引擎 API Key"),
    }


def normalize_size(raw_size, provider_spec: dict = None) -> str:
    default_size = provider_spec["default_size"] if provider_spec else "2k"
    normalized = str(raw_size or default_size).strip()
    return SIZE_ALIASES.get(normalized.lower(), normalized)


def build_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": "Xiaohongshu-Content-Employee/2.0.1",
    }


def build_generation_body(
    model: str,
    prompt: str,
    size: str,
    reference_images: list[str] | None = None,
) -> dict:
    body = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": "url",
        "watermark": False,
    }
    if reference_images:
        body["image"] = reference_images
    return body


def build_request(
    config: dict,
    prompt: str,
    size: str,
    quality: str,
    reference_images: list[str] | None = None,
) -> dict:
    normalized_size = normalize_size(size)
    return {
        "url": generation_url(config["base_url"]),
        "headers": build_headers(config["api_key"]),
        "body": build_generation_body(
            config["model"],
            prompt,
            normalized_size,
            reference_images,
        ),
    }


def generation_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/images/generations"


def extract_image_source(response_json: dict) -> Tuple[str, str]:
    data = response_json.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise RuntimeError(
            "火山引擎返回结构异常："
            f"{json.dumps(response_json, ensure_ascii=False)}"
        )

    first = data[0]
    image_url = str(first.get("url") or "").strip()
    if image_url:
        if not image_url.startswith(("https://", "http://")):
            raise RuntimeError("火山引擎返回的图片 URL 协议无效。")
        return "url", image_url

    encoded = str(first.get("b64_json") or "").strip()
    if encoded:
        return "base64", encoded

    raise RuntimeError(
        "火山引擎响应未包含 data[0].url 或 data[0].b64_json："
        f"{json.dumps(response_json, ensure_ascii=False)}"
    )
