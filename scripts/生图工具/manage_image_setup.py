#!/usr/bin/env python3
"""管理首次使用确认过的非敏感图片能力设置。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from configure_provider import atomic_write, read_existing_config
from provider_registry import get_provider, normalize_provider_id, resolve_model


SETUP_VERSION = 1


def empty_image_setup() -> dict:
    return {
        "setup_version": SETUP_VERSION,
        "completed": False,
        "visual_mode": None,
        "default_provider": None,
        "default_model": None,
        "default_size": None,
        "default_quality": None,
        "updated_at": None,
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _config_path(skill_root: Path) -> Path:
    return Path(skill_root).expanduser().resolve() / "config.json"


def _normalize_stored_setup(value: object) -> dict:
    if not isinstance(value, dict) or value.get("completed") is not True:
        return empty_image_setup()
    mode = value.get("visual_mode")
    if mode not in {"existing_only", "ai_assist"}:
        return empty_image_setup()
    result = empty_image_setup()
    result.update(
        {
            "setup_version": SETUP_VERSION,
            "completed": True,
            "visual_mode": mode,
            "default_provider": value.get("default_provider"),
            "default_model": value.get("default_model"),
            "default_size": value.get("default_size"),
            "default_quality": value.get("default_quality"),
            "updated_at": value.get("updated_at"),
        }
    )
    if mode == "existing_only":
        for field in (
            "default_provider",
            "default_model",
            "default_size",
            "default_quality",
        ):
            result[field] = None
    return result


def read_image_setup(skill_root: Path) -> dict:
    config = read_existing_config(_config_path(skill_root))
    return _normalize_stored_setup(config.get("image_setup"))


def _save_image_setup(skill_root: Path, image_setup: dict) -> dict:
    path = _config_path(skill_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    config = read_existing_config(path)
    config["image_setup"] = image_setup
    atomic_write(path, config)
    return dict(image_setup)


def set_existing_only(skill_root: Path) -> dict:
    setup = {
        "setup_version": SETUP_VERSION,
        "completed": True,
        "visual_mode": "existing_only",
        "default_provider": None,
        "default_model": None,
        "default_size": None,
        "default_quality": None,
        "updated_at": _now(),
    }
    return _save_image_setup(skill_root, setup)


def _default_quality(provider_id: str) -> str:
    if provider_id == "openai-gpt-image":
        return "high"
    if provider_id in {"thinkai-nano", "seedream", "google-nano-banana"}:
        return ""
    return "hd"


def set_ai_assist(
    skill_root: Path,
    provider: str,
    model_alias: str = "recommended",
    size: str | None = None,
    quality: str | None = None,
) -> dict:
    provider_id = normalize_provider_id(provider)
    spec = get_provider(provider_id)
    model = resolve_model(provider_id, model_alias)
    normalized_size = str(size or spec["default_size"]).strip()
    if not normalized_size:
        raise ValueError("图片尺寸不能为空。")
    normalized_quality = (
        _default_quality(provider_id)
        if quality is None
        else str(quality).strip()
    )
    setup = {
        "setup_version": SETUP_VERSION,
        "completed": True,
        "visual_mode": "ai_assist",
        "default_provider": provider_id,
        "default_model": model,
        "default_size": normalized_size,
        "default_quality": normalized_quality,
        "updated_at": _now(),
    }
    return _save_image_setup(skill_root, setup)


def reset_image_setup(skill_root: Path) -> dict:
    path = _config_path(skill_root)
    config = read_existing_config(path)
    if "image_setup" in config:
        del config["image_setup"]
        atomic_write(path, config)
    return empty_image_setup()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="管理小红书内容员工的一次性图片能力设置。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="读取当前图片能力设置")
    subparsers.add_parser("set-existing", help="只使用现有素材")
    ai = subparsers.add_parser("set-ai", help="保存 AI 图片渠道和模型")
    ai.add_argument("--provider", required=True, help="图片渠道 ID")
    ai.add_argument("--model-alias", default="recommended", help="模型档位")
    ai.add_argument("--size", help="默认生成尺寸")
    ai.add_argument("--quality", help="默认生成质量")
    subparsers.add_parser("reset", help="重置图片能力设置")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    skill_root = Path(__file__).resolve().parents[2]
    try:
        if args.command == "status":
            result = read_image_setup(skill_root)
        elif args.command == "set-existing":
            result = set_existing_only(skill_root)
        elif args.command == "set-ai":
            result = set_ai_assist(
                skill_root,
                provider=args.provider,
                model_alias=args.model_alias,
                size=args.size,
                quality=args.quality,
            )
        else:
            result = reset_image_setup(skill_root)
    except (OSError, ValueError) as exc:
        print(str(exc))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
