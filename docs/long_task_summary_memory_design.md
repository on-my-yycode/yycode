# 长任务摘要记忆设计

## 背景

当前 yoyoagent 已经具备四类上下文治理能力：

- `ContextCompressor` 会在上下文压力较高时压缩旧 `ToolMessage` 输出。
- `Message Token Manager` 可以分析当前上下文 token 占用，并手动压缩旧工具输出。
- `Session._prune_todo_artifacts()` 会在任务正常完成后裁剪内部 todo 工具调用和 todo tool result。
- `Task Summary Memory` 会在任务完成后生成确定性任务摘要，并在上下文压力下合并旧 summary、保留 latest/recent messages。

这些能力已经覆盖长任务摘要记忆的核心目标：稳定保留目标、约束、决策、文件、验证、风险和下一步，同时减少旧 todo/tool 输出与重复历史对后续任务的污染。本文档保留原设计和验收边界，用于解释当前实现依据；后续如继续投入，应定位为可选体验或模型增强，例如 summary 统计展示、手动 summary/undo 入口和模型生成式补充。

## 外部参考

Claude Code 和 Codex 的上下文压缩思路有几个共同点值得借鉴：

- 先压缩或移除低价值历史输出，再总结旧对话。
- 启动规则、工具 schema、项目说明等基础上下文应与对话历史分离，不应该被压入任务摘要里。
- 摘要应保留用户目标、约束、决策、已改文件、验证结果、风险和下一步，而不是泛泛复述聊天。
- 压缩后要避免反复重读同一批文件，否则节省的 token 会被重新探索抵消。

yoyoagent 的现有优势是 `TodoManager.memory` 已经维护以下字段，刚好可以作为确定性摘要骨架：

```text
user_goal
constraints
files_inspected
files_modified
decisions
test_results
open_risks
next_steps
```

首版应优先复用这份结构化事实，而不是直接让模型自由总结整段历史。

## 目标

- 长任务完成或上下文压力较高时，稳定保留任务级事实。
- 减少旧 Human/AI 对话和重复状态对后续上下文的污染。
- 与现有 todo artifact 清理、tool output 压缩、session persistence 兼容。
- 让恢复 session 后仍能知道上一轮做了什么、为什么做、还剩什么风险。
- timeline 只展示轻量摘要事件，不把大段摘要刷给用户。

## 非目标

- 首版不做长期跨 session 知识库。
- 首版不做向量检索或项目级 memory。
- 首版不物理删除最近用户请求、当前未完成 tool call 链路或审批上下文。
- 首版不依赖模型生成式摘要，避免幻觉和额外成本。
- 首版不改变 system prompt、tools schema、skills 加载规则。

## 核心对象

新增模块建议：

```text
agent/task_memory.py
```

核心类型：

```python
TaskSummaryMemory
TaskSummaryMemoryBuilder
TaskSummaryMemoryPolicy
```

`TaskSummaryMemory` 是一条进入 `Session.messages` 的受控摘要消息。建议使用 `HumanMessage` 承载，原因是当前 `Session.messages` 不包含 system prompt，使用 HumanMessage 对 provider payload 的影响最小，也便于 session persistence 原样保存。

消息应带有 metadata：

```python
additional_kwargs = {
    "context_policy": "summary_memory",
    "summary_memory": True,
    "covered_start_index": 12,
    "covered_end_index": 48,
    "source": "automatic",
}
```

## 摘要格式

摘要内容使用固定 Markdown 模板，但字段严格、短句优先：

```markdown
[Task Summary Memory]
scope: current_session
source: automatic
covered_messages: 12-48
token_change: 42000 -> 4000 estimated

## User Goal
...

## Constraints
- ...

## Current Plan
- completed: ...
- in_progress: ...
- pending: ...

## Decisions
- ...

## Files
Inspected:
- agent/session.py: ...

Modified:
- agent/task_memory.py: ...

## Verification
- pytest tests/test_x.py -q: passed
- ruff check .: not run, reason: docs-only

## Open Risks
- ...

## Next Steps
- ...
```

