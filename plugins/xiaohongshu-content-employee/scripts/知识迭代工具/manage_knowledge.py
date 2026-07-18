#!/usr/bin/env python3
"""Manage user-controlled adaptive knowledge outside the plugin package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION = "1.0"
STORAGE_REFERENCE = "xhs-user-data://knowledge"
NOTICE = (
    "个性化学习已开启：你明确修改和偏好会自动保存；"
    "外部事实和运营规律需要确认后才会长期使用；"
    "你可以随时查看学习记录、关闭个性化学习或删除学习记录。"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_home() -> Path:
    configured = os.environ.get("XHS_CONTENT_EMPLOYEE_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".xiaohongshu-content-employee"


def stable_id(prefix: str, *parts: str) -> str:
    normalized = "\0".join(part.strip().casefold() for part in parts)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def validate_text(name: str, value: str, maximum: int = 500) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError(f"{name} cannot be empty")
    if len(cleaned) > maximum:
        raise ValueError(f"{name} exceeds {maximum} characters")
    sensitive_patterns = (
        r"\bsk-[A-Za-z0-9_-]{12,}\b",
        r"(?i)\b(?:api[_ -]?key|password|access[_ -]?token)\s*[:=]\s*\S+",
    )
    if any(re.search(pattern, cleaned) for pattern in sensitive_patterns):
        raise ValueError(f"{name} appears to contain a secret")
    return cleaned


class KnowledgeStore:
    def __init__(self, home: Path):
        self.home = home
        self.profile_path = home / "profile.json"
        self.knowledge_path = home / "knowledge.json"

    def initialize(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        if not self.profile_path.exists():
            self._write(
                self.profile_path,
                {
                    "version": VERSION,
                    "enabled": True,
                    "preferences": [],
                    "updated_at": now_iso(),
                },
            )
        if not self.knowledge_path.exists():
            self._write(
                self.knowledge_path,
                {
                    "version": VERSION,
                    "items": [],
                    "updated_at": now_iso(),
                },
            )

    def _read(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, path: Path, data: dict[str, Any]) -> None:
        data["updated_at"] = now_iso()
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(path)

    def profile(self) -> dict[str, Any]:
        self.initialize()
        return self._read(self.profile_path)

    def knowledge(self) -> dict[str, Any]:
        self.initialize()
        return self._read(self.knowledge_path)

    def status(self) -> dict[str, Any]:
        profile = self.profile()
        knowledge = self.knowledge()
        counts = {"pending": 0, "approved": 0, "rejected": 0}
        for item in knowledge["items"]:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        return {
            "enabled": profile["enabled"],
            "storage_reference": STORAGE_REFERENCE,
            "notice": NOTICE if profile["enabled"] else "个性化学习已关闭。",
            "preference_count": len(profile["preferences"]),
            "knowledge_counts": counts,
        }

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        profile = self.profile()
        profile["enabled"] = enabled
        self._write(self.profile_path, profile)
        return self.status()

    def record_preference(
        self,
        workflow_id: str,
        category: str,
        value: str,
        evidence: str,
    ) -> dict[str, Any]:
        profile = self.profile()
        if not profile["enabled"]:
            return {"skipped": True, "reason": "learning_disabled"}

        workflow_id = validate_text("workflow_id", workflow_id, 120)
        category = validate_text("category", category, 80)
        value = validate_text("value", value)
        evidence = validate_text("evidence", evidence)
        item_id = stable_id("pref", category, value)

        for item in profile["preferences"]:
            if item["id"] != item_id:
                continue
            item["observations"] += 1
            item["last_workflow_id"] = workflow_id
            item["last_observed_at"] = now_iso()
            item["evidence"] = (item.get("evidence", []) + [evidence])[-10:]
            self._write(self.profile_path, profile)
            return {"skipped": False, "preference": item}

        preference = {
            "id": item_id,
            "category": category,
            "value": value,
            "observations": 1,
            "first_workflow_id": workflow_id,
            "last_workflow_id": workflow_id,
            "first_observed_at": now_iso(),
            "last_observed_at": now_iso(),
            "evidence": [evidence],
        }
        profile["preferences"].append(preference)
        self._write(self.profile_path, profile)
        return {"skipped": False, "preference": preference}

    def propose(
        self,
        workflow_id: str,
        kind: str,
        statement: str,
        source: str,
        observed_at: str,
    ) -> dict[str, Any]:
        profile = self.profile()
        if not profile["enabled"]:
            return {"skipped": True, "reason": "learning_disabled"}

        workflow_id = validate_text("workflow_id", workflow_id, 120)
        kind = validate_text("kind", kind, 80)
        statement = validate_text("statement", statement)
        source = validate_text("source", source)
        observed_at = validate_text("observed_at", observed_at, 40)
        item_id = stable_id("knowledge", kind, statement, source)
        knowledge = self.knowledge()

        for item in knowledge["items"]:
            if item["id"] == item_id:
                return {"skipped": False, "candidate": item, "duplicate": True}

        candidate = {
            "id": item_id,
            "kind": kind,
            "statement": statement,
            "source": source,
            "observed_at": observed_at,
            "workflow_id": workflow_id,
            "status": "pending",
            "reviewed_at": None,
        }
        knowledge["items"].append(candidate)
        self._write(self.knowledge_path, knowledge)
        return {"skipped": False, "candidate": candidate, "duplicate": False}

    def review(self, item_id: str, decision: str) -> dict[str, Any]:
        knowledge = self.knowledge()
        target_status = "approved" if decision == "approve" else "rejected"
        for item in knowledge["items"]:
            if item["id"] != item_id:
                continue
            item["status"] = target_status
            item["reviewed_at"] = now_iso()
            self._write(self.knowledge_path, knowledge)
            return {"candidate": item}
        raise ValueError("knowledge item not found")

    def context(self, category: str | None = None) -> dict[str, Any]:
        profile = self.profile()
        if not profile["enabled"]:
            return {
                "enabled": False,
                "storage_reference": STORAGE_REFERENCE,
                "preferences": [],
                "approved_knowledge": [],
            }

        preferences = profile["preferences"]
        if category:
            preferences = [
                item for item in preferences if item["category"] == category
            ]
        approved = [
            item for item in self.knowledge()["items"] if item["status"] == "approved"
        ]
        return {
            "enabled": True,
            "storage_reference": STORAGE_REFERENCE,
            "preferences": preferences,
            "approved_knowledge": approved,
        }

    def forget(self, item_id: str) -> dict[str, Any]:
        profile = self.profile()
        original_preferences = len(profile["preferences"])
        profile["preferences"] = [
            item for item in profile["preferences"] if item["id"] != item_id
        ]
        if len(profile["preferences"]) != original_preferences:
            self._write(self.profile_path, profile)
            return {"removed": True, "id": item_id}

        knowledge = self.knowledge()
        original_items = len(knowledge["items"])
        knowledge["items"] = [
            item for item in knowledge["items"] if item["id"] != item_id
        ]
        removed = len(knowledge["items"]) != original_items
        if removed:
            self._write(self.knowledge_path, knowledge)
        return {"removed": removed, "id": item_id}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=default_home())
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init")
    commands.add_parser("status")
    commands.add_parser("enable")
    commands.add_parser("disable")

    preference = commands.add_parser("record-preference")
    preference.add_argument("--workflow-id", required=True)
    preference.add_argument("--category", required=True)
    preference.add_argument("--value", required=True)
    preference.add_argument("--evidence", required=True)

    proposal = commands.add_parser("propose")
    proposal.add_argument("--workflow-id", required=True)
    proposal.add_argument(
        "--kind",
        required=True,
        choices=("fact", "operating_pattern", "content_pattern"),
    )
    proposal.add_argument("--statement", required=True)
    proposal.add_argument("--source", required=True)
    proposal.add_argument("--observed-at", required=True)

    review = commands.add_parser("review")
    review.add_argument("--id", required=True)
    review.add_argument("--decision", required=True, choices=("approve", "reject"))

    context = commands.add_parser("context")
    context.add_argument("--category")

    forget = commands.add_parser("forget")
    forget.add_argument("--id", required=True)
    return parser


def execute(args: argparse.Namespace) -> dict[str, Any]:
    store = KnowledgeStore(args.home.expanduser().resolve())
    if args.command in {"init", "status"}:
        store.initialize()
        return store.status()
    if args.command == "enable":
        return store.set_enabled(True)
    if args.command == "disable":
        return store.set_enabled(False)
    if args.command == "record-preference":
        return store.record_preference(
            args.workflow_id,
            args.category,
            args.value,
            args.evidence,
        )
    if args.command == "propose":
        return store.propose(
            args.workflow_id,
            args.kind,
            args.statement,
            args.source,
            args.observed_at,
        )
    if args.command == "review":
        return store.review(args.id, args.decision)
    if args.command == "context":
        return store.context(args.category)
    if args.command == "forget":
        return store.forget(args.id)
    raise ValueError(f"unsupported command: {args.command}")


def main() -> int:
    try:
        result = execute(build_parser().parse_args())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(
            json.dumps({"error": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
