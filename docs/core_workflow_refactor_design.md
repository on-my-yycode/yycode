# Core Workflow Refactor Design

## 实现状态

状态：主 agent 核心流程已按本设计完成第一轮重构。

已完成：

- `graph.py` 已变为 LangGraph 薄编排层；由于保留兼容入口，目前约 130 行，后续移除兼容包装后可继续压缩。
- 新增 `agent/nodes/`，拆出 LLM node、tools node、task guard node 和 AgentState。
- 新增 `agent/runtime/`，拆出 context、tool registry、tool scheduler、tool executor、workflow guard、approval service、tool events。
- 主 agent 工具执行链已迁移到 runtime 层。
- 保留 `graph.py` 兼容入口：`create_llm_node`、`create_tools_node`、`execute_tool_calls`。
- 文档已同步更新到 `docs/core_workflow.md`、`docs/project_structure.md`、`docs/workflow_diagram.mmd`、`docs/workflow_diagram_art.txt` 和 `docs/code_agent_roadmap.md`。

仍可继续优化：

- subagent 内部工具循环仍保留在 `agent/subagent.py`，后续可以复用 `ApprovalService` / `ToolExecutor`。
- task dependency graph 还未实现，目前仍是批次并发调度。

## 背景

当前核心流程主要集中在 `agent/graph.py` 中。这个文件同时承担了 LangGraph 组装、LLM 节点、工具节点、工具调度、运行时工具绑定、审批、workspace preflight、写文件保护、diff 展示、verify reminder、Task State guard、subagent runner 创建等职责。

这种集中式实现已经可以工作，但继续迭代会带来几个问题：

- `graph.py` 过重，业务规则和流程编排混在一起。
- 主 agent 和 subagent 的工具执行、审批、技能加载逻辑存在重复。
- 后续实现异步任务 DAG、后台 subagent、统一流式输出时，需要反复修改核心图文件。
- 单元测试只能围绕大函数打补丁，模块边界不够清晰。

## 重构目标

核心原则：`graph.py` 只描述流程图，不承载工具执行细节。

目标状态：

- `graph.py` 降到约 30-60 行，只负责组装节点和边。
- LLM 调用、工具执行、审批、workflow guard、Task State guard 分模块实现。
- 主 agent 和 subagent 尽量复用审批、工具注册、工具执行能力。
- 保持当前行为不变，先做结构拆分，再做功能演进。

## 目标目录结构

```text
agent/
  graph.py
  nodes/
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

## 模块职责

### `agent/graph.py`

只负责 LangGraph 编排：

```text
START
  -> llm
  -> tools      when tool_calls exist
  -> task_guard when no tool_calls
  -> END        when Task State is complete
```

不再包含工具执行、审批、diff、preflight 等业务逻辑。

### `agent/nodes/llm_node.py`

负责主 agent LLM 节点：

- LangChain message 到 provider message 的转换。
- 调用 `chat_with_retry(...)`。
- 发送 usage stream event。
- 构造 `AIMessage` 和 `tool_calls_data`。

可复用点：

- 消息格式转换函数可供 subagent 使用，避免重复实现。

### `agent/nodes/tools_node.py`

负责工具节点入口，但不直接执行工具细节：

```python
tool_calls = extract_tool_calls(last_ai_message)
tool_messages = await scheduler.execute(tool_calls, executor.execute)
extra_messages = workflow_guard.after_batch(tool_calls, tool_messages)
return {"messages": tool_messages + extra_messages}
```

### `agent/nodes/task_guard_node.py`

负责 Task State 完成前阻止结束：

- 如果 Task State 未创建，追加 HumanMessage 要求调用 `todo`。
- 如果 todo 仍有 pending/in_progress，追加 HumanMessage 要求继续执行。
- 如果 Task State 已完成，允许 END。

### `agent/runtime/context.py`

集中保存运行时依赖，减少函数参数层层传递：

```python
@dataclass
class AgentRuntimeContext:
    provider: LLMProvider
    workdir: Path
    session_id: str
    system_prompt: str
    todo_manager: TodoManager
    skill_dirs: list[str]
    stream_callback: StreamEventCallback | None
    approval_callback: ApprovalCallback | None
    workflow_state: WorkflowState
