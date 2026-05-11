"""LSP hover tool."""

from pathlib import Path

from tools.lsp_utils import LSP_TOOL_EXECUTION, run_lsp_tool


async def lsp_hover(path: str, line: int, character: int, workdir: Path | str | None = None) -> str:
    """Return hover text for a Python symbol position using LSP."""
    result = await run_lsp_tool(workdir, lambda manager: manager.hover(path, line, character))
    if isinstance(result, str) and result.startswith(("status:", "Error:")):
        return result
    return "hover:\n" + (str(result).strip() or "none")


lsp_hover_tool = {
    "name": "lsp_hover",
    "description": "Return type/signature/documentation hover text for a Python symbol position using LSP. Line and character are zero-based.",
    "execution": LSP_TOOL_EXECUTION,
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Workspace-relative Python file path."},
            "line": {"type": "integer", "description": "Zero-based line number."},
            "character": {"type": "integer", "description": "Zero-based character offset."},
        },
        "required": ["path", "line", "character"],
    },
}
