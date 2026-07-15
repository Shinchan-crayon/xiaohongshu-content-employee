#!/usr/bin/env python3
"""Install the eight Xiaohongshu content Skills into a Codex skills directory."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Set


EXPECTED_SKILLS = (
    "xhs-content-employee",
    "product-material-intake",
    "xhs-research-strategy",
    "xhs-copy-storyboard",
    "xhs-humanize-review",
    "xhs-visual-planner",
    "xhs-approved-image-generator",
    "xhs-html-delivery",
)

RESOURCE_PATTERN = re.compile(
    r"\.\./\.\./(?P<kind>references|assets|templates|scripts)/(?P<tail>[^\s`]+)"
)

SKILL_ROOT_FILES = ("SKILL.md",)
AGENT_FILES = (Path("agents") / "openai.yaml",)
HTML_DELIVERY_TEMPLATE_FILES = (
    Path("templates") / "HTML交付模板" / "delivery.html",
    Path("templates") / "HTML交付模板" / "delivery.css",
    Path("templates") / "HTML交付模板" / "delivery.js",
)
HTML_DELIVERY_SCRIPT = (
    Path("scripts") / "HTML生成工具" / "generate_delivery.py"
)
IMAGE_GENERATION_RUNTIME_FILES = (
    Path("assets") / "image_providers.json",
    Path("config.example.json"),
    Path("requirements.txt"),
    Path("scripts") / "生图工具" / "approval_hash.py",
    Path("scripts") / "生图工具" / "batch_generate.py",
    Path("scripts") / "生图工具" / "configure_provider.py",
    Path("scripts") / "生图工具" / "generate_image.py",
    Path("scripts") / "生图工具" / "provider_preflight.py",
    Path("scripts") / "生图工具" / "provider_registry.py",
    Path("scripts") / "生图工具" / "providers" / "__init__.py",
    Path("scripts") / "生图工具" / "providers" / "base.py",
    Path("scripts") / "生图工具" / "providers" / "custom.py",
    Path("scripts") / "生图工具" / "providers" / "google_image.py",
    Path("scripts") / "生图工具" / "providers" / "openai_image.py",
    Path("scripts") / "生图工具" / "providers" / "thinkai.py",
    Path("scripts") / "生图工具" / "providers" / "thinkai_nano.py",
    Path("scripts") / "生图工具" / "providers" / "volcengine.py",
    Path("scripts") / "图片合成工具" / "render_carousel.py",
)

SCRIPT_PATH = Path(__file__).resolve()
PACKAGE_ROOT = SCRIPT_PATH.parents[2]
PACKAGE_SKILLS_DIR = PACKAGE_ROOT / "skills"


class InstallError(Exception):
    """Raised when the installer cannot complete safely."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        type=Path,
        help="Install directly into this skills directory.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing installed Skills.",
    )
    return parser.parse_args()


def resolve_target(target: Path | None) -> Path:
    if target is not None:
        return target.expanduser().resolve()

    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return (Path(codex_home).expanduser() / "skills").resolve()
    return (Path.home() / ".codex" / "skills").resolve()


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def skill_resource_paths(source_skill_dir: Path, skill_text: str) -> Set[Path]:
    resources: Set[Path] = set()
    for match in RESOURCE_PATTERN.finditer(skill_text):
        resources.add(Path(match.group("kind")) / match.group("tail"))

    if source_skill_dir.name == "xhs-html-delivery":
        resources.update(HTML_DELIVERY_TEMPLATE_FILES)
        resources.add(HTML_DELIVERY_SCRIPT)
    if source_skill_dir.name == "xhs-approved-image-generator":
        resources.update(IMAGE_GENERATION_RUNTIME_FILES)

    return resources


def copy_skill_runtime(source_skill_dir: Path, staged_skill_dir: Path) -> None:
    for relative in SKILL_ROOT_FILES:
        copy_file(source_skill_dir / relative, staged_skill_dir / relative)
    for relative in AGENT_FILES:
        copy_file(source_skill_dir / relative, staged_skill_dir / relative)

    skill_text = (source_skill_dir / "SKILL.md").read_text(encoding="utf-8")
    rewritten = (
        skill_text.replace("../../references/", "references/")
        .replace("../../assets/", "assets/")
        .replace("../../templates/", "templates/")
        .replace("../../scripts/", "scripts/")
        .replace("../../config.example.json", "config.example.json")
        .replace("../../requirements.txt", "requirements.txt")
    )
    (staged_skill_dir / "SKILL.md").write_text(rewritten, encoding="utf-8")

    for relative in sorted(skill_resource_paths(source_skill_dir, skill_text)):
        source = PACKAGE_ROOT / relative
        if not source.is_file():
            raise InstallError(
                f"missing runtime resource for {source_skill_dir.name}: {relative.as_posix()}"
            )
        copy_file(source, staged_skill_dir / relative)


