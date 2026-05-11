"""LSP diagnostics tool."""

from pathlib import Path

from tools.lsp_utils import LSP_TOOL_EXECUTION, format_list, run_lsp_tool


async def lsp_diagnostics(path: str | None = None, workdir: Path | str | None = None) -> str:
    """Return diagnostics reported by the Python LSP server when available."""
    result = await run_lsp_tool(workdir, lambda manager: manager.diagnostics(path))
    if isinstance(result, str):
        return result
    if not result:
        return (
            "status: unsupported\n"
            "diagnostics: none\n"
            "reason: pull diagnostics are not implemented in the current LSP MVP; "
            "use verify for authoritative validation."
        )
    return format_list("diagnostics", result)


lsp_diagnostics_tool = {
    "name": "lsp_diagnostics",
    "description": "Return Python LSP diagnostics when available. MVP may return no_results for servers without pull diagnostics.",
    "execution": LSP_TOOL_EXECUTION,
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Optional workspace-relative Python file path."}},
        "required": [],
    },
}
