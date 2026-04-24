# 自动上下文压缩功能设计文档

## 概述

本文档记录 yoyoagent 当前已实现的上下文窗口显示与自动上下文压缩机制。该机制用于降低长期会话中 `messages` 无限增长带来的 API 失败、成本上升和响应变慢风险。

当前实现采用保守策略：在主 `Session` 调用 graph 前，优先使用 provider/tokenizer 计数检查上下文压力；精确计数不可用时回退到本地估算。当超过阈值时，只压缩较早的长 `ToolMessage` 输出，不压缩最近消息，也不摘要用户/AI 对话。

## 当前实现状态

已实现：

- `yoyo >>` 前显示当前上下文压力，格式为 `[used/window percent]`，例如 `[3.2k/224k 1.4%]`。
- 支持通过 `YOYO_CONTEXT_WINDOW_TOKENS` 覆盖上下文窗口大小。
- 对 `doubao-seed-2.0-code` 默认使用 `224_000` tokens 窗口，按最大输入长度而不是总上下文长度估算。
- 在 `Session.send()` 和 `Session.send_stream()` 调用 graph 前执行压缩检查。
- 当上下文 token 数超过窗口的 `70%` 时，压缩旧的长工具输出。
- Provider 层提供可选 `count_tokens(...)` 能力，Anthropic 使用 count endpoint，OpenAI 使用 `tiktoken` 计数。
- 精确计数失败时自动回退到本地字符估算，不阻塞主流程。
- 压缩触发时通过 stream 事件打印用户可见日志，例如 `[context] compressed 1 old tool outputs (1002 -> 42 tokens, exact)`。

未实现：

- Human/AI 对话摘要压缩。
- 重度压缩策略。
- 压缩历史持久化和监控指标。

## 问题背景

当前 LangGraph 状态使用追加式消息列表：

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
```

如果只在 graph 的 LLM 节点中临时压缩 `state["messages"]`，下一轮主会话仍会从 `Session.messages` 带回原始长历史。因此当前实现选择在 `Session` 层压缩 canonical history，也就是压缩真正持久存在的主会话消息列表。

消息流现在是：

```text
用户输入
  -> Session.add_user_message(...)
  -> Session._compress_context_if_needed()
  -> graph.ainvoke({"messages": self.messages})
  -> Session.messages = result["messages"]
```

## 上下文窗口大小

窗口大小由 `Session.context_window_tokens` 保存。

来源优先级：

1. 显式传入 `Session(..., context_window_tokens=...)`。
2. 环境变量 `YOYO_CONTEXT_WINDOW_TOKENS`。
3. 根据 provider/model 推断。
4. 默认值 `128_000`。

当前推断规则：

```python
if "doubao" in model and "code" in model:
    return 224_000
if "claude" in model:
    return 200_000
if any(name in model for name in ("gpt-4o", "gpt-4.1", "gpt-5")):
    return 128_000
return 128_000
```

`doubao-seed-2.0-code` 使用 `224k` 是因为火山引擎规格中最大上下文长度为 `256k`，但最大输入长度为 `224k`，剩余空间需要留给思考内容和输出。yoyoagent 的提示符展示的是当前输入上下文压力，因此使用 `224k` 更贴近实际可用输入预算。

可在 `.env` 中覆盖：

```env
YOYO_CONTEXT_WINDOW_TOKENS=224000
```

## Prompt 显示

`main.build_prompt(session)` 使用以下数据生成交互提示符：

- `session.estimate_token_usage()`：估算当前 system prompt + messages token 数。
- `session.context_window_tokens`：当前上下文窗口大小。
- `session.estimate_context_window_percent()`：估算使用百分比。

示例：

```text
[3.2k/224k 1.4%] yoyo >>
```

这里显示的是当前上下文压力，不是累计 API usage。累计 usage 仍保留在 `Session.cumulative_usage` 中，用于统计和 stream usage 事件。

## Token 计数

`LLMProvider` 提供可选计数接口：

```python
async def count_tokens(
    self,
    messages: list[dict],
    system_prompt: Optional[str] = None,
    tools: Optional[list[dict]] = None,
) -> Optional[int]:
    return None
```

返回值语义：

- `int`：provider/tokenizer 计数成功。
- `None`：当前 provider 不支持或计数资源不可用，调用方应回退估算。

当前实现：

- Anthropic provider 调用 `client.messages.count_tokens(...)`，传入与 `chat()` 一致的 `model`、`messages`、`system`、`tools`，返回 `input_tokens`。
- OpenAI provider 使用 `tiktoken` 对转换后的 OpenAI chat messages、system prompt 和 tools schema 计数。
- OpenAI tokenizer 资源不可用时返回 `None`，避免因为 tokenizer 缓存缺失或离线环境影响正常对话。
- Base provider 默认返回 `None`。

`Session.count_context_tokens(...)` 是统一入口：

```python
exact = await provider.count_tokens(
    messages=provider_messages,
    system_prompt=self.system_prompt,
    tools=TOOLS,
)
if exact is not None:
    return exact, True
return self.estimate_messages_token_usage(messages), False
```

初版只在压缩触发检查时调用 provider 计数，不在每次 `yoyo >>` prompt 构建时远程计数，避免额外延迟和成本。

## 压缩触发条件

当前压缩器位于 `agent/context_compressor.py`。

默认参数：

```python
DEFAULT_COMPRESSION_RATIO = 0.7
DEFAULT_KEEP_RECENT_MESSAGES = 20
DEFAULT_MAX_TOOL_CHARS = 2_000
```

触发逻辑：

```python
threshold_tokens = int(context_window_tokens * compression_ratio)
if context_tokens >= threshold_tokens:
    compress old long ToolMessage outputs
