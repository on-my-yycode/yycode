# Message Token Manager 设计

## 背景

当前项目已有 session messages 持久化、TUI 时间线、provider/tokenizer token counting 和自动上下文压缩能力。新的需求不是管理 session 生命周期，而是帮助用户理解当前会话内上下文 token 被哪些消息消耗，以及是否需要压缩。

因此本功能不命名为 Session Manager，而定位为：

```text
Message Token Manager
```

它只关注当前运行会话里的消息上下文和 token 压力。

## 边界

### 负责

- 统计当前会话上下文 token 占用。
- 展示每条消息的 estimated token、占比、类型和预览。
- 展示按 role/type 聚合的 token 消耗。
- 判断当前上下文压力，帮助用户知道是否接近模型上下文上限。
- 给出低风险压缩建议，说明预计节省 token 和风险。
- 首版支持用户确认后的手动压缩旧 tool output。

### 不负责

- 创建、切换、恢复或删除 session。
- 管理 session id。
- 管理跨 workspace 历史。
- 做 session 归档或搜索。
- 首版不做物理删除消息。
- 首版不做模型生成式摘要压缩。

这些仍属于 session persistence / session store / 后续路线图能力。

## 当前项目约束

当前 `Session.messages` 不包含 system prompt。system prompt 通过 provider 调用单独传入：

```python
provider.count_tokens(
    messages=messages_to_provider_format(messages),
    system_prompt=self.system_prompt,
    tools=TOOLS,
)
```

因此 UI 与统计模型需要把上下文拆成两个来源：

```text
system_prompt block
Session.messages[]
```

展示时可以把 system prompt 作为 protected 的单独区块，但不要把它伪装成 `message[0]`，否则 message index 会和真实 `Session.messages` 下标不一致。

## 管理对象

主要管理对象是当前运行会话中的：

```python
Session.messages
```

辅助统计对象包括：

```python
Session.system_prompt
TOOLS
Session.context_window_tokens
```

消息列表只展示真实 `Session.messages` 下标：

```text
message[0] user
message[1] assistant
message[2] tool
message[3] assistant
...
```

system prompt 和 tools schema 计入上下文总量，但在 UI 中作为单独 protected block 展示。

## Token 统计策略

首版需要区分两类 token：

```text
Exact context tokens
Estimated per-message tokens
```

### Exact context tokens

用于总览中的总上下文压力。优先复用当前 `Session.count_context_tokens()`：

- provider 支持时返回 exact token。
- provider 不支持或失败时回退到 estimate。

UI 中需要标注来源：

```text
Context: 92k / 128k tokens · exact
Context: 92k / 128k tokens · estimated
```

### Estimated per-message tokens

逐条 message token 首版使用估算值，复用或抽取当前 `Session.estimate_messages_token_usage()` / `_estimate_message_chars()` 的逻辑。

原因：

- 不同 provider 对逐条消息 token 的计算并不统一。
- 当前 provider counting 更适合统计整段上下文。
- 逐条 exact counting 会带来额外 API 成本或 tokenizer 复杂度。

因此消息列表列名建议明确写成：

```text
Est. Tokens
```

## 核心能力

### 1. Token 总览

展示当前上下文预算：

```text
Context Usage
Tokens: 92k / 128k · exact
Usage: 72%
Remaining: 36k
Pressure: High
```

按来源展示 token 分布：

```text
System prompt: 4k
Tools schema: 6k
User: 8k
Assistant: 22k
Tool: 58k
Other: 2k
```

目标是让用户一眼看到 token 主要被哪些来源消耗。

### 2. 消息级统计

按真实 `Session.messages` 下标展示消息占用：

```text
#   Type       Est. Tokens   %      Status       Recommendation
0   user       120           0.1%   protected    latest user request
1   assistant  2.8k          2.1%   keep         keep
2   tool       31k           24.2%  large        compress
3   tool       18k           14.1%  large        compress
4   assistant  7.5k          5.8%   keep         keep
```

建议字段：

- index
- role/type
- estimated token count
- 占当前上下文比例
- 是否 protected
- 是否可压缩
- 推荐操作
- 风险等级
- 内容预览

### 3. 上下文压力判断

压力等级：

```text
0% - 50%    Low
50% - 75%   Medium
75% - 90%   High
90%+        Critical
```

示例建议：

