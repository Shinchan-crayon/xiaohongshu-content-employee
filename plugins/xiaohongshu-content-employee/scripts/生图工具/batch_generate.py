#!/usr/bin/env python3
"""把整批最终 Prompt 直接并发发送给已选择的图片模型。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from generate_image import (
    generate_image,
    load_raw_config,
    resolve_selected_provider,
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
        seen_ids.add(item_id)
        seen_pages.add(page)
        items.append(
            {
                "id": item_id,
                "page": page,
                "prompt": prompt,
                "reference_image_path": str(
                    raw.get("reference_image_path") or ""
                ).strip(),
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


def batch_generate(
    plugin_root: Path,
    batch: dict,
    output_root: Path,
    max_workers: int | None = DEFAULT_MAX_WORKERS,
    provider: str | None = None,
    generator: Callable = generate_image,
) -> dict:
    plugin_root = Path(plugin_root).resolve()
    output_root = validate_output_root(plugin_root, Path(output_root))
    items = normalize_batch(batch)
    selected_provider = resolve_selected_provider(
        load_raw_config(plugin_root),
        provider,
    )
    worker_limit = validate_max_workers(max_workers)
    workers = len(items) if worker_limit == 0 else min(worker_limit, len(items))

    def run_job(item: dict) -> dict:
        with tempfile.TemporaryDirectory(prefix="xhs-image-") as temporary:
            try:
                result = generator(
                    plugin_root=plugin_root,
                    provider=selected_provider,
                    prompt=item["prompt"],
                    output_dir=Path(temporary),
                    reference_image_path=(
                        Path(item["reference_image_path"])
                        if item["reference_image_path"]
                        else None
                    ),
                )
                final_path = copy_to_final(item, result, output_root)
                return {
                    "id": item["id"],
                    "page": item["page"],
                    "generation_status": "complete",
                    "path": final_path.relative_to(output_root).as_posix(),
                    "provider": result["provider"],
                    "model": result["model"],
                    "width": result.get("width"),
                    "height": result.get("height"),
                    "error": None,
                }
            except Exception as exc:
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
    status = "complete" if not failed else ("partial" if completed else "failed")
    return {
        "status": status,
        "provider": selected_provider,
        "generated_images": completed,
        "failed_pages": failed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把整批最终 Prompt 直接并发发送给已选择的图片模型。"
    )
    parser.add_argument("--batch-file", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
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
        batch = json.loads(args.batch_file.read_text(encoding="utf-8"))
        result = batch_generate(
            plugin_root=plugin_root,
            batch=batch,
            output_root=args.output_root,
            max_workers=args.max_workers,
            provider=args.provider,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"complete", "partial"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
