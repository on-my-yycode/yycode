"""Anthropic LLM provider implementation."""

import json
from typing import Any, Optional, Callable

from anthropic import AsyncAnthropic

from agent.logger import get_logger

from .base import LLMProvider, ChatResponse, ToolCall
from .text_tool_calls import TextToolCallStreamFilter, parse_text_tool_calls

logger = get_logger(__name__)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
    ):
        self.model = model
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=base_url
        )

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: Optional[str] = None,
        stream_callback: Optional[Callable[[str, str], None]] = None,
    ) -> ChatResponse:
        """Send chat request to Anthropic API."""
        import traceback

        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 8000,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools

        try:
            # First try non-streaming mode (more reliable for compatible APIs)
            return await self._chat_non_streaming(kwargs, stream_callback)
        except Exception as e:
            logger.warning(f"Non-streaming failed, trying streaming: {e}")
            try:
                return await self._chat_streaming(kwargs, stream_callback)
            except Exception as e2:
                logger.error(f"Both modes failed. Last error: {type(e2).__name__}: {e2}")
                logger.error(f"Traceback:\n{traceback.format_exc()}")
                raise

    async def _chat_non_streaming(
        self,
        kwargs: dict,
        stream_callback: Optional[Callable[[str, str], None]] = None,
    ) -> ChatResponse:
        """Non-streaming chat mode."""
        message = await self.client.messages.create(**kwargs)

        current_text = ""
        tool_calls_data = []
        text_filter = TextToolCallStreamFilter()

        for block in message.content:
            if block.type == "text":
                current_text += block.text
                if stream_callback:
                    for safe_text in text_filter.feed(block.text):
                        await stream_callback("text_delta", safe_text)
            elif block.type == "tool_use":
                tool_calls_data.append({
                    "name": block.name,
                    "args": block.input,
                    "id": block.id,
                })

        usage = self._extract_usage(getattr(message, "usage", None))
        content_blocks = self._normalize_content_blocks(message.content)

        tool_calls = [
            ToolCall(id=tc["id"], name=tc["name"], args=tc["args"])
            for tc in tool_calls_data
        ]
        cleaned_text, text_tool_calls = parse_text_tool_calls(current_text)
        if text_tool_calls:
            current_text = cleaned_text
            tool_calls.extend(text_tool_calls)
        elif stream_callback:
            for safe_text in text_filter.flush():
                await stream_callback("text_delta", safe_text)

        return ChatResponse(
            content=current_text,
            tool_calls=tool_calls,
            content_blocks=content_blocks,
            raw_response=message,
            usage=usage,
        )

    async def _chat_streaming(
        self,
        kwargs: dict,
        stream_callback: Optional[Callable[[str, str], None]] = None,
    ) -> ChatResponse:
        """Streaming chat mode (fallback)."""
        current_text = ""
        tool_calls_data = []
        current_tool_use = None
        in_thinking = False
        text_filter = TextToolCallStreamFilter()

        async with self.client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "thinking":
                        in_thinking = True
                        if stream_callback:
                            await stream_callback("thinking_start", "")
                    elif block.type == "text":
                        in_thinking = False
                    elif block.type == "tool_use":
                        in_thinking = False
                        current_tool_use = {
                            "name": block.name,
                            "id": block.id,
                            "args": "",
                        }
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "thinking_delta":
                        if stream_callback:
                            await stream_callback("thinking_delta", delta.thinking)
                    elif delta.type == "text_delta":
                        current_text += delta.text
                        if stream_callback:
                            for safe_text in text_filter.feed(delta.text):
                                await stream_callback("text_delta", safe_text)
                    elif delta.type == "input_json_delta":
                        if current_tool_use:
                            current_tool_use["args"] += delta.partial_json
                elif event.type == "content_block_stop":
                    if in_thinking:
                        if stream_callback:
                            await stream_callback("thinking_end", "")
                        in_thinking = False
                    elif current_tool_use:
                        try:
                            args = json.loads(current_tool_use["args"])
                        except json.JSONDecodeError:
                            args = {}
                        tool_calls_data.append({
                            "name": current_tool_use["name"],
                            "args": args,
                            "id": current_tool_use["id"],
                        })
                        current_tool_use = None

            final_message = await stream.get_final_message()
            usage = self._extract_usage(getattr(final_message, "usage", None))
            content_blocks = self._normalize_content_blocks(final_message.content)

        tool_calls = [
            ToolCall(id=tc["id"], name=tc["name"], args=tc["args"])
            for tc in tool_calls_data
        ]
        cleaned_text, text_tool_calls = parse_text_tool_calls(current_text)
        if text_tool_calls:
            current_text = cleaned_text
            tool_calls.extend(text_tool_calls)
        elif stream_callback:
            for safe_text in text_filter.flush():
                await stream_callback("text_delta", safe_text)

        return ChatResponse(
            content=current_text,
            tool_calls=tool_calls,
            content_blocks=content_blocks,
            raw_response=final_message,
            usage=usage,
        )

    async def close(self) -> None:
        """Close the client."""
        await self.client.close()

    async def count_tokens(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        tools: Optional[list[dict]] = None,
    ) -> Optional[int]:
        """Count input tokens using the Anthropic-compatible count endpoint."""
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
            }
            if system_prompt:
                kwargs["system"] = system_prompt
            if tools:
                kwargs["tools"] = tools

            response = await self.client.messages.count_tokens(**kwargs)
            input_tokens = getattr(response, "input_tokens", None)
            return int(input_tokens) if input_tokens is not None else None
        except Exception:
            logger.warning("Count tokens not supported, falling back to estimation")
            return None

    def _extract_usage(self, usage: Any) -> Optional[dict[str, int]]:
        """Normalize Anthropic usage data."""
        if usage is None:
            return None
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        if input_tokens is None and output_tokens is None:
            return None
        return {
            "input_tokens": input_tokens or 0,
            "output_tokens": output_tokens or 0,
            "total_tokens": (input_tokens or 0) + (output_tokens or 0),
        }

    def _normalize_content_blocks(self, blocks: Any) -> list[dict[str, Any]]:
        """Convert Anthropic content blocks into provider-neutral serializable dicts."""
        normalized: list[dict[str, Any]] = []
        for block in blocks or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                normalized.append({"type": "text", "text": getattr(block, "text", "")})
            elif block_type == "thinking":
                thinking_block = {
                    "type": "thinking",
                    "thinking": getattr(block, "thinking", ""),
                }
                signature = getattr(block, "signature", None)
                if signature:
                    thinking_block["signature"] = signature
                normalized.append(thinking_block)
            elif block_type == "redacted_thinking":
                data = {"type": "redacted_thinking"}
                for field in ("data", "signature"):
                    value = getattr(block, field, None)
                    if value:
                        data[field] = value
                normalized.append(data)
            elif block_type == "tool_use":
                normalized.append(
                    {
                        "type": "tool_use",
                        "id": getattr(block, "id", None),
                        "name": getattr(block, "name", None),
                        "input": getattr(block, "input", None) or {},
                    }
                )
        return normalized
