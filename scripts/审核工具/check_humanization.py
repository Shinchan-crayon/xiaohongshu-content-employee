#!/usr/bin/env python3
"""Check Xiaohongshu body text for obvious formulaic writing risks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ADVICE_PATTERN = re.compile(
    r"需要|建议|提醒|避免|确认|检查|选择|为准|不能保证|如需|如果你"
)
MANUAL_FLOW_PATTERN = re.compile(
    r"先核对|材质也要看|如需额外|使用前|购买前|最终是否合适|候选清单"
)
GENERIC_CTA_PATTERN = re.compile(
    r"你.{0,24}(?:最容易忽略|更在意|最关注).{0,24}(?:还是|、).*[？?]$"
)
TEMPLATE_CONCLUSION_PATTERN = re.compile(
    r"进入候选清单|最终是否合适|以.{0,20}为准"
)


def split_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"[。！？!?；;]+", text)
        if sentence.strip()
    ]


def finding(code: str, severity: str, summary: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "summary": summary,
        "evidence": evidence,
    }


def analyze_text(
    text: str,
    *,
    ai_feature_percent: float | None = None,
) -> dict[str, Any]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    sentences = split_sentences(text)
    findings: list[dict[str, Any]] = []

    advice_hits = [sentence for sentence in sentences if ADVICE_PATTERN.search(sentence)]
    advice_ratio = len(advice_hits) / len(sentences) if sentences else 0.0
    if len(advice_hits) >= 5 and advice_ratio >= 0.35:
        findings.append(
            finding(
                "ADVICE_DENSITY",
                "HIGH",
                "建议、提醒和条件句过密，正文接近产品说明书。",
                advice_hits[:5],
            )
        )

    flow_hits = [
        paragraph
        for paragraph in paragraphs
        if MANUAL_FLOW_PATTERN.search(paragraph)
    ]
    if len(flow_hits) >= 3:
        findings.append(
            finding(
                "MANUAL_STYLE_FLOW",
                "HIGH",
                "正文按参数、材质、步骤、结论依次讲解，结构过于规整。",
                flow_hits[:4],
            )
        )

    ending = paragraphs[-1] if paragraphs else ""
    if GENERIC_CTA_PATTERN.search(ending):
        findings.append(
            finding(
                "GENERIC_CTA",
                "HIGH",
                "结尾使用常见的多选一互动模板。",
                [ending],
            )
        )

    conclusion_hits = [
        sentence
        for sentence in sentences
        if TEMPLATE_CONCLUSION_PATTERN.search(sentence)
    ]
    if conclusion_hits:
        findings.append(
            finding(
                "TEMPLATE_CONCLUSION",
                "MEDIUM",
                "结尾出现候选清单或“以某项为准”的标准总结。",
                conclusion_hits[:3],
            )
        )

    if ai_feature_percent is not None and ai_feature_percent >= 50:
        findings.append(
            finding(
                "DETECTOR_HIGH_AI",
                "FATAL",
                "外部检测反馈显示 AI 特征达到或超过 50%。",
                [f"ai_feature_percent={ai_feature_percent:g}"],
            )
        )

    high_risk_count = sum(
        item["severity"] in {"FATAL", "HIGH"} for item in findings
    )
    full_rewrite_required = any(
        item["code"] == "DETECTOR_HIGH_AI" for item in findings
    ) or high_risk_count >= 2
    status = "BLOCKED" if full_rewrite_required else ("WARN" if findings else "PASS")

    return {
        "status": status,
        "full_rewrite_required": full_rewrite_required,
        "metrics": {
            "paragraph_count": len(paragraphs),
            "sentence_count": len(sentences),
            "advice_sentence_count": len(advice_hits),
            "advice_sentence_ratio": round(advice_ratio, 3),
        },
        "findings": findings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="UTF-8 text file, or - to read from stdin",
    )
    parser.add_argument("--ai-feature-percent", type=float)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.input == "-":
        text = sys.stdin.read()
    else:
        text = Path(args.input).read_text(encoding="utf-8")

    result = analyze_text(text, ai_feature_percent=args.ai_feature_percent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
