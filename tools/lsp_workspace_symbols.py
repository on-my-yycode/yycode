"""LSP workspace symbols tool."""

from pathlib import Path

from tools.lsp_utils import LSP_TOOL_EXECUTION, format_list, run_lsp_tool


async def lsp_workspace_symbols(query: str, workdir: Path | str | None = None) -> str:
    """Search workspace symbols using LSP."""
    result = await run_lsp_tool(workdir, lambda manager: manager.workspace_symbols(query))
    return result if isinstance(result, str) else format_list("symbols", result)


lsp_workspace_symbols_tool = {
    "name": "lsp_workspace_symbols",
    "description": "Search Python workspace symbols by name using LSP semantic navigation.",
    "execution": LSP_TOOL_EXECUTION,
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Symbol name or query text."}},
        "required": ["query"],
    },
}
