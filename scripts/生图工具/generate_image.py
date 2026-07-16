#!/usr/bin/env python3
"""在用户明确批准 Prompt 后，通过选定渠道生成并下载图片。"""

import argparse
import base64
import binascii
import hashlib
import hmac
import http.client
import json
import os
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

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

from provider_registry import (
    FORMAL_PROVIDER_IDS,
    get_provider,
    normalize_provider_id,
)
from providers import get_adapter


SIZE_ALIASES = {
    "1k": "1920x1088",
    "2k": "2560x1440",
}
DEFAULT_BASE_URL = "https://www.thinkai.tv/v1"
DEFAULT_MODEL = "gpt-image-2"
CONNECT_TIMEOUT_SECONDS = 30
READ_TIMEOUT_SECONDS = 900
SENSITIVE_HEADER_NAMES = {
    "authorization",
    "x-api-key",
    "api-key",
    "x-goog-api-key",
}


class GenerationError(RuntimeError):
    """图片生成明确失败。"""


class GenerationUncertainError(GenerationError):
    """服务端可能已经生成或计费，本地不能安全判断结果。"""


def load_raw_config(skill_root: Path) -> dict:
    config_path = skill_root / "config.json"
    if not config_path.is_file():
        raise RuntimeError(
            f"未找到 {config_path}。请先运行图片渠道配置工具。"
        )

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取图片渠道配置：{exc}") from exc
    if not isinstance(config, dict):
        raise RuntimeError("config.json 必须是 JSON 对象。")
    return config


def load_config(skill_root: Path, provider: str = "thinkai-image-2") -> dict:
    config = load_raw_config(skill_root)
    normalized_provider = normalize_provider_id(provider)
    if normalized_provider in FORMAL_PROVIDER_IDS:
        spec = get_provider(normalized_provider)
        return get_adapter(normalized_provider).load_config(config, spec)
    providers = config.get("providers")
    if isinstance(providers, dict) and normalized_provider in providers:
        return get_adapter("custom").load_config(config, normalized_provider)
    raise RuntimeError(f"不支持或未配置的图片渠道：{provider}")


def resolve_size(raw_size: str) -> str:
    normalized = raw_size.strip().lower()
    return SIZE_ALIASES.get(normalized, raw_size.strip())


def resolve_provider_size(provider: str, raw_size: Optional[str]) -> str:
    normalized_provider = normalize_provider_id(provider)
    if str(raw_size or "").strip().lower() == "xhs-portrait":
        portrait_sizes = {
            "thinkai-image-2": "1536x2048",
            "thinkai-nano": "3:4@2K",
            "seedream": "1728x2304",
            "google-nano-banana": "3:4@2K",
        }
        if normalized_provider not in portrait_sizes:
            raise ValueError(
                f"{normalized_provider} 不支持 xhs-portrait 3:4 原生尺寸，"
                "请选择支持 3:4 原生输出的渠道或尺寸。"
            )
        return portrait_sizes[normalized_provider]
    if normalized_provider in FORMAL_PROVIDER_IDS:
        spec = get_provider(normalized_provider)
        return get_adapter(normalized_provider).normalize_size(raw_size, spec)
    return get_adapter("custom").normalize_size(raw_size, None)


def resolve_provider_quality(provider: str, raw_quality: Optional[str]) -> str:
    normalized_provider = normalize_provider_id(provider)
    quality = str(raw_quality or "").strip().lower()
    if normalized_provider == "seedream":
        return ""
    if normalized_provider == "google-nano-banana":
        return ""
    if normalized_provider == "thinkai-nano":
        return ""
    if normalized_provider == "openai-gpt-image":
        quality = "high" if quality == "hd" else quality
        if quality not in {"low", "medium", "high", "auto"}:
            raise ValueError(f"OpenAI 不支持图片质量：{raw_quality}。")
        return quality
    if normalized_provider == "thinkai-image-2":
        if quality not in {"standard", "hd"}:
            raise ValueError(f"ThinkAI Image 2 不支持图片质量：{raw_quality}。")
        return quality
    return quality or "hd"


def validate_prompt(prompt: str) -> str:
    normalized = prompt.strip()
    if not normalized:
        raise ValueError("已审核 Prompt 不能为空。")
    return normalized


