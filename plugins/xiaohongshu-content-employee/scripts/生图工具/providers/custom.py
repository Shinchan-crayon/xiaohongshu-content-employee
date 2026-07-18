"""受控自定义图片渠道适配器。

只支持预定义的同步 JSON 协议，不执行配置中的代码，也不接受任意请求头。
"""

import ipaddress
import re
from typing import Any, Dict, Tuple
from urllib.parse import urlsplit, urlunsplit

from providers.base import require_text


SUPPORTED_PROFILES = (
    "openai-image-compatible",
    "generic-sync-json-image",
)
SUPPORTED_RESPONSE_TYPES = ("url", "base64")
SUPPORTED_AUTH_TYPES = ("bearer", "api-key-header")

_HEADER_NAMES = {
    "x-api-key": "X-API-Key",
    "api-key": "api-key",
    "x-goog-api-key": "x-goog-api-key",
}
_PATH_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_PATH_INDEX = re.compile(r"^(0|[1-9][0-9]*)$")
_FORBIDDEN_PATH_PARTS = {"__proto__", "constructor", "prototype"}
_LOCAL_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home",
)


def validate_endpoint(endpoint: str) -> str:
    """校验并返回公网 HTTPS 地址，不执行 DNS 查询。"""

    normalized = require_text(endpoint, "自定义渠道 API 地址")
    try:
        parsed = urlsplit(normalized)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("自定义渠道 API 地址格式无效。") from exc

    if parsed.scheme.lower() != "https":
        raise ValueError("自定义渠道 API 地址必须使用 HTTPS。")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("自定义渠道 API 地址不得包含用户名或密码。")
    if not parsed.hostname:
        raise ValueError("自定义渠道 API 地址缺少主机名。")
    if parsed.fragment:
        raise ValueError("自定义渠道 API 地址不得包含片段。")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("自定义渠道 API 地址端口无效。")

    hostname = parsed.hostname.rstrip(".").lower()
    if (
        hostname == "localhost"
        or hostname.endswith(_LOCAL_HOST_SUFFIXES)
        or "." not in hostname
    ):
        raise ValueError("自定义渠道 API 地址必须使用公网主机。")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("自定义渠道 API 地址不得使用回环、私网或保留 IP。")

    netloc = parsed.netloc
    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


def _normalize_path(path: Any) -> str:
    normalized = require_text(path, "图片响应路径")
    if len(normalized) > 256:
        raise ValueError("图片响应路径过长。")

    parts = normalized.split(".")
    if not parts or len(parts) > 12:
        raise ValueError("图片响应路径层级无效。")
    for part in parts:
        if (
            not part
            or part in _FORBIDDEN_PATH_PARTS
            or not (_PATH_KEY.fullmatch(part) or _PATH_INDEX.fullmatch(part))
        ):
            raise ValueError("图片响应路径只能使用受限点路径。")
    return normalized


def _normalize_header_name(auth_type: str, header_name: Any) -> str:
    if auth_type == "bearer":
        if str(header_name or "").strip():
            raise ValueError("Bearer 鉴权不得自定义 Header。")
        return ""

    normalized = require_text(header_name, "API Key Header").lower()
    try:
        return _HEADER_NAMES[normalized]
    except KeyError as exc:
        raise ValueError(
            "API Key Header 仅支持 X-API-Key、api-key 或 x-goog-api-key。"
        ) from exc


def validate_api_key_header(header_name: str) -> str:
    """只允许预定义的 API Key Header，并返回规范名称。"""

    return _normalize_header_name("api-key-header", header_name)


def validate_response_path(path: str) -> str:
    """公开受限点路径校验，供配置向导复用。"""

    return _normalize_path(path)


def _provider_id(provider: Any) -> str:
    if isinstance(provider, str):
        return require_text(provider, "自定义渠道 ID")
    if isinstance(provider, dict):
        return require_text(
            provider.get("id") or provider.get("provider_id"),
            "自定义渠道 ID",
        )
    raise ValueError("自定义渠道 ID 格式无效。")


