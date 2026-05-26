"""Application-level path helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_app_root(raw_app_root: str | Path | None = None) -> Path:
    """Resolve the yoyoagent application root directory."""
    raw = raw_app_root or os.environ.get("YOYO_APP_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def resolve_resource_root(raw_app_root: str | Path | None = None) -> Path:
    """Resolve the user-editable yycode resource root for bundled files."""
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
    """Resolve the runtime data directory for yoyoagent-owned data."""
    raw = raw_runtime_data_dir or os.environ.get("YOYO_RUNTIME_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return app_root
