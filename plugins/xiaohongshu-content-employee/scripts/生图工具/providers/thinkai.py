"""ThinkAI OpenAI Image 兼容渠道适配器。"""

import json
import re
from typing import List, Optional, Tuple

from providers.base import require_text


SIZE_ALIASES = {
    "1k": "1920x1088",
    "2k": "2560x1440",
}

RATIO_SIZE_PATTERN = re.compile(r"([1-9]\d*):([1-9]\d*)@(1k|2k)", re.IGNORECASE)
RATIO_LONG_SIDE = {
    "1k": 1920,
    "2k": 2560,
}


def load_config(raw_config: dict, provider_spec: dict) -> dict:
    provider_id = require_text(provider_spec.get("id"), "ThinkAI 渠道 ID")
    provider_name = require_text(provider_spec.get("name"), "ThinkAI 渠道名称")
    expected_base_url = require_text(
        provider_spec.get("base_url"),
        f"{provider_name} API 地址",
    ).rstrip("/")
    expected_model = require_text(
        provider_spec.get("models", {}).get(provider_spec.get("recommended_model")),
        f"{provider_name} 模型",
    )
    providers = raw_config.get("providers")
    saved = providers.get(provider_id) if isinstance(providers, dict) else None
    if not isinstance(saved, dict):
        raise RuntimeError(f"未配置 {provider_name}。请先运行图片渠道配置向导。")

    api_key = require_text(saved.get("api_key"), f"{provider_name} API Key")
    base_url = str(saved.get("base_url") or expected_base_url).strip().rstrip("/")
    if base_url != expected_base_url:
        raise RuntimeError(f"{provider_name} 地址与固定契约不一致，请重新配置。")
    model_alias = str(
        saved.get("model_alias") or provider_spec.get("recommended_model")
    ).strip()
    model = str(saved.get("model") or "").strip()
    if model:
        if model != expected_model:
            raise RuntimeError(f"{provider_name} 模型与固定契约不一致，请重新配置。")
    elif model_alias != provider_spec.get("recommended_model"):
        raise RuntimeError(f"{provider_name} 模型档位与固定契约不一致，请重新配置。")
    else:
        model = expected_model
    return {
        "provider": provider_id,
        "provider_name": provider_name,
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
    }


def normalize_size(raw_size, provider_spec: dict) -> str:
    value = str(raw_size or provider_spec["default_size"]).strip()
    normalized_value = value.lower()
    alias = SIZE_ALIASES.get(normalized_value)
    if alias:
        return alias

    match = RATIO_SIZE_PATTERN.fullmatch(value)
    if not match:
        return value
    ratio_width, ratio_height, resolution = match.groups()
    ratio_width = int(ratio_width)
    ratio_height = int(ratio_height)
    long_side = max(ratio_width, ratio_height)
    target_long_side = RATIO_LONG_SIDE[resolution.lower()]

    def scaled_dimension(value: int) -> int:
        quotient, remainder = divmod(target_long_side * value, long_side)
        return quotient + (1 if remainder * 2 >= long_side else 0)

    return f"{scaled_dimension(ratio_width)}x{scaled_dimension(ratio_height)}"


def build_request(
    config: dict,
    prompt: str,
    size: str,
    quality: str,
    reference_images: Optional[List[Tuple[str, bytes, str]]] = None,
) -> dict:
    if reference_images:
        return {
            "url": f"{config['base_url']}/images/edits",
            "headers": {
                "Authorization": f"Bearer {config['api_key']}",
                "Accept": "*/*",
                "User-Agent": "Xiaohongshu-Content-Employee/2.1.0",
            },
            "data": {
                "model": config["model"],
                "prompt": prompt,
                "n": "1",
                "size": size,
                "quality": quality,
                "response_format": "url",
            },
            "files": [
                ("image[]", (filename, image_bytes, mime))
                for filename, image_bytes, mime in reference_images
            ],
        }
    return {
        "url": f"{config['base_url']}/images/generations",
        "headers": {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "Accept": "*/*",
            "User-Agent": "Xiaohongshu-Content-Employee/2.1.0",
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
            "ThinkAI GPT Image 2 4K 返回结构异常："
            f"{json.dumps(response_json, ensure_ascii=False)}"
        )
    image_url = str(data[0].get("url") or "").strip()
    if not image_url:
        raise RuntimeError("ThinkAI GPT Image 2 4K 响应未包含 data[0].url。")
    if not image_url.startswith(("https://", "http://", "data:image/")):
        raise RuntimeError("ThinkAI GPT Image 2 4K 返回的图片 URL 协议无效。")
    return "url", image_url
