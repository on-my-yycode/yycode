"""Anthropic LLM provider implementation."""

from typing import Any, Optional, Callable

from anthropic import AsyncAnthropic

from .base import LLMProvider, ChatResponse, ToolCall


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
        full_content = []
        current_text = ""
        tool_calls_data = []
        current_tool_use = None
        in_thinking = False

        kwargs = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 8000,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if tools:
            kwargs["tools"] = tools

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
                            await stream_callback("text_delta", delta.text)
                    elif delta.type == "input_json_delta":
                        if current_tool_use:
                            current_tool_use["args"] += delta.partial_json
                elif event.type == "content_block_stop":
                    if in_thinking:
                        if stream_callback:
                            await stream_callback("thinking_end", "")
                        in_thinking = False
                    elif current_tool_use:
                        import json
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

        if current_text:
            full_content.append(current_text)

        final_message = await stream.get_final_message()
        usage = self._extract_usage(getattr(final_message, "usage", None))

        tool_calls = [
            ToolCall(id=tc["id"], name=tc["name"], args=tc["args"])
            for tc in tool_calls_data
        ]

        return ChatResponse(
            content=current_text,
            tool_calls=tool_calls,
            raw_response=final_message,
            usage=usage,
        )

    async def close(self) -> None:
        """Close the client."""
        await self.client.close()

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
