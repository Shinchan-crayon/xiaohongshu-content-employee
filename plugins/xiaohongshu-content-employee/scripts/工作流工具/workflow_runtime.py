#!/usr/bin/env python3
"""小红书内容工作流的结构化产物、阶段顺序和外部运行状态。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Optional


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = PLUGIN_ROOT / "assets" / "workflow-contracts.json"
RUNTIME_FILE = "runtime.json"
ARTIFACT_NAMES = (
    "task.json",
    "material.json",
    "evidence.json",
    "content.json",
    "visual.json",
    "approval.json",
    "generation.json",
    "delivery.json",
    "runtime.json",
)
WRITABLE_ARTIFACT_NAMES = tuple(
    name for name in ARTIFACT_NAMES if name != RUNTIME_FILE
)
STATE_PATH = (
    "created",
    "prepared",
    "evidenced",
    "composed",
    "humanizing",
    "humanized",
    "prompt_pending_approval",
    "prompt_approved",
    "producing",
    "delivered",
    "completed",
)
LEGAL_TRANSITIONS = {
    current: {STATE_PATH[index + 1]} if index + 1 < len(STATE_PATH) else set()
    for index, current in enumerate(STATE_PATH)
}
REQUIRED_ARTIFACTS = {
    "prepared": ("material.json",),
    "evidenced": ("material.json", "evidence.json"),
    "composed": (
        "material.json",
        "evidence.json",
        "content.json",
        "visual.json",
    ),
    "humanizing": (
        "material.json",
        "evidence.json",
        "content.json",
        "visual.json",
    ),
    "humanized": (
        "material.json",
        "evidence.json",
        "content.json",
        "visual.json",
    ),
    "prompt_pending_approval": ("visual.json", "approval.json"),
    "prompt_approved": ("visual.json", "approval.json"),
    "producing": ("visual.json", "approval.json"),
    "delivered": ("generation.json", "delivery.json"),
    "completed": ("delivery.json",),
}
STAGE_TRANSITION_REQUIREMENTS = {
    "prepared": "research-worker",
    "evidenced": "research-worker",
    "composed": "compose-worker",
    "humanized": "humanize-worker",
    "delivered": "deliver-executor",
}
METRIC_FIELDS = (
    "token_count",
    "model_calls",
    "tool_calls",
    "retries",
    "paid_requests",
)
STAGE_LABELS = {
    "research-worker": "商品研究、身份与证据",
    "compose-worker": "文案与视觉",
    "humanize-worker": "文案自然化",
    "produce-executor": "并发生图",
    "deliver-executor": "HTML 交付",
}
MODEL_WORKER_IDS = (
    "research-worker",
    "compose-worker",
    "humanize-worker",
)
EXECUTOR_IDS = ("produce-executor", "deliver-executor")
INTERNAL_COPY_PHRASES = (
    "先锁定产品身份",
    "官方页面标题",
    "来源台账",
    "事实边界",
    "不可改写事实",
    "claim_ids",
    "post_claim_ids",
    "fact_check",
    "material_record",
    "workflow runtime",
    "stage transition",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> Optional[datetime]:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _duration_ms(started_at: object, finished_at: object) -> Optional[int]:
    started = _parse_timestamp(started_at)
    finished = _parse_timestamp(finished_at)
    if started is None or finished is None or finished < started:
        return None
    return round((finished - started).total_seconds() * 1000)


def _format_duration(duration_ms: Optional[int]) -> str:
    if duration_ms is None:
        return "未记录"
    total_seconds = max(0, round(duration_ms / 1000))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小时{minutes}分{seconds}秒"
    if minutes:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


def load_contracts() -> dict:
    try:
        payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取工作流契约：{exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("工作流契约版本无效。")
    if set(payload.get("artifacts") or {}) != set(ARTIFACT_NAMES):
        raise ValueError("工作流契约中的产物集合无效。")
    workers = payload.get("workers")
    if not isinstance(workers, dict) or set(workers) != set(MODEL_WORKER_IDS):
        raise ValueError("工作流契约中的 Worker 集合无效。")
    executors = payload.get("executors")
    if (
        not isinstance(executors, dict)
        or set(executors) != set(EXECUTOR_IDS)
    ):
        raise ValueError("工作流契约中的执行器集合无效。")
    state_path = payload.get("state_machine", {}).get("path")
    if state_path != list(STATE_PATH):
        raise ValueError("工作流契约中的状态机路径无效。")
    return payload


def default_runtime_root() -> Path:
    configured = str(os.environ.get("XHS_RUNTIME_ROOT") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    state_root = str(os.environ.get("XDG_STATE_HOME") or "").strip()
    if state_root:
        return (
            Path(state_root).expanduser().resolve()
            / "xiaohongshu-content-employee"
            / "runs"
        )
    return (
        Path.home().expanduser().resolve()
        / ".local"
        / "state"
        / "xiaohongshu-content-employee"
        / "runs"
    )


def _is_inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _atomic_write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def _atomic_write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(content)
            if not content.endswith("\n"):
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def _load_json(path: Path, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取{label}：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label}必须是 JSON 对象。")
    return payload


def _require_fields(payload: dict, fields: Iterable[str], label: str) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(f"{label}缺少字段：{', '.join(missing)}")


def _require_text(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label}不能为空。")
    return normalized


def _require_list(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{label}必须是数组。")
    return value


def _require_dict(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label}必须是对象。")
    return value


def _validate_id(value: object, kind: str, contracts: dict, label: str) -> str:
    normalized = _require_text(value, label)
    pattern = contracts["id_patterns"][kind]
    if re.fullmatch(pattern, normalized) is None:
        raise ValueError(f"{label}不是合法 ID：{normalized}")
    return normalized


def _validate_id_list(
    values: object,
    kind: str,
    contracts: dict,
    label: str,
) -> list[str]:
    result = []
    for index, value in enumerate(_require_list(values, label)):
        result.append(
            _validate_id(value, kind, contracts, f"{label}[{index}]")
        )
    return result


def _ensure_unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label}包含重复 ID。")


def _artifact_path(run_dir: Path, artifact_name: str) -> Path:
    if artifact_name not in ARTIFACT_NAMES:
        raise ValueError(f"未知工作流产物：{artifact_name}")
    return run_dir / artifact_name


def _load_artifact_if_present(run_dir: Path, artifact_name: str) -> Optional[dict]:
    path = _artifact_path(run_dir, artifact_name)
    if not path.is_file():
        return None
    return _load_json(path, artifact_name)


def _validate_material(payload: dict, contracts: dict) -> None:
    product_identity = _require_dict(
        payload["product_identity"],
        "product_identity",
    )
    identity_fields = contracts["artifacts"]["material.json"][
        "nested_required"
    ]["product_identity"]
    _require_fields(
        product_identity,
        identity_fields,
        "product_identity",
    )
    for field in (
        "source_url",
        "exact_page_title",
        "brand",
        "name",
        "category",
    ):
        _require_text(product_identity[field], f"product_identity.{field}")
    if not str(product_identity["source_url"]).startswith(("https://", "http://")):
        raise ValueError("product_identity.source_url 必须是 HTTP(S) 地址。")
    unresolved_fields = {
        _require_text(value, "product_identity.unresolved_fields[]")
        for value in _require_list(
            product_identity["unresolved_fields"],
            "product_identity.unresolved_fields",
        )
    }
    for field in ("model", "variant"):
        if not str(product_identity[field] or "").strip() and field not in unresolved_fields:
            raise ValueError(
                f"product_identity.{field} 无法确认时必须写入 unresolved_fields。"
            )
    for field in (
        "identifying_terms",
        "locked_terms",
        "forbidden_replacements",
    ):
        values = _require_list(
            product_identity[field],
            f"product_identity.{field}",
        )
        for index, value in enumerate(values):
            _require_text(value, f"product_identity.{field}[{index}]")
    if not product_identity["identifying_terms"]:
        raise ValueError("product_identity.identifying_terms 不能为空。")
    if not product_identity["locked_terms"]:
        raise ValueError("product_identity.locked_terms 不能为空。")

    references = _require_list(
        payload["product_reference_pack"],
        "product_reference_pack",
    )
    reference_ids = []
    for index, reference in enumerate(references):
        item = _require_dict(reference, f"product_reference_pack[{index}]")
        _require_fields(
            item,
            (
                "id",
                "path",
                "role",
                "supported_views",
                "source_claim_ids",
            ),
            f"product_reference_pack[{index}]",
        )
        reference_ids.append(
            _validate_id(
                item["id"],
                "reference",
                contracts,
                f"product_reference_pack[{index}].id",
            )
        )
        _require_text(item["path"], f"product_reference_pack[{index}].path")
        _require_text(item["role"], f"product_reference_pack[{index}].role")
        supported_views = _require_list(
            item["supported_views"],
            f"product_reference_pack[{index}].supported_views",
        )
        if not supported_views:
            raise ValueError(
                f"product_reference_pack[{index}].supported_views 不能为空。"
            )
        for view_index, view in enumerate(supported_views):
            _require_text(
                view,
                (
                    f"product_reference_pack[{index}]"
                    f".supported_views[{view_index}]"
                ),
            )
        _validate_id_list(
            item["source_claim_ids"],
            "claim",
            contracts,
            f"product_reference_pack[{index}].source_claim_ids",
        )
    _ensure_unique(reference_ids, "product_reference_pack")

    selling_points = _require_list(payload["selling_points"], "selling_points")
    selling_point_ids = []
    for index, selling_point in enumerate(selling_points):
        item = _require_dict(selling_point, f"selling_points[{index}]")
        required_fields = contracts["artifacts"]["material.json"][
            "item_required"
        ]["selling_points"]
        _require_fields(
            item,
            required_fields,
            f"selling_points[{index}]",
        )
        selling_point_ids.append(
            _validate_id(
                item["id"],
                "selling_point",
                contracts,
                f"selling_points[{index}].id",
            )
        )
        for field in (
            "product_feature",
            "user_problem",
            "user_benefit",
            "usage_scenario",
        ):
            _require_text(item[field], f"selling_points[{index}].{field}")
        _require_text(
            item["locked_wording"],
            f"selling_points[{index}].locked_wording",
        )
        _validate_id_list(
            item["source_claim_ids"],
            "claim",
            contracts,
            f"selling_points[{index}].source_claim_ids",
        )
        if not isinstance(item["priority"], int) or item["priority"] < 0:
            raise ValueError(f"selling_points[{index}].priority 必须是非负整数。")
        if not isinstance(item["must_use"], bool):
            raise ValueError(f"selling_points[{index}].must_use 必须是布尔值。")
        _require_list(
            item["forbidden_expansions"],
            f"selling_points[{index}].forbidden_expansions",
        )
    _ensure_unique(selling_point_ids, "selling_points")
    _require_list(payload["conflicts"], "conflicts")
    _require_list(payload["missing_material"], "missing_material")


def _validate_evidence(
    payload: dict,
    contracts: dict,
    run_dir: Path,
) -> None:
    sources = _require_list(payload["sources"], "sources")
    source_ids = []
    for index, source in enumerate(sources):
        item = _require_dict(source, f"sources[{index}]")
        _require_fields(item, ("id", "title", "url"), f"sources[{index}]")
        source_ids.append(
            _validate_id(
                item["id"],
                "source",
                contracts,
                f"sources[{index}].id",
            )
        )
        _require_text(item["title"], f"sources[{index}].title")
        url = _require_text(item["url"], f"sources[{index}].url")
        if not url.startswith(("https://", "http://")):
            raise ValueError(f"sources[{index}].url 必须是 HTTP(S) 地址。")
    _ensure_unique(source_ids, "sources")
    source_id_set = set(source_ids)

    claims = _require_list(payload["claims"], "claims")
    claim_ids = []
    for index, claim in enumerate(claims):
        item = _require_dict(claim, f"claims[{index}]")
        _require_fields(
            item,
            ("id", "text", "allowed_wording", "source_ids"),
            f"claims[{index}]",
        )
        claim_ids.append(
            _validate_id(
                item["id"],
                "claim",
                contracts,
                f"claims[{index}].id",
            )
        )
        _require_text(item["text"], f"claims[{index}].text")
        _require_list(item["allowed_wording"], f"claims[{index}].allowed_wording")
        referenced_sources = _validate_id_list(
            item["source_ids"],
            "source",
            contracts,
            f"claims[{index}].source_ids",
        )
        for source_id in referenced_sources:
            if source_id not in source_id_set:
                raise ValueError(f"claims[{index}] 引用了未知来源：{source_id}")
    _ensure_unique(claim_ids, "claims")
    claim_id_set = set(claim_ids)

    # topic_candidates is deprecated — kept optional for backward compat
    topics = payload.get("topic_candidates")
    if topics is not None:
        topics = _require_list(topics, "topic_candidates")
        for index, topic in enumerate(topics):
            item = _require_dict(topic, f"topic_candidates[{index}]")
            _require_fields(item, ("id", "title", "claim_ids"), f"topic_candidates[{index}]")
            _validate_id(item["id"], "topic", contracts, f"topic_candidates[{index}].id")
            _require_text(item["title"], f"topic_candidates[{index}].title")
            for claim_id in _validate_id_list(item["claim_ids"], "claim", contracts, f"topic_candidates[{index}].claim_ids"):
                if claim_id not in claim_id_set:
                    raise ValueError(f"topic_candidates[{index}] 引用了未知事实：{claim_id}")

    selected_topic_id = _validate_id(
        payload["selected_topic_id"],
        "topic",
        contracts,
        "selected_topic_id",
    )
    _require_text(payload["selected_topic_direction"], "selected_topic_direction")
    _validate_id_list(
        payload["selected_topic_claim_ids"],
        "claim",
        contracts,
        "selected_topic_claim_ids",
    )
    backup = payload.get("backup_topic_brief")
    if backup is not None and not isinstance(backup, str):
        raise ValueError("backup_topic_brief 必须是字符串。")

    learning_candidates = _require_list(
        payload.get("learning_candidates", []), "learning_candidates"
    )
    material_payload = _load_artifact_if_present(run_dir, "material.json")
    if material_payload is not None:
        for collection_name in ("product_reference_pack", "selling_points"):
            for index, item in enumerate(
                material_payload.get(collection_name, [])
            ):
                if not isinstance(item, dict):
                    continue
                for claim_id in item.get("source_claim_ids", []):
                    if claim_id not in claim_id_set:
                        raise ValueError(
                            f"{collection_name}[{index}] 引用了未知事实："
                            f"{claim_id}"
                        )


def _known_ids(run_dir: Path) -> tuple[set[str], set[str], set[str]]:
    material_payload = _load_artifact_if_present(run_dir, "material.json")
    evidence_payload = _load_artifact_if_present(run_dir, "evidence.json")
    if material_payload is None or evidence_payload is None:
        raise ValueError("写入内容产物前必须先写入 material.json 和 evidence.json。")
    selling_point_ids = {
        str(item["id"])
        for item in material_payload.get("selling_points", [])
        if isinstance(item, dict) and item.get("id")
    }
    reference_ids = {
        str(item["id"])
        for item in material_payload.get("product_reference_pack", [])
        if isinstance(item, dict) and item.get("id")
    }
    claim_ids = {
        str(item["id"])
        for item in evidence_payload.get("claims", [])
        if isinstance(item, dict) and item.get("id")
    }
    return selling_point_ids, claim_ids, reference_ids


def _check_known_ids(values: list[str], known: set[str], label: str) -> None:
    for value in values:
        if value not in known:
            raise ValueError(f"{label} 引用了未知 ID：{value}")


def _validate_visible_copy(text: str, label: str) -> None:
    normalized = text.casefold()
    matched = [
        phrase
        for phrase in INTERNAL_COPY_PHRASES
        if phrase.casefold() in normalized
    ]
    if matched:
        raise ValueError(
            f"{label} 包含内部工作流术语，请先转写为小红书成稿："
            + ", ".join(matched)
        )


def _reject_forbidden_replacements(
    texts: Iterable[tuple[str, str]],
    product_identity: dict,
) -> None:
    forbidden = [
        str(value).strip()
        for value in product_identity.get("forbidden_replacements", [])
        if str(value).strip()
    ]
    for label, text in texts:
        normalized = text.casefold()
        matched = [term for term in forbidden if term.casefold() in normalized]
        if matched:
            raise ValueError(
                f"{label} 使用了 product_identity.forbidden_replacements "
                "禁用替换词："
                + ", ".join(matched)
            )


def _validate_content(payload: dict, contracts: dict, run_dir: Path) -> None:
    titles = _require_list(payload["titles"], "titles")
    if len(titles) < 5:
        raise ValueError("titles 至少需要 5 个候选标题。")
    visible_copy = []
    for index, title in enumerate(titles):
        title_text = _require_text(title, f"titles[{index}]")
        _validate_visible_copy(title_text, f"titles[{index}]")
        visible_copy.append((f"titles[{index}]", title_text))
    post = _require_text(payload["post"], "post")
    _validate_visible_copy(post, "post")
    visible_copy.append(("post", post))
    selling_point_ids, claim_ids, _reference_ids = _known_ids(run_dir)
    material_payload = _load_artifact_if_present(run_dir, "material.json")
    if material_payload is None:
        raise ValueError("写入 content.json 前必须先写入 material.json。")
    product_identity = material_payload.get("product_identity", {})
    must_use_ids = {
        str(item["id"])
        for item in material_payload.get("selling_points", [])
        if isinstance(item, dict) and item.get("must_use") is True
    }
    post_selling_point_ids = _validate_id_list(
        payload["post_selling_point_ids"],
        "selling_point",
        contracts,
        "post_selling_point_ids",
    )
    _check_known_ids(
        post_selling_point_ids,
        selling_point_ids,
        "post_selling_point_ids",
    )
    post_claim_ids = _validate_id_list(
        payload["post_claim_ids"],
        "claim",
        contracts,
        "post_claim_ids",
    )
    _check_known_ids(post_claim_ids, claim_ids, "post_claim_ids")
    blocks = _require_list(payload["carousel_blocks"], "carousel_blocks")
    page_ids = []
    used_selling_point_ids = set()
    for index, block in enumerate(blocks):
        item = _require_dict(block, f"carousel_blocks[{index}]")
        _require_fields(
            item,
            ("id", "text", "selling_point_ids", "claim_ids"),
            f"carousel_blocks[{index}]",
        )
        page_ids.append(
            _validate_id(
                item["id"],
                "page",
                contracts,
                f"carousel_blocks[{index}].id",
            )
        )
        block_text = _require_text(
            item["text"],
            f"carousel_blocks[{index}].text",
        )
        _validate_visible_copy(
            block_text,
            f"carousel_blocks[{index}].text",
        )
        visible_copy.append((f"carousel_blocks[{index}].text", block_text))
        block_selling_point_ids = _validate_id_list(
            item["selling_point_ids"],
            "selling_point",
            contracts,
            f"carousel_blocks[{index}].selling_point_ids",
        )
        _check_known_ids(
            block_selling_point_ids,
            selling_point_ids,
            f"carousel_blocks[{index}].selling_point_ids",
        )
        used_selling_point_ids.update(block_selling_point_ids)
        _check_known_ids(
            _validate_id_list(
                item["claim_ids"],
                "claim",
                contracts,
                f"carousel_blocks[{index}].claim_ids",
            ),
            claim_ids,
            f"carousel_blocks[{index}].claim_ids",
        )
    _ensure_unique(page_ids, "carousel_blocks")
    missing_must_use = sorted(must_use_ids - used_selling_point_ids)
    if missing_must_use:
        raise ValueError(
            "content.json 未引用 must_use 卖点："
            + ", ".join(missing_must_use)
        )
    missing_post_must_use = sorted(must_use_ids - set(post_selling_point_ids))
    if missing_post_must_use:
        raise ValueError(
            "content.json 正文追溯未引用 must_use 卖点："
            + ", ".join(missing_post_must_use)
        )
    _reject_forbidden_replacements(visible_copy, product_identity)


def _validate_visual(payload: dict, contracts: dict, run_dir: Path) -> None:
    style_anchor = _require_dict(payload["style_anchor"], "style_anchor")
    if not style_anchor:
        raise ValueError("style_anchor 不能为空。")
    selling_point_ids, claim_ids, reference_ids = _known_ids(run_dir)
    material_payload = _load_artifact_if_present(run_dir, "material.json")
    if material_payload is None:
        raise ValueError("写入 visual.json 前必须先写入 material.json。")
    locked_terms = [
        str(value).strip()
        for value in material_payload.get("product_identity", {}).get(
            "locked_terms",
            [],
        )
        if str(value).strip()
    ]
    reference_map = {
        str(item["id"]): {
            "path": str(item["path"]),
            "supported_views": {
                str(view)
                for view in item.get("supported_views", [])
                if str(view).strip()
            },
        }
        for item in material_payload.get("product_reference_pack", [])
        if isinstance(item, dict) and item.get("id") and item.get("path")
    }
    pages = _require_list(payload["pages"], "pages")
    if not pages:
        raise ValueError("visual.pages 至少需要一页。")
    page_ids = []
    product_compositions = set()
    for index, page in enumerate(pages):
        item = _require_dict(page, f"pages[{index}]")
        _require_fields(
            item,
            (
                "id",
                "page_role",
                "shot_type",
                "subject_position",
                "subject_scale",
                "background_scene",
                "text_zone",
                "information_task",
                "prompt",
                "product_subject",
                "product_view",
                "reference_image_ids",
                "reference_image_paths",
                "selling_point_ids",
                "claim_ids",
            ),
            f"pages[{index}]",
        )
        page_ids.append(
            _validate_id(
                item["id"],
                "page",
                contracts,
                f"pages[{index}].id",
            )
        )
        for field in (
            "page_role",
            "shot_type",
            "subject_position",
            "subject_scale",
            "background_scene",
            "text_zone",
            "information_task",
            "prompt",
        ):
            _require_text(item[field], f"pages[{index}].{field}")
        if not isinstance(item["product_subject"], bool):
            raise ValueError(f"pages[{index}].product_subject 必须是布尔值。")
        selected_reference_ids = _validate_id_list(
            item["reference_image_ids"],
            "reference",
            contracts,
            f"pages[{index}].reference_image_ids",
        )
        _check_known_ids(
            selected_reference_ids,
            reference_ids,
            f"pages[{index}].reference_image_ids",
        )
        reference_paths = _require_list(
            item["reference_image_paths"],
            f"pages[{index}].reference_image_paths",
        )
        for path_index, path in enumerate(reference_paths):
            _require_text(
                path,
                f"pages[{index}].reference_image_paths[{path_index}]",
            )
        if item["product_subject"]:
            if not selected_reference_ids or not reference_paths:
                raise ValueError(
                    f"pages[{index}] 产品主体页必须绑定真实产品参考图。"
                )
            for path_index, reference_path in enumerate(reference_paths):
                raw_path = Path(reference_path).expanduser()
                resolved_path = (
                    raw_path.resolve()
                    if raw_path.is_absolute()
                    else (run_dir / raw_path).resolve()
                )
                if not resolved_path.is_file():
                    raise ValueError(
                        f"pages[{index}].reference_image_paths[{path_index}] "
                        "对应的真实产品参考图不存在。"
                    )
            expected_paths = [
                reference_map[reference_id]["path"]
                for reference_id in selected_reference_ids
            ]
            if reference_paths != expected_paths:
                raise ValueError(
                    f"pages[{index}] 参考图路径与 reference_image_ids 不匹配。"
                )
            missing_locked_terms = [
                term for term in locked_terms if term not in item["prompt"]
            ]
            if missing_locked_terms:
                raise ValueError(
                    f"pages[{index}].prompt 缺少锁定产品身份 locked_terms："
                    + ", ".join(missing_locked_terms)
                )
            product_view = _require_text(
                item["product_view"],
                f"pages[{index}].product_view",
            )
            supported_views = set()
            for reference_id in selected_reference_ids:
                supported_views.update(
                    reference_map[reference_id]["supported_views"]
                )
            if product_view not in supported_views:
                raise ValueError(
                    f"pages[{index}].product_view 不受参考图支持："
                    f"{product_view}"
                )
            composition = tuple(
                item[field]
                for field in (
                    "page_role",
                    "shot_type",
                    "subject_position",
                    "subject_scale",
                    "background_scene",
                    "text_zone",
                )
            )
            if composition in product_compositions:
                raise ValueError(
                    f"pages[{index}] 与其他产品主体页的构图字段完全相同。"
                )
            product_compositions.add(composition)
        _check_known_ids(
            _validate_id_list(
                item["selling_point_ids"],
                "selling_point",
                contracts,
                f"pages[{index}].selling_point_ids",
            ),
            selling_point_ids,
            f"pages[{index}].selling_point_ids",
        )
        _check_known_ids(
            _validate_id_list(
                item["claim_ids"],
                "claim",
                contracts,
                f"pages[{index}].claim_ids",
            ),
            claim_ids,
            f"pages[{index}].claim_ids",
        )
    _ensure_unique(page_ids, "pages")


def _validate_approval(payload: dict, run_dir: Path) -> None:
    status = str(payload["status"] or "").strip()
    if status not in {"pending", "approved"}:
        raise ValueError("approval.status 必须是 pending 或 approved。")
    prompt_hash = _require_text(payload["prompt_hash"], "approval.prompt_hash")
    if re.fullmatch(r"[0-9a-f]{64}", prompt_hash) is None:
        raise ValueError("approval.prompt_hash 必须是 SHA-256。")
    _require_text(payload["displayed_at"], "approval.displayed_at")
    if status == "pending":
        if payload["approved_at"] is not None or payload["approved_by"] is not None:
            raise ValueError("待批准状态不能包含 approved_at 或 approved_by。")
    else:
        _require_text(payload["approved_at"], "approval.approved_at")
        _require_text(payload["approved_by"], "approval.approved_by")
    visual_payload = _load_artifact_if_present(run_dir, "visual.json")
    if visual_payload is None:
        raise ValueError("写入 approval.json 前必须先写入 visual.json。")
    if prompt_hash != compute_prompt_hash(visual_payload):
        raise ValueError("approval.prompt_hash 与当前 Prompt 包不匹配。")


def _validate_generation(payload: dict, contracts: dict, run_dir: Path) -> None:
    if payload["status"] not in {
        "in_progress",
        "complete",
        "failed",
        "uncertain",
    }:
        raise ValueError("generation.status 无效。")
    visual_payload = _load_artifact_if_present(run_dir, "visual.json")
    if visual_payload is None:
        raise ValueError("写入 generation.json 前必须先写入 visual.json。")
    known_pages = {
        str(item["id"])
        for item in visual_payload.get("pages", [])
        if isinstance(item, dict) and item.get("id")
    }
    items = _require_list(payload["items"], "generation.items")
    request_ids = []
    page_attempts: dict[str, set[int]] = {}
    for index, item_value in enumerate(items):
        item = _require_dict(item_value, f"generation.items[{index}]")
        _require_fields(
            item,
            contracts["artifacts"]["generation.json"]["item_required"]["items"],
            f"generation.items[{index}]",
        )
        request_ids.append(
            _validate_id(
                item["request_id"],
                "request",
                contracts,
                f"generation.items[{index}].request_id",
            )
        )
        page_id = _validate_id(
            item["page_id"],
            "page",
            contracts,
            f"generation.items[{index}].page_id",
        )
        if page_id not in known_pages:
            raise ValueError(
                f"generation.items[{index}] 引用了未知页面：{page_id}"
            )
        attempt = item["attempt"]
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise ValueError(
                f"generation.items[{index}].attempt 必须是正整数。"
            )
        attempts = page_attempts.setdefault(page_id, set())
        if attempt in attempts:
            raise ValueError(
                f"generation.items[{index}] 的 page_id 与 attempt 重复。"
            )
        attempts.add(attempt)
        if item["request_status"] not in {
            "request_started",
            "response_received",
            "download_pending",
            "complete",
            "failed",
            "uncertain",
        }:
            raise ValueError(
                f"generation.items[{index}].request_status 无效。"
            )
        _require_text(item["provider"], f"generation.items[{index}].provider")
        _require_text(item["model"], f"generation.items[{index}].model")
        _require_text(item["started_at"], f"generation.items[{index}].started_at")
        for field in (
            "response_received_at",
            "download_started_at",
            "completed_at",
        ):
            value = item[field]
            if value is not None:
                _require_text(value, f"generation.items[{index}].{field}")
        token_count = item["token_count"]
        if token_count is not None and (
            not isinstance(token_count, int)
            or isinstance(token_count, bool)
            or token_count < 0
        ):
            raise ValueError(
                f"generation.items[{index}].token_count 必须是非负整数或 null。"
            )
        cost_amount = item["cost_amount"]
        if cost_amount is not None and (
            isinstance(cost_amount, bool)
            or not isinstance(cost_amount, (int, float))
            or cost_amount < 0
        ):
            raise ValueError(
                f"generation.items[{index}].cost_amount 必须是非负数或 null。"
            )
        if cost_amount is not None:
            _require_text(
                item["cost_currency"],
                f"generation.items[{index}].cost_currency",
            )
        if item["request_status"] == "complete":
            _require_text(item.get("path"), f"generation.items[{index}].path")
            _require_text(
                item["completed_at"],
                f"generation.items[{index}].completed_at",
            )
    _ensure_unique(request_ids, "generation.items.request_id")
    if payload["status"] == "complete":
        latest_by_page = {}
        for item in items:
            page_id = str(item["page_id"])
            current = latest_by_page.get(page_id)
            if current is None or int(item["attempt"]) > int(current["attempt"]):
                latest_by_page[page_id] = item
        if set(latest_by_page) != known_pages or any(
            item["request_status"] != "complete"
            for item in latest_by_page.values()
        ):
            raise ValueError(
                "generation.status 为 complete 时全部计划页面必须完成。"
            )


def _validate_delivery(payload: dict) -> None:
    _require_text(payload["html_path"], "delivery.html_path")
    _require_text(payload["runtime_log_path"], "delivery.runtime_log_path")
    if payload["generation_status"] != "complete":
        raise ValueError("delivery.generation_status 必须是 complete。")
    _require_text(payload["completed_at"], "delivery.completed_at")


def validate_artifact(
    run_dir: Path,
    artifact_name: str,
    payload: dict,
) -> None:
    run_dir = Path(run_dir).expanduser().resolve()
    contracts = load_contracts()
    contract = contracts["artifacts"].get(artifact_name)
    if not isinstance(payload, dict) or not isinstance(contract, dict):
        raise ValueError(f"{artifact_name} 必须是 JSON 对象。")
    _require_fields(payload, contract["required"], artifact_name)
    if payload["schema_version"] != 1:
        raise ValueError(f"{artifact_name}.schema_version 必须是 1。")
    runtime = load_runtime(run_dir)
    if payload["run_id"] != runtime["run_id"]:
        raise ValueError(f"{artifact_name}.run_id 与当前运行不匹配。")

    if artifact_name == "task.json":
        _require_text(payload["summary"], "task.summary")
        _require_text(payload["content_goal"], "task.content_goal")
    elif artifact_name == "material.json":
        _validate_material(payload, contracts)
    elif artifact_name == "evidence.json":
        _validate_evidence(payload, contracts, run_dir)
    elif artifact_name == "content.json":
        _validate_content(payload, contracts, run_dir)
    elif artifact_name == "visual.json":
        _validate_visual(payload, contracts, run_dir)
    elif artifact_name == "approval.json":
        _validate_approval(payload, run_dir)
    elif artifact_name == "generation.json":
        _validate_generation(payload, contracts, run_dir)
    elif artifact_name == "delivery.json":
        _validate_delivery(payload)
    elif artifact_name == "runtime.json":
        raise ValueError("runtime.json 只能由运行时维护。")


def create_run(plugin_root: Path, delivery_root: Path, task: dict) -> Path:
    plugin_root = Path(plugin_root).expanduser().resolve()
    delivery_root = Path(delivery_root).expanduser().resolve()
    runtime_root = default_runtime_root()
    if _is_inside(runtime_root, plugin_root) or _is_inside(
        runtime_root,
        delivery_root,
    ):
        raise ValueError("运行目录不能位于插件成品目录或 HTML 交付目录内。")
    runtime_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_id = f"xhs-{timestamp}-{secrets.token_hex(4)}"
    run_dir = runtime_root / run_id
    run_dir.mkdir()

    runtime = {
        "schema_version": 1,
        "run_id": run_id,
        "task_summary": str((task or {}).get("summary") or "").strip(),
        "stage": "created",
        "approval_status": "not_requested",
        "default_image_provider": (
            str((task or {}).get("default_image_provider") or "").strip()
            or None
        ),
        "default_image_model": (
            str((task or {}).get("default_image_model") or "").strip()
            or None
        ),
        "created_at": utc_now(),
        "plugin_root": str(plugin_root),
        "delivery_root": str(delivery_root),
        "artifacts": {},
        "worker_sessions": {},
        "delivery_paths": {
            "html_path": None,
            "runtime_log_path": None,
        },
        "transitions": [],
        "stage_metrics": {},
    }
    _atomic_write_json(run_dir / RUNTIME_FILE, runtime)
    task_payload = {
        "schema_version": 1,
        "run_id": run_id,
        **dict(task or {}),
    }
    write_artifact(run_dir, "task.json", task_payload)
    return run_dir


def load_runtime(run_dir: Path) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    runtime = _load_json(run_dir / RUNTIME_FILE, RUNTIME_FILE)
    if runtime.get("schema_version") != 1:
        raise ValueError("runtime.json 版本无效。")
    contracts = load_contracts()
    run_id = str(runtime.get("run_id") or "")
    if re.fullmatch(contracts["run_id_pattern"], run_id) is None:
        raise ValueError("runtime.json run_id 无效。")
    if runtime.get("stage") not in LEGAL_TRANSITIONS:
        raise ValueError("runtime.json stage 无效。")
    _require_fields(
        runtime,
        load_contracts()["artifacts"]["runtime.json"]["required"],
        "runtime.json",
    )
    return runtime


def build_prompt_package(visual_payload: dict) -> dict:
    if not isinstance(visual_payload, dict):
        raise ValueError("visual.json 必须是 JSON 对象。")
    style_anchor = _require_dict(
        visual_payload.get("style_anchor"),
        "visual.style_anchor",
    )
    pages = []
    for index, raw_page in enumerate(
        _require_list(visual_payload.get("pages"), "visual.pages")
    ):
        page = _require_dict(raw_page, f"visual.pages[{index}]")
        pages.append(
            {
                "page_id": _require_text(
                    page.get("id"),
                    f"visual.pages[{index}].id",
                ),
                "prompt": _require_text(
                    page.get("prompt"),
                    f"visual.pages[{index}].prompt",
                ),
                "reference_image_ids": list(
                    _require_list(
                        page.get("reference_image_ids"),
                        f"visual.pages[{index}].reference_image_ids",
                    )
                ),
                "reference_image_paths": list(
                    _require_list(
                        page.get("reference_image_paths"),
                        f"visual.pages[{index}].reference_image_paths",
                    )
                ),
                "information_task": _require_text(
                    page.get("information_task"),
                    f"visual.pages[{index}].information_task",
                ),
            }
        )
    return {
        "style_anchor": style_anchor,
        "pages": pages,
    }


def compute_prompt_hash(visual_payload: dict) -> str:
    package = build_prompt_package(visual_payload)
    hash_payload = {
        "style_anchor": package["style_anchor"],
        "pages": [
            {
                "page_id": page["page_id"],
                "prompt": page["prompt"],
                "reference_image_ids": page["reference_image_ids"],
                "reference_image_paths": page["reference_image_paths"],
            }
            for page in package["pages"]
        ],
    }
    canonical = json.dumps(
        hash_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _set_pending_approval(
    run_dir: Path,
    prompt_hash: str,
    displayed_at: Optional[str] = None,
) -> dict:
    runtime = load_runtime(run_dir)
    approval = {
        "schema_version": 1,
        "run_id": runtime["run_id"],
        "status": "pending",
        "prompt_hash": prompt_hash,
        "displayed_at": displayed_at or utc_now(),
        "approved_at": None,
        "approved_by": None,
    }
    validate_artifact(run_dir, "approval.json", approval)
    approval_path = _atomic_write_json(run_dir / "approval.json", approval)
    runtime = load_runtime(run_dir)
    runtime["artifacts"]["approval.json"] = str(approval_path)
    runtime["approval_status"] = "pending"
    _atomic_write_json(run_dir / RUNTIME_FILE, runtime)
    return approval


def display_prompt_package(run_dir: Path) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    if runtime["stage"] not in {
        "humanized",
        "prompt_pending_approval",
        "prompt_approved",
    }:
        raise ValueError(
            "只有 humanized 或 Prompt 审批阶段可以展示 Prompt 包。"
        )
    visual = _load_json(run_dir / "visual.json", "visual.json")
    validate_artifact(run_dir, "visual.json", visual)
    package = build_prompt_package(visual)
    prompt_hash = compute_prompt_hash(visual)
    approval = _set_pending_approval(run_dir, prompt_hash)
    runtime = load_runtime(run_dir)
    if runtime["stage"] == "humanized":
        transition(run_dir, "prompt_pending_approval")
    elif runtime["stage"] == "prompt_approved":
        runtime["stage"] = "prompt_pending_approval"
        runtime["transitions"].append(
            {
                "from": "prompt_approved",
                "to": "prompt_pending_approval",
                "at": utc_now(),
                "reason": "prompt_package_redisplayed",
            }
        )
        _atomic_write_json(run_dir / RUNTIME_FILE, runtime)
    return {
        "schema_version": 1,
        "run_id": approval["run_id"],
        "prompt_hash": prompt_hash,
        "displayed_at": approval["displayed_at"],
        **package,
    }


def finish_compose(
    run_dir: Path,
    metrics: Optional[dict] = None,
) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    if runtime["stage"] != "evidenced":
        raise ValueError(
            "compose-finish 只能在 evidenced 阶段完成 Compose。"
        )
    compose_metrics = runtime["stage_metrics"].get("compose-worker")
    if not isinstance(compose_metrics, dict):
        raise ValueError("compose-worker 尚未启动。")
    if not compose_metrics.get("finished_at"):
        finish_stage(
            run_dir,
            "compose-worker",
            [run_dir / "content.json", run_dir / "visual.json"],
            metrics,
        )
    transition(run_dir, "composed")
    return transition(run_dir, "humanizing")


def finish_humanize_and_display_prompt(
    run_dir: Path,
    metrics: Optional[dict] = None,
) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    if runtime["stage"] != "humanizing":
        raise ValueError(
            "humanize-present 只能在 humanizing 阶段完成文案自然化并展示 Prompt。"
        )
    humanize_metrics = runtime["stage_metrics"].get("humanize-worker")
    if not isinstance(humanize_metrics, dict):
        raise ValueError("humanize-worker 尚未启动。")
    if not humanize_metrics.get("finished_at"):
        finish_stage(
            run_dir,
            "humanize-worker",
            [run_dir / "content.json"],
            metrics,
        )
    transition(run_dir, "humanized")
    return display_prompt_package(run_dir)


def validate_prompt_approval(run_dir: Path) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    approval = _load_json(run_dir / "approval.json", "approval.json")
    validate_artifact(run_dir, "approval.json", approval)
    if approval["status"] != "approved":
        raise ValueError("当前 Prompt 包尚未获得用户批准。")
    visual = _load_json(run_dir / "visual.json", "visual.json")
    current_hash = compute_prompt_hash(visual)
    if approval["prompt_hash"] != current_hash:
        raise ValueError("批准哈希与当前 Prompt 包不匹配。")
    return approval


def approve_prompt(
    run_dir: Path,
    approved_by: str,
    prompt_hash: Optional[str] = None,
) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    if runtime["stage"] != "prompt_pending_approval":
        raise ValueError("只有 prompt_pending_approval 可以接收用户批准。")
    pending = _load_json(run_dir / "approval.json", "approval.json")
    validate_artifact(run_dir, "approval.json", pending)
    expected_hash = compute_prompt_hash(
        _load_json(run_dir / "visual.json", "visual.json")
    )
    supplied_hash = str(prompt_hash or pending["prompt_hash"]).strip()
    if supplied_hash != expected_hash or pending["prompt_hash"] != expected_hash:
        raise ValueError("批准哈希与当前 Prompt 包不匹配。")
    approval = {
        **pending,
        "status": "approved",
        "approved_at": utc_now(),
        "approved_by": _require_text(approved_by, "approved_by"),
    }
    validate_artifact(run_dir, "approval.json", approval)
    approval_path = _atomic_write_json(run_dir / "approval.json", approval)
    runtime = load_runtime(run_dir)
    runtime["artifacts"]["approval.json"] = str(approval_path)
    runtime["approval_status"] = "approved"
    _atomic_write_json(run_dir / RUNTIME_FILE, runtime)
    transition(run_dir, "prompt_approved")
    return approval


def get_approval_status(run_dir: Path) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    approval = _load_artifact_if_present(run_dir, "approval.json")
    return {
        "schema_version": 1,
        "run_id": runtime["run_id"],
        "stage": runtime["stage"],
        "status": (
            str(approval.get("status"))
            if isinstance(approval, dict)
            else "not_requested"
        ),
        "prompt_hash": (
            approval.get("prompt_hash")
            if isinstance(approval, dict)
            else None
        ),
        "displayed_at": (
            approval.get("displayed_at")
            if isinstance(approval, dict)
            else None
        ),
        "approved_at": (
            approval.get("approved_at")
            if isinstance(approval, dict)
            else None
        ),
        "approved_by": (
            approval.get("approved_by")
            if isinstance(approval, dict)
            else None
        ),
    }


def write_artifact(run_dir: Path, artifact_name: str, payload: dict) -> Path:
    run_dir = Path(run_dir).expanduser().resolve()
    if artifact_name not in WRITABLE_ARTIFACT_NAMES:
        raise ValueError(f"产物不能通过 write_artifact 写入：{artifact_name}")
    path = _artifact_path(run_dir, artifact_name)
    runtime_before = load_runtime(run_dir)
    previous_prompt_hash = None
    if artifact_name == "visual.json" and path.is_file():
        previous_prompt_hash = compute_prompt_hash(
            _load_json(path, "visual.json")
        )
    validate_artifact(run_dir, artifact_name, payload)
    _atomic_write_json(path, payload)
    runtime = load_runtime(run_dir)
    runtime["artifacts"][artifact_name] = str(path)
    if artifact_name == "approval.json":
        runtime["approval_status"] = payload["status"]
    if artifact_name == "delivery.json":
        runtime["delivery_paths"] = {
            "html_path": payload["html_path"],
            "runtime_log_path": payload.get("runtime_log_path"),
        }
    _atomic_write_json(run_dir / RUNTIME_FILE, runtime)
    if (
        artifact_name == "visual.json"
        and previous_prompt_hash is not None
        and previous_prompt_hash != compute_prompt_hash(payload)
        and runtime_before["stage"]
        in {"prompt_pending_approval", "prompt_approved"}
    ):
        _set_pending_approval(run_dir, compute_prompt_hash(payload))
        if runtime_before["stage"] == "prompt_approved":
            runtime = load_runtime(run_dir)
            runtime["stage"] = "prompt_pending_approval"
            runtime["transitions"].append(
                {
                    "from": "prompt_approved",
                    "to": "prompt_pending_approval",
                    "at": utc_now(),
                    "reason": "prompt_package_changed",
                }
            )
            _atomic_write_json(run_dir / RUNTIME_FILE, runtime)
    return path


def transition(
    run_dir: Path,
    target_stage: str,
    artifact_names: Iterable[str] = (),
) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    current = runtime["stage"]
    target = str(target_stage or "").strip()
    if target not in LEGAL_TRANSITIONS.get(current, set()):
        raise ValueError(f"非法阶段迁移：{current} -> {target}")

    if target == "delivered":
        generation_path = run_dir / "generation.json"
        if generation_path.is_file():
            generation_payload = _load_json(
                generation_path,
                "generation.json",
            )
            if generation_payload.get("status") != "complete":
                raise ValueError(
                    "全部计划页面未达到 complete，不能进入 delivered。"
                )

    required = list(REQUIRED_ARTIFACTS.get(target, ()))
    for artifact_name in artifact_names:
        if artifact_name not in required:
            required.append(artifact_name)
    for artifact_name in required:
        path = _artifact_path(run_dir, artifact_name)
        if not path.is_file():
            raise ValueError(
                f"阶段 {target} 缺少必需产物：{artifact_name}"
            )
        validate_artifact(
            run_dir,
            artifact_name,
            _load_json(path, artifact_name),
        )
    if target == "prompt_pending_approval":
        approval = _load_json(run_dir / "approval.json", "approval.json")
        if approval["status"] != "pending":
            raise ValueError("进入 prompt_pending_approval 前必须写入待批准状态。")
        if approval["prompt_hash"] != compute_prompt_hash(
            _load_json(run_dir / "visual.json", "visual.json")
        ):
            raise ValueError("待批准哈希与当前 Prompt 包不匹配。")
    if target in {"prompt_approved", "producing"}:
        validate_prompt_approval(run_dir)
    if target == "delivered":
        generation_payload = _load_json(
            run_dir / "generation.json",
            "generation.json",
        )
        if generation_payload.get("status") != "complete":
            raise ValueError(
                "全部计划页面未达到 complete，不能进入 delivered。"
            )
        visual_payload = _load_json(run_dir / "visual.json", "visual.json")
        planned_pages = {
            str(page.get("id"))
            for page in visual_payload.get("pages", [])
            if isinstance(page, dict) and page.get("id")
        }
        latest_by_page = {}
        for item in generation_payload.get("items", []):
            if not isinstance(item, dict):
                continue
            page_id = str(item.get("page_id") or "")
            current_item = latest_by_page.get(page_id)
            if current_item is None or int(item.get("attempt") or 0) > int(
                current_item.get("attempt") or 0
            ):
                latest_by_page[page_id] = item
        if set(latest_by_page) != planned_pages or any(
            item.get("request_status") != "complete"
            for item in latest_by_page.values()
        ):
            raise ValueError("图片缺失、失败或状态不确定，不能进入 delivered。")
        output_root = Path(
            generation_payload.get("output_root")
            or runtime["delivery_root"]
        ).expanduser().resolve()
        for page_id, item in latest_by_page.items():
            raw_path = Path(str(item.get("path") or "")).expanduser()
            image_path = (
                raw_path.resolve()
                if raw_path.is_absolute()
                else (output_root / raw_path).resolve()
            )
            if not image_path.is_file():
                raise ValueError(f"页面 {page_id} 的图片文件不存在。")
        delivery_payload = _load_json(
            run_dir / "delivery.json",
            "delivery.json",
        )
        if delivery_payload["generation_status"] != "complete":
            raise ValueError("delivery.json 只能交付完整生图结果。")
        html_path = Path(delivery_payload["html_path"]).expanduser()
        if not html_path.is_file():
            raise ValueError("HTML 交付文件不存在，不能进入 delivered。")
        runtime_log_path = delivery_payload["runtime_log_path"]
        if not Path(runtime_log_path).expanduser().is_file():
            raise ValueError("运行日志不存在，不能进入 delivered。")
    if target == "completed":
        delivery_payload = _load_json(
            run_dir / "delivery.json",
            "delivery.json",
        )
        html_path = Path(delivery_payload["html_path"]).expanduser()
        if not html_path.is_file():
            raise ValueError("HTML 交付文件不存在，不能标记 completed。")
        runtime_log_path = delivery_payload["runtime_log_path"]
        if not Path(runtime_log_path).expanduser().is_file():
            raise ValueError("运行日志不存在，不能标记 completed。")
    required_stage = STAGE_TRANSITION_REQUIREMENTS.get(target)
    if required_stage is not None:
        required_metrics = runtime["stage_metrics"].get(required_stage)
        if (
            not isinstance(required_metrics, dict)
            or not required_metrics.get("finished_at")
        ):
            raise ValueError(
                f"阶段 {target} 必须先完成 {required_stage}。"
            )

    runtime["stage"] = target
    if target == "prompt_pending_approval":
        runtime["approval_status"] = "pending"
    elif target in {"prompt_approved", "producing"}:
        runtime["approval_status"] = "approved"
    runtime["transitions"].append(
        {
            "from": current,
            "to": target,
            "at": utc_now(),
        }
    )
    if target == "completed":
        completed_at = runtime["transitions"][-1]["at"]
        runtime["completed_at"] = completed_at
        runtime["duration_ms"] = _duration_ms(
            runtime.get("created_at"),
            completed_at,
        )
    _atomic_write_json(run_dir / RUNTIME_FILE, runtime)
    return runtime


def _measure_paths(paths: Iterable[Path]) -> tuple[list[str], int]:
    rendered = []
    total = 0
    for value in paths:
        path = Path(value).expanduser().resolve()
        rendered.append(str(path))
        if path.is_file():
            total += path.stat().st_size
    return rendered, total


def start_stage(
    run_dir: Path,
    stage: str,
    loaded_skills: Iterable[str],
    input_paths: Iterable[Path],
    worker_session_id: Optional[str] = None,
) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    stage_name = _require_text(stage, "stage")
    if stage_name in runtime["stage_metrics"]:
        raise ValueError(f"阶段已经启动：{stage_name}")
    contracts = load_contracts()
    worker_contract = contracts["workers"].get(stage_name)
    executor_contract = contracts["executors"].get(stage_name)
    stage_contract = worker_contract or executor_contract
    if stage_contract is None:
        raise ValueError(f"未知阶段：{stage_name}")
    skill_names = [
        _require_text(value, "loaded_skill") for value in loaded_skills
    ]
    inputs, input_bytes = _measure_paths(input_paths)
    session_id = None
    if stage_contract is not None:
        if runtime["stage"] != stage_contract["start_stage"]:
            raise ValueError(
                f"{stage_name} 只能在 {stage_contract['start_stage']} 阶段启动。"
            )
        if skill_names != stage_contract["loaded_skills"]:
            raise ValueError(f"{stage_name} 的 Skill 清单不符合契约。")
        expected_inputs = [
            str((run_dir / artifact_name).resolve())
            for artifact_name in stage_contract["input_artifacts"]
        ]
        if inputs != expected_inputs:
            raise ValueError(f"{stage_name} 的输入清单不符合契约。")
        if any(not Path(path).is_file() for path in inputs):
            raise ValueError(f"{stage_name} 的输入产物不存在。")
        required_stage = stage_contract.get("requires_completed_stage")
        if required_stage:
            required_metrics = runtime["stage_metrics"].get(required_stage)
            if (
                not isinstance(required_metrics, dict)
                or not required_metrics.get("finished_at")
            ):
                raise ValueError(
                    f"{stage_name} 启动前必须先完成 {required_stage}。"
                )
    if worker_contract is not None:
        session_id = _require_text(
            worker_session_id,
            f"{stage_name}.worker_session_id",
        )
        if session_id in set(runtime["worker_sessions"].values()):
            raise ValueError(
                "不同 Worker 必须使用不同的无历史会话 worker_session_id。"
            )
    elif worker_session_id is not None:
        raise ValueError(f"{stage_name} 是程序执行器，不接受 Worker 会话。")
    runtime["stage_metrics"][stage_name] = {
        "started_at": utc_now(),
        "finished_at": None,
        "loaded_skills": skill_names,
        "input_paths": inputs,
        "output_paths": [],
        "input_bytes": input_bytes,
        "output_bytes": 0,
        "token_count": None,
        "model_calls": 0,
        "tool_calls": 0,
        "retries": 0,
        "paid_requests": 0,
        "cost_amount": None,
        "cost_currency": None,
        "cost_status": "unavailable",
    }
    runtime["stage_metrics"][stage_name]["worker_id"] = stage_name
    runtime["stage_metrics"][stage_name]["worker_session_id"] = session_id
    if worker_contract is not None:
        runtime["worker_sessions"][stage_name] = session_id
    _atomic_write_json(run_dir / RUNTIME_FILE, runtime)
    return runtime


def finish_stage(
    run_dir: Path,
    stage: str,
    output_paths: Iterable[Path],
    metrics: Optional[dict] = None,
) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    stage_name = _require_text(stage, "stage")
    stage_metrics = runtime["stage_metrics"].get(stage_name)
    if not isinstance(stage_metrics, dict):
        raise ValueError(f"阶段尚未开始：{stage_name}")
    if stage_metrics.get("finished_at"):
        raise ValueError(f"阶段已经完成：{stage_name}")
    contracts = load_contracts()
    worker_contract = contracts["workers"].get(stage_name)
    executor_contract = contracts["executors"].get(stage_name)
    stage_contract = worker_contract or executor_contract
    if stage_contract is None:
        raise ValueError(f"未知阶段：{stage_name}")
    outputs, output_bytes = _measure_paths(output_paths)
    if stage_contract is not None:
        expected_outputs = [
            str((run_dir / artifact_name).resolve())
            for artifact_name in stage_contract["output_artifacts"]
        ]
        if outputs != expected_outputs:
            raise ValueError(f"{stage_name} 的输出清单不符合契约。")
        if any(not Path(path).is_file() for path in outputs):
            raise ValueError(f"{stage_name} 的输出产物不存在。")
    updated_metrics = dict(stage_metrics)
    updated_metrics["output_paths"] = outputs
    updated_metrics["output_bytes"] = output_bytes
    for field in METRIC_FIELDS:
        if metrics is not None and field in metrics:
            value = metrics[field]
            if field == "token_count" and value is None:
                updated_metrics[field] = None
                continue
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} 必须是非负整数或空值。")
            updated_metrics[field] = value
    if metrics is not None and any(
        field in metrics
        for field in ("cost_amount", "cost_currency", "cost_status")
    ):
        cost_amount = metrics.get("cost_amount")
        cost_currency = str(metrics.get("cost_currency") or "").strip().upper()
        cost_status = str(
            metrics.get("cost_status")
            or ("reported" if cost_amount is not None else "unavailable")
        ).strip()
        if cost_status not in {"reported", "unavailable"}:
            raise ValueError("cost_status 必须是 reported 或 unavailable。")
        if cost_status == "reported":
            if (
                isinstance(cost_amount, bool)
                or not isinstance(cost_amount, (int, float))
                or cost_amount < 0
                or not cost_currency
            ):
                raise ValueError(
                    "已上报费用必须包含非负 cost_amount 和 cost_currency。"
                )
            updated_metrics["cost_amount"] = cost_amount
            updated_metrics["cost_currency"] = cost_currency
        else:
            updated_metrics["cost_amount"] = None
            updated_metrics["cost_currency"] = None
        updated_metrics["cost_status"] = cost_status
    if stage_contract is not None:
        model_calls = updated_metrics["model_calls"]
        exact_calls = stage_contract.get("exact_model_calls")
        minimum_calls = stage_contract.get("minimum_model_calls")
        if exact_calls is not None and model_calls != exact_calls:
            if stage_name == "compose-worker":
                raise ValueError(
                    "compose-worker 必须恰好调用一次 compose 模型。"
                )
            raise ValueError(
                f"{stage_name} 的模型调用次数必须为 {exact_calls}。"
            )
        if minimum_calls is not None and model_calls < minimum_calls:
            raise ValueError(
                f"{stage_name} 至少需要 {minimum_calls} 次模型调用。"
            )
    updated_metrics["finished_at"] = utc_now()
    updated_metrics["duration_ms"] = _duration_ms(
        updated_metrics.get("started_at"),
        updated_metrics["finished_at"],
    )
    runtime["stage_metrics"][stage_name] = updated_metrics
    _atomic_write_json(run_dir / RUNTIME_FILE, runtime)

    current_idx = STATE_PATH.index(runtime["stage"]) if runtime["stage"] in STATE_PATH else -1
    if current_idx >= 0 and current_idx + 1 < len(STATE_PATH):
        runtime = transition(run_dir, STATE_PATH[current_idx + 1])
    else:
        _atomic_write_json(run_dir / RUNTIME_FILE, runtime)

    return runtime


def _transition_duration(
    runtime: dict,
    start_targets: set[str],
    end_sources: set[str],
) -> Optional[int]:
    started_at = None
    for transition_item in runtime.get("transitions", []):
        if not isinstance(transition_item, dict):
            continue
        if transition_item.get("to") in start_targets:
            started_at = transition_item.get("at")
            continue
        if (
            started_at is not None
            and transition_item.get("from") in end_sources
        ):
            return _duration_ms(started_at, transition_item.get("at"))
    return None


def _load_optional_run_payload(run_dir: Path, filename: str) -> Optional[dict]:
    path = run_dir / filename
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _reported_cost(
    value: object,
    currency: object,
) -> Optional[tuple[str, Decimal]]:
    normalized_currency = str(currency or "").strip().upper()
    if isinstance(value, bool) or not normalized_currency:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return normalized_currency, amount


def _summary_status(reported: int, unavailable: int) -> str:
    if reported == 0:
        return "unavailable"
    return "partial" if unavailable else "complete"


def build_run_summary(run_dir: Path) -> dict:
    run_dir = Path(run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    generation = _load_optional_run_payload(run_dir, "generation.json") or {}
    delivery = _load_optional_run_payload(run_dir, "delivery.json") or {}
    completed_at = (
        runtime.get("completed_at")
        or delivery.get("completed_at")
        or next(
            (
                item.get("at")
                for item in reversed(runtime.get("transitions", []))
                if isinstance(item, dict) and item.get("at")
            ),
            None,
        )
    )
    total_duration_ms = runtime.get("duration_ms")
    if not isinstance(total_duration_ms, int) or total_duration_ms < 0:
        total_duration_ms = _duration_ms(
            runtime.get("created_at"),
            completed_at,
        )

    stage_metrics = runtime.get("stage_metrics")
    if not isinstance(stage_metrics, dict):
        stage_metrics = {}
    stages = []
    for stage_id, stage_label in STAGE_LABELS.items():
        metrics = stage_metrics.get(stage_id)
        if isinstance(metrics, dict):
            duration = metrics.get("duration_ms")
            if not isinstance(duration, int) or duration < 0:
                duration = _duration_ms(
                    metrics.get("started_at"),
                    metrics.get("finished_at"),
                )
            status = (
                "complete" if metrics.get("finished_at") else "in_progress"
            )
        else:
            duration = None
            status = "unavailable"
        stages.append(
            {
                "id": stage_id,
                "label": stage_label,
                "status": status,
                "duration_ms": duration,
                "duration": _format_duration(duration),
            }
        )

    token_total = 0
    token_reported = 0
    token_unavailable = 0
    cost_amounts: dict[str, Decimal] = {}
    cost_reported = 0
    cost_unavailable = 0

    usage_sources = [
        metrics
        for stage_id, metrics in stage_metrics.items()
        if stage_id in STAGE_LABELS and isinstance(metrics, dict)
    ]
    generation_items = generation.get("items")

    for source in usage_sources:
        token_value = source.get("token_count")
        if isinstance(token_value, int) and not isinstance(token_value, bool) and token_value >= 0:
            token_total += token_value
            token_reported += 1
        else:
            token_unavailable += 1

        cost = _reported_cost(
            source.get("cost_amount"),
            source.get("cost_currency"),
        )
        if cost is None:
            cost_unavailable += 1
        else:
            currency, amount = cost
            cost_amounts[currency] = cost_amounts.get(currency, Decimal("0")) + amount
            cost_reported += 1

    normalized_costs = [
        {
            "currency": currency,
            "amount": float(amount),
        }
        for currency, amount in sorted(cost_amounts.items())
    ]
    items = [
        item
        for item in generation_items or []
        if isinstance(item, dict)
    ]
    latest_by_page = {}
    for item in items:
        page_id = str(item.get("page_id") or "")
        current = latest_by_page.get(page_id)
        if current is None or int(item.get("attempt") or 0) > int(
            current.get("attempt") or 0
        ):
            latest_by_page[page_id] = item
    succeeded = sum(
        item.get("request_status") == "complete"
        for item in latest_by_page.values()
    )
    total_requests = len(latest_by_page)
    success_percentage = (
        round(succeeded * 100 / total_requests, 2)
        if total_requests
        else None
    )
    failed_or_uncertain_requests = [
        {
            "page_id": str(item.get("page_id") or "unknown"),
            "status": str(item.get("request_status") or "unknown"),
            "error": str(item.get("error") or "").strip(),
        }
        for item in items
        if item.get("request_status") != "complete"
    ]
    model_provider_pairs = {
        (
            str(item.get("provider") or "").strip(),
            str(item.get("model") or "").strip(),
        )
        for item in items
        if str(item.get("provider") or "").strip()
        or str(item.get("model") or "").strip()
    }
    default_pair = (
        str(runtime.get("default_image_provider") or "").strip(),
        str(runtime.get("default_image_model") or "").strip(),
    )
    if default_pair[0] or default_pair[1]:
        model_provider_pairs.add(default_pair)

    return {
        "schema_version": 1,
        "run_id": runtime["run_id"],
        "workflow_status": runtime["stage"],
        "total_duration_ms": total_duration_ms,
        "total_duration": _format_duration(total_duration_ms),
        "stages": stages,
        "tokens": {
            "status": _summary_status(token_reported, token_unavailable),
            "reported_total": token_total if token_reported else None,
            "reported_sources": token_reported,
            "unavailable_sources": token_unavailable,
        },
        "cost": {
            "status": _summary_status(cost_reported, cost_unavailable),
            "reported_amounts": normalized_costs,
            "reported_sources": cost_reported,
            "unavailable_sources": cost_unavailable,
            "estimated": False,
        },
        "success_rate": {
            "scope": "image_requests",
            "succeeded": succeeded,
            "total": total_requests,
            "percentage": success_percentage,
        },
        "models_and_providers": [
            {"provider": provider, "model": model}
            for provider, model in sorted(model_provider_pairs)
        ],
        "failed_or_uncertain_requests": failed_or_uncertain_requests,
        "failed_requests": failed_or_uncertain_requests,
    }


def _format_percentage(value: Optional[float]) -> str:
    if value is None:
        return "未记录"
    if float(value).is_integer():
        return f"{int(value)}%"
    return f"{value:.2f}".rstrip("0").rstrip(".") + "%"


def render_run_summary(summary: dict) -> str:
    tokens = summary.get("tokens") or {}
    token_status = tokens.get("status")
    if token_status == "unavailable":
        token_text = "宿主或渠道未返回，未估算"
    elif token_status == "partial":
        token_text = (
            f"已记录 {tokens.get('reported_total')}；"
            "其余宿主或渠道未返回，未估算"
        )
    else:
        token_text = f"{tokens.get('reported_total')}"

    cost = summary.get("cost") or {}
    rendered_costs = " + ".join(
        f"{item['currency']} {item['amount']:.6f}".rstrip("0").rstrip(".")
        for item in cost.get("reported_amounts", [])
    )
    cost_status = cost.get("status")
    if cost_status == "unavailable":
        cost_text = "宿主或渠道未返回，未估算"
    elif cost_status == "partial":
        cost_text = (
            f"已记录 {rendered_costs}；"
            "其余宿主或渠道未返回，未估算"
        )
    else:
        cost_text = rendered_costs

    success = summary.get("success_rate") or {}
    success_text = (
        f"{success.get('succeeded', 0)}/{success.get('total', 0)}"
        f"（{_format_percentage(success.get('percentage'))}）"
        if success.get("total")
        else "暂无生图请求"
    )
    lines = [
        "# 小红书内容员工运行日志",
        "",
        f"- 运行 ID：`{summary.get('run_id', '未记录')}`",
        f"- 工作流状态：`{summary.get('workflow_status', '未记录')}`",
        f"- 总耗时：{summary.get('total_duration', '未记录')}",
        "",
        "## 阶段耗时",
        "",
        "| 阶段 | 状态 | 耗时 |",
        "| --- | --- | --- |",
    ]
    stages = summary.get("stages") or []
    if stages:
        lines.extend(
            f"| {item['label']} | {item['status']} | {item['duration']} |"
            for item in stages
        )
    else:
        lines.append("| 未记录 | unavailable | 未记录 |")
    lines.extend(
        (
            "",
            "## 资源与成功率",
            "",
            f"- Token：{token_text}",
            f"- 费用：{cost_text}",
            f"- 图片成功率：{success_text}",
        )
    )
    models_and_providers = summary.get("models_and_providers") or []
    model_provider_text = "；".join(
        (
            f"{item.get('provider') or '未记录渠道'} / "
            f"{item.get('model') or '未记录模型'}"
        )
        for item in models_and_providers
    ) or "未记录"
    lines.append(f"- 模型和渠道：{model_provider_text}")
    failed_requests = summary.get("failed_or_uncertain_requests") or []
    if failed_requests:
        lines.extend(("", "## 失败或不确定请求", ""))
        for item in failed_requests:
            detail = item.get("error") or "渠道未返回详细错误"
            lines.append(
                f"- `{item.get('page_id')}`："
                f"{item.get('status')}；{detail}"
            )
    lines.extend(
        (
            "",
            "> Token 与费用只记录宿主或渠道实际返回的数据，不进行估算。",
        )
    )
    return "\n".join(lines)


def write_run_log(run_dir: Path, output_path: Path) -> Path:
    run_dir = Path(run_dir).expanduser().resolve()
    runtime = load_runtime(run_dir)
    delivery_root = Path(runtime["delivery_root"]).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if not _is_inside(destination, delivery_root):
        raise ValueError("运行日志必须写入 HTML 交付目录。")
    plugin_root = Path(runtime["plugin_root"]).expanduser().resolve()
    if _is_inside(destination, plugin_root):
        raise ValueError("运行日志不能写入插件成品目录。")
    return _atomic_write_text(
        destination,
        render_run_summary(build_run_summary(run_dir)),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行小红书内容工作流状态机。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--plugin-root", type=Path, required=True)
    create_parser.add_argument("--delivery-root", type=Path, required=True)
    create_parser.add_argument("--task-file", type=Path, required=True)

    write_parser = subparsers.add_parser("write")
    write_parser.add_argument("--run-dir", type=Path, required=True)
    write_parser.add_argument("--artifact", choices=ARTIFACT_NAMES, required=True)
    write_parser.add_argument("--payload-file", type=Path, required=True)

    transition_parser = subparsers.add_parser("transition")
    transition_parser.add_argument("--run-dir", type=Path, required=True)
    transition_parser.add_argument("--target", required=True)

    start_parser = subparsers.add_parser("stage-start")
    start_parser.add_argument("--run-dir", type=Path, required=True)
    start_parser.add_argument("--stage", required=True)
    start_parser.add_argument("--loaded-skill", action="append", default=[])
    start_parser.add_argument("--input", type=Path, action="append", default=[])
    start_parser.add_argument("--worker-session-id")

    finish_parser = subparsers.add_parser("stage-finish")
    finish_parser.add_argument("--run-dir", type=Path, required=True)
    finish_parser.add_argument("--stage", required=True)
    finish_parser.add_argument("--output", type=Path, action="append", default=[])
    finish_parser.add_argument("--metrics-file", type=Path)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("--run-dir", type=Path, required=True)

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("--run-dir", type=Path, required=True)
    summary_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
    )
    summary_parser.add_argument("--output", type=Path)

    prompt_show_parser = subparsers.add_parser("prompt-show")
    prompt_show_parser.add_argument("--run-dir", type=Path, required=True)

    compose_finish_parser = subparsers.add_parser("compose-finish")
    compose_finish_parser.add_argument("--run-dir", type=Path, required=True)
    compose_finish_parser.add_argument("--metrics-file", type=Path)

    humanize_present_parser = subparsers.add_parser("humanize-present")
    humanize_present_parser.add_argument("--run-dir", type=Path, required=True)
    humanize_present_parser.add_argument("--metrics-file", type=Path)

    approval_pending_parser = subparsers.add_parser("approval-pending")
    approval_pending_parser.add_argument("--run-dir", type=Path, required=True)

    approval_approve_parser = subparsers.add_parser("approval-approve")
    approval_approve_parser.add_argument("--run-dir", type=Path, required=True)
    approval_approve_parser.add_argument("--approved-by", required=True)
    approval_approve_parser.add_argument("--prompt-hash")

    approval_validate_parser = subparsers.add_parser("approval-validate")
    approval_validate_parser.add_argument("--run-dir", type=Path, required=True)

    approval_status_parser = subparsers.add_parser("approval-status")
    approval_status_parser.add_argument("--run-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "create":
            task = _load_json(args.task_file, "task file")
            result = {"run_dir": str(create_run(
                args.plugin_root,
                args.delivery_root,
                task,
            ))}
        elif args.command == "write":
            payload = _load_json(args.payload_file, "payload file")
            result = {
                "artifact_path": str(
                    write_artifact(args.run_dir, args.artifact, payload)
                )
            }
        elif args.command == "transition":
            result = transition(args.run_dir, args.target)
        elif args.command == "stage-start":
            result = start_stage(
                args.run_dir,
                args.stage,
                args.loaded_skill,
                args.input,
                args.worker_session_id,
            )
        elif args.command == "stage-finish":
            metrics = (
                _load_json(args.metrics_file, "metrics file")
                if args.metrics_file
                else None
            )
            result = finish_stage(
                args.run_dir,
                args.stage,
                args.output,
                metrics,
            )
        elif args.command == "show":
            result = load_runtime(args.run_dir)
        elif args.command == "compose-finish":
            metrics = (
                _load_json(args.metrics_file, "metrics file")
                if args.metrics_file
                else None
            )
            result = finish_compose(
                args.run_dir,
                metrics,
            )
        elif args.command == "humanize-present":
            metrics = (
                _load_json(args.metrics_file, "metrics file")
                if args.metrics_file
                else None
            )
            result = finish_humanize_and_display_prompt(
                args.run_dir,
                metrics,
            )
        elif args.command in {"prompt-show", "approval-pending"}:
            result = display_prompt_package(args.run_dir)
        elif args.command == "approval-approve":
            result = approve_prompt(
                args.run_dir,
                args.approved_by,
                args.prompt_hash,
            )
        elif args.command == "approval-validate":
            result = validate_prompt_approval(args.run_dir)
        elif args.command == "approval-status":
            result = get_approval_status(args.run_dir)
        else:
            result = build_run_summary(args.run_dir)
    except Exception as exc:
        print(str(exc), file=os.sys.stderr)
        return 1
    if args.command == "summary" and args.output:
        try:
            output = write_run_log(args.run_dir, args.output)
        except Exception as exc:
            print(str(exc), file=os.sys.stderr)
            return 1
        print(json.dumps(
            {"runtime_log": str(output)},
            ensure_ascii=False,
            indent=2,
        ))
    elif args.command == "summary" and args.format == "text":
        print(render_run_summary(result))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
