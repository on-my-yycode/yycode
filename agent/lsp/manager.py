"""High-level manager for read-only Python LSP navigation."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from agent.lsp.client import LspClient, LspClientError
from agent.lsp.types import (
    Diagnostic,
    Location,
    Symbol,
    path_to_uri,
    range_start,
    symbol_kind_name,
    uri_to_path,
)
from tools.workspace import Workspace


class LspUnavailable(RuntimeError):
    """Raised when no supported language server is available."""


def _python_server_command() -> list[str] | None:
    if shutil.which("pyright-langserver"):
        return ["pyright-langserver", "--stdio"]
    if shutil.which("pylsp"):
        return ["pylsp"]
    return None


class LspManager:
    """Lazy Python LSP manager scoped to one workspace."""

    def __init__(self, workdir: Path | str, timeout: float = 10.0):
        self.workspace = Workspace(Path(workdir))
        self.timeout = timeout
        self._client: LspClient | None = None
        self._opened: set[str] = set()

    async def document_symbols(self, path: str) -> list[Symbol]:
        file_path = self._safe_python_file(path)
        client = await self._client_for_python()
        await self._open(client, file_path)
        result = await client.request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": path_to_uri(str(file_path))}},
        )
        return self._parse_document_symbols(result or [], file_path)

    async def workspace_symbols(self, query: str) -> list[Symbol]:
        client = await self._client_for_python()
        result = await client.request("workspace/symbol", {"query": query})
        return [self._parse_workspace_symbol(item) for item in (result or [])]

    async def definition(self, path: str, line: int, character: int) -> list[Location]:
        return await self._locations_request("textDocument/definition", path, line, character)

    async def references(
        self,
        path: str,
        line: int,
        character: int,
        include_declaration: bool = False,
    ) -> list[Location]:
        return await self._locations_request(
            "textDocument/references",
            path,
            line,
            character,
            extra={"context": {"includeDeclaration": include_declaration}},
        )

    async def hover(self, path: str, line: int, character: int) -> str:
        file_path = self._safe_python_file(path)
        client = await self._client_for_python()
        await self._open(client, file_path)
        result = await client.request("textDocument/hover", self._position_params(file_path, line, character))
        contents = (result or {}).get("contents") if isinstance(result, dict) else result
        return self._format_hover(contents)

    async def diagnostics(self, path: str | None = None) -> list[Diagnostic]:
        if path:
            file_path = self._safe_python_file(path)
            client = await self._client_for_python()
            await self._open(client, file_path)
        elif self._client is None:
            await self._client_for_python()
        # Pull diagnostics are not universally supported. Return an empty list rather than guessing.
        return []

    async def shutdown(self) -> None:
        if self._client:
            await self._client.shutdown()
        self._client = None
        self._opened.clear()

    async def _client_for_python(self) -> LspClient:
        if self._client is not None and self._client.process is not None and self._client.process.returncode is None:
            return self._client
        command = _python_server_command()
        if not command:
            raise LspUnavailable("pyright-langserver and pylsp not found")
        self._client = LspClient(command, self.workspace.root, timeout=self.timeout)
        try:
            await self._client.start()
        except FileNotFoundError as exc:
            raise LspUnavailable(f"language server not found: {command[0]}") from exc
        except (OSError, LspClientError, asyncio.TimeoutError) as exc:
            raise LspUnavailable(f"language server failed to start: {exc}") from exc
        return self._client

    async def _open(self, client: LspClient, file_path: Path) -> None:
        uri = path_to_uri(str(file_path))
        if uri in self._opened:
            return
        await client.did_open(uri, file_path.read_text(), language_id="python")
        self._opened.add(uri)

    async def _locations_request(
        self,
        method: str,
        path: str,
        line: int,
        character: int,
        extra: dict[str, Any] | None = None,
    ) -> list[Location]:
        file_path = self._safe_python_file(path)
        client = await self._client_for_python()
        await self._open(client, file_path)
        params = self._position_params(file_path, line, character)
        if extra:
            params.update(extra)
        result = await client.request(method, params)
        if isinstance(result, dict):
            result = [result]
        return [self._parse_location(item) for item in (result or [])]

    def _position_params(self, file_path: Path, line: int, character: int) -> dict[str, Any]:
        return {
            "textDocument": {"uri": path_to_uri(str(file_path))},
            "position": {"line": max(0, int(line)), "character": max(0, int(character))},
        }

    def _safe_python_file(self, path: str) -> Path:
        file_path = self.workspace.safe_path(path)
        if not file_path.exists():
            raise ValueError(f"file does not exist: {path}")
        if not file_path.is_file():
            raise ValueError(f"path is not a file: {path}")
        if file_path.suffix != ".py":
            raise ValueError(f"only Python files are supported in LSP MVP: {path}")
        return file_path

    def _parse_document_symbols(self, items: list[dict[str, Any]], file_path: Path) -> list[Symbol]:
        symbols: list[Symbol] = []

        def visit(item: dict[str, Any], container: str | None = None) -> None:
            line, character = range_start(item)
            name = str(item.get("name", "<unknown>"))
            symbols.append(
                Symbol(
                    name=name,
                    kind=symbol_kind_name(item.get("kind")),
                    container_name=container,
                    location=Location(self.workspace.relative_path(file_path), line, character, name),
                )
            )
            for child in item.get("children") or []:
                visit(child, name)

        for item in items:
            visit(item)
        return symbols

    def _parse_workspace_symbol(self, item: dict[str, Any]) -> Symbol:
        location = item.get("location") or {}
        parsed_location = self._parse_location(location, name=item.get("name"))
        return Symbol(
            name=str(item.get("name", "<unknown>")),
            kind=symbol_kind_name(item.get("kind")),
            container_name=item.get("containerName"),
            location=parsed_location,
        )

    def _parse_location(self, item: dict[str, Any], name: str | None = None) -> Location:
        uri = item.get("uri") or item.get("targetUri") or ""
        path = Path(uri_to_path(uri))
        relative = self.workspace.relative_path(path) if path.exists() else uri
        line, character = range_start(item.get("range") and item or item.get("targetSelectionRange", {}) or {})
        return Location(relative, line, character, str(name) if name else None)

    def _format_hover(self, contents: Any) -> str:
        if not contents:
            return ""
        if isinstance(contents, str):
            return contents
        if isinstance(contents, dict):
            value = contents.get("value") or contents.get("language") or str(contents)
            return str(value)
        if isinstance(contents, list):
            return "\n".join(self._format_hover(item) for item in contents if item)
        return str(contents)


_MANAGERS: dict[Path, LspManager] = {}


def get_lsp_manager(workdir: Path | str) -> LspManager:
    """Return a cached LSP manager for a workspace."""
    root = Workspace(Path(workdir)).root
    manager = _MANAGERS.get(root)
    if manager is None:
        manager = LspManager(root)
        _MANAGERS[root] = manager
    return manager


async def shutdown_lsp_managers() -> None:
    """Shutdown all cached LSP managers."""
    managers = list(_MANAGERS.values())
    _MANAGERS.clear()
    for manager in managers:
        await manager.shutdown()