```

例如对 `doubao-seed-2.0-code`：

```text
context_window_tokens = 224_000
compression_ratio = 0.7
threshold_tokens = 156_800
```

## 压缩策略

当前只实现轻度压缩。

策略规则：

- 只处理 `ToolMessage`。
- 只处理最近 `20` 条消息之前的旧消息。
- 只处理内容长度超过 `2_000` 字符的工具输出。
- 保留 `tool_call_id` 和 `name`。
- 复制原始 `additional_kwargs`。
- 添加 `context_compressed=True` 和 `original_chars` 元数据。
- 不删除消息，不改变消息顺序。

压缩后的工具输出示例：

```text
[Compressed old tool output]
tool: bash
original_chars: 12000
reason: context window usage crossed the compression threshold.
```

这样做的目的是优先压缩最容易膨胀的 bash/read_file/load_skill/subagent 等工具结果，同时避免破坏最近一轮 tool call / tool result 的上下文关系。

## 可观测性

压缩发生后，`Session._compress_context_if_needed()` 会发出结构化 stream 事件：

```python
StreamEvent(
    source="main",
    session_id=self.id,
    event_type="context_compressed",
    content="compressed 1 old tool outputs (1002 -> 42 tokens, exact)",
)
```

`ConsoleStreamRenderer` 收到该事件后打印：

```text
[context] compressed 1 old tool outputs (1002 -> 42 tokens, exact)
```

计数来源会体现在日志末尾：

- `exact`：压缩前后都使用 provider/tokenizer 计数成功。
- `estimated`：至少有一次计数回退到了本地估算。

该事件也可被后续统一流式输出层转发给其它端使用。

## 关键设计取舍

### 为什么在 Session 层压缩

`Session.messages` 是长期会话历史的真实来源。Graph state 使用 `add_messages` reducer，更适合追加节点输出，不适合替换整段历史。如果压缩只发生在 LLM node 内部，压缩结果不会自然回写到下一轮主会话。

因此当前实现选择：

```text
Session.messages 压缩后再传入 graph
```

这保证压缩结果会持续生效。

### 为什么只压缩旧 ToolMessage

工具输出通常是上下文膨胀主因，尤其是 `bash`、`read_file`、`load_skill`、`subagent` 返回。先压缩旧工具输出可以用最小行为变化获得明显 token 节省。

当前不压缩 Human/AI 对话，是为了避免摘要质量不稳定导致任务意图丢失。

### 为什么保留最近 20 条消息

最近消息最可能包含当前任务状态、最新工具调用和模型下一步决策依据。保留最近 20 条可以降低破坏 OpenAI/Anthropic 工具调用顺序语义的风险。

## 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| token 估算不准 | 可能过早或过晚压缩 | 已优先使用 provider/tokenizer 计数，失败时回退估算 |
| 工具输出被压缩后细节丢失 | 模型可能无法引用旧日志细节 | 仅压缩旧工具输出，保留最近消息 |
| 没有可压缩 ToolMessage 时仍超过窗口 | 仍可能调用失败 | 后续增加摘要压缩或重度压缩 |
| 压缩后的 ToolMessage 再次被压缩 | 无实际收益 | 已通过内容变短降低重复压缩概率，后续可显式跳过 `context_compressed` |

## 测试覆盖

当前测试覆盖：

- prompt 显示上下文窗口压力，而不是累计 usage。
- token 数格式支持 `k/m`。
- `YOYO_CONTEXT_WINDOW_TOKENS` 解析。
- `doubao-seed-2.0-code` 默认推断为 `224k`。
- Base provider 默认不支持计数并返回 `None`。
- Anthropic provider 调用 count endpoint 并返回 `input_tokens`。
- OpenAI provider 使用 tokenizer 计数 messages/system/tools，tokenizer 不可用时返回 `None`。
- Session 压缩优先使用 provider 计数，并在日志中标记 `exact` 或 `estimated`。
- 超阈值时压缩旧工具输出并发出 `context_compressed` 事件。
- usage 累计逻辑保持不变。

验证命令：

```bash
pytest
```

## 后续计划

### Phase 1: 计数增强

- 为更多 OpenAI-compatible / Anthropic-compatible 网关验证 tokenizer 或 endpoint 支持情况。
- 在 prompt 显示中可选标记 estimated/exact，但避免每轮输入前都调用远程计数。
- 增加 debug 日志记录计数失败原因。

### Phase 2: 中度压缩

- 对较早的 Human/AI 对话生成摘要消息。
- 摘要生成应禁用工具调用，避免递归复杂化。
- 摘要结果需要保留用户目标、关键决策、已修改文件、测试结果和未完成事项。

### Phase 3: 重度压缩

- 当轻度和中度压缩仍无法降到安全阈值时，只保留 system prompt、摘要和最近 K 条消息。
- 增加更明确的用户可见日志，说明压缩级别和潜在信息损失。

### Phase 4: 可配置策略

- 支持配置 `compression_ratio`、`keep_recent_messages`、`max_tool_chars`。
- 支持禁用自动压缩。
- 支持导出压缩历史用于调试。

## 总结

当前实现是一个低风险 MVP：它不改变 graph 拓扑，不引入额外 LLM 调用，不摘要用户意图，只在主会话进入 graph 前压缩旧的长工具输出，并通过 stream 事件让用户看到压缩发生。

这个版本已经能缓解长期 coding session 中最常见的上下文膨胀问题，同时为后续精确 token 计数、多级摘要压缩和统一流式输出保留了扩展空间。