```text
当前上下文压力：High

建议：
- 压缩 3 条历史 tool output，预计节省 42k tokens
- 保留最近 20 条消息
- 不压缩最新用户需求和当前任务相关消息
- 不物理删除 assistant/tool call 链路
```

### 4. 压缩建议

首版只建议压缩：

```text
old_tool_outputs
```

规则：

- 只压缩旧的 `ToolMessage`。
- 优先压缩超长 tool result。
- 不压缩最近 N 条消息。
- 不压缩已经压缩过的 tool output。
- 不压缩未完成 tool call 链路。
- 不压缩 latest user message。
- 不压缩 approval 相关上下文。

建议数据结构：

```python
@dataclass
class CompressionSuggestion:
    message_indexes: list[int]
    strategy: str
    reason: str
    original_tokens: int
    estimated_after_tokens: int
    saved_tokens: int
    risk: Literal["low", "medium", "high"]
```

### 5. 手动压缩

首版手动压缩不调用模型生成摘要，只做确定性的 compact marker 替换。这样成本低、行为可预测，也不会引入新的模型幻觉。

压缩后必须保留：

- message 顺序。
- `ToolMessage.name`。
- `ToolMessage.tool_call_id`。
- 原 `additional_kwargs` 中必要 metadata。
- `context_compressed=True` 标记。
- 原始字符数或估算 token 数。

压缩后的内容示例：

```text
[Compressed old tool output]
tool: read_file
original_chars: 18420
estimated_original_tokens: 4605
reason: manually compressed by Message Token Manager.
```

这与当前 `ContextCompressor` 的安全策略一致，只是触发方式从后台自动变成用户确认后的手动操作。

## 保护规则

首版只做压缩，不做清除。但仍需要为每条消息标出保护状态，避免后续扩展时边界不清。

默认 protected：

- system prompt block。
- tools schema block。
- latest user message。
- 最近 N 条消息。
- 当前正在执行任务相关消息。
- approval 相关上下文。
- 未完成 tool call 链路。

默认 compressible：

- 旧的长 `ToolMessage`。
- 未被 `context_compressed` 标记的 tool output。
- 不在最近 N 条消息内。

默认 keep：

- 用户关键需求。
- assistant 架构决策。
- 当前任务计划相关消息。
- 已压缩 marker。

## UI 设计

建议新增当前会话内的消息 token 面板：

```text
MessageTokenManagerScreen
```

打开方式：

```text
Ctrl+M
```

`/messages` 命令不纳入当前设计规划，避免新增一套命令解析入口。

### ASCII UI 草图

```text
┌ Message Token Manager ──────────────────────────────────────────────────────┐
│ Context: 92k / 128k tokens · exact   72%   Pressure: High                  │
│ Remaining: 36k      Suggested savings: 44k                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Breakdown                                                                   │
│ System: 4k   Tools schema: 6k   User: 8k   Assistant: 22k   Tool: 58k       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Messages                                                                    │
│ #   Type       Est. Tokens   %       Status       Recommendation            │
│ 0   user       120           0.1%    protected    latest user request       │
│ 1   assistant  2.8k          2.1%    keep         keep                      │
│ 2   tool       31k           24.2%   large        compress                  │
│ 3   tool       18k           14.1%   large        compress                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Preview                                                                     │
│ #2 tool result: read_file                                                   │
│ Original: ~31k tokens · After: ~200 tokens · Save: ~30.8k · Risk: Low       │
│ Reason: old tool output outside recent message window                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Actions: Enter preview · C compress selected · A compress suggested · Ctrl+M close │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Textual 组件建议

采用左右分栏，和当前 `Ctrl+D` 文件变更面板体验保持一致：

```text
ModalScreen
  └── Horizontal
        ├── ListView(message-list)
        └── RichLog(message-detail)
```

## 数据模型

### MessageTokenStat

```python
@dataclass
class MessageTokenStat:
    index: int
    role: str
    message_type: str
    estimated_tokens: int
    percent: float
    preview: str
    protected: bool
    compressible: bool
    recommendation: str
    risk: Literal["low", "medium", "high"]
```

### ContextBlockStat

用于展示不属于 `Session.messages` 的上下文来源，例如 system prompt 和 tools schema。

```python
@dataclass
class ContextBlockStat:
    name: str
    estimated_tokens: int
    protected: bool
    preview: str
