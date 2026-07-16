#!/usr/bin/env python3
"""并发生成已批准的小红书成品图，不做本地图片加工。"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from generate_image import (
    approval_digest,
    generate_approved_image,
    load_config,
    resolve_provider_quality,
    resolve_provider_size,
)
from provider_preflight import verify_local


DEFAULT_MAX_WORKERS = 0
MAX_ATTEMPTS = 3
STATE_FILENAME = "generation-state.json"
ITEM_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
FINAL_STATUSES = {"complete", "omitted_similar"}


class BatchGenerationError(RuntimeError):
    """批量生图输入、状态或执行不符合约束。"""


def validate_max_workers(value: int | None) -> int:
    if value is None:
        return 0
    if value < 0:
        raise ValueError("并发数不能小于 0；0 表示一次并发全部待生成页面。")
    return value


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _normalized_batch(batch: dict) -> dict:
    if not isinstance(batch, dict) or batch.get("schema_version") != 1:
        raise ValueError("批量生图文件版本无效。")
    raw_items = batch.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("批量生图至少需要一个图片项目。")

    items = []
    seen_ids = set()
    seen_pages = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("图片项目必须是对象。")
        item_id = str(raw.get("id") or "").strip()
        if not ITEM_ID_PATTERN.fullmatch(item_id) or item_id in seen_ids:
            raise ValueError(f"图片项目 ID 无效或重复：{item_id}")
        try:
            page = int(raw.get("page"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"图片项目页码无效：{item_id}") from exc
        if page < 1 or page in seen_pages:
            raise ValueError(f"图片项目页码无效或重复：{page}")
        seen_ids.add(item_id)
        seen_pages.add(page)

        normalized = {
            "id": item_id,
            "page": page,
            "prompt": str(raw.get("prompt") or "").strip(),
            "generation_batch_approval": str(
                raw.get("generation_batch_approval") or ""
            ).strip(),
            "provider": str(raw.get("provider") or "").strip(),
            "model": str(raw.get("model") or "").strip(),
            "size": str(raw.get("size") or "").strip(),
            "quality": str(raw.get("quality") or "").strip(),
            "approval_digest": str(raw.get("approval_digest") or "")
            .strip()
            .lower(),
            "reference_image_path": str(
                raw.get("reference_image_path") or ""
            ).strip(),
            "reference_image_sha256": str(
                raw.get("reference_image_sha256") or ""
            ).strip().lower(),
        }
        required = (
            "prompt",
            "provider",
            "model",
            "size",
            "quality",
            "approval_digest",
        )
        if any(not normalized[field] for field in required):
            raise ValueError(f"图片项目执行条件不完整：{item_id}")
        if normalized["provider"] == "seedream" and (
            not normalized["reference_image_path"]
            or not re.fullmatch(r"[0-9a-f]{64}", normalized["reference_image_sha256"])
        ):
            raise ValueError(f"Seedream 图片项目必须绑定官网参考图及哈希：{item_id}")
        items.append(normalized)

    items.sort(key=lambda item: item["page"])
    return {"schema_version": 1, "items": items}


def create_batch_state(batch: dict) -> dict:
    normalized = _normalized_batch(batch)
    return {
        "schema_version": 1,
        "batch_digest": _canonical_hash(normalized),
        "status": "ready",
        "items": [
            {
                "id": item["id"],
                "page": item["page"],
                "generation_status": "pending",
                "attempts": 0,
                "errors": [],
                "result": None,
                "final_path": None,
                "duplicate_of": None,
                "error": None,
            }
            for item in normalized["items"]
        ],
    }


def _load_or_create_state(output_root: Path, batch: dict) -> dict:
    state_path = output_root / STATE_FILENAME
    expected = create_batch_state(batch)
    if not state_path.exists():
        _atomic_write_json(state_path, expected)
        return expected
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchGenerationError("批量生成状态文件无法读取。") from exc
    if (
        not isinstance(state, dict)
        or state.get("schema_version") != 1
        or state.get("batch_digest") != expected["batch_digest"]
    ):
        raise BatchGenerationError("批量输入已变化，旧生成状态不能继续使用。")
    state_items = state.get("items")
    if not isinstance(state_items, list) or [
        item.get("id") for item in state_items
    ] != [item["id"] for item in expected["items"]]:
        raise BatchGenerationError("批量生成状态与当前轮播顺序不一致。")
    for item in state_items:
        item.setdefault("attempts", 0)
        item.setdefault("errors", [])
        item.setdefault("duplicate_of", None)
        if item.get("generation_status") in {"sending", "uncertain"}:
            item["generation_status"] = "pending"
    return state


def _save_state(output_root: Path, state: dict) -> None:
    _atomic_write_json(output_root / STATE_FILENAME, state)


def _acquire_lock(output_root: Path) -> int:
    lock_path = output_root / ".generation.lock"
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise BatchGenerationError("当前任务已有一个批量生图执行器。") from exc
    return descriptor


def _release_lock(descriptor: int) -> None:
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _validate_output_root(skill_root: Path, output_root: Path) -> Path:
    root = output_root.expanduser().resolve()
    plugin = skill_root.expanduser().resolve()
    if root == plugin or plugin in root.parents:
        raise ValueError("批量生图输出目录不能位于插件目录内。")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validate_reference(item: dict) -> None:
    if not item["reference_image_path"]:
        return
    path = Path(item["reference_image_path"]).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"官网产品参考图不存在：{item['id']}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if not hmac.compare_digest(actual, item["reference_image_sha256"]):
        raise ValueError(f"官网产品参考图与批准版本不一致：{item['id']}")


def _validate_approvals(
    skill_root: Path,
    batch: dict,
    config_loader: Callable,
    preflight: Callable,
) -> list[dict]:
    normalized = _normalized_batch(batch)
    runtime_by_provider = {}
    prepared = []
    for item in normalized["items"]:
        if item["generation_batch_approval"] != "confirmed":
            raise ValueError(f"图片项目尚未获得用户明确批准：{item['id']}")
        _validate_reference(item)
        provider = item["provider"]
        if provider not in runtime_by_provider:
            check = preflight(skill_root, provider)
            config = config_loader(skill_root, provider)
            if (
                check.get("status") != "verified-local"
                or check.get("network_request_sent") is not False
            ):
                raise ValueError(f"图片渠道本地预检不通过：{provider}")
            if (
                check.get("provider") != item["provider"]
                or check.get("model") != item["model"]
            ):
                raise ValueError(
                    f"图片渠道或模型预检结果与批准版本不一致：{item['id']}"
                )
            runtime_by_provider[provider] = config
        config = runtime_by_provider[provider]
        if config.get("provider") != provider or config.get("model") != item["model"]:
            raise ValueError(f"图片渠道或模型与批准版本不一致：{item['id']}")
        resolved_size = resolve_provider_size(provider, item["size"])
        resolved_quality = resolve_provider_quality(provider, item["quality"])
        digest = approval_digest(
            item["prompt"],
            provider=provider,
            model=item["model"],
            size=resolved_size,
            quality=resolved_quality,
            reference_image_sha256=item["reference_image_sha256"],
        )
        if not hmac.compare_digest(digest, item["approval_digest"]):
            raise ValueError(f"图片项目批准已失效：{item['id']}")
        prepared.append(item)
    return prepared


def _relative_result(output_root: Path, result: dict) -> dict:
    normalized = {}
    for key, value in result.items():
        if key.endswith("_path") and isinstance(value, str):
            path = Path(value).expanduser().resolve()
            try:
                normalized[key] = path.relative_to(output_root).as_posix()
            except ValueError as exc:
                raise BatchGenerationError(
                    "生成结果路径超出当前用户任务目录。"
                ) from exc
        else:
            normalized[key] = value
    return normalized


def _copy_model_output(item: dict, result: dict, output_root: Path) -> Path:
    source = Path(str(result.get("image_path") or "")).expanduser().resolve()
    if not source.is_file():
        raise BatchGenerationError("图片渠道返回成功，但生成图片文件不存在。")
    suffix = source.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise BatchGenerationError("生成图片格式不是 PNG、JPEG 或 WebP。")
    destination = output_root / "final" / f"{item['page']:02d}-{item['id']}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)
    return destination


def _image_fingerprint(path: Path) -> tuple[int, ...] | None:
    try:
        from PIL import Image

        with Image.open(path) as image:
            pixels = list(image.convert("L").resize((16, 16)).getdata())
        average = sum(pixels) / len(pixels)
        return tuple(1 if pixel >= average else 0 for pixel in pixels)
    except Exception:
        return None


def _is_near_duplicate(left: Path, right: Path) -> bool:
    if hashlib.sha256(left.read_bytes()).digest() == hashlib.sha256(
        right.read_bytes()
    ).digest():
        return True
    left_hash = _image_fingerprint(left)
    right_hash = _image_fingerprint(right)
    if left_hash is None or right_hash is None:
        return False
    distance = sum(a != b for a, b in zip(left_hash, right_hash))
    return distance <= 12


def _remove_similar_images(output_root: Path, state: dict) -> None:
    kept: list[dict] = []
    for item in state["items"]:
        if item["generation_status"] != "complete" or not item.get("final_path"):
            continue
        current = output_root / item["final_path"]
        duplicate = next(
            (
                other
                for other in kept
                if _is_near_duplicate(
                    current,
                    output_root / str(other["final_path"]),
                )
            ),
            None,
        )
        if duplicate is None:
            kept.append(item)
            continue
        current.unlink(missing_ok=True)
        item["generation_status"] = "omitted_similar"
        item["duplicate_of"] = duplicate["id"]
        item["final_path"] = None
        item["error"] = None


def batch_generate(
    skill_root: Path,
    batch: dict,
    output_root: Path,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    generator: Callable = generate_approved_image,
    config_loader: Callable = load_config,
    preflight: Callable = verify_local,
) -> dict:
    worker_limit = validate_max_workers(max_workers)
    skill_root = Path(skill_root).resolve()
    output_root = _validate_output_root(skill_root, Path(output_root))
    lock_descriptor = _acquire_lock(output_root)
    try:
        prepared_items = _validate_approvals(
            skill_root,
            batch,
            config_loader,
            preflight,
        )
        state = _load_or_create_state(output_root, batch)
        state_by_id = {item["id"]: item for item in state["items"]}
        pending = [
            item
            for item in prepared_items
            if state_by_id[item["id"]]["generation_status"] not in FINAL_STATUSES
            and int(state_by_id[item["id"]].get("attempts", 0)) < MAX_ATTEMPTS
        ]
        if not pending:
            _remove_similar_images(output_root, state)
            failed = [
                item for item in state["items"]
                if item["generation_status"] not in FINAL_STATUSES
            ]
            state["status"] = "blocked" if failed else "complete"
            state["failed_pages"] = [
                {"page": item["page"], "error": item.get("error")}
                for item in failed
            ]
            _save_state(output_root, state)
            return state

        state_lock = threading.Lock()
        state["status"] = "generating"
        for item in pending:
            state_by_id[item["id"]]["generation_status"] = "sending"
        _save_state(output_root, state)

        def run_job(item: dict) -> tuple[dict, str] | None:
            state_item = state_by_id[item["id"]]
            while state_item["attempts"] < MAX_ATTEMPTS:
                with state_lock:
                    state_item["attempts"] += 1
                    attempt = state_item["attempts"]
                    state_item["generation_status"] = "sending"
                    state_item["error"] = None
                    _save_state(output_root, state)
                try:
                    attempt_output_dir = (
                        output_root
                        / "artifacts"
                        / item["id"]
                        / f"attempt-{attempt}"
                    )
                    item_output_root = output_root / "artifacts" / item["id"]
                    raw_result = generator(
                        skill_root=skill_root,
                        provider=item["provider"],
                        prompt=item["prompt"],
                        approval_hash=item["approval_digest"],
                        size=item["size"],
                        quality=item["quality"],
                        output_dir=attempt_output_dir,
                        allowed_output_root=item_output_root,
                        reference_image_path=(
                            Path(item["reference_image_path"])
                            if item["reference_image_path"]
                            else None
                        ),
                        reference_image_sha256=(
                            item["reference_image_sha256"] or None
                        ),
                    )
                    final_path = _copy_model_output(item, raw_result, output_root)
                    return _relative_result(output_root, raw_result), str(final_path)
                except Exception as exc:
                    message = str(exc) or exc.__class__.__name__
                    with state_lock:
                        state_item["errors"].append(
                            {"attempt": attempt, "error": message}
                        )
                        state_item["error"] = message
                        state_item["generation_status"] = (
                            "failed"
                            if state_item["attempts"] >= MAX_ATTEMPTS
                            else "retrying"
                        )
                        _save_state(output_root, state)
            return None

        workers = len(pending) if worker_limit == 0 else min(worker_limit, len(pending))
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="xhs-image",
        ) as executor:
            futures = {executor.submit(run_job, item): item for item in pending}
            for future in as_completed(futures):
                item = futures[future]
                state_item = state_by_id[item["id"]]
                outcome = future.result()
                with state_lock:
                    if outcome is not None:
                        result, final_path = outcome
                        state_item["generation_status"] = "complete"
                        state_item["result"] = result
                        state_item["final_path"] = (
                            Path(final_path)
                            .resolve()
                            .relative_to(output_root)
                            .as_posix()
                        )
                        state_item["error"] = None
                    _save_state(output_root, state)

        _remove_similar_images(output_root, state)
        failed = [
            item for item in state["items"]
            if item["generation_status"] not in FINAL_STATUSES
        ]
        state["failed_pages"] = [
            {
                "page": item["page"],
                "id": item["id"],
                "attempts": item["attempts"],
                "error": item.get("error"),
            }
            for item in failed
        ]
        state["status"] = "blocked" if failed else "complete"
        _save_state(output_root, state)
        return state
    finally:
        _release_lock(lock_descriptor)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="一次并发生成全部已批准的小红书成品图。"
    )
    parser.add_argument("--batch-file", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="最大并发数；默认 0 表示待生成页面全部并发，无固定上限",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plugin_root = Path(__file__).resolve().parents[2]
    try:
        payload = json.loads(args.batch_file.read_text(encoding="utf-8"))
        state = batch_generate(
            plugin_root,
            payload,
            args.output_root,
            max_workers=args.max_workers,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0 if state["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
