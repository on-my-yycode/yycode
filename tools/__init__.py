"""Tools package - auto-register tools."""

import importlib
import pkgutil
from pathlib import Path
from typing import Dict, Callable, Any

TOOL_HANDLERS: Dict[str, Callable] = {}
TOOLS: list[Dict[str, Any]] = []


def register_tool(handler: Callable, tool_def: Dict[str, Any]) -> None:
    """Register a tool with its handler."""
    tool_name = tool_def["name"]
    TOOL_HANDLERS[tool_name] = handler
    TOOLS.append(tool_def)


def auto_register_tools() -> None:
    """Auto-discover and register all tools in the tools package."""
    package_dir = Path(__file__).parent

    for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
        if module_name == "__init__":
            continue

        module = importlib.import_module(f".{module_name}", __name__)

        # Look for tool definition (ends with '_tool')
        tool_def = None
        handler = None
        tool_name = None

        for attr_name in dir(module):
            if attr_name.endswith("_tool") and isinstance(getattr(module, attr_name), dict):
                tool_def = getattr(module, attr_name)
                tool_name = tool_def["name"]
                # Try to find matching handler (same name as tool)
                if hasattr(module, tool_name):
                    handler = getattr(module, tool_name)
                break

        if tool_def and handler:
            register_tool(handler, tool_def)


# Auto-register tools on import
auto_register_tools()

__all__ = ["TOOL_HANDLERS", "TOOLS", "register_tool"]