def load_config(raw_config: dict, provider: Any) -> dict:
    """读取并规范化一个已保存的自定义渠道配置。"""

    if not isinstance(raw_config, dict):
        raise ValueError("图片渠道配置必须是 JSON 对象。")
    provider_id = _provider_id(provider)
    providers = raw_config.get("providers")
    provider_config = providers.get(provider_id) if isinstance(providers, dict) else None
    if not isinstance(provider_config, dict):
        raise RuntimeError(f"未配置自定义图片渠道：{provider_id}")

    profile = require_text(provider_config.get("profile"), "自定义协议类型")
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"不支持的自定义协议类型：{profile}")

    auth_type = require_text(
        provider_config.get("auth_type", "bearer"),
        "鉴权类型",
    ).lower()
    if auth_type not in SUPPORTED_AUTH_TYPES:
        raise ValueError(f"不支持的自定义鉴权类型：{auth_type}")

    response_type = require_text(
        provider_config.get("response_type"),
        "图片响应类型",
    ).lower()
    if response_type not in SUPPORTED_RESPONSE_TYPES:
        raise ValueError(f"不支持的图片响应类型：{response_type}")

    response_path = _normalize_path(provider_config.get("response_path"))
    if profile == "openai-image-compatible":
        expected_path = (
            "data.0.url" if response_type == "url" else "data.0.b64_json"
        )
        if response_path != expected_path:
            raise ValueError(
                "OpenAI 图片兼容协议仅允许 data.0.url 或 data.0.b64_json。"
            )

    endpoint = validate_endpoint(provider_config.get("endpoint"))
    return {
        "provider": provider_id,
        "provider_name": require_text(
            provider_config.get("display_name", provider_id),
            "自定义渠道名称",
        ),
        "display_name": require_text(
            provider_config.get("display_name", provider_id),
            "自定义渠道名称",
        ),
        "profile": profile,
        "endpoint": endpoint,
        "base_url": endpoint,
        "model": require_text(provider_config.get("model"), "自定义渠道模型"),
        "api_key": require_text(provider_config.get("api_key"), "自定义渠道 API Key"),
        "auth_type": auth_type,
        "api_key_header": _normalize_header_name(
            auth_type,
            provider_config.get("api_key_header"),
        ),
        "response_path": response_path,
        "response_type": response_type,
    }


def normalize_size(raw_size: Any, provider_spec: Any = None) -> str:
    """为受控同步协议保留用户尺寸；未指定时使用兼容默认值。"""

    del provider_spec
    normalized = require_text(raw_size or "1024x1024", "图片尺寸")
    if len(normalized) > 64:
        raise ValueError("图片尺寸参数过长。")
    return normalized


def _build_headers(config: dict) -> Dict[str, str]:
    auth_type = require_text(config.get("auth_type"), "鉴权类型").lower()
    if auth_type not in SUPPORTED_AUTH_TYPES:
        raise ValueError(f"不支持的自定义鉴权类型：{auth_type}")
    header_name = _normalize_header_name(
        auth_type,
        config.get("api_key_header"),
    )
    api_key = require_text(config.get("api_key"), "自定义渠道 API Key")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Xiaohongshu-Content-Employee/2.0.0",
    }
    if auth_type == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers[header_name] = api_key
    return headers


def build_request(
    config: dict,
    prompt: str,
    size: str,
    quality: str,
) -> dict:
    """根据受支持的协议生成同步 JSON 请求描述。"""

    profile = require_text(config.get("profile"), "自定义协议类型")
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"不支持的自定义协议类型：{profile}")
    response_type = require_text(
        config.get("response_type"),
        "图片响应类型",
    ).lower()
    if response_type not in SUPPORTED_RESPONSE_TYPES:
        raise ValueError(f"不支持的图片响应类型：{response_type}")

    body = {
        "model": require_text(config.get("model"), "自定义渠道模型"),
        "prompt": require_text(prompt, "Prompt"),
        "size": require_text(size, "图片尺寸"),
    }
    normalized_quality = str(quality or "").strip()
    if normalized_quality:
        body["quality"] = normalized_quality

    if profile == "openai-image-compatible":
        body.update(
            {
                "n": 1,
                "response_format": (
                    "url" if response_type == "url" else "b64_json"
                ),
            }
        )

    return {
        "url": validate_endpoint(config.get("endpoint")),
        "headers": _build_headers(config),
        "body": body,
    }


def _value_at_path(response_json: Any, path: str) -> Any:
    current = response_json
    for part in _normalize_path(path).split("."):
        if _PATH_INDEX.fullmatch(part):
            if not isinstance(current, list):
                raise RuntimeError(f"图片响应路径在 {part} 处不是数组。")
            index = int(part)
            if index >= len(current):
                raise RuntimeError(f"图片响应路径索引越界：{part}")
            current = current[index]
        else:
            if not isinstance(current, dict) or part not in current:
                raise RuntimeError(f"图片响应缺少字段：{part}")
            current = current[part]
    return current


def extract_image_source(
    response_json: Any,
    config_or_path: Any,
    response_type: str = "",
) -> Tuple[str, str]:
    """按受限点路径提取一个 HTTPS URL 或 Base64 图片数据。"""

    if isinstance(config_or_path, dict):
        path = config_or_path.get("response_path")
        source_type = config_or_path.get("response_type")
    else:
        path = config_or_path
        source_type = response_type

    normalized_type = require_text(source_type, "图片响应类型").lower()
    if normalized_type not in SUPPORTED_RESPONSE_TYPES:
        raise ValueError(f"不支持的图片响应类型：{normalized_type}")

    value = _value_at_path(response_json, _normalize_path(path))
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("图片响应路径未返回有效字符串。")
    normalized_value = value.strip()

    if normalized_type == "url":
        return "url", validate_endpoint(normalized_value)
    return "base64", normalized_value
