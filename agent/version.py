"""Project version helpers."""

from __future__ import annotations

from functools import cache
from importlib import metadata
from pathlib import Path


@cache
def project_version() -> str:
    """Return the yycode project version from installed metadata or source metadata."""
    source_version = _pyproject_version()
    if source_version:
        return source_version
    try:
        return metadata.version("yycode")
    except metadata.PackageNotFoundError:
        return ""


@cache
def display_version() -> str:
    """Return the user-facing yycode version string."""
    version = project_version()
    return f"v{version}" if version else "v0.0.0"


def _pyproject_version() -> str:
    try:
        import tomllib

        root = Path(__file__).resolve().parents[1]
        payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        return str(payload.get("project", {}).get("version") or "")
    except Exception:
        return ""
