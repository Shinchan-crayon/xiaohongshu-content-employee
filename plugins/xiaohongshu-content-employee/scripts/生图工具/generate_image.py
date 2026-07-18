#!/usr/bin/env python3
"""把最终 Prompt 原样发送给已选择的图片模型并保存返回图片。"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

try:
    import requests
except ModuleNotFoundError:
    print(
        "缺少 Python 依赖 requests。请在插件根目录运行："
        "python3 -m pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(2)


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from provider_registry import (  # noqa: E402
    FORMAL_PROVIDER_IDS,
    get_provider,
    normalize_provider_id,
)
from providers import get_adapter  # noqa: E402


CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 85
DOWNLOAD_TIMEOUT_SECONDS = 20
DEFAULT_QUALITY = {
    "thinkai-image-2": "hd",
    "openai-gpt-image": "high",
}


class GenerationError(RuntimeError):
    """图片请求、下载或保存失败。"""


def require_prompt(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise GenerationError("Prompt 不能为空。")
    return normalized


def load_raw_config(plugin_root: Path) -> dict:
    config_path = plugin_root / "config.json"
    if not config_path.is_file():
        raise GenerationError(
            "尚未选择生图模型。首次使用请先运行 "
            "python3 scripts/生图工具/configure_provider.py --list。"
        )
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GenerationError(f"无法读取 config.json：{exc}") from exc
    if not isinstance(raw_config, dict):
        raise GenerationError("config.json 必须是 JSON 对象。")
    return raw_config


def resolve_selected_provider(
    raw_config: dict,
    requested_provider: Optional[str] = None,
) -> str:
    selected = normalize_provider_id(
        requested_provider or raw_config.get("default_provider")
    )
    if not selected:
        raise GenerationError(
            "尚未选择默认生图模型。首次使用请先列出模型并完成一次选择。"
        )
    if selected in FORMAL_PROVIDER_IDS:
        return selected
    providers = raw_config.get("providers")
    if (
        isinstance(providers, dict)
        and selected in providers
        and (selected == "custom" or selected.startswith("custom-"))
    ):
        return selected
    raise GenerationError(f"默认生图渠道未配置或不受支持：{selected}")


def load_provider(
    plugin_root: Path,
    requested_provider: Optional[str] = None,
) -> tuple[str, object, dict, Optional[dict]]:
    raw_config = load_raw_config(plugin_root)
    provider_id = resolve_selected_provider(raw_config, requested_provider)
    if provider_id in FORMAL_PROVIDER_IDS:
        provider_spec = get_provider(provider_id)
        adapter = get_adapter(provider_id)
        config = adapter.load_config(raw_config, provider_spec)
        return provider_id, adapter, config, provider_spec

    adapter = get_adapter("custom")
    config = adapter.load_config(raw_config, provider_id)
    return provider_id, adapter, config, None


def resolve_request_size(
    provider_id: str,
    adapter: object,
    config: dict,
    provider_spec: Optional[dict],
) -> str:
    if provider_spec is not None:
        return adapter.normalize_size(None, provider_spec)
    return adapter.normalize_size(config.get("default_size") or "1024x1536", None)


def encode_reference_image(reference_image_path: Optional[Path]) -> list[str] | None:
    if reference_image_path is None:
        return None
    path = Path(reference_image_path).expanduser().resolve()
    if not path.is_file():
        raise GenerationError("产品参考图不存在。")
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    if mime is None:
        raise GenerationError("产品参考图只支持 JPEG、PNG 或 WebP。")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return [f"data:{mime};base64,{encoded}"]


def build_request(
    provider_id: str,
    adapter: object,
    config: dict,
    prompt: str,
    size: str,
    reference_image_path: Optional[Path],
) -> dict:
    quality = DEFAULT_QUALITY.get(provider_id, "")
    if provider_id == "seedream":
        return adapter.build_request(
            config,
            prompt,
            size,
            quality,
            encode_reference_image(reference_image_path),
        )
    return adapter.build_request(config, prompt, size, quality)


def redact_secrets(detail: object, request: dict) -> str:
    sanitized = str(detail)
    headers = request.get("headers")
    if not isinstance(headers, dict):
        return sanitized
    for name, value in headers.items():
        if str(name).lower() not in {
            "authorization",
            "x-api-key",
            "api-key",
            "x-goog-api-key",
        }:
            continue
        secret = str(value or "").strip()
        if not secret:
            continue
        sanitized = sanitized.replace(secret, "<redacted>")
        if secret.lower().startswith("bearer "):
            sanitized = sanitized.replace(secret[7:].strip(), "<redacted>")
    return sanitized


def request_generation(provider_name: str, request: dict) -> dict:
    try:
        response = requests.post(
            request["url"],
            json=request["body"],
            headers=request["headers"],
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        status = exc.response.status_code if exc.response is not None else None
        detail = exc.response.text if exc.response is not None else str(exc)
        detail = redact_secrets(detail, request)
        raise GenerationError(
            f"{provider_name} 请求失败"
            + (f"，HTTP {status}" if status is not None else "")
            + f"：{detail}"
        ) from exc

    try:
        payload = response.json()
    except requests.JSONDecodeError as exc:
        raise GenerationError(f"{provider_name} 返回内容无法解析。") from exc
    if not isinstance(payload, dict):
        raise GenerationError(f"{provider_name} 返回内容不是 JSON 对象。")
    return payload


def extract_image_source(
    provider_id: str,
    adapter: object,
    config: dict,
    payload: dict,
) -> tuple[str, str]:
    if provider_id in FORMAL_PROVIDER_IDS:
        return adapter.extract_image_source(payload)
    return adapter.extract_image_source(payload, config)


def decode_data_url(value: str) -> bytes:
    header, separator, encoded = value.partition(",")
    if not separator or not header.startswith("data:image/") or ";base64" not in header:
        raise GenerationError("图片 Data URL 格式无效。")
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise GenerationError("图片 Data URL 数据无效。") from exc


def extension_from_bytes(image_bytes: bytes, fallback: str = ".png") -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_bytes.startswith(b"\xff\xd8"):
        return ".jpg"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return ".webp"
    return fallback


def extension_from_url(image_url: str) -> str:
    suffix = Path(urlsplit(image_url).path).suffix.lower()
    return suffix if suffix in {".png", ".jpg", ".jpeg", ".webp"} else ".png"


def image_bytes_from_source(source_type: str, source_value: str) -> tuple[bytes, str]:
    if source_type == "base64":
        try:
            image_bytes = base64.b64decode(source_value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise GenerationError("图片渠道返回的 Base64 数据无效。") from exc
        return image_bytes, extension_from_bytes(image_bytes)
    if source_value.startswith("data:image/"):
        image_bytes = decode_data_url(source_value)
        return image_bytes, extension_from_bytes(image_bytes)

    try:
        response = requests.get(
            source_value,
            headers={"Accept": "*/*"},
            timeout=(CONNECT_TIMEOUT_SECONDS, DOWNLOAD_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GenerationError(f"图片下载失败：{exc}") from exc
    fallback = extension_from_url(source_value)
    return response.content, extension_from_bytes(response.content, fallback)


def dimensions_from_size(size: str) -> tuple[Optional[int], Optional[int]]:
    match = re.fullmatch(r"(\d+)x(\d+)", str(size or "").strip().lower())
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def generate_image(
    plugin_root: Path,
    prompt: str,
    output_dir: Path,
    provider: Optional[str] = None,
    reference_image_path: Optional[Path] = None,
) -> dict:
    plugin_root = Path(plugin_root).resolve()
    target_dir = Path(output_dir).expanduser().resolve()
    if target_dir == plugin_root or plugin_root in target_dir.parents:
        raise GenerationError("图片输出目录不能位于插件成品目录内。")
    target_dir.mkdir(parents=True, exist_ok=True)

    final_prompt = require_prompt(prompt)
    provider_id, adapter, config, provider_spec = load_provider(
        plugin_root,
        provider,
    )
    size = resolve_request_size(provider_id, adapter, config, provider_spec)
    request = build_request(
        provider_id,
        adapter,
        config,
        final_prompt,
        size,
        reference_image_path,
    )
    provider_name = str(
        config.get("provider_name")
        or config.get("display_name")
        or provider_id
    )
    payload = request_generation(provider_name, request)
    source_type, source_value = extract_image_source(
        provider_id,
        adapter,
        config,
        payload,
    )
    image_bytes, extension = image_bytes_from_source(source_type, source_value)
    image_path = target_dir / f"image{extension}"
    image_path.write_bytes(image_bytes)
    width, height = dimensions_from_size(size)
    return {
        "provider": provider_id,
        "model": config["model"],
        "requested_size": size,
        "width": width,
        "height": height,
        "image_path": str(image_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把最终 Prompt 原样发送给已选择的图片模型。"
    )
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--provider", help="临时覆盖 config.json 中的默认渠道")
    parser.add_argument("--reference-image", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plugin_root = Path(__file__).resolve().parents[2]
    try:
        result = generate_image(
            plugin_root=plugin_root,
            prompt=args.prompt,
            output_dir=args.output_dir,
            provider=args.provider,
            reference_image_path=args.reference_image,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
