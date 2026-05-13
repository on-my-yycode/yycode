"""Small JSON-RPC 2.0 helpers for ACP stdio transport."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


@dataclass(frozen=True)
class JsonRpcMessage:
    """One decoded JSON-RPC message."""

    method: str | None = None
    params: Any = None
    id: str | int | None = None
    is_request: bool = False
    is_notification: bool = False


class JsonRpcError(Exception):
    """JSON-RPC error with a stable code."""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


def decode_message(line: str) -> JsonRpcMessage:
    """Decode one newline-delimited JSON-RPC message."""
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise JsonRpcError(PARSE_ERROR, "Parse error") from exc
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request")
    method = payload.get("method")
    if method is None:
        return JsonRpcMessage(id=payload.get("id"))
    if not isinstance(method, str):
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request")
    has_id = "id" in payload
    return JsonRpcMessage(
        method=method,
        params=payload.get("params"),
        id=payload.get("id"),
        is_request=has_id,
        is_notification=not has_id,
    )


def response(result: Any, request_id: str | int | None) -> dict[str, Any]:
    """Build a JSON-RPC success response."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(
    code: int,
    message: str,
    request_id: str | int | None = None,
    data: Any = None,
) -> dict[str, Any]:
    """Build a JSON-RPC error response."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def request(method: str, params: Any, request_id: str | int) -> dict[str, Any]:
    """Build a JSON-RPC request."""
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def notification(method: str, params: Any) -> dict[str, Any]:
    """Build a JSON-RPC notification."""
    return {"jsonrpc": "2.0", "method": method, "params": params}


def encode(payload: dict[str, Any]) -> str:
    """Encode one JSON-RPC payload as a stdio line."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