def approval_digest(
    prompt: str,
    provider: str = "thinkai-image-2",
    model: Optional[str] = None,
    size: Optional[str] = None,
    quality: Optional[str] = None,
    reference_image_sha256: Optional[str] = None,
) -> str:
    normalized_prompt = validate_prompt(prompt)
    payload = json.dumps(
        {
            "prompt": normalized_prompt,
            "provider": normalize_provider_id(provider),
            "model": str(model or "").strip(),
            "size": str(size or "").strip(),
            "quality": str(quality or "").strip(),
            "reference_image_sha256": str(
                reference_image_sha256 or ""
            ).strip().lower(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_approval(
    prompt: str,
    expected_digest: str,
    provider: str = "thinkai-image-2",
    model: Optional[str] = None,
    size: Optional[str] = None,
    quality: Optional[str] = None,
    reference_image_sha256: Optional[str] = None,
) -> str:
    normalized = validate_prompt(prompt)
    actual_digest = approval_digest(
        normalized,
        provider,
        model,
        size,
        quality,
        reference_image_sha256,
    )
    if not hmac.compare_digest(actual_digest, expected_digest.strip().lower()):
        raise ValueError("当前 Prompt 与用户审核通过的版本不一致，请重新展示并审核。")
    return normalized


def build_generation_body(
    model: str,
    prompt: str,
    size: str,
    quality: str,
    n: int,
) -> dict:
    return {
        "model": model,
        "prompt": prompt,
        "n": n,
        "size": size,
        "quality": quality,
        "response_format": "url",
    }


def build_request_context(config: dict) -> tuple[str, str, dict]:
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": "curl/8.7.1",
    }
    return config["base_url"], config["model"], headers


def sanitize_error_detail(detail: object, headers: dict) -> str:
    """移除服务端错误正文中可能回显的鉴权信息。"""

    sanitized = str(detail)
    sensitive_values = set()
    for key, value in headers.items():
        if str(key).lower() not in SENSITIVE_HEADER_NAMES:
            continue
        normalized = str(value).strip()
        if not normalized:
            continue
        sensitive_values.add(normalized)
        if normalized.lower().startswith("bearer "):
            sensitive_values.add(normalized[7:].strip())

    for secret in sorted(sensitive_values, key=len, reverse=True):
        if secret:
            sanitized = sanitized.replace(secret, "<redacted>")
    return sanitized


def request_json(
    method: str,
    url: str,
    headers: dict,
    body: Optional[dict] = None,
    service_name: str = "ThinkAI",
) -> dict:
    try:
        response = requests.request(
            method,
            url,
            json=body,
            headers=headers,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        payload = response.text
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        detail = exc.response.text if exc.response is not None else str(exc)
        detail = sanitize_error_detail(detail, headers)
        if status_code == 408 or (status_code is not None and status_code >= 500):
            raise GenerationUncertainError(
                f"{service_name} 返回 HTTP {status_code}，"
                "无法安全确认付费生成请求是否已完成。"
                f"请先检查渠道后台：{detail}"
            ) from exc
        raise RuntimeError(
            f"{service_name} 请求失败，HTTP {status_code}：{detail}。"
            "付费生成请求不会自动重试。"
        ) from exc
    except (
        requests.exceptions.MissingSchema,
        requests.exceptions.InvalidSchema,
        requests.exceptions.InvalidURL,
        requests.exceptions.InvalidHeader,
    ) as exc:
        raise GenerationError(
            f"{service_name} 请求配置无效：{exc}"
        ) from exc
    except requests.RequestException as exc:
        raise GenerationUncertainError(
            f"{service_name} 生成请求结果不确定，服务端可能已受理并计费。"
            "为避免重复生成，本工具不会自动重试；"
            f"请先在 {service_name} 后台确认任务记录，再决定是否重新执行。"
            f"原始错误：{exc}"
        ) from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        payload = sanitize_error_detail(payload, headers)
        raise GenerationUncertainError(
            f"{service_name} 已返回成功响应，但响应不是可解析的 JSON，"
            f"结果状态不确定：{payload[:500]}"
        ) from exc


def extract_adapter_source(adapter, response_json: dict, config: dict):
    if config["provider"] in FORMAL_PROVIDER_IDS:
        return adapter.extract_image_source(response_json)
    return adapter.extract_image_source(response_json, config)


def request_generation(config: dict, request: dict, adapter=None) -> dict:
    if adapter is None:
        adapter = get_adapter(
            config["provider"]
            if config["provider"] in FORMAL_PROVIDER_IDS
            else "custom"
        )
    data = request_json(
        "POST",
        request["url"],
        request["headers"],
        request["body"],
        service_name=config.get("provider_name", config["provider"]),
    )
    try:
        extract_adapter_source(adapter, data, config)
    except Exception as exc:
        raise GenerationUncertainError(
            "图片渠道已经返回响应，但无法确认图片字段，结果状态不确定。"
        ) from exc
    return data


def curl_download(image_url: str) -> bytes:
    curl = subprocess.run(
        ["curl", "-L", "--fail", "--silent", "--show-error", image_url],
        capture_output=True,
        check=False,
        timeout=600,
    )
    if curl.returncode == 0 and curl.stdout:
        return curl.stdout
    stderr = curl.stderr.decode("utf-8", errors="replace").strip()
    if stderr:
        raise RuntimeError(f"curl 图片下载失败：{stderr}")
    raise RuntimeError(f"curl 图片下载失败，退出码 {curl.returncode}")


def download_image(image_url: str) -> bytes:
    req = urllib.request.Request(
        image_url,
        headers={
            "Accept": "*/*",
            "User-Agent": "curl/8.7.1",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"图片下载失败，HTTP {exc.code}：{detail}") from exc
    except http.client.IncompleteRead as exc:
        try:
            return curl_download(image_url)
        except RuntimeError as curl_exc:
            raise RuntimeError(f"图片下载不完整：{exc}；{curl_exc}") from exc
    except urllib.error.URLError as exc:
        try:
            return curl_download(image_url)
        except RuntimeError as curl_exc:
            raise RuntimeError(f"图片下载失败：{exc}；{curl_exc}") from exc


def get_jpeg_dimensions(image_bytes: bytes) -> Tuple[int, int]:
    position = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while position + 3 < len(image_bytes):
        if image_bytes[position] != 0xFF:
            position += 1
            continue
        while position < len(image_bytes) and image_bytes[position] == 0xFF:
            position += 1
        if position >= len(image_bytes):
            break
        marker = image_bytes[position]
        position += 1
        if marker in {0xD8, 0xD9}:
            continue
        if position + 1 >= len(image_bytes):
            break
        segment_length = int.from_bytes(image_bytes[position : position + 2], "big")
        if segment_length < 2 or position + segment_length > len(image_bytes):
            break
        if marker in sof_markers and segment_length >= 7:
            height = int.from_bytes(image_bytes[position + 3 : position + 5], "big")
            width = int.from_bytes(image_bytes[position + 5 : position + 7], "big")
            if width and height:
                return width, height
        position += segment_length
    raise RuntimeError("返回的 JPEG 无法读取尺寸。")


def inspect_image(image_bytes: bytes) -> Tuple[str, int, int]:
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n" and len(image_bytes) >= 24:
        width = int.from_bytes(image_bytes[16:20], "big")
        height = int.from_bytes(image_bytes[20:24], "big")
        return "png", width, height
    if image_bytes[:2] == b"\xff\xd8":
        width, height = get_jpeg_dimensions(image_bytes)
        return "jpg", width, height
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        chunk = image_bytes[12:16]
        if chunk == b"VP8X" and len(image_bytes) >= 30:
            width = 1 + int.from_bytes(image_bytes[24:27], "little")
            height = 1 + int.from_bytes(image_bytes[27:30], "little")
            return "webp", width, height
        if chunk == b"VP8L" and len(image_bytes) >= 25:
            bits = int.from_bytes(image_bytes[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return "webp", width, height
        raise RuntimeError("返回的 WebP 无法读取尺寸。")
    raise RuntimeError("图片不是支持的 PNG、JPEG 或 WebP 格式。")


def decode_data_url(value: str) -> bytes:
    header, separator, encoded = value.partition(",")
    if not separator or not header.startswith("data:image/") or ";base64" not in header:
        raise RuntimeError("图片 Data URL 格式无效。")
    try:
        return base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise RuntimeError("图片 Data URL 数据无效。") from exc


def extract_image_bytes(config: dict, response_json: dict) -> Tuple[bytes, str, str]:
    provider = config["provider"]
    adapter_id = provider if provider in FORMAL_PROVIDER_IDS else "custom"
    adapter = get_adapter(adapter_id)
    source_type, source_value = extract_adapter_source(adapter, response_json, config)

    if source_type == "base64":
        try:
            return base64.b64decode(source_value, validate=True), source_type, ""
        except (ValueError, binascii.Error) as exc:
            raise RuntimeError("图片 Base64 数据无效。") from exc
    if source_value.startswith("data:image/"):
        return decode_data_url(source_value), "data_url", ""

    return download_image(source_value), source_type, source_value


def redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    if parts.scheme not in {"http", "https"}:
        return value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def redact_snapshot(value, omitted_values=None):
    omitted_values = omitted_values or set()
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"api_key", "authorization", "x-goog-api-key"}:
                result[key] = "<redacted>"
            elif lowered in {"b64_json", "data"} and isinstance(item, str) and len(item) > 256:
                result[key] = "<base64 omitted>"
            else:
                result[key] = redact_snapshot(item, omitted_values)
        return result
    if isinstance(value, list):
        return [redact_snapshot(item, omitted_values) for item in value]
    if isinstance(value, str) and value in omitted_values:
        return "<base64 omitted>"
    if isinstance(value, str) and value.startswith("data:image/"):
        return "<reference image omitted>"
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        return redact_url(value)
    return value


def write_artifacts(
    skill_root: Path,
    config: dict,
    request_body: dict,
    response_json: dict,
    output_dir: Optional[str],
    output_dir_fd: Optional[int] = None,
) -> dict:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_dir = (
        Path(output_dir).expanduser()
        if output_dir
        else Path.cwd() / "xiaohongshu-images" / stamp
    )
    if output_dir_fd is None:
        target_dir = target_dir.resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        _verify_output_directory_identity(target_dir, output_dir_fd)

    adapter_id = (
        config["provider"]
        if config["provider"] in FORMAL_PROVIDER_IDS
        else "custom"
    )
    adapter = get_adapter(adapter_id)
    source_type, source_value = extract_adapter_source(
        adapter,
        response_json,
        config,
    )
    omitted_values = (
        {source_value}
        if source_type == "base64" or source_value.startswith("data:image/")
        else set()
    )

    request_path = target_dir / "request.json"
    response_path = target_dir / "response.json"
    _write_output_bytes(
        request_path,
        (
            json.dumps(
                redact_snapshot(deepcopy(request_body)),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode("utf-8"),
        output_dir_fd,
    )
    _write_output_bytes(
        response_path,
        (
            json.dumps(
                redact_snapshot(deepcopy(response_json), omitted_values),
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        ).encode("utf-8"),
        output_dir_fd,
    )

    image_bytes, source_type, image_url = extract_image_bytes(config, response_json)
    image_format, width, height = inspect_image(image_bytes)
    image_path = target_dir / f"image.{image_format}"
    _write_output_bytes(image_path, image_bytes, output_dir_fd)
    if output_dir_fd is not None:
        _verify_output_directory_identity(target_dir, output_dir_fd)
    is_remote_url = image_url.startswith(("https://", "http://"))

    artifacts = {
        "image_path": str(image_path),
        "request_path": str(request_path),
        "response_path": str(response_path),
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
        "image_url": redact_url(image_url) if is_remote_url else None,
        "image_source": (
            "base64"
            if source_type == "base64"
            else ("data_url" if source_type == "data_url" else "remote_url")
        ),
        "actual_size": f"{width}x{height}",
    }
    return artifacts


def resolve_output_directory(
    output_dir: Optional[Path],
    allowed_output_root: Optional[Path] = None,
) -> Optional[Path]:
    if output_dir is None:
        return None
    raw_target = Path(output_dir).expanduser()
    if allowed_output_root is None:
        return raw_target

    raw_root = Path(allowed_output_root).expanduser()
    if raw_root.is_symlink() or raw_target.is_symlink():
        raise GenerationError("文章图片输出目录不能使用符号链接。")
    root = raw_root.resolve()
    target = raw_target.resolve()
    if target == root or root not in target.parents:
        raise GenerationError("文章图片输出目录超出允许范围。")
    return Path(os.path.abspath(raw_target))


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _verify_output_directory_identity(path: Path, directory_fd: int) -> None:
    try:
        path_stat = os.stat(path, follow_symlinks=False)
        fd_stat = os.fstat(directory_fd)
    except OSError as exc:
        raise GenerationUncertainError(
            "文章图片输出目录在生成期间发生变化，不能安全保存结果。"
        ) from exc
    if (
        not stat.S_ISDIR(path_stat.st_mode)
        or path_stat.st_dev != fd_stat.st_dev
        or path_stat.st_ino != fd_stat.st_ino
    ):
        raise GenerationUncertainError(
            "文章图片输出目录在生成期间发生变化，不能安全保存结果。"
        )


def _open_bounded_output_directory(
    output_dir: Path,
    allowed_output_root: Path,
    trusted_root: Path,
) -> int:
    anchor = Path(os.path.abspath(Path(trusted_root).expanduser()))
    raw_root = Path(os.path.abspath(Path(allowed_output_root).expanduser()))
    raw_target = Path(os.path.abspath(Path(output_dir).expanduser()))
    try:
        root_parts = raw_root.relative_to(anchor).parts
        target_parts = raw_target.relative_to(raw_root).parts
    except ValueError as exc:
        raise GenerationError("文章图片输出目录超出可信根目录。") from exc
    if len(target_parts) != 1 or target_parts[0] in {"", ".", ".."}:
        raise GenerationError("文章图片输出目录必须直接位于允许目录内。")

    current_fd = None
    target_fd = None
    keep_target_fd = False
    try:
        current_fd = os.open(anchor, _directory_open_flags())
        for index, part in enumerate(root_parts):
            if part in {"", ".", ".."}:
                raise GenerationError("文章图片输出目录包含无效路径。")
            if index == len(root_parts) - 1:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
            next_fd = os.open(
                part,
                _directory_open_flags(),
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
        try:
            os.mkdir(target_parts[0], mode=0o700, dir_fd=current_fd)
        except FileExistsError:
            pass
        target_fd = os.open(
            target_parts[0],
            _directory_open_flags(),
            dir_fd=current_fd,
        )
        _verify_output_directory_identity(raw_target, target_fd)
        keep_target_fd = True
        return target_fd
    except GenerationError:
        raise
    except OSError as exc:
        raise GenerationError(
            "无法安全创建文章图片输出目录。"
        ) from exc
    finally:
        if current_fd is not None:
            os.close(current_fd)
        if target_fd is not None and not keep_target_fd:
            os.close(target_fd)


def _write_output_bytes(
    path: Path,
    content: bytes,
    directory_fd: Optional[int],
) -> None:
    if directory_fd is None:
        path.write_bytes(content)
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    file_fd = os.open(path.name, flags, 0o600, dir_fd=directory_fd)
    with os.fdopen(file_fd, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def generate_approved_image(
    skill_root: Path,
    provider: str,
    prompt: str,
    approval_hash: str,
    size: Optional[str] = None,
    quality: str = "hd",
    output_dir: Optional[Path] = None,
    allowed_output_root: Optional[Path] = None,
    reference_image_path: Optional[Path] = None,
    reference_image_sha256: Optional[str] = None,
) -> dict:
    """执行一张已审核图片，供单图 CLI 和文章工作流共同复用。"""

    resolved_output_dir = resolve_output_directory(
        output_dir,
        allowed_output_root,
    )
    config = load_config(Path(skill_root), provider)
    resolved_size = resolve_provider_size(config["provider"], size)
    approval_quality = resolve_provider_quality(config["provider"], quality)
    reference_data_urls = None
    normalized_reference_hash = str(reference_image_sha256 or "").strip().lower()
    if reference_image_path is not None:
        reference_path = Path(reference_image_path).expanduser().resolve()
        if not reference_path.is_file():
            raise GenerationError("产品参考图不存在。")
        reference_bytes = reference_path.read_bytes()
        actual_reference_hash = hashlib.sha256(reference_bytes).hexdigest()
        if not normalized_reference_hash or not hmac.compare_digest(
            actual_reference_hash,
            normalized_reference_hash,
        ):
            raise GenerationError("产品参考图与批准版本不一致。")
        suffix = reference_path.suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(suffix)
        if mime_type is None:
            raise GenerationError("产品参考图只支持 JPEG、PNG 或 WebP。")
        reference_data_urls = [
            f"data:{mime_type};base64,"
            + base64.b64encode(reference_bytes).decode("ascii")
        ]
    if config["provider"] == "seedream" and not reference_data_urls:
        raise GenerationError("Seedream 产品生图必须绑定官网产品参考图。")
    approved_prompt = validate_approval(
        prompt,
        approval_hash,
        config["provider"],
        config["model"],
        resolved_size,
        approval_quality,
        normalized_reference_hash,
    )
    adapter_id = (
        config["provider"]
        if config["provider"] in FORMAL_PROVIDER_IDS
        else "custom"
    )
    adapter = get_adapter(adapter_id)
    if config["provider"] == "seedream":
        request = adapter.build_request(
            config,
            approved_prompt,
            resolved_size,
            approval_quality,
            reference_data_urls,
        )
    else:
        request = adapter.build_request(
            config,
            approved_prompt,
            resolved_size,
            approval_quality,
        )
    output_dir_fd = None
    try:
        if resolved_output_dir is not None and allowed_output_root is not None:
            output_dir_fd = _open_bounded_output_directory(
                resolved_output_dir,
                allowed_output_root,
                Path(allowed_output_root).expanduser().parent,
            )
        response_json = request_generation(config, request, adapter)
        try:
            artifacts = write_artifacts(
                Path(skill_root),
                config,
                request["body"],
                response_json,
                (
                    str(resolved_output_dir)
                    if resolved_output_dir is not None
                    else None
                ),
                output_dir_fd=output_dir_fd,
            )
        except GenerationUncertainError:
            raise
        except Exception as exc:
            raise GenerationUncertainError(
                "图片渠道已经返回结果，但本地保存或下载失败，"
                "不得自动重新发送生成请求。"
            ) from exc
    finally:
        if output_dir_fd is not None:
            os.close(output_dir_fd)

    summary = {
        "provider": config["provider"],
        "base_url": config.get("base_url", config.get("endpoint")),
        "model": config["model"],
        "requested_size": resolved_size,
        "actual_size": artifacts["actual_size"],
        **artifacts,
    }
    if approval_quality:
        summary["quality"] = approval_quality
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="通过选定渠道生成已审核通过的图片。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--provider",
        default="thinkai-image-2",
        help="图片生成渠道 ID",
    )
    parser.add_argument("--approved", action="store_true", required=True, help="确认用户已明确批准 Prompt")
    parser.add_argument("--approval-hash", required=True, help="用户批准的精确 Prompt SHA-256")
    parser.add_argument("--prompt", required=True, help="已审核通过的最终 Prompt")
    parser.add_argument(
        "--size",
        default=None,
        help=(
            "尺寸；ThinkAI Image 2 可用 1k/2k，"
            "ThinkAI Nano 使用 16:9@2K 等格式"
        ),
    )
    parser.add_argument(
        "--quality",
        default="hd",
        choices=["standard", "hd", "low", "medium", "high", "auto"],
    )
    parser.add_argument(
        "--reference-image",
        type=Path,
        default=None,
        help="官网产品参考图；Seedream 产品生图必须提供",
    )
    parser.add_argument(
        "--reference-image-sha256",
        default=None,
        help="官网产品参考图 SHA-256；必须与批准哈希使用的值一致",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plugin_root = Path(__file__).resolve().parents[2]

    try:
        summary = generate_approved_image(
            plugin_root,
            args.provider,
            args.prompt,
            args.approval_hash,
            args.size,
            args.quality,
            reference_image_path=args.reference_image,
            reference_image_sha256=args.reference_image_sha256,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