首版摘要可以从 `TodoManager.memory`、todo items、当前消息窗口和工具事件 metadata 中确定性生成。没有信息时不要编造，用 `none recorded` 或省略该小节。

## 触发策略

### 1. 自动触发：上下文压力高

在 `Session._compress_context_if_needed()` 中保持现有顺序：

```text
先压缩旧 ToolMessage
再重新估算 token
如果仍超过 task summary threshold，则尝试摘要旧任务上下文
```

建议阈值：

```text
tool_output_compression_threshold = 70% context window
task_summary_threshold = 75% context window
critical_threshold = 90% context window
```

首版可以只在存在已完成任务范围时自动摘要，避免在任务进行中删掉仍有用的近期过程。

### 2. 阶段触发：任务完成

当 `todo_manager.can_finish_task()` 为 true 时：

```text
build final task summary memory
prune todo artifacts
save messages
```

如果本轮消息很短，可以只执行 todo artifact 清理，不生成摘要。建议满足任一条件再生成：

- 本轮新增消息数超过 8。
- 本轮估算 token 超过 8k。
- 本轮包含超过 3 个工具调用。
- 本轮修改了文件或运行了验证。

### 3. 手动触发：Message Token Manager

后续可在 `Ctrl+M` 中增加建议项：

```text
Create Task Summary Memory
```

首版实现可以不做 UI，只预留 `Session.summarize_task_context()` API。

## 压缩边界

### 不能摘要替换

- 最新用户消息。
- 最近 N 条消息，建议 N=20。
- 当前未完成 tool call 链路中的 AIMessage / ToolMessage。
- 审批相关消息和审批失败消息。
- system prompt、tools schema、skills 内容。
- 当前任务未完成时的最新 todo / Task State 事实。
- 已有最新一条 Task Summary Memory。

### 可以摘要替换

- 已完成阶段的旧 Human/AI 对话。
- 已压缩的旧 tool output marker。
- 已完成任务中的 todo tool call 和 todo ToolMessage。
- 重复的中间状态说明。
- 已经被摘要覆盖的早期 assistant 过程消息。

## Session 消息重写策略

推荐新增：

```python
Session._summarize_completed_task_context(task_start_index: int, task_end_index: int)
```

首版行为：

1. 从 `messages[task_start_index:task_end_index]` 和 `TodoManager.memory` 生成 `Task Summary Memory`。
2. 保留 `messages[:task_start_index]` 中最近一条 summary memory。
3. 将可替换范围压缩成一条 summary memory。
4. 保留最后 assistant final answer，方便恢复 session 后仍能看到上一轮结论。
5. 再调用 `_prune_todo_artifacts()` 清理 todo 工具调用。

示意：

```text
before:
  old summary
  user request
  assistant planning + todo call
  todo ToolMessage
  tool messages
  assistant progress
  final answer

after:
  old summary
  user request
  [Task Summary Memory]
  final answer
```

如果 final answer 已完整合并到 summary，后续版本可以考虑只保留 summary，但首版不建议这么激进。

## 与现有模块关系

### ContextCompressor

继续只负责旧 `ToolMessage` 的确定性 marker 压缩，不处理 Human/AI 对话。

### Message Token Manager

负责展示上下文压力、候选压缩项，以及后续手动触发 summary。`Task Summary Memory` 应显示为 protected，不建议被普通 tool output 压缩逻辑处理。

### TodoManager

继续负责实时任务计划和任务内 memory。`TaskSummaryMemoryBuilder` 从 `TodoManager.get_task_state()` 读取结构化事实，不反向修改 todo。

### SessionStore

继续保存 canonical `Session.messages`。摘要后的消息就是 canonical history，恢复 session 时不需要重新生成。

### TUI Timeline

只显示轻量事件：

```text
Context summarized · 18 old messages -> Task Summary Memory · saved ~32k tokens
```

不在 timeline 中展开完整 summary，避免时间流噪声。

## 实现阶段

### Phase 0：evals MVP 先行

