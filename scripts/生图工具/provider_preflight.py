#!/usr/bin/env python3
"""本地检查图片渠道配置，不发送任何网络请求。"""

import argparse
import json
import sys
from pathlib import Path

from provider_registry import (
    FORMAL_PROVIDER_IDS,
    get_provider,
    list_provider_choices,
    normalize_provider_id,
)
from providers import get_adapter


def read_config(skill_root: Path) -> dict:
    path = skill_root / "config.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取 config.json：{exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("config.json 必须是 JSON 对象。")
    return value


def is_configured(raw_config: dict, provider_id: str) -> bool:
    if normalize_provider_id(provider_id) == "thinkai-image-2":
        return bool(str(raw_config.get("api_key") or "").strip())
    providers = raw_config.get("providers")
    return (
        isinstance(providers, dict)
        and isinstance(providers.get(provider_id), dict)
        and bool(str(providers[provider_id].get("api_key") or "").strip())
    )


def load_provider_config(raw_config: dict, provider_id: str) -> tuple[dict, object, dict]:
    normalized = normalize_provider_id(provider_id)
    if normalized in FORMAL_PROVIDER_IDS:
        spec = get_provider(normalized)
        adapter = get_adapter(normalized)
        return adapter.load_config(raw_config, spec), adapter, spec

    providers = raw_config.get("providers")
    if isinstance(providers, dict) and normalized in providers:
        adapter = get_adapter("custom")
        return adapter.load_config(raw_config, normalized), adapter, {}
    raise RuntimeError(f"未配置或不支持的图片渠道：{provider_id}")


def verify_local(skill_root: Path, provider_id: str) -> dict:
    raw_config = read_config(skill_root)
    config, adapter, spec = load_provider_config(raw_config, provider_id)
    raw_size = spec.get("default_size") if spec else None
    size = adapter.normalize_size(raw_size, spec)
    quality = (
        "high"
        if config["provider"] == "openai-gpt-image"
        else (
            ""
            if config["provider"] in {
                "thinkai-nano",
                "seedream",
                "google-nano-banana",
            }
            else "hd"
        )
    )
    request = adapter.build_request(config, "本地配置检查", size, quality)

    return {
        "status": "verified-local",
        "network_request_sent": False,
        "provider": config["provider"],
        "provider_name": config.get(
            "provider_name",
            config.get("display_name", config["provider"]),
        ),
        "model": config["model"],
        "default_size": size,
        "endpoint": request["url"],
        "api_key": "<configured>",
    }


def list_status(skill_root: Path) -> dict:
    raw_config = read_config(skill_root)
    choices = []
    for item in list_provider_choices():
        provider_id = item["id"]
        if provider_id == "custom":
            providers = raw_config.get("providers")
            configured = sorted(
                key
                for key in providers
                if key == "custom" or key.startswith("custom-")
            ) if isinstance(providers, dict) else []
            choices.append({**item, "configured_ids": configured})
        else:
            choices.append(
                {
                    **item,
                    "status": (
                        "configured"
                        if is_configured(raw_config, provider_id)
                        else "not-configured"
                    ),
                }
            )
    return {
        "default_provider": "thinkai-image-2",
        "network_request_sent": False,
        "choices": choices,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="本地检查图片渠道配置；不会发送网络请求或生成图片。"
    )
    parser.add_argument("--provider", help="要验证的渠道 ID")
    parser.add_argument("--list", action="store_true", help="列出全部渠道配置状态")
    args = parser.parse_args()
    plugin_root = Path(__file__).resolve().parents[2]

    try:
        result = (
            verify_local(plugin_root, args.provider)
            if args.provider and not args.list
            else list_status(plugin_root)
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
