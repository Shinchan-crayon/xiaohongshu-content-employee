#!/usr/bin/env python3
"""受控并发生成并合成已批准的小红书轮播图片。"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import re
import sys
import tempfile
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
from typing import Callable

from generate_image import (
    GenerationUncertainError,
    approval_digest,
    generate_approved_image,
    load_config,
    resolve_provider_quality,
    resolve_provider_size,
)
from provider_preflight import verify_local


DEFAULT_MAX_WORKERS = 3
MAX_MAX_WORKERS = 8
STATE_FILENAME = "generation-state.json"
ITEM_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class BatchGenerationError(RuntimeError):
    """批量生图输入、状态或执行不符合约束。"""


class CompositionUncertainError(GenerationUncertainError):
    """付费生图已完成，但本地合成结果不能安全确认。"""


def validate_max_workers(value: int) -> int:
    if not 1 <= value <= MAX_MAX_WORKERS:
        raise ValueError(f"并发数必须在 1 到 {MAX_MAX_WORKERS} 之间。")
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

        render = raw.get("render")
        if not isinstance(render, dict):
            raise ValueError(f"图片项目缺少合成配置：{item_id}")
        if render.get("generated_image_target") != "background_path":
            raise ValueError(
                f"AI 图片只能作为背景使用，不能重绘真实产品：{item_id}"
            )

        normalized = {
            "id": item_id,
            "page": page,
            "prompt": str(raw.get("prompt") or "").strip(),
            "prompt_review": str(raw.get("prompt_review") or "").strip(),
            "provider": str(raw.get("provider") or "").strip(),
            "model": str(raw.get("model") or "").strip(),
            "size": str(raw.get("size") or "").strip(),
            "quality": str(raw.get("quality") or "").strip(),
            "approval_digest": str(raw.get("approval_digest") or "")
            .strip()
            .lower(),
            "render": deepcopy(render),
        }
        if any(
            not normalized[field]
            for field in (
                "prompt",
                "provider",
                "model",
                "size",
                "quality",
                "approval_digest",
            )
        ):
            raise ValueError(f"图片项目执行条件不完整：{item_id}")
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
                "result": None,
                "final_path": None,
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
        if item["prompt_review"] != "confirmed":
            raise ValueError(f"图片项目尚未获得用户明确批准：{item['id']}")
        provider = item["provider"]
        if provider not in runtime_by_provider:
            check = preflight(skill_root, provider)
            config = config_loader(skill_root, provider)
            if (
                check.get("status") != "verified-local"
                or check.get("network_request_sent") is not False
                or check.get("provider") != provider
                or check.get("model") != config.get("model")
            ):
                raise ValueError(f"图片渠道本地预检不通过：{provider}")
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
        )
        if not hmac.compare_digest(digest, item["approval_digest"]):
            raise ValueError(f"图片项目审核批准已失效：{item['id']}")
        prepared.append(item)
    return prepared


def compose_carousel_item(item: dict, result: dict, output_path: Path) -> str:
    renderer_dir = Path(__file__).resolve().parent.parent / "图片合成工具"
    if str(renderer_dir) not in sys.path:
        sys.path.insert(0, str(renderer_dir))
    from render_carousel import atomic_save, render

    image_path = Path(str(result.get("image_path") or "")).expanduser()
    if not image_path.is_file():
        raise CompositionUncertainError("生图已完成，但生成图片不存在，无法合成。")
    payload = deepcopy(item["render"])
    payload.pop("generated_image_target", None)
    payload["background_path"] = str(image_path)
    payload["output_path"] = str(output_path)
    image, _font_path = render(payload)
    atomic_save(image, output_path)
    return str(output_path)


def _relative_result(output_root: Path, result: dict) -> dict:
    normalized = {}
    for key, value in result.items():
        if key.endswith("_path") and isinstance(value, str):
            path = Path(value).expanduser().resolve()
            try:
                normalized[key] = path.relative_to(output_root).as_posix()
            except ValueError as exc:
                raise CompositionUncertainError(
                    "生成结果路径超出当前用户任务目录。"
                ) from exc
        else:
            normalized[key] = value
    return normalized


def batch_generate(
    skill_root: Path,
    batch: dict,
    output_root: Path,
    max_workers: int = DEFAULT_MAX_WORKERS,
    generator: Callable = generate_approved_image,
    compositor: Callable = compose_carousel_item,
    config_loader: Callable = load_config,
    preflight: Callable = verify_local,
) -> dict:
    validate_max_workers(max_workers)
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

        interrupted = [
            item for item in state["items"]
            if item["generation_status"] == "sending"
        ]
        if interrupted:
            for item in interrupted:
                item["generation_status"] = "uncertain"
                item["error"] = "上次执行在付费请求期间中断，请先检查渠道后台。"
            state["status"] = "blocked"
            _save_state(output_root, state)
            return state

        if any(
            item["generation_status"] in {"failed", "uncertain"}
            for item in state["items"]
        ):
            state["status"] = "blocked"
            _save_state(output_root, state)
            return state

        pending = [
            item for item in prepared_items
            if state_by_id[item["id"]]["generation_status"] != "complete"
        ]
        if not pending:
            state["status"] = "complete"
            _save_state(output_root, state)
            return state

        def run_job(item: dict) -> tuple[dict, str]:
            raw_result = generator(
                skill_root=skill_root,
                provider=item["provider"],
                prompt=item["prompt"],
                approval_hash=item["approval_digest"],
                size=item["size"],
                quality=item["quality"],
                output_dir=output_root / "artifacts" / item["id"],
                allowed_output_root=output_root / "artifacts",
            )
            final_path = (
                output_root
                / "final"
                / f"{item['page']:02d}-{item['id']}.png"
            )
            try:
                composed_path = compositor(item, raw_result, final_path)
            except GenerationUncertainError:
                raise
            except Exception as exc:
                raise CompositionUncertainError(
                    "付费生图已经完成，但本地合成失败，不得自动重新生成。"
                ) from exc
            return _relative_result(output_root, raw_result), str(composed_path)

        next_index = 0
        futures: dict[Future, dict] = {}
        stopped = False
        state["status"] = "generating"
        _save_state(output_root, state)

        with ThreadPoolExecutor(
            max_workers=min(max_workers, len(pending)),
            thread_name_prefix="xhs-image",
        ) as executor:
            def submit_next() -> bool:
                nonlocal next_index
                if stopped or next_index >= len(pending):
                    return False
                item = pending[next_index]
                next_index += 1
                state_item = state_by_id[item["id"]]
                state_item["generation_status"] = "sending"
                state_item["error"] = None
                _save_state(output_root, state)
                futures[executor.submit(run_job, item)] = item
                return True

            for _ in range(min(max_workers, len(pending))):
                submit_next()

            while futures:
                future = next(as_completed(tuple(futures)))
                item = futures.pop(future)
                state_item = state_by_id[item["id"]]
                try:
                    result, composed_path = future.result()
                except GenerationUncertainError as exc:
                    state_item["generation_status"] = "uncertain"
                    state_item["error"] = str(exc)
                    stopped = True
                except Exception as exc:
                    state_item["generation_status"] = "failed"
                    state_item["error"] = str(exc)
                    stopped = True
                else:
                    state_item["generation_status"] = "complete"
                    state_item["result"] = result
                    final = Path(composed_path).expanduser().resolve()
                    try:
                        state_item["final_path"] = final.relative_to(
                            output_root
                        ).as_posix()
                    except ValueError:
                        state_item["generation_status"] = "uncertain"
                        state_item["error"] = "合成图片路径超出当前用户任务目录。"
                        stopped = True
                _save_state(output_root, state)
                if not stopped:
                    submit_next()

        state["status"] = (
            "complete"
            if all(
                item["generation_status"] == "complete"
                for item in state["items"]
            )
            else "blocked"
        )
        _save_state(output_root, state)
        return state
    finally:
        _release_lock(lock_descriptor)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="并发生成并合成已批准的小红书轮播图片。"
    )
    parser.add_argument("--batch-file", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="最大并发数，默认 3，范围 1-8",
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
