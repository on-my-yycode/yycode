"""ACP prompt content conversion helpers."""

from __future__ import annotations

from typing import Any


MAX_EMBEDDED_TEXT_CHARS = 20_000


def content_blocks_to_text(content: Any) -> str:
    """Convert ACP content blocks or plain text into a yoyoagent prompt string."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return _block_to_text(content)
    if not isinstance(content, list):
        return str(content or "")
    parts = [_block_to_text(block) for block in content]
    return "\n\n".join(part for part in parts if part).strip()


def _block_to_text(block: Any) -> str:
    if isinstance(block, str):
        return block
    if not isinstance(block, dict):
        return str(block)
    block_type = str(block.get("type") or block.get("kind") or "text")
    if block_type in {"text", "markdown"}:
        return str(block.get("text") or block.get("content") or "")
    if block_type in {"resource_link", "resource", "uri"}:
        uri = block.get("uri") or block.get("url") or block.get("path") or ""
        name = block.get("name") or block.get("title") or "resource"
        return f"Context resource: {name}\n{uri}".strip()
    if block_type in {"embedded_resource", "embedded"}:
        uri = block.get("uri") or block.get("url") or block.get("path") or ""
        text = str(block.get("text") or block.get("content") or block.get("data") or "")
        if len(text) > MAX_EMBEDDED_TEXT_CHARS:
            text = text[:MAX_EMBEDDED_TEXT_CHARS] + "\n... embedded resource truncated"
        header = f"Embedded context resource: {uri}" if uri else "Embedded context resource:"
        return f"{header}\n```\n{text}\n```"
    if block_type in {"image", "audio"}:
        return f"[Unsupported ACP {block_type} content omitted]"
    return str(block.get("text") or block.get("content") or block)

