"""LSP references lookup tool."""

from pathlib import Path

from tools.lsp_utils import LSP_TOOL_EXECUTION, format_list, run_lsp_tool


async def lsp_references(
    path: str,
    line: int,
    character: int,
    include_declaration: bool = False,
    workdir: Path | str | None = None,
) -> str:
    """Find references for a Python symbol position using LSP."""
    result = await run_lsp_tool(
        workdir,
        lambda manager: manager.references(path, line, character, include_declaration),
    )
    return result if isinstance(result, str) else format_list("references", result)


lsp_references_tool = {
    "name": "lsp_references",
    "description": "Find reference locations for a Python symbol position using LSP. Line and character are zero-based.",
    "execution": LSP_TOOL_EXECUTION,
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Workspace-relative Python file path."},
            "line": {"type": "integer", "description": "Zero-based line number."},
            "character": {"type": "integer", "description": "Zero-based character offset."},
            "include_declaration": {"type": "boolean", "description": "Whether to include the declaration location."},
        },
        "required": ["path", "line", "character"],
    },
}
