#!/usr/bin/env python3
"""批准有效后，把整批最终 Prompt 并发发送给已选择的图片模型。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from generate_image import (
    DownloadPendingError,
    GenerationUncertainError,
    extension_from_url,
    generate_image,
    load_raw_config,
    recover_download,
    resolve_selected_provider,
)
from provider_registry import provider_supports_reference_images


WORKFLOW_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "工作流工具"
if str(WORKFLOW_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_RUNTIME_DIR))

from workflow_runtime import (  # noqa: E402
    finish_stage,
    load_runtime,
    start_stage,
    utc_now,
    write_artifact,
)


DEFAULT_MAX_WORKERS = 0


class BatchGenerationError(RuntimeError):
    """批量生图无法执行。"""


def validate_max_workers(value: int | None) -> int:
    if value is None:
        return DEFAULT_MAX_WORKERS
    if value < 0:
        raise ValueError("并发数不能小于 0；0 表示全部并发。")
    return value


def normalize_batch(batch: dict) -> list[dict]:
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
        prompt = str(raw.get("prompt") or "").strip()
        try:
            page = int(raw.get("page"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"图片项目页码无效：{item_id or 'unknown'}") from exc
        if not item_id or item_id in seen_ids:
            raise ValueError(f"图片项目 ID 为空或重复：{item_id}")
        if page < 1 or page in seen_pages:
            raise ValueError(f"图片项目页码无效或重复：{page}")
        if not prompt:
            raise ValueError(f"图片项目 Prompt 为空：{item_id}")
        raw_reference_paths = raw.get("reference_image_paths", [])
        if not isinstance(raw_reference_paths, list):
            raise ValueError(
                f"图片项目 reference_image_paths 必须是数组：{item_id}"
            )
        reference_image_paths = [
            str(path).strip()
            for path in raw_reference_paths
            if str(path).strip()
        ]
        seen_ids.add(item_id)
        seen_pages.add(page)
        items.append(
            {
                "id": item_id,
                "page": page,
                "prompt": prompt,
                "reference_image_paths": reference_image_paths,
            }
        )
    return sorted(items, key=lambda item: item["page"])


def validate_output_root(plugin_root: Path, output_root: Path) -> Path:
    root = output_root.expanduser().resolve()
    plugin = plugin_root.expanduser().resolve()
    if root == plugin or plugin in root.parents:
        raise ValueError("生图输出目录不能位于插件成品目录内。")
    root.mkdir(parents=True, exist_ok=True)
    return root


def copy_to_final(item: dict, result: dict, output_root: Path) -> Path:
    source = Path(str(result.get("image_path") or "")).expanduser().resolve()
    if not source.is_file():
        raise BatchGenerationError("图片渠道没有返回可保存的图片文件。")
    suffix = source.suffix.lower() or ".png"
    destination = output_root / "images" / f"{item['page']:02d}-{item['id']}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def _latest_records(items: list[dict]) -> dict[str, dict]:
    latest = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        page_id = str(item.get("page_id") or "")
        if not page_id:
            continue
        current = latest.get(page_id)
        if current is None or int(item.get("attempt") or 0) > int(
            current.get("attempt") or 0
        ):
            latest[page_id] = item
    return latest


class GenerationStateRecorder:
    def __init__(
        self,
        run_dir: Path,
        output_root: Path,
        allow_existing: bool = False,
    ):
        self.run_dir = Path(run_dir).expanduser().resolve()
        self.run_id = load_runtime(self.run_dir)["run_id"]
        self.output_root = Path(output_root).expanduser().resolve()
        self.lock = threading.Lock()
        self.items = []
        self.status = "in_progress"
        existing_path = self.run_dir / "generation.json"
        if existing_path.is_file():
            try:
                existing = json.loads(existing_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise BatchGenerationError(
                    f"已有 generation.json 无法读取，禁止重复提交：{exc}"
                ) from exc
            if not isinstance(existing, dict):
                raise BatchGenerationError(
                    "已有 generation.json 格式无效，禁止重复提交。"
                )
            if existing.get("run_id") != self.run_id:
                raise BatchGenerationError(
                    "已有 generation.json 与当前运行不匹配，禁止重复提交。"
                )
            existing_items = existing.get("items")
            if not isinstance(existing_items, list):
                raise BatchGenerationError(
                    "已有 generation.json.items 格式无效，禁止重复提交。"
                )
            if existing_items and not allow_existing:
                if any(
                    item.get("request_status") == "download_pending"
                    for item in existing_items
                    if isinstance(item, dict)
                ):
                    raise BatchGenerationError(
                        "已有 download_pending 请求，只允许恢复已有 URL，"
                        "禁止重新提交生图。"
                    )
                raise BatchGenerationError(
                    "已有生图请求状态，禁止重复提交付费请求。"
                )
            self.items = self._normalize_existing_items(existing_items)
            self.status = str(existing.get("status") or "failed")
        self._flush()

    def _normalize_existing_items(self, items: list[dict]) -> list[dict]:
        normalized = []
        next_attempt: dict[str, int] = {}
        for raw_item in items:
            if not isinstance(raw_item, dict):
                continue
            record = dict(raw_item)
            page_id = str(record.get("page_id") or "").strip()
            if not page_id:
                continue
            fallback_attempt = next_attempt.get(page_id, 0) + 1
            attempt = record.get("attempt")
            if (
                not isinstance(attempt, int)
                or isinstance(attempt, bool)
                or attempt < 1
            ):
                attempt = fallback_attempt
            next_attempt[page_id] = max(next_attempt.get(page_id, 0), attempt)
            record.setdefault(
                "request_id",
                f"req-{page_id}-{uuid.uuid4().hex[:8]}",
            )
            record.setdefault("page", 0)
            record.setdefault("provider", "unknown")
            record.setdefault("model", "unknown")
            record.setdefault("request_status", "failed")
            record.setdefault("started_at", utc_now())
            record.setdefault("response_received_at", None)
            record.setdefault("download_started_at", None)
            record.setdefault("completed_at", None)
            record["attempt"] = attempt
            record.setdefault("token_count", None)
            record.setdefault("cost_amount", None)
            record.setdefault("cost_currency", None)
            record.setdefault("error", None)
            normalized.append(record)
        return normalized

    def _flush(self) -> None:
        payload = {
            "schema_version": 1,
            "run_id": self.run_id,
            "status": self.status,
            "output_root": str(self.output_root),
            "items": sorted(
                self.items,
                key=lambda item: (
                    item.get("page", 0),
                    item.get("attempt", 0),
                ),
            ),
        }
        write_artifact(self.run_dir, "generation.json", payload)

    def begin(self, item: dict, provider: str) -> dict:
        with self.lock:
            attempts = [
                int(record.get("attempt") or 0)
                for record in self.items
                if record.get("page_id") == item["id"]
            ]
            record = {
                "request_id": f"req-{item['id']}-{uuid.uuid4().hex[:8]}",
                "page_id": item["id"],
                "page": item["page"],
                "provider": str(provider or "unknown"),
                "model": "unknown",
                "request_status": "request_started",
                "started_at": utc_now(),
                "response_received_at": None,
                "download_started_at": None,
                "completed_at": None,
                "attempt": (max(attempts) if attempts else 0) + 1,
                "token_count": None,
                "cost_amount": None,
                "cost_currency": None,
                "error": None,
            }
            self.items.append(record)
            self.status = "in_progress"
            self._flush()
            return record

    def update(self, item: dict, event: dict) -> None:
        with self.lock:
            normalized_event = dict(event)
            if (
                normalized_event.get("request_status") == "complete"
                and not str(normalized_event.get("path") or "").strip()
            ):
                normalized_event["request_status"] = "response_received"
            matching = [
                record
                for record in self.items
                if record.get("page_id") == item["id"]
            ]
            if not matching:
                raise BatchGenerationError(
                    f"页面 {item['id']} 尚未创建生图请求记录。"
                )
            record = max(
                matching,
                key=lambda value: int(value.get("attempt") or 0),
            )
            request_status = normalized_event.get("request_status")
            event_time = utc_now()
            if request_status == "request_started":
                record["started_at"] = record.get("started_at") or event_time
            elif request_status == "response_received":
                record["response_received_at"] = event_time
            elif request_status == "download_pending":
                record["response_received_at"] = (
                    record.get("response_received_at") or event_time
                )
                record["download_started_at"] = event_time
            elif request_status == "complete":
                record["response_received_at"] = (
                    record.get("response_received_at") or event_time
                )
                record["download_started_at"] = (
                    record.get("download_started_at") or event_time
                )
                record["completed_at"] = event_time
            elif request_status in {"failed", "uncertain"}:
                record["completed_at"] = event_time
            for key in (
                "request_status",
                "provider",
                "model",
                "requested_size",
                "path",
                "source_url",
                "error",
                "token_count",
                "token_status",
                "cost_amount",
                "cost_currency",
                "cost_status",
            ):
                if key not in normalized_event:
                    continue
                value = normalized_event[key]
                if key in {"token_count", "cost_amount", "cost_currency"}:
                    if value is None or value == "":
                        continue
                if key == "token_status":
                    if (
                        value == "unavailable"
                        and record.get("token_status") == "reported"
                    ):
                        continue
                if key == "cost_status":
                    if (
                        value == "unavailable"
                        and record.get("cost_status") == "reported"
                    ):
                        continue
                record[key] = value
            self._flush()

    def finish(self) -> str:
        with self.lock:
            latest = _latest_records(self.items)
            self.status = (
                "complete"
                if latest
                and all(
                    item.get("request_status") == "complete"
                    for item in latest.values()
                )
                else "failed"
            )
            self._flush()
            return self.status


def pending_destination(item: dict, source_url: str, output_root: Path) -> Path:
    suffix = extension_from_url(source_url)
    return (
        output_root
        / "images"
        / f"{item['page']:02d}-{item['id']}{suffix}"
    )


def recover_pending_downloads(run_dir: Path, output_root: Path) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    recorder = GenerationStateRecorder(
        run_dir,
        output_root,
        allow_existing=True,
    )
    recovered = 0
    failed = 0
    for item in recorder.items:
        if item.get("request_status") != "download_pending":
            continue
        source_url = str(item.get("source_url") or "").strip()
        relative_path = str(item.get("path") or "").strip()
        if not source_url or not relative_path:
            failed += 1
            continue
        try:
            raw_path = Path(relative_path).expanduser()
            if raw_path.is_absolute():
                raise ValueError("恢复路径必须位于输出目录内。")
            destination = (output_root / raw_path).resolve()
            if destination == output_root or output_root not in destination.parents:
                raise ValueError("恢复路径不能越过输出目录。")
            item["download_started_at"] = utc_now()
            recovered_path = recover_download(
                source_url,
                destination,
            )
            item["path"] = recovered_path.relative_to(output_root).as_posix()
            item["request_status"] = "complete"
            item["completed_at"] = utc_now()
            item["error"] = None
            recovered += 1
        except Exception as exc:
            item["request_status"] = "failed"
            item["completed_at"] = utc_now()
            item["error"] = str(exc) or exc.__class__.__name__
            failed += 1
    status = recorder.finish()
    return {
        "status": status,
        "recovered": recovered,
        "failed": failed,
    }


def batch_generate(
    plugin_root: Path,
    batch: dict,
    output_root: Path,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    provider: str | None = None,
    generator: Callable = generate_image,
    run_dir: Path | None = None,
    _allow_existing: bool = False,
) -> dict:
    plugin_root = Path(plugin_root).resolve()
    output_root = validate_output_root(plugin_root, Path(output_root))
    items = normalize_batch(batch)
    raw_config = (
        load_raw_config(plugin_root)
        if provider is None or (plugin_root / "config.json").is_file()
        else {}
    )
    selected_provider = resolve_selected_provider(raw_config, provider)
    if any(item["reference_image_paths"] for item in items):
        if not provider_supports_reference_images(selected_provider):
            raise BatchGenerationError(
                f"{selected_provider} 不支持产品参考图，请改用支持参考图的生图渠道。"
            )
    worker_limit = validate_max_workers(max_workers)
    workers = len(items) if worker_limit == 0 else min(worker_limit, len(items))
    recorder = (
        GenerationStateRecorder(
            run_dir,
            output_root,
            allow_existing=_allow_existing,
        )
        if run_dir is not None
        else None
    )

    def run_job(item: dict) -> dict:
        if recorder is not None:
            recorder.begin(item, selected_provider)
        with tempfile.TemporaryDirectory(prefix="xhs-image-") as temporary:
            lifecycle_callback = (
                (lambda event: recorder.update(item, event))
                if recorder is not None
                else None
            )
            try:
                arguments = {
                    "plugin_root": plugin_root,
                    "provider": selected_provider,
                    "prompt": item["prompt"],
                    "output_dir": Path(temporary),
                    "reference_image_paths": [
                        Path(path) for path in item["reference_image_paths"]
                    ],
                }
                if lifecycle_callback is not None:
                    arguments["lifecycle_callback"] = lifecycle_callback
                result = generator(
                    **arguments,
                )
                final_path = copy_to_final(item, result, output_root)
                if recorder is not None:
                    recorder.update(
                        item,
                        {
                            "request_status": "complete",
                            "provider": result["provider"],
                            "model": result["model"],
                            "path": final_path.relative_to(output_root).as_posix(),
                            "error": None,
                            "token_count": result.get("token_count"),
                            "token_status": result.get(
                                "token_status",
                                "unavailable",
                            ),
                            "cost_amount": result.get("cost_amount"),
                            "cost_currency": result.get("cost_currency"),
                            "cost_status": result.get(
                                "cost_status",
                                "unavailable",
                            ),
                        },
                    )
                return {
                    "id": item["id"],
                    "page": item["page"],
                    "generation_status": "complete",
                    "path": final_path.relative_to(output_root).as_posix(),
                    "provider": result["provider"],
                    "model": result["model"],
                    "width": result.get("width"),
                    "height": result.get("height"),
                    "token_count": result.get("token_count"),
                    "token_status": result.get("token_status", "unavailable"),
                    "cost_amount": result.get("cost_amount"),
                    "cost_currency": result.get("cost_currency"),
                    "cost_status": result.get("cost_status", "unavailable"),
                    "error": None,
                }
            except DownloadPendingError as exc:
                destination = pending_destination(
                    item,
                    exc.source_url,
                    output_root,
                )
                relative_path = destination.relative_to(output_root).as_posix()
                if recorder is not None:
                    recorder.update(
                        item,
                        {
                            "request_status": "download_pending",
                            "provider": exc.provider,
                            "model": exc.model,
                            "requested_size": exc.requested_size,
                            "source_url": exc.source_url,
                            "path": relative_path,
                            "error": str(exc),
                        },
                    )
                return {
                    "id": item["id"],
                    "page": item["page"],
                    "generation_status": "download_pending",
                    "path": relative_path,
                    "provider": exc.provider,
                    "model": exc.model,
                    "width": None,
                    "height": None,
                    "error": str(exc),
                    "source_url": exc.source_url,
                }
            except GenerationUncertainError as exc:
                if recorder is not None:
                    recorder.update(
                        item,
                        {
                            "request_status": "uncertain",
                            "provider": selected_provider,
                            "model": "unknown",
                            "error": str(exc),
                        },
                    )
                return {
                    "id": item["id"],
                    "page": item["page"],
                    "generation_status": "uncertain",
                    "path": None,
                    "provider": selected_provider,
                    "model": None,
                    "width": None,
                    "height": None,
                    "error": str(exc),
                }
            except Exception as exc:
                if recorder is not None:
                    recorder.update(
                        item,
                        {
                            "request_status": "failed",
                            "provider": selected_provider,
                            "model": "unknown",
                            "error": str(exc) or exc.__class__.__name__,
                        },
                    )
                return {
                    "id": item["id"],
                    "page": item["page"],
                    "generation_status": "failed",
                    "path": None,
                    "provider": selected_provider,
                    "model": None,
                    "width": None,
                    "height": None,
                    "error": str(exc) or exc.__class__.__name__,
                }

    results = []
    with ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="xhs-image",
    ) as executor:
        futures = {executor.submit(run_job, item): item for item in items}
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item["page"])
    completed = [item for item in results if item["generation_status"] == "complete"]
    failed = [item for item in results if item["generation_status"] == "failed"]
    incomplete = [
        item for item in results if item["generation_status"] != "complete"
    ]
    status = (
        "complete"
        if not incomplete
        else "failed"
    )
    if recorder is not None:
        status = recorder.finish()
    return {
        "status": status,
        "provider": selected_provider,
        "generated_images": completed,
        "failed_pages": incomplete,
    }


def manual_retry_page(
    plugin_root: Path,
    batch: dict,
    output_root: Path,
    run_dir: Path,
    page_id: str,
    confirmed: bool,
    provider: str | None = None,
    generator: Callable = generate_image,
) -> dict:
    if not confirmed:
        raise BatchGenerationError("人工确认后才能重新发起生图请求。")
    normalized_items = normalize_batch(batch)
    selected = [
        item for item in normalized_items if item["id"] == str(page_id).strip()
    ]
    if len(selected) != 1:
        raise BatchGenerationError(f"找不到需要重试的页面：{page_id}")
    run_dir = Path(run_dir).expanduser().resolve()
    state_path = run_dir / "generation.json"
    if not state_path.is_file():
        raise BatchGenerationError("缺少 generation.json，不能人工重试。")
    existing = json.loads(state_path.read_text(encoding="utf-8"))
    latest = _latest_records(existing.get("items", []))
    previous = latest.get(str(page_id).strip())
    if previous is None:
        raise BatchGenerationError(f"页面没有历史请求记录：{page_id}")
    if previous.get("request_status") not in {"failed", "uncertain"}:
        raise BatchGenerationError(
            "只有 failed 或 uncertain 请求经人工确认后才能重新发起。"
        )
    retry_provider = str(
        provider or previous.get("provider") or ""
    ).strip() or None
    return batch_generate(
        plugin_root=plugin_root,
        batch={"schema_version": 1, "items": selected},
        output_root=output_root,
        provider=retry_provider,
        generator=generator,
        run_dir=run_dir,
        _allow_existing=True,
    )


def build_executor_metrics(run_dir: Path) -> dict:
    generation_path = Path(run_dir).expanduser().resolve() / "generation.json"
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    items = [
        item
        for item in generation.get("items", [])
        if isinstance(item, dict)
    ]
    token_values = [
        item["token_count"]
        for item in items
        if isinstance(item.get("token_count"), int)
        and not isinstance(item.get("token_count"), bool)
        and item["token_count"] >= 0
    ]
    costs = [
        (str(item.get("cost_currency") or "").strip().upper(), item["cost_amount"])
        for item in items
        if isinstance(item.get("cost_amount"), (int, float))
        and not isinstance(item.get("cost_amount"), bool)
        and item["cost_amount"] >= 0
        and str(item.get("cost_currency") or "").strip()
    ]
    currencies = {currency for currency, _amount in costs}
    cost_reported = bool(costs) and len(currencies) == 1
    return {
        "token_count": sum(token_values) if token_values else None,
        "model_calls": 0,
        "tool_calls": 1,
        "retries": sum(
            max(0, int(item.get("attempt") or 1) - 1)
            for item in items
        ),
        "paid_requests": len(items),
        "cost_amount": (
            sum(float(amount) for _currency, amount in costs)
            if cost_reported
            else None
        ),
        "cost_currency": next(iter(currencies)) if cost_reported else None,
        "cost_status": "reported" if cost_reported else "unavailable",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批准有效后，把整批最终 Prompt 并发发送给已选择的图片模型。"
    )
    parser.add_argument("--batch-file", type=Path)
    parser.add_argument(
        "--recover-downloads",
        action="store_true",
        help="只恢复 generation.json 中已有 URL 的下载，不重新生图",
    )
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="最大并发数；0 表示全部并发",
    )
    parser.add_argument("--provider", help="临时覆盖 config.json 中的默认渠道")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plugin_root = Path(__file__).resolve().parents[2]
    try:
        if args.recover_downloads:
            if args.run_dir is None:
                raise ValueError("恢复下载必须提供 --run-dir。")
            result = recover_pending_downloads(args.run_dir, args.output_root)
        else:
            if args.batch_file is None:
                raise ValueError("正常生图必须提供 --batch-file。")
            batch = json.loads(args.batch_file.read_text(encoding="utf-8"))
            if args.run_dir is not None:
                start_stage(
                    args.run_dir,
                    "produce-executor",
                    [],
                    [
                        args.run_dir / "visual.json",
                        args.run_dir / "approval.json",
                    ],
                )
            result = batch_generate(
                plugin_root=plugin_root,
                batch=batch,
                output_root=args.output_root,
                max_workers=args.max_workers,
                provider=args.provider,
                run_dir=args.run_dir,
            )
            if args.run_dir is not None:
                finish_stage(
                    args.run_dir,
                    "produce-executor",
                    [args.run_dir / "generation.json"],
                    build_executor_metrics(args.run_dir),
                )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
