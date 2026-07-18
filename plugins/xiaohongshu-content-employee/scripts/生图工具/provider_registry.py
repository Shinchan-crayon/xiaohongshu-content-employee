#!/usr/bin/env python3
"""读取并校验图片渠道注册表。"""

import json
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = PLUGIN_ROOT / "assets" / "image_providers.json"
FORMAL_PROVIDER_IDS = (
    "thinkai-image-2",
    "thinkai-nano",
    "seedream",
    "openai-gpt-image",
    "google-nano-banana",
)
USER_CHOICE_IDS = (*FORMAL_PROVIDER_IDS, "custom")
LEGACY_PROVIDER_ALIASES = {
    "thinkai": "thinkai-image-2",
    "thinkai-image2": "thinkai-image-2",
    "volcengine": "seedream",
    "openai": "openai-gpt-image",
    "google": "google-nano-banana",
}


def normalize_provider_id(provider_id: str) -> str:
    normalized = str(provider_id or "").strip().lower()
    return LEGACY_PROVIDER_ALIASES.get(normalized, normalized)


def _require_text(value, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label}不能为空。")
    return normalized


def _validate_https_url(value, label: str) -> str:
    url = _require_text(value, label).rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{label}必须是无凭据的 HTTPS 地址。")
    return url


def load_registry(path: Optional[Path] = None) -> dict:
    registry_path = Path(path) if path else DEFAULT_REGISTRY_PATH
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取图片渠道注册表：{exc}") from exc
    if not isinstance(registry, dict):
        raise ValueError("图片渠道注册表必须是 JSON 对象。")

    provider_list = registry.get("providers")
    if not isinstance(provider_list, list):
        raise ValueError("图片渠道注册表 providers 必须是数组。")
    choices = [item.get("id") for item in provider_list if isinstance(item, dict)]
    if choices != list(USER_CHOICE_IDS):
        raise ValueError(
            "图片渠道菜单必须依次为 ThinkAI Image 2、ThinkAI Nano、"
            "火山引擎、OpenAI、Google、其他。"
        )

    providers = {
        item["id"]: item
        for item in provider_list
        if isinstance(item, dict) and item.get("id") in FORMAL_PROVIDER_IDS
    }
    if tuple(providers) != FORMAL_PROVIDER_IDS:
        raise ValueError("正式图片渠道集合不符合当前插件契约。")

    for provider_id, provider in providers.items():
        if not isinstance(provider, dict):
            raise ValueError(f"渠道 {provider_id} 配置必须是 JSON 对象。")
        if provider.get("status") != "supported":
            raise ValueError(f"渠道 {provider_id} 尚未标记为可用。")
        _require_text(provider.get("name"), f"渠道 {provider_id} 名称")
        _require_text(provider.get("adapter"), f"渠道 {provider_id} 适配器")
        _validate_https_url(provider.get("base_url"), f"渠道 {provider_id} API 地址")
        models = provider.get("models")
        if not isinstance(models, dict) or not models:
            raise ValueError(f"渠道 {provider_id} 缺少模型映射。")
        recommended = _require_text(
            provider.get("recommended_model"),
            f"渠道 {provider_id} 推荐模型档位",
        )
        if recommended not in models:
            raise ValueError(f"渠道 {provider_id} 推荐模型档位不存在。")
        for alias, model in models.items():
            _require_text(alias, f"渠道 {provider_id} 模型档位")
            _require_text(model, f"渠道 {provider_id} 模型 ID")
        if "api_key" in provider:
            raise ValueError(f"渠道注册表不得保存 API Key：{provider_id}")
    custom = provider_list[-1]
    if custom.get("id") != "custom" or custom.get("restricted") is not True:
        raise ValueError("其他渠道必须保持受限配置。")
    return {"providers": providers, "custom": custom}


def list_provider_choices(path: Optional[Path] = None) -> list:
    registry = load_registry(path)
    providers = registry["providers"]
    result = [
        {
            "id": provider_id,
            "name": providers[provider_id]["name"],
            "status": providers[provider_id]["status"],
            "models": dict(providers[provider_id]["models"]),
            "recommended_model": providers[provider_id]["models"][
                providers[provider_id]["recommended_model"]
            ],
            "default_size": providers[provider_id]["default_size"],
        }
        for provider_id in FORMAL_PROVIDER_IDS
    ]
    result.append(dict(registry["custom"]))
    return result


def get_provider(provider_id: str, path: Optional[Path] = None) -> dict:
    normalized = normalize_provider_id(provider_id)
    registry = load_registry(path)
    provider = registry["providers"].get(normalized)
    if not isinstance(provider, dict):
        raise ValueError(f"不支持的正式图片渠道：{provider_id}")
    return {"id": normalized, **provider}


def resolve_model(
    provider_id: str,
    model_alias: Optional[str] = None,
    path: Optional[Path] = None,
) -> str:
    provider = get_provider(provider_id, path)
    alias = str(model_alias or provider["recommended_model"]).strip().lower()
    model = provider["models"].get(alias)
    if not model:
        supported = "、".join(provider["models"])
        raise ValueError(
            f"{provider['name']} 不支持的模型档位：{alias}。可选：{supported}"
        )
    return str(model).strip()