```

### `agent/runtime/workflow_guard.py`

负责 workspace 级约束和后置提醒：

- `workspace_state` / `git_diff` preflight。
- 禁止 `write_file` 修改已有文件。
- 禁止直接使用 `edit_file`。
- 写入成功后设置 `needs_verify`。
- `verify` 后清理 `needs_verify`。
- 批次结束后决定是否注入 verify reminder。

建议状态对象：

```python
@dataclass
class WorkflowState:
    workspace_state_checked: bool = False
    git_diff_checked: bool = False
    needs_verify: bool = False
    approved_write_keys: set[tuple[str, str, str]] = field(default_factory=set)
```

### `agent/runtime/approval_service.py`

负责运行时审批：

- 生成 `ApprovalRequest`。
- 附带写文件前的 `diff_preview`。
- 调用 `approval_callback`。
- 管理同一轮任务内的审批缓存。
- 审批通过后注入 `approved=True`。
- 审批拒绝时抛出 `ApprovalDenied`。

目标接口：

```python
class ApprovalService:
    async def approve(self, tool_name: str, args: dict) -> dict:
        ...
```

返回值是可直接传给工具 handler 的 args。

### `agent/runtime/tool_registry.py`

负责运行时工具绑定：

- `todo` 绑定当前 `TodoManager`。
- `list_skills` / `load_skill` 绑定当前 `SkillRegistry`。
- `subagent` 绑定当前 `SubagentRunner`。
- 其它工具来自 `TOOL_HANDLERS`。

目标接口：

```python
class RuntimeToolRegistry:
    def resolve(self, tool_name: str) -> Callable | None:
        ...

    def execution_for(self, tool_name: str) -> ToolExecutionPolicy:
        ...
```

### `agent/runtime/tool_scheduler.py`

负责工具调用的并发/串行调度：

- read-only safe 工具可并发。
- `todo`、workspace write、process、worker subagent 串行。
- explorer/architect/tester/security subagent 可按当前策略并发。
- 保持结果顺序和 tool_call 顺序一致。

当前 `execute_tool_calls(...)` 可以先整体迁移到这里。

### `agent/runtime/tool_executor.py`

负责单个工具调用的完整生命周期：

```text
1. emit tool_start
2. resolve handler
3. run workflow preflight guard
4. enforce edit/write rules
5. approve tool call and inject approved=true
6. execute handler with timeout/retry
7. build ToolMessage
8. accumulate subagent usage if needed
9. update workflow state
10. emit diff/tool_result
11. emit tool_end
```

目标接口：

```python
class ToolExecutor:
    async def execute(self, tool_call) -> ToolMessage:
        ...
```

### `agent/runtime/tool_events.py`

负责工具事件格式化：

- tool start 描述。
- diff result 提取和截断。
- tool output 是否表示成功写入。

这样 `ToolExecutor` 不需要知道展示细节。

## 新执行链路

```text
Session.send()
  -> prepare task state
  -> maybe compress context
  -> graph.ainvoke()

graph:
  START -> llm_node

llm_node:
  provider messages
  -> chat_with_retry
  -> AIMessage

conditional:
  if tool_calls:
    -> tools_node
  else:
    -> task_guard_node

tools_node:
  tool_calls
  -> ToolScheduler
  -> ToolExecutor per tool
  -> ToolMessage list + extra HumanMessage reminders
  -> llm_node

task_guard_node:
  if Task State incomplete:
    -> HumanMessage blocker
    -> llm_node
  else:
    -> END
