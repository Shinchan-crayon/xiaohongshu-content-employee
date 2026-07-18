"""渠道适配器共享校验。"""

from typing import Any


def require_text(value, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise RuntimeError(f"{label}不能为空。")
    if "\r" in normalized or "\n" in normalized:
        raise RuntimeError(f"{label}格式无效。")
    return normalized


def provider_config(raw_config: dict, provider_id: str) -> dict:
    providers = raw_config.get("providers")
    if not isinstance(providers, dict):
        raise RuntimeError(f"未配置图片渠道：{provider_id}")
    value = providers.get(provider_id)
    if not isinstance(value, dict):
        raise RuntimeError(f"未配置图片渠道：{provider_id}")
    return value


def value_at_path(payload: Any, path: str) -> Any:
    current = payload
    for part in require_text(path, "响应字段路径").split("."):
        if isinstance(current, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise RuntimeError(f"响应字段路径无效：{path}") from exc
            if index < 0 or index >= len(current):
                raise RuntimeError(f"响应字段不存在：{path}")
            current = current[index]
        elif isinstance(current, dict):
            if part not in current:
                raise RuntimeError(f"响应字段不存在：{path}")
            current = current[part]
        else:
            raise RuntimeError(f"响应字段不存在：{path}")
    return current
