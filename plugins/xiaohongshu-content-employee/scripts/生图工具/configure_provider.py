#!/usr/bin/env python3
"""配置当前 Skill 的图片生成渠道。"""

import argparse
import getpass
import json
import os
import sys
import tempfile
from pathlib import Path

from provider_registry import (
    FORMAL_PROVIDER_IDS,
    get_provider,
    list_provider_choices,
    normalize_provider_id,
    resolve_model,
)


CUSTOM_PROFILES = ("openai-image-compatible", "generic-sync-json-image")
DEFAULT_PROVIDER = "thinkai-image-2"


def read_existing_config(config_path: Path) -> dict:
    if not config_path.is_file():
        return {}
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取现有配置：{exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("现有 config.json 必须是 JSON 对象。")
    return config


def atomic_write(config_path: Path, config: dict) -> None:
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=".config.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            os.chmod(temp_path, 0o600)
            json.dump(config, temp_file, ensure_ascii=False, indent=2)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, config_path)
        os.chmod(config_path, 0o600)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def normalize_api_key(api_key: str, provider_name: str) -> str:
    normalized = str(api_key or "").strip()
    if not normalized:
        raise ValueError(f"{provider_name} API Key 不能为空。")
    if "\r" in normalized or "\n" in normalized:
        raise ValueError(f"{provider_name} API Key 格式无效。")
    return normalized


def save_formal_provider_config(
    skill_root: Path,
    provider: str,
    api_key: str,
    model_alias: str = "recommended",
) -> Path:
    provider_id = normalize_provider_id(provider)
    if provider_id not in FORMAL_PROVIDER_IDS:
        raise ValueError(f"不支持的正式图片渠道：{provider}")
    spec = get_provider(provider_id)
    normalized_key = normalize_api_key(api_key, spec["name"])
    alias = str(model_alias or spec["recommended_model"]).strip().lower()
    resolve_model(provider_id, alias)

    skill_root.mkdir(parents=True, exist_ok=True)
    config_path = skill_root / "config.json"
    config = read_existing_config(config_path)
    if provider_id == "thinkai-image-2":
        config.update(
            {
                "base_url": spec["base_url"],
                "model": resolve_model("thinkai-image-2", alias),
                "api_key": normalized_key,
            }
        )
    else:
        providers = config.get("providers")
        if not isinstance(providers, dict):
            providers = {}
            config["providers"] = providers
        providers[provider_id] = {
            "api_key": normalized_key,
            "model_alias": alias,
        }
    if config.get("default_provider") in {None, "", "thinkai"}:
        config["default_provider"] = DEFAULT_PROVIDER
    atomic_write(config_path, config)
    return config_path


def save_custom_provider_config(
    skill_root: Path,
    provider_id: str,
    display_name: str,
    api_key: str,
    profile: str,
    endpoint: str,
    model: str,
    auth_type: str,
    api_key_header: str,
    response_path: str,
    response_type: str,
) -> Path:
    from providers import custom

    normalized_id = str(provider_id or "").strip().lower()
    if normalized_id != "custom" and not normalized_id.startswith("custom-"):
        raise ValueError("自定义渠道 ID 必须是 custom 或以 custom- 开头。")
    if profile not in CUSTOM_PROFILES:
        raise ValueError(f"不支持的自定义协议：{profile}")
    normalized_endpoint = custom.validate_endpoint(endpoint)
    normalized_key = normalize_api_key(api_key, display_name or normalized_id)
    normalized_auth = str(auth_type or "bearer").strip().lower()
    if normalized_auth not in {"bearer", "api-key-header"}:
        raise ValueError("自定义渠道只支持 Bearer 或 API-Key Header 鉴权。")
    header_name = str(api_key_header or "").strip()
    if normalized_auth == "api-key-header":
        custom.validate_api_key_header(header_name)
    else:
        header_name = ""
    normalized_response_type = str(response_type or "").strip().lower()
    if normalized_response_type not in {"url", "base64"}:
        raise ValueError("自定义渠道响应类型只能是 url 或 base64。")
    normalized_response_path = custom.validate_response_path(response_path)
    normalized_model = str(model or "").strip()
    if not normalized_model:
        raise ValueError("自定义渠道模型 ID 不能为空。")
    if profile == "openai-image-compatible":
        expected_path = (
            "data.0.url"
            if normalized_response_type == "url"
            else "data.0.b64_json"
        )
        if normalized_response_path != expected_path:
            raise ValueError(
                "OpenAI 图片兼容协议的响应路径必须与返回类型匹配。"
            )

    skill_root.mkdir(parents=True, exist_ok=True)
    config_path = skill_root / "config.json"
    config = read_existing_config(config_path)
    providers = config.get("providers")
    if not isinstance(providers, dict):
        providers = {}
        config["providers"] = providers
    providers[normalized_id] = {
        "display_name": str(display_name or normalized_id).strip(),
        "api_key": normalized_key,
        "profile": profile,
        "endpoint": normalized_endpoint,
        "model": normalized_model,
        "auth_type": normalized_auth,
        "api_key_header": header_name,
        "response_path": normalized_response_path,
        "response_type": normalized_response_type,
    }
    if config.get("default_provider") in {None, "", "thinkai"}:
        config["default_provider"] = DEFAULT_PROVIDER
    atomic_write(config_path, config)
    return config_path