```

### MessageContextSummary

```python
@dataclass
class MessageContextSummary:
    total_tokens: int
    token_source: Literal["exact", "estimated"]
    context_window_tokens: int
    remaining_tokens: int
    pressure: Literal["low", "medium", "high", "critical"]
    by_role: dict[str, int]
    by_type: dict[str, int]
    largest_messages: list[int]
    compression_savings_estimate: int
```

## 核心服务设计

建议新增独立服务：

```text
MessageContextManager
```

职责：

```python
class MessageContextManager:
    def analyze(messages, *, system_prompt, tools, context_window_tokens) -> MessageContextSummary
    def context_blocks(system_prompt, tools) -> list[ContextBlockStat]
    def message_stats(messages) -> list[MessageTokenStat]
    def suggest_compression(messages) -> list[CompressionSuggestion]
    def compress_selected(messages, indexes) -> list[BaseMessage]
```

命名上避免使用 `SessionManager`，因为它不管理 session 生命周期。

## 与自动上下文压缩的关系

现有 `ContextCompressor` 是后台机制：

```text
上下文压力高时自动触发
```

Message Token Manager 是前台决策工具：

```text
让用户看到为什么需要压缩，以及压缩哪些内容最划算
```

关系：

```text
ContextCompressor
  - 继续负责自动压缩旧 tool output
  - 可抽出公共 trim/marker 逻辑供手动压缩复用

MessageContextManager
  - 负责统计
  - 负责建议
  - 负责预估收益
  - 在用户确认后调用公共压缩逻辑
```

## 执行流程

### 打开面板

```text
用户按 Ctrl+M
  -> 读取当前 Session.messages / system_prompt / tools
  -> 计算 token stats
  -> 生成 compression suggestions
  -> 展示 MessageTokenManagerScreen
```

### 手动压缩

```text
用户选择 Compress Suggested 或 Compress Selected
  -> 展示 affected messages 和 estimated savings
  -> 用户确认
  -> 压缩选中的旧 ToolMessage content 为 compact marker
  -> 更新 Session.messages
  -> 保存当前 session messages
  -> 刷新 token stats
  -> timeline 增加 context_compressed 事件
```

## 测试建议

### Token 统计测试

- system prompt 作为 context block 统计，不占用 `Session.messages` index。
- 不同 message role 的 estimated token 统计正确。
- context percent 计算正确。
- exact token source 和 estimated fallback 可区分。
- 超大 tool output 被识别为 largest message。

### 建议生成测试

- 旧 tool output 生成 compression suggestion。
- 最近消息不会被建议压缩。
- latest user message 不会被建议压缩。
- 已压缩消息不会重复建议压缩。
- 未完成 tool call 链路不会被建议压缩。

### 压缩测试

- 压缩后消息顺序不变。
- `ToolMessage.name` 保留。
- `ToolMessage.tool_call_id` 保留。
- 原始 content 被 compact marker 替换。
- `context_compressed=True` 被写入 metadata。
- token 估算下降。

### TUI 测试

- `Ctrl+M` 打开面板。
- 消息列表展示 estimated token 数。
- system prompt / tools schema 作为 protected block 展示。
- 选择消息后 preview 更新。
- Compress 操作有确认。
- 无可压缩消息时显示 empty state。

## 风险与边界

### 逐条 token 是估算

不同 provider tokenizer 差异较大。首版 UI 应明确标注 per-message token 为 estimated，整体 context token 则标注 exact 或 estimated。

### 压缩不是语义摘要

首版只做 compact marker，不做模型摘要。优点是稳定、便宜、低风险；缺点是压缩后无法恢复工具输出细节。

### tool call 链路不能破坏

assistant tool call 和 tool result 必须保持配对关系。首版只替换 `ToolMessage.content`，不物理删除消息。

### 用户误操作

手动压缩可能不可逆。需要确认提示，并展示 affected messages、预计节省和风险。

## 推荐结论

首版 Message Token Manager 应聚焦：

```text
只读统计 + 压缩建议 + 手动压缩旧 ToolMessage
```

它的价值是让用户知道 token 被谁消耗了，并能对低风险的大型历史 tool output 做可控压缩。

清除消息、undo、策略配置、模型摘要压缩等后续能力不放在本设计文档中，统一进入路线图管理。
