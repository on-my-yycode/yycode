"""LSP document symbols tool."""

from pathlib import Path

from tools.lsp_utils import LSP_TOOL_EXECUTION, format_list, run_lsp_tool


async def lsp_document_symbols(path: str, workdir: Path | str | None = None) -> str:
    """List symbols in a Python file using LSP."""
    result = await run_lsp_tool(workdir, lambda manager: manager.document_symbols(path))
    return result if isinstance(result, str) else format_list("symbols", result)


lsp_document_symbols_tool = {
    "name": "lsp_document_symbols",
    "description": "List classes, functions, methods, and variables in a Python file using LSP semantic navigation.",
    "execution": LSP_TOOL_EXECUTION,
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Workspace-relative Python file path."}},
        "required": ["path"],
    },
}
