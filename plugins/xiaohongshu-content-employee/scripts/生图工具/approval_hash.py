#!/usr/bin/env python3
"""为已展示 Prompt 计算渠道绑定的审核哈希，不发送生成请求。"""

import argparse
import json
import sys
from pathlib import Path

from generate_image import (
    approval_digest,
    load_config,
    resolve_provider_quality,
    resolve_provider_size,
)


def calculate_hash(
    skill_root: Path,
    provider: str,
    prompt: str,
    raw_size: str,
    quality: str = "hd",
    reference_image_sha256: str = "",
) -> dict:
    config = load_config(skill_root, provider)
    resolved_provider = config["provider"]
    size = resolve_provider_size(resolved_provider, raw_size)
    approval_quality = resolve_provider_quality(resolved_provider, quality)
    return {
        "provider": resolved_provider,
        "model": config["model"],
        "size": size,
        "quality": approval_quality,
        "approval_hash": approval_digest(
            prompt,
            provider=resolved_provider,
            model=config["model"],
            size=size,
            quality=approval_quality,
            reference_image_sha256=reference_image_sha256,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="计算当前 Prompt 的审核哈希，不调用图片生成 API。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--provider",
        default="thinkai-image-2",
        help="图片生成渠道 ID；自定义渠道使用已保存的 custom-* ID",
    )
    parser.add_argument(
        "--reference-image-sha256",
        default="",
        help="官网产品参考图 SHA-256；批量工作流仅首图提供",
    )
    parser.add_argument("--prompt", required=True, help="已展示给用户的精确 Prompt")
    parser.add_argument(
        "--size",
        default=None,
        help="尺寸；未指定时使用所选正式渠道的推荐值",
    )
    parser.add_argument(
        "--quality",
        default="hd",
        choices=["standard", "hd", "low", "medium", "high", "auto"],
        help="图片质量；火山引擎当前不发送该字段",
    )
    args = parser.parse_args()

    plugin_root = Path(__file__).resolve().parents[2]
    try:
        result = calculate_hash(
            plugin_root,
            args.provider,
            args.prompt,
            args.size,
            args.quality,
            args.reference_image_sha256,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