长任务摘要会重写 `Session.messages`，风险高于普通工具输出压缩。它可能影响模型能看到的历史事实、tool call / ToolMessage 配对、session resume、todo artifact 清理，以及新任务是否被旧任务污染。

因此在实现摘要前，先建立一个轻量 evals 基线：

```text
evals/
  run.py
  common.py
  tasks/
    context_session_baseline/
      eval.py
```

首批 evals 聚焦保护摘要实现会触碰的行为：

- 已完成任务不会把旧 todo artifacts 留到下一轮上下文。
- session resume 后仍能恢复关键 messages。
- 旧 tool output 自动压缩后仍保留 tool linkage。
- 未完成任务不会被当成已完成任务清理。
- 多文件/验证类任务事实能被稳定识别为后续摘要输入。

这一步不追求完整 eval 平台，也不引入模型评分。先用确定性 fake provider 和本地检查建立可重复基线，后续再扩展 bugfix、feature、refactor、security review 等任务集。

### Phase 1：确定性摘要

- 新增 `agent/task_memory.py`。
- 从 `TodoManager.memory` 和当前 todo items 生成固定格式摘要。
- 给 summary message 增加 `context_policy=summary_memory` metadata。
- 增加单元测试覆盖摘要格式、字段保留和空字段处理。

### Phase 2：Session 接入

- 在任务完成路径中生成 summary memory。
- 与 `_prune_todo_artifacts()` 串联，确保 todo artifacts 被清理但摘要保留。
- 增加 `context_summarized` stream event。
- session 保存后恢复，summary memory 仍在。

### Phase 3：压缩旧 Human/AI 对话

- 引入安全范围选择策略。
- 保留最新用户消息、最近 N 条消息和未完成 tool call 链路。
- 替换已完成旧任务范围为 summary memory。
- 与现有自动 tool output 压缩按顺序执行。

### Phase 4：模型生成式增强

在确定性摘要稳定后再引入模型摘要，用于补充：

- decisions 背后的原因。
- 文件修改意图。
- open risks 和 next steps 的自然语言整理。

模型输出必须走 schema 校验，失败时退回确定性摘要。模型不能覆盖 `TodoManager.memory` 中已有事实，只能补充缺失描述。

### Phase 5：TUI / Message Token Manager 手动入口

- 在 `Ctrl+M` 面板中展示 summary memory 统计。
- 增加手动 `Create Task Summary Memory` 操作。
- 增加最近一次 summary undo，复用现有 message compression backup 思路。

## 测试计划

- 任务完成后生成一条 `[Task Summary Memory]`。
- todo ToolMessage 被清理，但 summary 保留 goal、decisions、files、test_results。
- 未完成任务不会摘要替换关键上下文。
- 最新用户消息和最近 N 条消息不被替换。
- 恢复 session 后 summary memory 仍存在。
- 多轮任务不会无限堆叠 summary，至少保留最新有效摘要。
- provider payload 中没有断裂的 tool call / ToolMessage 配对。
- 自动 tool output 压缩与 task summary 可以连续执行，不互相覆盖。
- timeline 只出现轻量 `context_summarized` 事件，不输出完整 summary。

## 验收标准

首版验收以可靠为先：

- 长任务完成后，session 中不再残留大量 todo tool result。
- 上一轮关键事实仍可被模型读取：目标、约束、改过哪些文件、跑过哪些验证、剩余风险。
- 新任务开始时，模型不会被上一轮 todo 状态污染。
- 上下文 token 明显下降，且 `Ctrl+M` 能看到 summary memory 的占用。
- timeline 保持干净，只显示摘要事件。

## 风险与缓解

- 摘要丢失细节：首版保留最近 N 条消息和 final answer，不急于删除全部历史。
- 摘要幻觉：首版只做确定性摘要，后续模型摘要必须 schema 校验。
- tool call 链路断裂：只替换完整完成的历史范围，保留未完成链路。
- 重复摘要污染：summary memory 需要 metadata 标记，后续压缩时识别并合并旧 summary。
- 过度压缩导致重读文件：摘要必须保留 files_inspected、files_modified 和关键定位信息。