def verify_staged_skill(skill_dir: Path) -> None:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    for prefix in (
        "../../references/",
        "../../assets/",
        "../../templates/",
        "../../scripts/",
    ):
        if prefix in text:
            raise InstallError(f"unrewritten resource path remains in {skill_dir.name}")

    for match in re.finditer(
        r"`((?:references|assets|templates|scripts)/[^`]+)`",
        text,
    ):
        relative = Path(match.group(1))
        if not (skill_dir / relative).is_file():
            raise InstallError(
                f"installed Skill is missing referenced file: {skill_dir.name}/{relative.as_posix()}"
            )

    if skill_dir.name == "xhs-html-delivery":
        if not (skill_dir / HTML_DELIVERY_SCRIPT).is_file():
            raise InstallError("xhs-html-delivery is missing generate_delivery.py")
        for template in HTML_DELIVERY_TEMPLATE_FILES:
            if not (skill_dir / template).is_file():
                raise InstallError(
                    f"xhs-html-delivery is missing template file: {template.as_posix()}"
                )
    if skill_dir.name == "xhs-approved-image-generator":
        for runtime_file in IMAGE_GENERATION_RUNTIME_FILES:
            if not (skill_dir / runtime_file).is_file():
                raise InstallError(
                    "xhs-approved-image-generator is missing runtime file: "
                    f"{runtime_file.as_posix()}"
                )


def build_staging_area(staging_root: Path) -> None:
    for skill_name in EXPECTED_SKILLS:
        source_skill_dir = PACKAGE_SKILLS_DIR / skill_name
        if not source_skill_dir.is_dir():
            raise InstallError(f"missing packaged Skill: {skill_name}")
        staged_skill_dir = staging_root / skill_name
        copy_skill_runtime(source_skill_dir, staged_skill_dir)
        verify_staged_skill(staged_skill_dir)


def existing_skill_conflicts(target: Path) -> Iterable[Path]:
    for skill_name in EXPECTED_SKILLS:
        candidate = target / skill_name
        if candidate.exists():
            yield candidate


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def rollback_force_install(
    installed_paths: list[Path], backed_up_paths: list[tuple[Path, Path]]
) -> None:
    for installed in reversed(installed_paths):
        if installed.exists():
            remove_path(installed)
    for original, backup in reversed(backed_up_paths):
        if backup.exists():
            backup.rename(original)


def install(staging_root: Path, target: Path, force: bool) -> None:
    conflicts = list(existing_skill_conflicts(target))
    if conflicts and not force:
        names = ", ".join(path.name for path in conflicts)
        raise InstallError(f"target Skill already exists: {names}")

    target.mkdir(parents=True, exist_ok=True)
    if not force:
        for skill_name in EXPECTED_SKILLS:
            shutil.copytree(staging_root / skill_name, target / skill_name)
        return

    transaction_root = Path(
        tempfile.mkdtemp(prefix=".install-transaction-", dir=target)
    )
    new_root = transaction_root / "new"
    backup_root = transaction_root / "backup"
    installed_paths: list[Path] = []
    backed_up_paths: list[tuple[Path, Path]] = []

    try:
        new_root.mkdir()
        backup_root.mkdir()

        for skill_name in EXPECTED_SKILLS:
            shutil.copytree(staging_root / skill_name, new_root / skill_name)

        try:
            for skill_name in EXPECTED_SKILLS:
                destination = target / skill_name
                if destination.exists():
                    backup = backup_root / skill_name
                    destination.rename(backup)
                    backed_up_paths.append((destination, backup))

            for skill_name in EXPECTED_SKILLS:
                prepared = new_root / skill_name
                destination = target / skill_name
                prepared.rename(destination)
                installed_paths.append(destination)
        except Exception:
            rollback_force_install(installed_paths, backed_up_paths)
            raise
    finally:
        if transaction_root.exists():
            shutil.rmtree(transaction_root)


def main() -> int:
    args = parse_args()
    target = resolve_target(args.target)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="codex-skill-build-", dir=target.parent) as tmp:
            staging_root = Path(tmp) / "skills"
            staging_root.mkdir()
            build_staging_area(staging_root)
            install(staging_root, target, args.force)
    except (InstallError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    print("Installed Skills:")
    for skill_name in EXPECTED_SKILLS:
        print(f"- {skill_name}")
    print("Public entry: xhs-content-employee")
    print(f"Target: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
