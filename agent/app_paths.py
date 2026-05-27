"""Application-level path helpers."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import NamedTuple


def resolve_app_root(raw_app_root: str | Path | None = None) -> Path:
    """Resolve the yoyoagent application root directory."""
    raw = raw_app_root or os.environ.get("YOYO_APP_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def resolve_resource_root(raw_app_root: str | Path | None = None) -> Path:
    """Resolve the bundled yycode resource root for default files."""
    raw = raw_app_root or os.environ.get("YOYO_APP_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()

    source_root = Path(__file__).resolve().parents[1]
    if (source_root / "skills").is_dir():
        return source_root

    prefix_root = Path(sys.prefix).resolve()
    if (prefix_root / "skills").is_dir():
        return prefix_root

    return source_root


def resolve_runtime_data_dir(
    app_root: Path,
    raw_runtime_data_dir: str | Path | None = None,
) -> Path:
    """Resolve the user-editable runtime data directory for yycode-owned data."""
    raw = raw_runtime_data_dir or os.environ.get("YOYO_RUNTIME_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return default_user_data_dir()


def default_user_data_dir() -> Path:
    """Return the default per-user yycode data directory."""
    if sys.platform == "darwin":
        return (Path.home() / "Library" / "Application Support" / "yycode").resolve()
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return (Path(base).expanduser() / "yycode").resolve()
        return (Path.home() / "AppData" / "Roaming" / "yycode").resolve()
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return (Path(base).expanduser() / "yycode").resolve()
    return (Path.home() / ".local" / "share" / "yycode").resolve()


def ensure_default_skills_dir(runtime_data_dir: Path, resource_root: Path) -> Path:
    """Initialize the user-editable skills directory from bundled defaults if needed."""
    skills_dir = runtime_data_dir / "skills"
    if skills_dir.exists():
        return skills_dir

    bundled_skills = resource_root / "skills"
    if bundled_skills.is_dir():
        skills_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(bundled_skills, skills_dir)
    else:
        skills_dir.mkdir(parents=True, exist_ok=True)
    return skills_dir


class SkillSyncResult(NamedTuple):
    """Summary of a bundled skill sync into the user data directory."""

    source_dir: Path
    target_dir: Path
    copied: list[Path]
    updated: list[Path]
    skipped: list[Path]


def sync_default_skills_dir(runtime_data_dir: Path, resource_root: Path) -> SkillSyncResult:
    """Copy bundled skills into user data, overwriting matching bundled files only."""
    source_dir = resource_root / "skills"
    target_dir = runtime_data_dir / "skills"
    copied: list[Path] = []
    updated: list[Path] = []
    skipped: list[Path] = []

    if not source_dir.is_dir():
        target_dir.mkdir(parents=True, exist_ok=True)
        return SkillSyncResult(source_dir, target_dir, copied, updated, skipped)

    for source_path in sorted(path for path in source_dir.rglob("*") if path.is_file()):
        relative_path = source_path.relative_to(source_dir)
        target_path = target_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            if target_path.read_bytes() == source_path.read_bytes():
                skipped.append(relative_path)
                continue
            updated.append(relative_path)
        else:
            copied.append(relative_path)
        shutil.copy2(source_path, target_path)

    return SkillSyncResult(source_dir, target_dir, copied, updated, skipped)
