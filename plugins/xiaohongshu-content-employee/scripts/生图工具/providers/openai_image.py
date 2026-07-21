"""OpenAI Image API 渠道适配器。"""

import base64
import binascii
from typing import Tuple

from providers.base import require_text


DEFAULT_SIZE_ALIASES = {
    "1k": "1024x1024",
    "square": "1024x1024",
    "landscape": "1536x1024",
    "portrait": "1024x1536",
}
SUPPORTED_SIZES = {"1024x1024", "1536x1024", "1024x1536", "auto"}
SUPPORTED_QUALITIES = {"low", "medium", "high", "auto"}


def _provider_id(provider_spec: dict) -> str:
    return str(provider_spec.get("id") or "openai-gpt-image").strip()


def _model_id(provider_spec: dict, model_alias: str) -> str:
    models = provider_spec.get("models")
    if not isinstance(models, dict):
        raise RuntimeError("OpenAI 渠道注册信息缺少模型配置。")

    model = models.get(model_alias)
    if isinstance(model, dict):
        model = model.get("id")
    if not isinstance(model, str) or not model.strip():
        raise RuntimeError(f"OpenAI 不支持模型档位：{model_alias}。")
    return model.strip()


def load_config(raw_config: dict, provider_spec: dict) -> dict:
    """从用户配置读取密钥，并从注册表解析固定地址与模型。"""
    provider_id = _provider_id(provider_spec)
    providers = raw_config.get("providers")
    provider_config = providers.get(provider_id) if isinstance(providers, dict) else None
    if not isinstance(provider_config, dict):
        raise RuntimeError("未配置 OpenAI。请先运行图片渠道配置向导。")

    base_url = require_text(provider_spec.get("base_url"), "OpenAI API 地址").rstrip("/")
    if not base_url.startswith("https://"):
        raise RuntimeError("OpenAI 渠道注册的 API 地址无效。")

    default_alias = require_text(
        provider_spec.get("recommended_model")
        or provider_spec.get("recommended_model_alias")
        or "recommended",
        "OpenAI 推荐模型档位",
    )
    model_alias = require_text(
        provider_config.get("model_alias", default_alias),
        "OpenAI 模型档位",
    )

    return {
        "provider": provider_id,
        "base_url": base_url,
        "model": _model_id(provider_spec, model_alias),
        "model_alias": model_alias,
        "api_key": require_text(provider_config.get("api_key"), "OpenAI API Key"),
    }


def normalize_size(raw_size: str, provider_spec: dict) -> str:
    """将用户尺寸别名转换为 OpenAI Image API 支持的尺寸。"""
    default_size = provider_spec.get("default_size") if provider_spec else None
    normalized = require_text(
        raw_size or default_size or "1024x1024",
        "OpenAI 图片尺寸",
    ).lower()
    aliases = provider_spec.get("size_aliases")
    if not isinstance(aliases, dict):
        aliases = DEFAULT_SIZE_ALIASES
    size = str(aliases.get(normalized, normalized)).strip().lower()
    if size not in SUPPORTED_SIZES:
        raise RuntimeError(f"OpenAI 不支持图片尺寸：{raw_size}。")
    return size


def build_request(
    config: dict,
    prompt: str,
    size: str,
    quality: str,
) -> dict:
    """构造单次 OpenAI Image API 请求，不执行网络调用。"""
    base_url = require_text(config.get("base_url"), "OpenAI API 地址").rstrip("/")
    model = require_text(config.get("model"), "OpenAI 模型")
    api_key = require_text(config.get("api_key"), "OpenAI API Key")
    prompt_text = require_text(prompt, "图片 Prompt")
    normalized_size = normalize_size(size, {})
    normalized_quality = require_text(quality, "OpenAI 图片质量").lower()
    if normalized_quality == "hd":
        normalized_quality = "high"
    if normalized_quality not in SUPPORTED_QUALITIES:
        raise RuntimeError(f"OpenAI 不支持图片质量：{quality}。")

    return {
        "url": f"{base_url}/images/generations",
        "headers": {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Xiaohongshu-Content-Employee/2.1.1",
        },
        "body": {
            "model": model,
            "prompt": prompt_text,
            "n": 1,
            "size": normalized_size,
            "quality": normalized_quality,
        },
    }


def _validated_base64(value: object) -> str:
    encoded = str(value or "").strip()
    if not encoded:
        return ""
    try:
        base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("OpenAI 返回的图片 Base64 数据无效。") from exc
    return encoded


def extract_image_source(response_json: dict) -> Tuple[str, str]:
    """从 OpenAI 响应中提取 Base64 图片或 HTTPS 图片地址。"""
    data = response_json.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise RuntimeError("OpenAI 返回结构异常：缺少 data[0] 图片结果。")

    first = data[0]
    encoded = _validated_base64(first.get("b64_json"))
    if encoded:
        return "base64", encoded

    image_url = str(first.get("url") or "").strip()
    if image_url:
        if not image_url.startswith("https://"):
            raise RuntimeError("OpenAI 返回的图片 URL 协议无效。")
        return "url", image_url

    raise RuntimeError(
        "OpenAI 响应未包含 data[0].b64_json 或 data[0].url。"
    )
