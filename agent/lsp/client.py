"""Minimal async JSON-RPC client for Language Server Protocol processes."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any


class LspClientError(RuntimeError):
    """Raised when an LSP client operation fails."""


class LspClient:
    """Small JSON-RPC client for a single language server process."""

    def __init__(self, command: Sequence[str], root: Path, timeout: float = 10.0):
        self.command = list(command)
        self.root = root.resolve()
        self.timeout = timeout
        self.process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._initialized = False

    async def start(self) -> None:
        """Start and initialize the language server."""
        if self.process is not None and self.process.returncode is None:
            return
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.root),
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        await self.initialize()

    async def initialize(self) -> None:
        """Send initialize/initialized handshake."""
        if self._initialized:
            return
        result = await self.request(
            "initialize",
            {
                "processId": None,
                "rootUri": self.root.as_uri(),
                "capabilities": {},
                "workspaceFolders": [{"uri": self.root.as_uri(), "name": self.root.name}],
            },
        )
        if result is None:
            raise LspClientError("language server returned empty initialize result")
        await self.notify("initialized", {})
        self._initialized = True

    async def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC request and return its result."""
        if self.process is None or self.process.stdin is None:
            raise LspClientError("language server is not running")
        request_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        try:
            response = await asyncio.wait_for(future, timeout=self.timeout)
        finally:
            self._pending.pop(request_id, None)
        if "error" in response:
            error = response["error"]
            message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            raise LspClientError(message)
        return response.get("result")

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC notification."""
        if self.process is None or self.process.stdin is None:
            raise LspClientError("language server is not running")
        await self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def did_open(self, uri: str, text: str, language_id: str = "python") -> None:
        """Notify the server that a document is open."""
        await self.notify(
            "textDocument/didOpen",
            {"textDocument": {"uri": uri, "languageId": language_id, "version": 1, "text": text}},
        )

    async def shutdown(self) -> None:
        """Shutdown the language server process."""
        proc = self.process
        if proc is None:
            return
        try:
            if proc.returncode is None:
                try:
                    await self.request("shutdown", {})
                    await self.notify("exit", {})
                except Exception:
                    proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
        finally:
            if self._reader_task:
                self._reader_task.cancel()
            self.process = None
            self._initialized = False

    async def _send(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        assert self.process is not None and self.process.stdin is not None
        self.process.stdin.write(header + body)
        await self.process.stdin.drain()

    async def _read_loop(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        reader = self.process.stdout
        while True:
            try:
                headers: dict[str, str] = {}
                while True:
                    line = await reader.readline()
                    if not line:
                        raise EOFError("language server stdout closed")
                    if line in {b"\r\n", b"\n"}:
                        break
                    key, _, value = line.decode("ascii", errors="replace").partition(":")
                    headers[key.lower()] = value.strip()
                length = int(headers.get("content-length", "0"))
                if length <= 0:
                    continue
                body = await reader.readexactly(length)
                message = json.loads(body.decode("utf-8"))
                if "id" in message and (future := self._pending.get(int(message["id"]))) and not future.done():
                    future.set_result(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                for future in list(self._pending.values()):
                    if not future.done():
                        future.set_exception(exc)
                return
