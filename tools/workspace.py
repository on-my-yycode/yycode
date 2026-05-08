"""Workspace path helpers shared by tools and runtime."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    """Resolved workspace root with safe path helpers."""

    root: Path

    def __post_init__(self) -> None:
        resolved = self.root.expanduser().resolve()
        if not resolved.exists():
            raise ValueError(f"workspace does not exist: {resolved}")
        if not resolved.is_dir():
            raise ValueError(f"workspace is not a directory: {resolved}")
        object.__setattr__(self, "root", resolved)

    def safe_path(self, path: str | Path) -> Path:
        """Return an absolute path constrained within the workspace."""
        raw_path = Path(path).expanduser()
        resolved = raw_path.resolve() if raw_path.is_absolute() else (self.root / raw_path).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError(f"Path escapes workspace: {path}")
        return resolved

    def relative_path(self, path: str | Path) -> str:
        """Return a workspace-relative path after safety checks."""
        return str(self.safe_path(path).relative_to(self.root))


def resolve_workspace(path: str | Path | None = None) -> Workspace:
    """Resolve a user-provided workspace or default to the current directory."""
    return Workspace(Path(path).expanduser() if path is not None else Path.cwd())
