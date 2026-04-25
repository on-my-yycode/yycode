# yoyoagent 核心工作流架构

## 概览

yoyoagent 的核心流程现在采用 “LangGraph 编排层 + nodes + runtime 服务” 的分层结构。

核心原则：

- `agent/graph.py` 只负责组装 LangGraph 节点和边。
- LLM 调用逻辑放在 `agent/nodes/llm_node.py`。
- 工具节点入口放在 `agent/nodes/tools_node.py`。
- Task State 结束保护放在 `agent/nodes/task_guard_node.py`。
- 工具注册、审批、workflow guard、调度和执行细节放在 `agent/runtime/`。

## 工作流图

```text
User Input
  -> Session.send()
  -> Context compression if needed
  -> LangGraph

LangGraph:
  START
    -> llm
    -> tools       when tool calls exist
    -> task_guard  when no tool calls
    -> END         only when Task State is complete
```

## 目录分层

```text
agent/
  graph.py
  nodes/
    state.py
    llm_node.py
    tools_node.py
    task_guard_node.py
  runtime/
    context.py
    tool_registry.py
    tool_executor.py
    tool_scheduler.py
    workflow_guard.py
    approval_service.py
    tool_events.py
```

## 关键组件

### Session

`agent/session.py` 负责会话级状态：

- session id
- provider
- workdir
- system prompt
- message history
- stream callback
- approval callback
- TodoManager
- context compression
- cumulative usage

每次 `send()` 会：

1. 为新用户输入重置 Task State。
2. 添加 HumanMessage。
3. 必要时压缩旧上下文。
4. 调用 LangGraph。
5. 捕获审批拒绝或 LLM 失败。
6. 累计 usage。

### graph.py

`agent/graph.py` 是薄编排层。

它创建 `AgentRuntimeContext`，并组装：

- `llm`
- `tools`
- `task_guard`

当前保留了这些兼容入口，方便旧测试和外部调用逐步迁移：

- `create_llm_node(...)`
- `create_tools_node(...)`
- `execute_tool_calls(...)`

### AgentRuntimeContext

`agent/runtime/context.py` 集中保存图运行时依赖：

- provider
- system prompt
- TodoManager
- workdir
- session id
- skill dirs
- stream callback
- approval callback
- tool schemas
- tool handlers
- workflow state
- run_tool 函数

这样 nodes 和 runtime 服务不需要层层传递长参数列表。

### LLM Node

`agent/nodes/llm_node.py` 负责：

- LangChain message 转 provider message。
- 调用 `chat_with_retry(...)`。
- 转发 provider stream events。
- 发送 usage event。
- 将 provider tool calls 包装成 `AIMessage`。

### Tools Node

`agent/nodes/tools_node.py` 只负责批处理入口：

1. 读取最后一条 AIMessage 的 `tool_calls_data`。
2. 使用 `ToolScheduler` 调度工具调用。
3. 使用 `ToolExecutor` 执行单个工具。
4. 记录 todo reminder 计数。
5. 追加 workflow guard 生成的 HumanMessage。

### Task Guard Node

`agent/nodes/task_guard_node.py` 负责强制 Task State 规则：

- 没有创建 Task State 时，不允许结束。
- 仍有 pending/in_progress todo 时，不允许结束。
- 只有所有 todo completed 后，才允许 END。

## Runtime 服务

### ToolRegistry

`agent/runtime/tool_registry.py` 负责运行时工具绑定：

- `todo` 绑定当前 TodoManager。
- `list_skills` / `load_skill` 绑定当前 SkillRegistry。
- `subagent` 创建当前上下文下的 SubagentRunner。
- 其它工具来自 `TOOL_HANDLERS`。

它也负责读取工具 `execution` metadata：

- side effects
- concurrency
- timeout

### ToolScheduler

`agent/runtime/tool_scheduler.py` 负责工具并发调度：

- read-only safe 工具可并发。
- workspace write 串行。
- session_state 串行。
- worker subagent 串行。
- explorer/architect/tester/security subagent 可并发。

调度器保证输出顺序与 tool call 顺序一致。

### ToolExecutor

`agent/runtime/tool_executor.py` 是单个工具调用的执行流水线：

```text
emit tool_start
  -> workflow preflight guard
  -> edit/write guard
  -> approval service
  -> run tool with timeout/retry
  -> build ToolMessage
  -> update workflow state
  -> emit diff result if needed
emit tool_end
```

### WorkflowGuard

`agent/runtime/workflow_guard.py` 负责代码 agent 工作流约束：

- 写入前必须先经过 `workspace_state` 和 `git_diff` preflight。
- `write_file` 不能修改已有文件。
- `edit_file` 被阻断并要求使用 `apply_patch`。
- 成功写入后设置 `needs_verify`。
- `verify` 后清理 `needs_verify`。
- 批次结束后追加 verify reminder。

### ApprovalService

`agent/runtime/approval_service.py` 负责运行时审批：

- 根据工具参数生成 `ApprovalRequest`。
- 为文件写入生成执行前 `diff_preview`。
- 调用控制台审批或 silent auto approval。
- 缓存同一轮任务内相同 action/path 的审批。
- 审批通过后注入 `approved=True`。
- 拒绝时抛出 `ApprovalDenied`。

### Tool Events

`agent/runtime/tool_events.py` 负责展示相关格式化：

- tool start 描述。
- tool output 中提取 diff。
- 判断写入工具是否成功。
- diff preview 截断。

## Subagent

`agent/subagent.py` 仍然提供隔离子会话：

- explorer
- architect
- worker
- tester
- security

子 agent 拥有独立消息历史，禁用 `subagent` 和 `todo`，避免递归委派和污染父 Task State。

后续可以进一步把 subagent 的工具执行迁移到 `ToolExecutor` / `ApprovalService`，实现完全复用。

## Task State

`TodoManager` 现在是 Task State 管理器，不只是 todo list。

它维护：

- todo items
- user goal
- constraints
- files inspected
- files modified
- decisions
- test results
- open risks
- next steps

主图通过 `task_guard` 强制要求：

- 每个用户任务必须创建 Task State。
- 最终回答前所有 todo 必须 completed。

## Skills

skills 是动态加载设计：

- 启动时只注入 skill name + description。
- 需要完整说明时调用 `load_skill`。
- `list_skills` / `load_skill` 由 RuntimeToolRegistry 绑定当前 SkillRegistry。

## 审批与 Diff Preview

文件修改工具现在会在执行前生成 `diff_preview`：

- `apply_patch` exact replacement：基于当前文件生成预览 diff。
- `apply_patch` unified diff：直接展示待应用 patch。
- `write_file` 新文件：展示 `/dev/null -> 新文件` diff。

控制台审批先展示 diff，再询问用户是否执行。

## 测试覆盖

关键测试包括：

- `tests/test_tool_concurrency.py`
- `tests/test_task_guard.py`
- `tests/test_task_state.py`
- `tests/test_safety.py`
- `tests/test_apply_patch_tool.py`
- `tests/test_subagent.py`
- `tests/test_skills.py`

这些测试覆盖：

- 工具并发/串行调度。
- Task State 强制完成。
- 运行时审批。
- 写入前 diff preview。
- workflow guard。
- subagent 基本行为。
- skills 动态加载。