def print_choices() -> None:
    for index, item in enumerate(list_provider_choices(), start=1):
        print(f"{index}. {item['name']} ({item['id']})")


def read_api_key(use_stdin: bool, label: str) -> str:
    if use_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    return getpass.getpass(f"{label} API Key: ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="配置小红书内容员工的图片生成渠道。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "provider",
        nargs="?",
        help=(
            "thinkai-image-2、thinkai-nano、seedream、openai-gpt-image、"
            "google-nano-banana 或 custom"
        ),
    )
    parser.add_argument("--list", action="store_true", help="列出支持的图片渠道")
    parser.add_argument("--model-alias", default="recommended", help="模型档位")
    parser.add_argument("--api-key-stdin", action="store_true", help="从标准输入读取 API Key")
    parser.add_argument("--custom-id", default="custom", help="自定义渠道 ID")
    parser.add_argument("--name", default="其他渠道", help="自定义渠道显示名称")
    parser.add_argument("--profile", choices=CUSTOM_PROFILES, help="自定义协议")
    parser.add_argument("--endpoint", help="自定义渠道 HTTPS 图片生成 Endpoint")
    parser.add_argument("--model", help="自定义渠道模型 ID")
    parser.add_argument(
        "--auth-type",
        choices=["bearer", "api-key-header"],
        default="bearer",
        help="自定义渠道鉴权方式",
    )
    parser.add_argument("--api-key-header", default="", help="API-Key Header 名称")
    parser.add_argument("--response-path", default="data.0.url", help="图片字段路径")
    parser.add_argument(
        "--response-type",
        choices=["url", "base64"],
        default="url",
        help="图片字段类型",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.list or not args.provider:
        print_choices()
        return 0

    provider_id = normalize_provider_id(args.provider)
    plugin_root = Path(__file__).resolve().parents[2]
    try:
        if provider_id in FORMAL_PROVIDER_IDS:
            spec = get_provider(provider_id)
            api_key = read_api_key(args.api_key_stdin, spec["name"])
            save_formal_provider_config(
                plugin_root,
                provider_id,
                api_key,
                args.model_alias,
            )
            result = {
                "status": "configured",
                "provider": provider_id,
                "provider_name": spec["name"],
                "model_alias": args.model_alias,
                "model": resolve_model(provider_id, args.model_alias),
                "default_provider": DEFAULT_PROVIDER,
            }
        elif provider_id == "custom":
            if not args.profile or not args.endpoint or not args.model:
                parser.error("custom 必须提供 --profile、--endpoint 和 --model。")
            api_key = read_api_key(args.api_key_stdin, args.name)
            save_custom_provider_config(
                plugin_root,
                provider_id=args.custom_id,
                display_name=args.name,
                api_key=api_key,
                profile=args.profile,
                endpoint=args.endpoint,
                model=args.model,
                auth_type=args.auth_type,
                api_key_header=args.api_key_header,
                response_path=args.response_path,
                response_type=args.response_type,
            )
            result = {
                "status": "configured",
                "provider": args.custom_id,
                "provider_name": args.name,
                "profile": args.profile,
                "default_provider": DEFAULT_PROVIDER,
            }
        else:
            parser.error(f"不支持的图片渠道：{args.provider}")
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
