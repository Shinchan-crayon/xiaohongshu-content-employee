"""ThinkAI Image 2 适配器，保持旧版配置与请求契约。"""

import json

from providers.base import require_text


SIZE_ALIASES = {
    "1k": "1920x1088",
    "2k": "2560x1440",
}


def load_config(raw_config: dict, provider_spec: dict) -> dict:
    api_key = require_text(raw_config.get("api_key"), "ThinkAI Image 2 API Key")
    base_url = require_text(
        raw_config.get("base_url"),
        "ThinkAI Image 2 API 地址",
    ).rstrip("/")
    model = require_text(raw_config.get("model"), "ThinkAI Image 2 模型")
    if base_url != provider_spec["base_url"]:
        raise RuntimeError("ThinkAI Image 2 地址与固定契约不一致，请重新配置。")
    expected_model = provider_spec["models"][provider_spec["recommended_model"]]
    if model != expected_model:
        raise RuntimeError("ThinkAI Image 2 模型与固定契约不一致，请重新配置。")
    return {
        "provider": "thinkai-image-2",
        "provider_name": provider_spec["name"],
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
    }


def normalize_size(raw_size, provider_spec: dict) -> str:
    value = str(raw_size or provider_spec["default_size"]).strip()
    return SIZE_ALIASES.get(value.lower(), value)


def build_request(config: dict, prompt: str, size: str, quality: str) -> dict:
    return {
        "url": f"{config['base_url']}/images/generations",
        "headers": {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "User-Agent": "curl/8.7.1",
        },
        "body": {
            "model": config["model"],
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": quality,
            "response_format": "url",
        },
    }


def extract_image_source(response_json: dict):
    data = response_json.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise RuntimeError(
            "ThinkAI Image 2 返回结构异常："
            f"{json.dumps(response_json, ensure_ascii=False)}"
        )
    image_url = str(data[0].get("url") or "").strip()
    if not image_url:
        raise RuntimeError("ThinkAI Image 2 响应未包含 data[0].url。")
    if not image_url.startswith(("https://", "http://", "data:image/")):
        raise RuntimeError("ThinkAI Image 2 返回的图片 URL 协议无效。")
    return "url", image_url
