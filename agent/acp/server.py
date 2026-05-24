"""ACP stdio server."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, TextIO

from agent.acp.jsonrpc import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    JsonRpcError,
    decode_message,
    encode,
    error_response,
    notification,
    request,
    response,
)
from agent.acp.session_manager import AcpSessionManager


ACP_PROTOCOL_VERSION = 1


class AcpServer:
    """Minimal newline-delimited JSON-RPC server for ACP stdio."""

    def __init__(
        self,
        *,
        stdin: TextIO | None = None,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
        auto_approve: bool = False,
    ) -> None:
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr
        self._write_lock = asyncio.Lock()
        self._next_id = 1
        self._pending: dict[str | int, asyncio.Future] = {}
        self.sessions = AcpSessionManager(self.notify, self.request_client, auto_approve=auto_approve)

    async def serve(self) -> None:
        """Run the stdio read loop until EOF."""
        try:
            while True:
                line = await asyncio.to_thread(self.stdin.readline)
                if not line:
                    break
                await self.handle_line(line)
        finally:
            await self.sessions.close()

    async def handle_line(self, line: str) -> None:
        """Handle one JSON-RPC line."""
        try:
            message = decode_message(line)
        except JsonRpcError as exc:
            await self._write(error_response(exc.code, exc.message))
            return

        if not message.method:
            self._resolve_response(line)
            return
        if message.is_notification:
            await self._handle_notification(message.method, message.params)
            return
        try:
            result = await self._dispatch(message.method, _params_dict(message.params))
        except JsonRpcError as exc:
            await self._write(error_response(exc.code, exc.message, message.id, exc.data))
        except Exception as exc:
            print(f"ACP method failed: {message.method}: {exc}", file=self.stderr)
            await self._write(error_response(INTERNAL_ERROR, str(exc), message.id))
        else:
            await self._write(response(result, message.id))

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification to the ACP client."""
        await self._write(notification(method, params))

    async def request_client(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request to the ACP client and await its response."""
        request_id = self._next_request_id()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future
        await self._write(request(method, params, request_id))
        result = await future
        return result if isinstance(result, dict) else {"result": result}

    async def _dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "initialize":
            return _initialize_result()
        if method == "session/new":
            return await self.sessions.new_session(params)
        if method == "session/load":
            return await self.sessions.load_session(params)
        if method == "session/prompt":
            return await self.sessions.prompt(params)
        if method == "session/cancel":
            return await self.sessions.cancel(params)
        raise JsonRpcError(METHOD_NOT_FOUND, f"Method not found: {method}")

    async def _handle_notification(self, method: str, params: Any) -> None:
        if method in {"initialized", "$/cancelRequest"}:
            return
        print(f"Ignoring ACP notification: {method} {params!r}", file=self.stderr)

    def _resolve_response(self, line: str) -> None:
        import json

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return
        request_id = payload.get("id")
        future = self._pending.pop(request_id, None)
        if future is None or future.done():
            return
        if "error" in payload:
            error = payload.get("error") or {}
            future.set_exception(RuntimeError(str(error.get("message") or error)))
        else:
            future.set_result(payload.get("result"))

    async def _write(self, payload: dict[str, Any]) -> None:
        async with self._write_lock:
            self.stdout.write(encode(payload))
            self.stdout.write("\n")
            self.stdout.flush()

    def _next_request_id(self) -> str:
        value = f"yoyo-acp-{self._next_id}"
        self._next_id += 1
        return value


def _params_dict(params: Any) -> dict[str, Any]:
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise JsonRpcError(INVALID_PARAMS, "params must be an object")
    return params


def _initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": ACP_PROTOCOL_VERSION,
        "agentCapabilities": {
            "loadSession": True,
            "promptCapabilities": {
                "image": False,
                "audio": False,
                "embeddedContext": True,
            },
            "mcpCapabilities": {
                "http": False,
                "sse": False,
            },
        },
        "agentInfo": {
            "name": "yycode",
            "title": "yycode",
            "version": _project_version(),
        },
        "authMethods": [],
    }


def _project_version() -> str:
    try:
        import tomllib

        root = Path(__file__).resolve().parents[2]
        payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        return str(payload.get("project", {}).get("version") or "")
    except Exception:
        return ""


async def run_stdio_server(*, auto_approve: bool = False) -> None:
    """Run the ACP stdio server."""
    await AcpServer(auto_approve=auto_approve).serve()


def main(*, auto_approve: bool = False) -> None:
    """Synchronous entrypoint for python -m agent.acp.server."""
    asyncio.run(run_stdio_server(auto_approve=auto_approve))


if __name__ == "__main__":
    main()
