"""Tests for read-only LSP tools."""

import asyncio
import sys

from agent.lsp.client import LspClient
from agent.lsp.manager import LspManager
from agent.runtime.workspace_tools import WORKSPACE_BOUND_TOOLS
from tools import TOOL_HANDLERS, TOOLS
from tools.lsp_diagnostics import lsp_diagnostics
from tools.lsp_document_symbols import lsp_document_symbols


LSP_TOOL_NAMES = {
    "lsp_document_symbols",
    "lsp_workspace_symbols",
    "lsp_definition",
    "lsp_references",
    "lsp_hover",
    "lsp_diagnostics",
}


def test_lsp_tools_are_registered_and_workspace_bound():
    tool_names = {tool["name"] for tool in TOOLS}

    assert LSP_TOOL_NAMES <= tool_names
    assert LSP_TOOL_NAMES <= WORKSPACE_BOUND_TOOLS
    for name in LSP_TOOL_NAMES:
        assert name in TOOL_HANDLERS


def test_lsp_tool_returns_unavailable_when_no_server(monkeypatch, tmp_path):
    (tmp_path / "sample.py").write_text("def hello():\n    return 'hi'\n")
    monkeypatch.setattr("agent.lsp.manager.shutil.which", lambda name: None)

    result = asyncio.run(lsp_document_symbols("sample.py", workdir=tmp_path))

    assert "status: unavailable" in result
    assert "fallback: use grep and read_file" in result


def test_lsp_tool_rejects_workspace_escape(tmp_path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("def outside():\n    pass\n")

    result = asyncio.run(lsp_document_symbols(str(outside), workdir=tmp_path))

    assert result.startswith("Error:")
    assert "Path escapes workspace" in result


def test_lsp_manager_parses_document_symbols_without_server(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text("class Greeter:\n    def hello(self):\n        return 'hi'\n")
    manager = LspManager(tmp_path)
    payload = [
        {
            "name": "Greeter",
            "kind": 5,
            "selectionRange": {"start": {"line": 0, "character": 6}},
            "children": [
                {
                    "name": "hello",
                    "kind": 6,
                    "selectionRange": {"start": {"line": 1, "character": 8}},
                }
            ],
        }
    ]

    symbols = manager._parse_document_symbols(payload, sample)

    assert [symbol.name for symbol in symbols] == ["Greeter", "hello"]
    assert symbols[0].format() == "class Greeter sample.py:1:7 Greeter"
    assert symbols[1].format() == "method Greeter.hello sample.py:2:9 hello"


def test_lsp_manager_parses_symbol_information_locations(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text("def hello():\n    return 'hi'\n")
    manager = LspManager(tmp_path)
    payload = [
        {
            "name": "hello",
            "kind": 12,
            "location": {
                "uri": sample.as_uri(),
                "range": {"start": {"line": 0, "character": 4}},
            },
        }
    ]

    symbols = manager._parse_document_symbols(payload, sample)

    assert symbols[0].format() == "function hello sample.py:1:5 hello"


def test_lsp_manager_filters_noisy_document_symbol_kinds(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text("import os\n\ndef useful():\n    pass\n")
    manager = LspManager(tmp_path)
    payload = [
        {"name": "sample", "kind": 2, "selectionRange": {"start": {"line": 0, "character": 0}}},
        {"name": "useful", "kind": 12, "selectionRange": {"start": {"line": 2, "character": 4}}},
    ]

    symbols = manager._parse_document_symbols(payload, sample)

    assert [symbol.name for symbol in symbols] == ["useful"]


def test_lsp_manager_filters_workspace_external_locations(tmp_path):
    manager = LspManager(tmp_path)
    outside = tmp_path.parent / "external.py"
    item = {
        "uri": outside.as_uri(),
        "range": {"start": {"line": 3, "character": 2}},
    }

    assert manager._parse_location(item) is None


def test_lsp_diagnostics_reports_unsupported_for_empty_mvp_result(monkeypatch, tmp_path):
    (tmp_path / "sample.py").write_text("def hello():\n    return 'hi'\n")

    class FakeManager:
        async def diagnostics(self, path=None):
            return []

    monkeypatch.setattr("tools.lsp_utils.get_lsp_manager", lambda workdir: FakeManager())

    result = asyncio.run(lsp_diagnostics("sample.py", workdir=tmp_path))

    assert "status: unsupported" in result
    assert "use verify for authoritative validation" in result


def test_lsp_client_json_rpc_request_response(tmp_path):
    server = tmp_path / "fake_lsp_server.py"
    server.write_text(
        """
import json
import sys


def read_message():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if line in (b"\\r\\n", b"\\n", b""):
            break
        key, value = line.decode().split(":", 1)
        headers[key.lower()] = value.strip()
    if not headers:
        return None
    body = sys.stdin.buffer.read(int(headers["content-length"]))
    return json.loads(body.decode())


def write_message(payload):
    body = json.dumps(payload).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\\r\\n\\r\\n".encode() + body)
    sys.stdout.buffer.flush()


while True:
    message = read_message()
    if message is None:
        break
    method = message.get("method")
    if "id" in message:
        if method == "initialize":
            write_message({"jsonrpc": "2.0", "id": message["id"], "result": {"capabilities": {}}})
        elif method == "custom/echo":
            write_message({"jsonrpc": "2.0", "id": message["id"], "result": message.get("params")})
        elif method == "shutdown":
            write_message({"jsonrpc": "2.0", "id": message["id"], "result": None})
            break
""".strip()
    )

    async def run():
        client = LspClient([sys.executable, str(server)], tmp_path, timeout=2)
        await client.start()
        result = await client.request("custom/echo", {"ok": True})
        await client.shutdown()
        return result

    assert asyncio.run(run()) == {"ok": True}
