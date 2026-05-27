"""OpenAI LLM provider implementation."""

import json
import logging
from typing import Any, Optional, Callable

from openai import AsyncOpenAI
import tiktoken

from .base import LLMProvider, ChatResponse, ToolCall
from .text_tool_calls import TextToolCallStreamFilter, parse_text_tool_calls

logger = logging.getLogger(__name__)


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
                    reasoning_content = msg.get("reasoning_content")
                    if reasoning_content:
                        assistant_msg["reasoning_content"] = reasoning_content
                    openai_messages.append(assistant_msg)
                else:
                    assistant_msg = {"role": "assistant", "content": content}
                    reasoning_content = msg.get("reasoning_content")
                    if reasoning_content:
                        assistant_msg["reasoning_content"] = reasoning_content
                    openai_messages.append(assistant_msg)

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
        reasoning_content = None
        usage = None

        if stream_callback:
            text_filter = TextToolCallStreamFilter()
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                tools=openai_tools,
                stream=True,
                stream_options={"include_usage": True},
                max_tokens=16384,
            )

            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = self._extract_usage(chunk.usage)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                delta_reasoning = getattr(delta, "reasoning_content", None)
                if delta_reasoning:
                    reasoning_content = (reasoning_content or "") + delta_reasoning

                if delta.content:
                    current_text += delta.content
                    for safe_text in text_filter.feed(delta.content):
                        await stream_callback("text_delta", safe_text)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        while tc.index >= len(tool_calls_data):
                            tool_calls_data.append({
                                "id": None,
                                "name": None,
                                "args": "",
                            })
                        current_tool_call = tool_calls_data[tc.index]
                        if tc.id:
                            current_tool_call["id"] = tc.id
                        if tc.function and tc.function.name:
                            current_tool_call["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            current_tool_call["args"] += tc.function.arguments
            for safe_text in text_filter.flush():
                await stream_callback("text_delta", safe_text)
        else:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                tools=openai_tools,
                stream=False,
                max_tokens=16384,
            )
            usage = self._extract_usage(getattr(response, "usage", None))
            choice = response.choices[0]
            reasoning_content = getattr(choice.message, "reasoning_content", None)
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
        for index, tc in enumerate(tool_calls_data):
            args = _parse_tool_arguments(tc)
            tool_calls.append(
                ToolCall(
                    id=tc.get("id") or f"call_{index}",
                    name=tc.get("name") or "<unknown>",
                    args=args,
                )
            )

        cleaned_text, text_tool_calls = parse_text_tool_calls(current_text)
        if text_tool_calls:
            current_text = cleaned_text
            tool_calls.extend(text_tool_calls)

        return ChatResponse(
            content=current_text,
            tool_calls=tool_calls,
            content_blocks=_openai_content_blocks(current_text, reasoning_content),
            raw_response=None,
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
        """Count input tokens for OpenAI chat-style requests using tiktoken."""
        openai_messages = self._convert_messages(messages)
        if system_prompt:
            openai_messages.insert(0, {"role": "system", "content": system_prompt})
        openai_tools = self._convert_tools(tools) if tools else None

        encoding = self._encoding_for_model()
        if encoding is None:
            return None
        total = 0
        for message in openai_messages:
            total += 3
            for key, value in message.items():
                if value is None:
                    continue
                total += len(encoding.encode(self._stringify_token_value(value)))
                if key == "name":
                    total += 1
        total += 3
        if openai_tools:
            # Tool schema accounting is model-dependent; compact JSON keeps this close.
            total += len(encoding.encode(json.dumps(openai_tools, separators=(",", ":"))))
        return total

    def _encoding_for_model(self):
        try:
            return tiktoken.encoding_for_model(self.model)
        except Exception:
            try:
                return tiktoken.get_encoding("o200k_base")
            except Exception:
                return None

    def _stringify_token_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

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


def _parse_tool_arguments(tool_call_data: dict[str, Any]) -> dict[str, Any]:
    """Parse provider tool-call arguments and log safe diagnostics on failure."""
    raw_args = tool_call_data.get("args") or ""
    tool_name = tool_call_data.get("name") or "<unknown>"
    tool_id = tool_call_data.get("id") or "<missing>"
    if not raw_args:
        logger.warning(
            "OpenAI tool call has empty arguments: tool=%s id=%s",
            tool_name,
            tool_id,
        )
        return {}
    try:
        parsed = json.loads(raw_args)
    except json.JSONDecodeError as exc:
        logger.warning(
            "OpenAI tool call arguments failed JSON parsing: tool=%s id=%s args_len=%d error=%s pos=%d line=%d col=%d",
            tool_name,
            tool_id,
            len(raw_args),
            exc.msg,
            exc.pos,
            exc.lineno,
            exc.colno,
        )
        return {}
    if not isinstance(parsed, dict):
        logger.warning(
            "OpenAI tool call arguments parsed to non-object: tool=%s id=%s args_type=%s args_len=%d",
            tool_name,
            tool_id,
            type(parsed).__name__,
            len(raw_args),
        )
        return {}
    logger.debug(
        "OpenAI tool call arguments parsed: tool=%s id=%s args_len=%d arg_keys=%s",
        tool_name,
        tool_id,
        len(raw_args),
        sorted(str(key) for key in parsed.keys()),
    )
    return parsed


def _openai_content_blocks(content: str, reasoning_content: Optional[str]) -> Optional[list[dict[str, Any]]]:
    blocks: list[dict[str, Any]] = []
    if reasoning_content:
        blocks.append({"type": "reasoning_content", "reasoning_content": reasoning_content})
    if content:
        blocks.append({"type": "text", "text": content})
    return blocks or None
