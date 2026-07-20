"""Google Gemini Interactions 图片生成渠道适配器。"""

import base64
import binascii
from typing import Tuple

from providers.base import require_text


SUPPORTED_ASPECT_RATIOS = {
    "1:1",
    "2:3",
    "3:2",
    "3:4",
    "4:3",
    "4:5",
    "5:4",
    "9:16",
    "16:9",
    "21:9",
    "1:8",
    "8:1",
    "1:4",
    "4:1",
}
SUPPORTED_IMAGE_SIZES = {"512", "1K", "2K", "4K"}
DEFAULT_SIZE_ALIASES = {
    "1k": "1:1@1K",
    "2k": "1:1@2K",
    "4k": "1:1@4K",
    "square": "1:1@1K",
    "landscape": "16:9@1K",
    "portrait": "9:16@1K",
}


def _provider_id(provider_spec: dict) -> str:
    return str(provider_spec.get("id") or "google-nano-banana").strip()


def _model_id(provider_spec: dict, model_alias: str) -> str:
    models = provider_spec.get("models")
    if not isinstance(models, dict):
        raise RuntimeError("Google 渠道注册信息缺少模型配置。")

    model = models.get(model_alias)
    if isinstance(model, dict):
        model = model.get("id")
    if not isinstance(model, str) or not model.strip():
        raise RuntimeError(f"Google 不支持模型档位：{model_alias}。")
    return model.strip()


def load_config(raw_config: dict, provider_spec: dict) -> dict:
    """从用户配置读取密钥，并从注册表解析固定地址与模型。"""
    provider_id = _provider_id(provider_spec)
    providers = raw_config.get("providers")
    provider_config = providers.get(provider_id) if isinstance(providers, dict) else None
    if not isinstance(provider_config, dict):
        raise RuntimeError("未配置 Google Nano Banana。请先运行图片渠道配置向导。")

    base_url = require_text(provider_spec.get("base_url"), "Google API 地址").rstrip("/")
    if not base_url.startswith("https://"):
        raise RuntimeError("Google 渠道注册的 API 地址无效。")

    default_alias = require_text(
        provider_spec.get("recommended_model")
        or provider_spec.get("recommended_model_alias")
        or "recommended",
        "Google 推荐模型档位",
    )
    model_alias = require_text(
        provider_config.get("model_alias", default_alias),
        "Google 模型档位",
    )

    return {
        "provider": provider_id,
        "base_url": base_url,
        "model": _model_id(provider_spec, model_alias),
        "model_alias": model_alias,
        "api_key": require_text(provider_config.get("api_key"), "Google API Key"),
    }


def normalize_size(raw_size: str, provider_spec: dict) -> str:
    """将比例和清晰度转换为 Interactions API 图片参数。"""
    default_size = provider_spec.get("default_size") if provider_spec else None
    normalized = require_text(
        raw_size or default_size or "1:1@1K",
        "Google 图片尺寸",
    )
    aliases = provider_spec.get("size_aliases")
    if not isinstance(aliases, dict):
        aliases = DEFAULT_SIZE_ALIASES
    mapped = str(aliases.get(normalized.lower(), normalized)).strip()

    if "@" in mapped:
        aspect_ratio, image_size = mapped.split("@", 1)
    elif ":" in mapped:
        aspect_ratio, image_size = mapped, "1K"
    else:
        aspect_ratio, image_size = "1:1", mapped

    aspect_ratio = aspect_ratio.strip()
    image_size = image_size.strip().upper()
    if image_size == "512":
        image_size = "512"

    if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
        raise RuntimeError(f"Google 不支持图片比例：{aspect_ratio}。")
    if image_size not in SUPPORTED_IMAGE_SIZES:
        raise RuntimeError(f"Google 不支持图片尺寸：{image_size}。")

    return f"{aspect_ratio}@{image_size}"


def parse_size(value: str) -> dict:
    normalized = normalize_size(value, {})
    aspect_ratio, image_size = normalized.split("@", 1)
    return {
        "aspect_ratio": aspect_ratio,
        "image_size": image_size,
    }


def build_request(
    config: dict,
    prompt: str,
    size: str,
    quality: str,
) -> dict:
    """构造单次 Google Interactions API 请求，不执行网络调用。"""
    del quality  # Interactions 图片输出没有与 OpenAI quality 等价的字段。
    base_url = require_text(config.get("base_url"), "Google API 地址").rstrip("/")
    model = require_text(config.get("model"), "Google 模型")
    api_key = require_text(config.get("api_key"), "Google API Key")
    prompt_text = require_text(prompt, "图片 Prompt")
    image_format = parse_size(size)

    return {
        "url": f"{base_url}/interactions",
        "headers": {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Xiaohongshu-Content-Employee/2.0.1",
        },
        "body": {
            "model": model,
            "input": prompt_text,
            "response_format": {
                "type": "image",
                "mime_type": "image/jpeg",
                "aspect_ratio": image_format["aspect_ratio"],
                "image_size": image_format["image_size"],
            },
        },
    }


def _validated_base64(value: object) -> str:
    encoded = str(value or "").strip()
    if not encoded:
        return ""
    try:
        base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("Google 返回的图片 Base64 数据无效。") from exc
    return encoded


def extract_image_source(response_json: dict) -> Tuple[str, str]:
    """只从 model_output 步骤中提取图片内容。"""
    steps = response_json.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RuntimeError("Google 返回结构异常：缺少 steps。")

    for step in steps:
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue
        content = step.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "image":
                continue

            encoded = _validated_base64(item.get("data"))
            if encoded:
                return "base64", encoded

            image_url = str(item.get("uri") or "").strip()
            if image_url:
                if not image_url.startswith("https://"):
                    raise RuntimeError("Google 返回的图片 URI 协议无效。")
                return "url", image_url

            raise RuntimeError("Google 图片结果未包含 data 或 uri。")

    raise RuntimeError("Google 响应未包含 model_output 图片结果。")
