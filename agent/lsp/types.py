"""Small typed containers and formatters for LSP results."""

from dataclasses import dataclass
from typing import Any


SYMBOL_KINDS = {
    1: "file",
    2: "module",
    3: "namespace",
    4: "package",
    5: "class",
    6: "method",
    7: "property",
    8: "field",
    9: "constructor",
    10: "enum",
    11: "interface",
    12: "function",
    13: "variable",
    14: "constant",
    15: "string",
    16: "number",
    17: "boolean",
    18: "array",
    19: "object",
    20: "key",
    21: "null",
    22: "enumMember",
    23: "struct",
    24: "event",
    25: "operator",
    26: "typeParameter",
}

SEVERITIES = {1: "error", 2: "warning", 3: "information", 4: "hint"}


@dataclass(frozen=True)
class Location:
    """A workspace-relative source location."""

    path: str
    line: int
    character: int
    name: str | None = None

    def format(self) -> str:
        suffix = f" {self.name}" if self.name else ""
        return f"{self.path}:{self.line + 1}:{self.character + 1}{suffix}"


@dataclass(frozen=True)
class Symbol:
    """A document or workspace symbol."""

    name: str
    kind: str
    location: Location
    container_name: str | None = None

    def format(self) -> str:
        container = f" {self.container_name}." if self.container_name else " "
        return f"{self.kind}{container}{self.name} {self.location.format()}"


@dataclass(frozen=True)
class Diagnostic:
    """An LSP diagnostic."""

    path: str
    line: int
    character: int
    severity: str
    message: str
    code: str | None = None

    def format(self) -> str:
        code = f" {self.code}" if self.code else ""
        return f"{self.path}:{self.line + 1}:{self.character + 1} {self.severity}{code} {self.message}"


def uri_to_path(uri: str) -> str:
    """Convert a file URI to a local path string."""
    from urllib.parse import unquote, urlparse

    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return uri
    return unquote(parsed.path)


def path_to_uri(path: str) -> str:
    """Convert a local path string to a file URI."""
    from pathlib import Path

    return Path(path).resolve().as_uri()


def range_start(item: dict[str, Any]) -> tuple[int, int]:
    """Return zero-based line/character from an LSP range-like item."""
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    start = (
        item.get("range", {}).get("start")
        or item.get("selectionRange", {}).get("start")
        or location.get("range", {}).get("start")
        or {}
    )
    return int(start.get("line", 0)), int(start.get("character", 0))


def symbol_kind_name(kind: Any) -> str:
    """Return a readable symbol kind."""
    return SYMBOL_KINDS.get(int(kind or 0), "symbol")


def diagnostic_severity(severity: Any) -> str:
    """Return a readable diagnostic severity."""
    return SEVERITIES.get(int(severity or 0), "diagnostic")
