#!/usr/bin/env python3
"""把最终 Prompt 原样发送给已选择的图片模型并保存返回图片。"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import math
import sys
from pathlib import Path
from typing import Callable, Optional
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
    provider_supports_reference_images,
)
from providers import get_adapter  # noqa: E402


CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 85
DOWNLOAD_TIMEOUT_SECONDS = 20
DEFAULT_QUALITY = {
    "thinkai-gpt-image-2-4k": "hd",
    "openai-gpt-image": "high",
}


class GenerationError(RuntimeError):
    """图片请求、下载或保存失败。"""


class GenerationUncertainError(GenerationError):
    """付费请求已开始，但无法确认渠道是否已经完成计费或生成。"""


class DownloadPendingError(GenerationError):
    """渠道已返回图片 URL，但图片尚未下载到本地。"""

    def __init__(
        self,
        source_url: str,
        provider: str,
        model: str,
        requested_size: str,
    ):
        super().__init__("图片已生成，但下载尚未完成。")
        self.source_url = source_url
        self.provider = provider
        self.model = model
        self.requested_size = requested_size


LifecycleCallback = Optional[Callable[[dict], None]]


def emit_lifecycle(callback: LifecycleCallback, **event) -> None:
    if callback is not None:
        callback(dict(event))


def _nonnegative_number(value: object) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        return None
    return normalized


def extract_usage_metrics(payload: dict) -> dict:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        usage = {}

    token_count = None
    for key in ("total_tokens", "total_token_count", "totalTokens"):
        candidate = usage.get(key)
        if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate >= 0:
            token_count = candidate
            break
    if token_count is None:
        token_parts = []
        for keys in (
            ("input_tokens", "input_token_count", "prompt_tokens"),
            ("output_tokens", "output_token_count", "completion_tokens"),
        ):
            value = next(
                (
                    usage.get(key)
                    for key in keys
                    if isinstance(usage.get(key), int)
                    and not isinstance(usage.get(key), bool)
                    and usage.get(key) >= 0
                ),
                None,
            )
            if value is not None:
                token_parts.append(value)
        if token_parts:
            token_count = sum(token_parts)

    raw_cost = usage.get("cost")
    if raw_cost is None:
        raw_cost = payload.get("cost")
    cost_currency = None
    if isinstance(raw_cost, dict):
        cost_amount = _nonnegative_number(
            raw_cost.get("amount", raw_cost.get("value"))
        )
        cost_currency = str(
            raw_cost.get("currency")
            or usage.get("currency")
            or payload.get("currency")
            or ""
        ).strip().upper()
    else:
        cost_amount = _nonnegative_number(
            raw_cost
            if raw_cost is not None
            else usage.get("total_cost", payload.get("total_cost"))
        )
        cost_currency = str(
            usage.get("currency") or payload.get("currency") or ""
        ).strip().upper()
    if cost_amount is None or not cost_currency:
        cost_amount = None
        cost_currency = None

    return {
        "token_count": token_count,
        "token_status": "reported" if token_count is not None else "unavailable",
        "cost_amount": cost_amount,
        "cost_currency": cost_currency,
        "cost_status": "reported" if cost_amount is not None else "unavailable",
    }


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
    requested_size: Optional[str] = None,
) -> str:
    if requested_size:
        if provider_id != "thinkai-gpt-image-2-4k":
            raise GenerationError(
                "--size 目前仅支持 thinkai-gpt-image-2-4k。"
            )
        return adapter.normalize_size(requested_size, provider_spec)
    if provider_spec is not None:
        return adapter.normalize_size(None, provider_spec)
    return adapter.normalize_size(config.get("default_size") or "1024x1536", None)


def encode_reference_images(
    reference_image_paths: Optional[list[Path]],
) -> list[str] | None:
    if not reference_image_paths:
        return None
    encoded_images = []
    for reference_image_path in reference_image_paths:
        path = Path(reference_image_path).expanduser().resolve()
        if not path.is_file():
            raise GenerationError(f"产品参考图不存在：{path}")
        mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(path.suffix.lower())
        if mime is None:
            raise GenerationError(
                f"产品参考图只支持 JPEG、PNG 或 WebP：{path.name}"
            )
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        encoded_images.append(f"data:{mime};base64,{encoded}")
    return encoded_images


def load_reference_image_files(
    reference_image_paths: Optional[list[Path]],
) -> list[tuple[str, bytes, str]] | None:
    if not reference_image_paths:
        return None
    files = []
    for reference_image_path in reference_image_paths:
        path = Path(reference_image_path).expanduser().resolve()
        if not path.is_file():
            raise GenerationError(f"产品参考图不存在：{path}")
        mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(path.suffix.lower())
        if mime is None:
            raise GenerationError(
                f"产品参考图只支持 JPEG、PNG 或 WebP：{path.name}"
            )
        files.append((path.name, path.read_bytes(), mime))
    return files


def build_request(
    provider_id: str,
    adapter: object,
    config: dict,
    prompt: str,
    size: str,
    reference_image_paths: Optional[list[Path]],
) -> dict:
    quality = DEFAULT_QUALITY.get(provider_id, "")
    if provider_id == "seedream":
        return adapter.build_request(
            config,
            prompt,
            size,
            quality,
            encode_reference_images(reference_image_paths),
        )
    if provider_id == "thinkai-gpt-image-2-4k":
        return adapter.build_request(
            config,
            prompt,
            size,
            quality,
            load_reference_image_files(reference_image_paths),
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
        request_kwargs = {
            "headers": request["headers"],
            "timeout": (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        }
        if "files" in request:
            request_kwargs["data"] = request["data"]
            request_kwargs["files"] = request["files"]
        else:
            request_kwargs["json"] = request["body"]
        response = requests.post(
            request["url"],
            **request_kwargs,
        )
        response.raise_for_status()
    except (requests.Timeout, requests.ConnectionError) as exc:
        detail = redact_secrets(str(exc), request)
        raise GenerationUncertainError(
            f"{provider_name} 请求结果不确定：{detail}"
        ) from exc
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


def recover_download(source_url: str, destination: Path) -> Path:
    normalized_url = require_prompt(source_url)
    target = Path(destination).expanduser().resolve()
    image_bytes, extension = image_bytes_from_source("url", normalized_url)
    if not target.suffix:
        target = target.with_suffix(extension)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(image_bytes)
    return target


def generate_image(
    plugin_root: Path,
    prompt: str,
    output_dir: Path,
    provider: Optional[str] = None,
    reference_image_paths: Optional[list[Path]] = None,
    lifecycle_callback: LifecycleCallback = None,
    size: Optional[str] = None,
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
    if reference_image_paths and not provider_supports_reference_images(provider_id):
        raise GenerationError(
            f"{provider_id} 不支持产品参考图，请改用支持参考图的生图渠道。"
        )
    requested_size = resolve_request_size(
        provider_id,
        adapter,
        config,
        provider_spec,
        size,
    )
    request = build_request(
        provider_id,
        adapter,
        config,
        final_prompt,
        requested_size,
        reference_image_paths,
    )
    provider_name = str(
        config.get("provider_name")
        or config.get("display_name")
        or provider_id
    )
    lifecycle_base = {
        "provider": provider_id,
        "model": config["model"],
        "requested_size": requested_size,
    }
    emit_lifecycle(
        lifecycle_callback,
        request_status="request_started",
        **lifecycle_base,
    )
    try:
        payload = request_generation(provider_name, request)
    except GenerationUncertainError:
        emit_lifecycle(
            lifecycle_callback,
            request_status="uncertain",
            **lifecycle_base,
        )
        raise
    except GenerationError as exc:
        emit_lifecycle(
            lifecycle_callback,
            request_status="failed",
            error=str(exc),
            **lifecycle_base,
        )
        raise
    usage_metrics = extract_usage_metrics(payload)
    emit_lifecycle(
        lifecycle_callback,
        request_status="response_received",
        **usage_metrics,
        **lifecycle_base,
    )
    source_type, source_value = extract_image_source(
        provider_id,
        adapter,
        config,
        payload,
    )
    try:
        image_bytes, extension = image_bytes_from_source(source_type, source_value)
    except GenerationError as exc:
        if source_type == "url" or source_value.startswith(("http://", "https://")):
            pending = DownloadPendingError(
                source_value,
                provider_id,
                config["model"],
                requested_size,
            )
            emit_lifecycle(
                lifecycle_callback,
                request_status="download_pending",
                source_url=source_value,
                error=str(exc),
                **lifecycle_base,
            )
            raise pending from exc
        emit_lifecycle(
            lifecycle_callback,
            request_status="failed",
            error=str(exc),
            **lifecycle_base,
        )
        raise
    image_path = target_dir / f"image{extension}"
    image_path.write_bytes(image_bytes)
    return {
        "provider": provider_id,
        "model": config["model"],
        "requested_size": requested_size,
        "image_path": str(image_path),
        "request_status": "complete",
        **usage_metrics,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把最终 Prompt 原样发送给已选择的图片模型。"
    )
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--provider", help="临时覆盖 config.json 中的默认渠道")
    parser.add_argument(
        "--size",
        help="ThinkAI 4K 尺寸，例如 16:9@1k 或 4:3@2k",
    )
    parser.add_argument(
        "--reference-image",
        type=Path,
        action="append",
        dest="reference_images",
        help="产品参考图，可重复传入多张",
    )
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
            size=args.size,
            reference_image_paths=args.reference_images,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
