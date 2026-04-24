"""List directory tool - display directory structure in tree format."""

from pathlib import Path

WORKDIR = Path.cwd()


def safe_path(p: str) -> Path:
    """Get a safe path within the workspace."""
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def _build_tree(path: Path, prefix: str = "", max_depth: int = None, current_depth: int = 0) -> str:
    """Recursively build a tree representation of the directory."""
    if max_depth is not None and current_depth > max_depth:
        return ""
    
    result = []
    try:
        items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except (PermissionError, OSError):
        return prefix + "└── [Permission denied]\n"
    
    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        current_prefix = "└── " if is_last else "├── "
        result.append(prefix + current_prefix + item.name)
        
        if item.is_dir():
            extension = "    " if is_last else "│   "
            subtree = _build_tree(item, prefix + extension, max_depth, current_depth + 1)
            if subtree:
                result.append(subtree)
    
    return "\n".join(result) if result else ""


def list_dir(path: str = ".", max_depth: int = None) -> str:
    """List directory and subdirectories in tree format.
    
    Args:
        path: Directory path to list (defaults to current directory)
        max_depth: Maximum depth to traverse (None for unlimited)
    
    Returns:
        Tree-formatted string of the directory structure
    """
    try:
        target_path = safe_path(path)
        if not target_path.exists():
            return f"Error: Path does not exist: {path}"
        if not target_path.is_dir():
            return f"Error: Not a directory: {path}"
        
        tree_lines = [target_path.name + "/"]
        subtree = _build_tree(target_path, "", max_depth)
        if subtree:
            tree_lines.append(subtree)
        
        result = "\n".join(tree_lines)
        return result[:50000]  # Limit output size
    except Exception as e:
        return f"Error: {e}"


list_dir_tool = {
    "name": "list_dir",
    "description": "List directory and subdirectories in tree format.",
    "execution": {
        "side_effects": "read_only",
        "concurrency": "safe",
        "timeout_seconds": 30,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path to list (defaults to current directory)"},
            "max_depth": {"type": "integer", "description": "Maximum depth to traverse (optional)"}
        },
        "required": [],
    },
}
