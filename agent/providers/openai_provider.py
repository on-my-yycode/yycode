"""OpenAI LLM provider implementation."""

import json
from typing import Any, Optional, Callable

from openai import AsyncOpenAI

from .base import LLMProvider, ChatResponse, ToolCall


class OpenAIProvider(LLMProvider):
    """OpenAI API provider (compatible with OpenAI-like APIs)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
    ):
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        """Convert Anthropic-style messages to OpenAI format."""
        openai_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if block.get("type") == "tool_result":
                            # OpenAI handles tool results differently
                            openai_messages.append({
                                "role": "tool",
                                "tool_call_id": block["tool_use_id"],
                                "content": block["content"],
                            })
                        elif block.get("type") == "text":
                            text_parts.append(block["text"])
                    if text_parts:
                        openai_messages.append({
                            "role": "user",
                            "content": "\n".join(text_parts),
                        })
                else:
                    openai_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                if isinstance(content, list):
                    text_parts = []
                    tool_calls = []
                    for block in content:
                        if block.get("type") == "text":
                            text_parts.append(block["text"])
                        elif block.get("type") == "tool_use":
                            tool_calls.append({
                                "id": block["id"],
                                "type": "function",
                                "function": {
                                    "name": block["name"],
                                    "arguments": json.dumps(block["input"]),
                                },
                            })
                    assistant_msg = {
                        "role": "assistant",
                        "content": "\n".join(text_parts) if text_parts else None,
                    }
                    if tool_calls:
                        assistant_msg["tool_calls"] = tool_calls
                    openai_messages.append(assistant_msg)
                else:
                    openai_messages.append({"role": "assistant", "content": content})

        return openai_messages

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert Anthropic-style tools to OpenAI format."""
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            })
        return openai_tools

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: Optional[str] = None,
        stream_callback: Optional[Callable[[str, str], None]] = None,
    ) -> ChatResponse:
        """Send chat request to OpenAI API."""
        openai_messages = self._convert_messages(messages)
        openai_tools = self._convert_tools(tools) if tools else None

        if system_prompt:
            openai_messages.insert(0, {"role": "system", "content": system_prompt})

        current_text = ""
        tool_calls_data = []
        usage = None

        if stream_callback:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                tools=openai_tools,
                stream=True,
                stream_options={"include_usage": True},
                max_tokens=4096,
            )

            current_tool_call = None

            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = self._extract_usage(chunk.usage)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if delta.content:
                    current_text += delta.content
                    await stream_callback("text_delta", delta.content)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index >= len(tool_calls_data):
                            tool_calls_data.append({
                                "id": tc.id,
                                "name": tc.function.name if tc.function else None,
                                "args": "",
                            })
                            current_tool_call = tool_calls_data[-1]
                        if tc.function and tc.function.arguments:
                            current_tool_call["args"] += tc.function.arguments
        else:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                tools=openai_tools,
                stream=False,
                max_tokens=4096,
            )
            usage = self._extract_usage(getattr(response, "usage", None))
            choice = response.choices[0]
            if choice.message.content:
                current_text = choice.message.content
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls_data.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": tc.function.arguments,
                    })

        tool_calls = []
        for tc in tool_calls_data:
            try:
                args = json.loads(tc["args"]) if tc["args"] else {}
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], args=args))

        return ChatResponse(
            content=current_text,
            tool_calls=tool_calls,
            raw_response=None,
            usage=usage,
        )

    async def close(self) -> None:
        """Close the client."""
        await self.client.close()

    def _extract_usage(self, usage: Any) -> Optional[dict[str, int]]:
        """Normalize OpenAI usage data."""
        if usage is None:
            return None
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if input_tokens is None and output_tokens is None and total_tokens is None:
            return None
        if total_tokens is None:
            total_tokens = (input_tokens or 0) + (output_tokens or 0)
        return {
            "input_tokens": input_tokens or 0,
            "output_tokens": output_tokens or 0,
            "total_tokens": total_tokens or 0,
        }
