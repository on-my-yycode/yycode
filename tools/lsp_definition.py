"""LSP definition lookup tool."""

from pathlib import Path

from tools.lsp_utils import LSP_TOOL_EXECUTION, format_list, run_lsp_tool


async def lsp_definition(path: str, line: int, character: int, workdir: Path | str | None = None) -> str:
    """Find definitions for a Python symbol position using LSP."""
    result = await run_lsp_tool(workdir, lambda manager: manager.definition(path, line, character))
    return result if isinstance(result, str) else format_list("definitions", result)


lsp_definition_tool = {
    "name": "lsp_definition",
    "description": "Find definition locations for a Python symbol position using LSP. Line and character are zero-based.",
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
