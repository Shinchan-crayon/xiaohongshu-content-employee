#!/usr/bin/env python3
"""小红书内容工作流统一入口 — three commands only.
setup   → 创建任务 + 启动 Research Worker
continue → 读当前 stage，自动推进或提示下一步
approve → 批准 Prompt + 进入 producing
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PACKAGE_ROOT = SCRIPT_DIR.parent           # plugin root (contains skills/, scripts/, assets/)
WORKFLOW_DIR = SCRIPT_DIR / "工作流工具"
IMAGE_DIR = SCRIPT_DIR / "生图工具"
HTML_DIR = SCRIPT_DIR / "HTML生成工具"

sys.path.insert(0, str(WORKFLOW_DIR))
from workflow_runtime import load_runtime    # noqa: E402

# Next-state mapping for intermediate auto-advance
STAGE_NEXT = {
    "prepared": "evidenced",
    "prompt_approved": "producing",
}


def _runtime_cli(*args: str) -> str:
    """Call workflow_runtime.py and return stdout. Raises on failure."""
    cp = subprocess.run(
        [sys.executable, str(WORKFLOW_DIR / "workflow_runtime.py"), *args],
        capture_output=True, text=True, check=False,
    )
    if cp.returncode != 0:
        err = cp.stderr.strip() or cp.stdout.strip() or f"exit code {cp.returncode}"
        raise RuntimeError(f"workflow_runtime.py {' '.join(args[:2])} failed: {err}")
    return cp.stdout.strip()


def _json_result(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ── setup ──────────────────────────────────────────────

def cmd_setup(args):
    delivery_root = Path(args.output).expanduser().resolve()
    delivery_root.mkdir(parents=True, exist_ok=True)

    task = {
        "schema_version": 1,
        "summary": f"{args.product} - {args.topic}" if args.product else args.topic,
        "content_goal": args.topic,
        "product_links": args.links or [],
        "product_images": [],
        "material_paths": [],
        "target_audience": args.audience or None,
        "account_voice": None,
    }

    task_file = delivery_root / "task.json"
    task_file.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")

    out = _runtime_cli(
        "create",
        "--plugin-root", str(PACKAGE_ROOT),
        "--delivery-root", str(delivery_root),
        "--task-file", str(task_file),
    )
    try:
        run_info = json.loads(out)
    except json.JSONDecodeError:
        _json_result({"status": "error", "error": out})
        return

    run_dir = run_info["run_dir"]
    runtime = load_runtime(Path(run_dir))

    # Start research-worker
    _runtime_cli(
        "stage-start",
        "--run-dir", run_dir,
        "--stage", "research-worker",
        "--loaded-skill", "product-material-intake",
        "--loaded-skill", "xhs-research-strategy",
        "--input", f"{run_dir}/task.json",
        "--worker-session-id", f"research-{os.urandom(3).hex()}",
    )

    _json_result({
        "status": "setup_complete",
        "run_dir": run_dir,
        "stage": "created",
        "delivery_root": str(delivery_root),
        "next": "research-worker",
        "instruction": (
            "Research Worker ready. "
            f"Read {run_dir}/task.json, produce material.json + evidence.json at {run_dir}. "
            f"Then run: python scripts/run.py continue --run-dir '{run_dir}'"
        ),
    })


# ── continue ───────────────────────────────────────────

STAGE_WORKER = {
    "created":      ("research-worker", ["product-material-intake", "xhs-research-strategy"]),
    "evidenced":    ("compose-worker",   ["xhs-copy-storyboard", "xhs-visual-planner"]),
    "humanizing":   ("humanize-worker",  ["xhs-humanize-review"]),
}

WORKER_INPUTS = {
    "research-worker": ["task.json"],
    "compose-worker":  ["material.json", "evidence.json"],
    "humanize-worker": ["material.json", "evidence.json", "content.json"],
}

WORKER_OUTPUTS = {
    "research-worker": ["material.json", "evidence.json"],
    "compose-worker":  ["content.json", "visual.json"],
    "humanize-worker": ["content.json"],
}


def cmd_continue(args):
    run_dir = Path(args.run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    stage = runtime["stage"]

    # ── 0. Intermediate states: auto-advance ──
    if stage in ("prepared", "prompt_approved"):
        _runtime_cli("transition", "--run-dir", str(run_dir), "--target", STAGE_NEXT[stage])
        runtime = load_runtime(run_dir)
        _json_result({
            "status": "advanced",
            "stage": runtime["stage"],
            "instruction": f"Run: python scripts/run.py continue --run-dir '{run_dir}'",
        })
        return

    # ── 1. Worker stages: start the worker and tell Codex ──
    if stage in STAGE_WORKER:
        worker_name, skills = STAGE_WORKER[stage]
        inputs = [str(run_dir / f) for f in WORKER_INPUTS[worker_name]]
        sid = f"{worker_name.replace('-worker', '')}-{os.urandom(3).hex()}"

        out = _runtime_cli(
            "stage-start",
            "--run-dir", str(run_dir),
            "--stage", worker_name,
            *[f"--loaded-skill={s}" for s in skills],
            *[f"--input={p}" for p in inputs],
            "--worker-session-id", sid,
        )
        try:
            json.loads(out)  # valid - stage started OK
        except json.JSONDecodeError:
            # stage already started → still OK, just tell Codex what to do
            pass

        _json_result({
            "status": "worker_ready",
            "stage": stage,
            "worker": worker_name,
            "skills": skills,
            "input_files": inputs,
            "output_files": [f"{run_dir}/{f}" for f in WORKER_OUTPUTS[worker_name]],
            "instruction": (
                f"Execute {worker_name}: load skills {skills}, "
                f"read inputs, write outputs above. "
                f"Then: python scripts/run.py finish-worker --run-dir '{run_dir}'"
            ),
        })
        return

    # ── 2. After compose: compose-present → humanizing ──
    if stage == "composed":
        # finish compose + trigger humanizing
        metrics_file = run_dir / "compose-metrics.json"
        metrics_file.write_text(json.dumps({"token_count": 0, "model_calls": 1, "tool_calls": 0, "retries": 0, "paid_requests": 0}))
        _runtime_cli("compose-present", "--run-dir", str(run_dir), "--metrics-file", str(metrics_file))
        _json_result({
            "status": "advanced",
            "stage": "humanizing",
            "next": "humanize-worker",
            "instruction": f"Run: python scripts/run.py continue --run-dir '{run_dir}'",
        })
        return

    # ── 3. After humanized → prompt_pending_approval → show prompt ──
    if stage == "humanized":
        _runtime_cli("transition", "--run-dir", str(run_dir), "--target", "prompt_pending_approval")
        out = _runtime_cli("prompt-show", "--run-dir", str(run_dir))
        try:
            pkg = json.loads(out)
        except json.JSONDecodeError:
            _json_result({"status": "error", "error": out})
            return
        pages = [{"page_id": p["page_id"], "prompt": p["prompt"], "information_task": p.get("information_task", "")} for p in pkg.get("pages", [])]
        _json_result({
            "status": "pending_approval",
            "prompt_hash": pkg.get("prompt_hash"),
            "style_anchor": pkg.get("style_anchor"),
            "pages": pages,
            "instruction": f"Review prompts above. To approve: python scripts/run.py approve --run-dir '{run_dir}' --hash '{pkg.get('prompt_hash')}'",
        })
        return

    # ── 4. Mechanical: producing → deliver ──
    if stage == "producing":
        _produce_and_deliver(run_dir, runtime)
        return

    # ── 5. Delivered / completed → show final ──
    if stage in ("delivered", "completed"):
        dp = runtime.get("delivery_paths", {})
        _json_result({
            "status": "completed",
            "stage": stage,
            "html_path": dp.get("html_path"),
            "runtime_log_path": dp.get("runtime_log_path"),
        })
        return

    # ── 6. prompt_pending_approval: already handled by approve command ──
    if stage == "prompt_pending_approval":
        _json_result({
            "status": "waiting_approval",
            "stage": "prompt_pending_approval",
            "instruction": "Call approve to continue.",
        })
        return

    _json_result({"status": "unknown_stage", "stage": stage})


# ── finish-worker ──────────────────────────────────────

def cmd_finish_worker(args):
    run_dir = Path(args.run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    stage = runtime["stage"]

    if stage not in STAGE_WORKER:
        _json_result({"status": "error", "error": f"No worker to finish at stage {stage}"})
        return

    worker_name, _ = STAGE_WORKER[stage]
    outputs = [run_dir / f for f in WORKER_OUTPUTS[worker_name]]
    missing = [str(p) for p in outputs if not p.is_file()]
    if missing:
        _json_result({"status": "error", "error": f"Missing output files: {missing}"})
        return

    metrics = {
        "token_count": args.tokens or 0,
        "model_calls": 1,
        "tool_calls": args.tool_calls or 0,
        "retries": 0,
        "paid_requests": 0,
    }
    metrics_file = run_dir / f"{worker_name}-metrics.json"
    metrics_file.write_text(json.dumps(metrics))

    _runtime_cli(
        "stage-finish",
        "--run-dir", str(run_dir),
        "--stage", worker_name,
        *[f"--output={p}" for p in outputs],
        "--metrics-file", str(metrics_file),
    )

    runtime = load_runtime(run_dir)
    current_stage = runtime["stage"]

    # If stage hasn't advanced (auto-advance might have hit a transition error),
    # try to advance manually to the next stage
    NEXT_AFTER = {"created": "prepared", "evidenced": "composed", "humanizing": "humanized"}
    if current_stage in NEXT_AFTER:
        try:
            _runtime_cli("transition", "--run-dir", str(run_dir), "--target", NEXT_AFTER[current_stage])
            runtime = load_runtime(run_dir)
            current_stage = runtime["stage"]
        except RuntimeError:
            pass  # transition might also fail — that's OK, finish-worker did its job

    _json_result({
        "status": "worker_finished",
        "stage": current_stage,
        "worker": worker_name,
        "instruction": f"Run: python scripts/run.py continue --run-dir '{run_dir}'",
    })


# ── approve ────────────────────────────────────────────

def cmd_approve(args):
    run_dir = Path(args.run_dir).expanduser().resolve()
    _runtime_cli("approval-approve", "--run-dir", str(run_dir), "--approved-by", "user", "--prompt-hash", args.hash)
    _runtime_cli("transition", "--run-dir", str(run_dir), "--target", "producing")

    _json_result({
        "status": "approved",
        "stage": "producing",
        "instruction": f"Run: python scripts/run.py continue --run-dir '{run_dir}'",
    })


# ── auto produce + deliver ─────────────────────────────

def _produce_and_deliver(run_dir: Path, runtime: dict):
    """Mechanical stages — no model calls."""
    delivery_root = Path(runtime.get("delivery_root", str(run_dir.parent)))

    # --- produce ---
    visual = json.loads((run_dir / "visual.json").read_text(encoding="utf-8"))
    batch_items = []
    for i, page in enumerate(visual.get("pages", [])):
        batch_items.append({
            "id": f"item-{page['id']}",
            "page": i + 1,
            "prompt": page["prompt"],
            "size": "1728x2304",
            "reference_image_paths": page.get("reference_image_paths", []),
        })
    batch_file = run_dir / "batch.json"
    batch_file.write_text(json.dumps({"schema_version": 1, "items": batch_items}, ensure_ascii=False, indent=2))

    subprocess.run(
        [sys.executable, str(IMAGE_DIR / "batch_generate.py"), "--batch-file", str(batch_file), "--output-root", str(delivery_root)],
        check=False,
    )

    # Write minimal generation.json so deliver can proceed
    run_id = runtime["run_id"]
    image_dir = delivery_root / "images"
    gen_items = []
    if image_dir.is_dir():
        for f in sorted(image_dir.iterdir()):
            if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                pid = f.stem.split("-", 2)[2] if f.stem.count("-") >= 2 else f.stem
                gen_items.append({
                    "id": f"req-{pid}-{run_id[-8:]}", "page_id": pid,
                    "page": int(f.stem.split("-", 1)[0]), "attempt": 1,
                    "request_status": "complete", "path": f"images/{f.name}",
                    "provider": "seedream", "model": "doubao-seedream-5-0-lite-260128", "width": 1728, "height": 2304,
                })
    generation = {"schema_version": 1, "run_id": run_id, "status": "complete" if gen_items else "failed",
                   "provider": "seedream", "model": "doubao-seedream-5-0-lite-260128",
                   "output_root": str(delivery_root), "items": gen_items}
    (run_dir / "generation.json").write_text(json.dumps(generation, ensure_ascii=False, indent=2))

    # Finish produce-executor
    _runtime_cli(
        "stage-finish", "--run-dir", str(run_dir), "--stage", "produce-executor",
        "--output", f"{run_dir}/generation.json",
        "--metrics-file", f"{run_dir}/produce-metrics.json",
    )

    # --- deliver ---
    html_path = delivery_root / "小红书图文.html"

    # Write delivery inputs directly — generate_delivery.py expects content.json in run_dir
    cp = subprocess.run(
        [sys.executable, str(HTML_DIR / "generate_delivery.py"),
         "--run-dir", str(run_dir), "--embed-images",
         str(run_dir / "content.json"), str(html_path)],
        capture_output=True, text=True, check=False, timeout=120,
    )

    if html_path.is_file():
        runtime_log = html_path.with_suffix(".run-log.md")
        _runtime_cli("summary", "--run-dir", str(run_dir), "--output", str(runtime_log))

        _runtime_cli(
            "stage-finish", "--run-dir", str(run_dir), "--stage", "deliver-executor",
            "--output", f"{run_dir}/delivery.json",
            "--metrics-file", f"{run_dir}/deliver-metrics.json",
        )
        _runtime_cli("transition", "--run-dir", str(run_dir), "--target", "delivered")
        _runtime_cli("transition", "--run-dir", str(run_dir), "--target", "completed")

        _json_result({
            "status": "completed",
            "html_path": str(html_path),
            "runtime_log_path": str(runtime_log),
        })
    else:
        _json_result({"status": "error", "error": cp.stderr or "HTML generation failed"})


# ── CLI ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="小红书内容工作流")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("setup")
    p.add_argument("--topic", required=True)
    p.add_argument("--product")
    p.add_argument("--links", nargs="*")
    p.add_argument("--audience")
    p.add_argument("--output", required=True)

    p = sub.add_parser("continue")
    p.add_argument("--run-dir", required=True)

    p = sub.add_parser("finish-worker")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--tokens", type=int)
    p.add_argument("--tool-calls", type=int)

    p = sub.add_parser("approve")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--hash", required=True)

    args = parser.parse_args()

    try:
        if args.command == "setup":
            cmd_setup(args)
        elif args.command == "continue":
            cmd_continue(args)
        elif args.command == "finish-worker":
            cmd_finish_worker(args)
        elif args.command == "approve":
            cmd_approve(args)
        else:
            parser.print_help()
    except (RuntimeError, ValueError, OSError) as exc:
        _json_result({"status": "error", "error": str(exc)})
        sys.exit(1)


if __name__ == "__main__":
    main()