```

## 迁移计划

### Phase 1: 低风险搬迁

目标：不改行为，只移动代码。

1. 新增 `agent/runtime/tool_scheduler.py`。
2. 把 `execute_tool_calls(...)` 从 `graph.py` 移过去。
3. 保持原测试通过。

### Phase 2: WorkflowGuard

1. 新增 `agent/runtime/workflow_guard.py`。
2. 移出以下逻辑：
   - `has_preflight`
   - `run_guard_preflight`
   - `should_require_apply_patch`
   - `apply_patch_required_message`
   - `needs_verify` 管理
3. 更新工具节点调用 guard。

### Phase 3: ApprovalService

1. 新增 `agent/runtime/approval_service.py`。
2. 迁移审批缓存和 `approved=True` 注入。
3. 主 agent 和 subagent 共用同一套审批逻辑。
4. 保留现有 `ApprovalRequest` 数据结构。

### Phase 4: ToolRegistry

1. 新增 `agent/runtime/tool_registry.py`。
2. 统一绑定：
   - `todo`
   - `list_skills`
   - `load_skill`
   - `subagent`
   - `TOOL_HANDLERS`
3. 后续 subagent 也改用 registry，减少重复。

### Phase 5: ToolExecutor

1. 新增 `agent/runtime/tool_executor.py`。
2. 把 `execute_tool_call(...)` 整体迁入。
3. `tools_node` 只保留批处理入口。

### Phase 6: Nodes 拆分

1. 新增 `agent/nodes/llm_node.py`。
2. 新增 `agent/nodes/tools_node.py`。
3. 新增 `agent/nodes/task_guard_node.py`。
4. `graph.py` 只保留图组装。

## 测试策略

每个阶段都要求全量测试通过。

建议新增或拆分测试：

- `tests/test_tool_scheduler.py`
  - 并发批次保持顺序。
  - 串行工具会 flush 并发批次。

- `tests/test_workflow_guard.py`
  - 写入前必须 workspace_state/git_diff。
  - `write_file` 不允许改已有文件。
  - 成功写入后要求 verify。

- `tests/test_approval_service.py`
  - 自动注入 `approved=True`。
  - 审批缓存复用。
  - 拒绝审批抛出 `ApprovalDenied`。
  - diff preview 不写文件。

- `tests/test_tool_executor.py`
  - tool_start/tool_end 事件。
  - subagent usage 写入 ToolMessage。
  - 写入成功后发送 diff event。

- `tests/test_task_guard.py`
  - 未创建 Task State 不允许结束。
  - 未完成 todo 不允许结束。
  - 全部 completed 后允许结束。

## 风险与控制

### 风险：拆分期间行为漂移

控制：

- 每个阶段只移动一个职责。
- 保持函数签名尽量兼容。
- 每步跑全量测试。

### 风险：审批逻辑和 subagent 行为不一致

控制：

- ApprovalService 先服务主 agent。
- 主 agent 稳定后再迁移 subagent。
- 保留 subagent 专属测试。

### 风险：graph 节点拆分后循环边错误

控制：

- 最后再拆 nodes。
- `tests/test_task_guard.py` 覆盖 END 条件。
- fake provider 集成测试覆盖工具循环。

### 风险：长期任务循环更难调试

控制：

- 保留 stream events。
- ToolExecutor 统一记录 tool_start/tool_end。
- WorkflowGuard 生成明确的 blocker message。

## 完成后的 graph.py 目标形态

```python
def build_graph(runtime: AgentRuntimeContext):
    builder = StateGraph(AgentState)

    builder.add_node("llm", create_llm_node(runtime))
    builder.add_node("tools", create_tools_node(runtime))
    builder.add_node("task_guard", create_task_guard_node(runtime.todo_manager))

    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", route_after_llm)
    builder.add_edge("tools", "llm")
    builder.add_conditional_edges("task_guard", route_after_task_guard(runtime.todo_manager))

    return builder.compile()
```

`graph.py` 不再知道审批、diff、skills、subagent 创建细节。

## 推荐执行顺序

第一轮重构已完成 Phase 1 到 Phase 6 的主 agent 迁移。

建议下一步：

1. 将 subagent 内部工具执行迁移到 `RuntimeToolRegistry` / `ApprovalService` / `ToolExecutor`。
2. 为 `workflow_guard.py`、`approval_service.py`、`tool_executor.py` 增加更细粒度单元测试。
3. 在 `ToolScheduler` 基础上设计 task dependency graph。
4. 逐步移除 `graph.py` 中的兼容包装入口。
