# Task Graph DAG 调度设计

## Summary

为 yoyoagent 增加一个任务依赖图执行能力：主 agent 可以把复杂用户目标拆成一组有依赖关系的任务节点，由 `task_graph` 按 DAG 顺序执行。DAG 不替代 `todo`，而是作为 `todo` 的执行增强层；`todo` 负责任务状态，`task_graph` 负责依赖调度，`subagent` 负责具体执行。

MVP 采用同步执行：主 agent 调用一次 `task_graph`，等待整个 DAG 完成或失败后继续。

## Goals

- 让复杂代码任务可以按“调研 -> 设计 -> 实现 -> 测试 -> 安全审查”的依赖顺序自动推进。
- 支持无依赖节点并发执行，减少等待时间。
- 保持 `worker` 写文件任务串行，避免多个写入任务互相覆盖。
- 复用现有 `subagent` 角色、审批、工具执行、stream event 和 task guard 机制。
- 给主 agent 返回结构化执行报告，方便它更新 `todo` 并最终回复用户。

## Non-Goals

MVP 不做以下能力：

- 后台任务列表。
- 用户切入某个 DAG 节点会话。
- 跨进程持久化和恢复。
- 复杂动态重规划。
- 多个 worker 并行写同一 workspace。
- 完整工作树级隔离。

## 当前系统关系

当前项目已有四层能力：

- `todo`：记录用户目标、任务清单和任务记忆，并由 `task_guard` 强制任务完成后才能退出。
- `subagent`：支持 `explorer`、`architect`、`worker`、`tester`、`security` 角色。
- `tool_scheduler`：在单轮模型输出多个 tool call 时，根据工具 metadata 做并发/串行调度。
- `workflow_guard` / `approval_service`：在写入前做 workspace preflight、审批和 diff preview。

DAG 调度位于这些能力之上：

```text
User Goal
  -> todo 建立任务状态
  -> task_graph 建立任务依赖图
  -> DAG scheduler 找到 ready 节点
  -> subagent 执行节点
  -> 汇总结果并返回主 agent
  -> 主 agent 更新 todo
  -> task_guard 判断能否结束
```

## 建议工具：`task_graph`

新增 `tools/task_graph.py`，声明 Anthropic-style tool schema。实际 handler 在 runtime 中绑定当前 provider、workdir、system prompt、stream callback 和 approval callback。

### 输入结构

```json
{
  "tasks": [
    {
      "id": "research",
      "title": "调研现有实现",
      "role": "explorer",
      "task": "阅读当前输入和相关代码，找出实现入口和风险点。",
      "depends_on": []
    },
    {
      "id": "design",
      "title": "设计修改方案",
      "role": "architect",
      "task": "基于调研结果设计最小可落地方案。",
      "depends_on": ["research"]
    },
    {
      "id": "implement",
      "title": "实现代码修改",
      "role": "worker",
      "task": "按设计实现代码修改，避免无关改动。",
      "depends_on": ["design"]
    },
    {
      "id": "test",
      "title": "验证功能",
      "role": "tester",
      "task": "运行相关测试，必要时补充测试。",
      "depends_on": ["implement"]
    },
    {
      "id": "security",
      "title": "安全审查",
      "role": "security",
      "task": "审查实现是否引入安全风险。",
      "depends_on": ["implement"]
    }
  ],
  "context": "来自主 agent 的额外上下文，可选。",
  "max_concurrency": 3,
  "fail_fast": true
}
```

### 输出结构

```text
Task graph result
status: completed
completed: 5
failed: 0
skipped: 0

Nodes:
- research: completed
  summary: ...
- design: completed
  summary: ...
- implement: completed
  summary: ...
- test: completed
  summary: ...
- security: completed
  summary: ...

Aggregate:
- files_changed: ...
- verification: ...
- risks: ...
```

失败时：

```text
Task graph result
status: failed
failed_node: implement
reason: ...
completed_before_failure: research, design
skipped: test, security
```

## 节点模型

建议新增 `agent/task_graph.py`：

```python
@dataclass
class TaskNode:
    id: str
    title: str
    role: str
    task: str
    depends_on: list[str] = field(default_factory=list)
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    result: str = ""
    error: str = ""
```

```python
@dataclass
class TaskGraphResult:
    status: Literal["completed", "failed"]
    nodes: list[TaskNode]
    summary: str
```

## 调度规则

### Ready 节点

一个节点可以执行，当且仅当：

- 节点状态为 `pending`。
- 所有 `depends_on` 节点都已 `completed`。

### 并发规则

- `explorer`、`architect`、`tester`、`security` 可以并发。
- `worker` 默认串行。
- 如果 ready 节点中包含 `worker`，先执行一个 `worker`，其它写入相关节点等待。
- `max_concurrency` 限制每批最多并发节点数。

### 失败规则

MVP 默认 `fail_fast=true`：

- 任一节点失败后，DAG 停止推进。
- 依赖失败节点的后续节点标记为 `skipped`。
- 返回失败节点的错误和已完成节点摘要。

后续可支持 `fail_fast=false`：

- 独立分支继续执行。
- 依赖失败节点的分支跳过。

### 循环检测

执行前必须校验：

- `id` 唯一。
- `depends_on` 引用存在。
- 图中不存在环。
- 节点数量不超过安全上限，例如 20。

## 与 Subagent 的关系

每个 DAG 节点由一个 subagent 执行。`TaskGraphRunner` 复用当前 runtime 创建的 `SubagentRunner`：

```text
TaskNode(role="explorer") -> subagent(role="explorer", task=...)
TaskNode(role="worker")   -> subagent(role="worker", task=...)
```

节点 task 中应自动注入：

- 当前节点标题和任务说明。
- 已完成依赖节点的摘要。
- 主 agent 传入的全局 context。
- 输出格式要求。

示例：

```text
Task:
实现代码修改

Context:
用户目标: ...
依赖结果:
- research: ...
- design: ...

Return:
- status
- summary
- files_changed
- verification
- risks
```

## 与 Todo 的关系

`task_graph` 不直接替代 `todo`。

推荐主 agent 行为：

1. 先调用 `todo` 建立高层任务状态。
2. 对复杂任务调用 `task_graph` 执行依赖图。
3. 根据 `task_graph` 汇总结果更新 `todo` memory。
4. 所有工作完成后调用 `todo` 标记 completed。

这样可以保持当前 `task_guard` 逻辑不变。

## Runtime 集成

### 新增文件

```text
agent/task_graph.py
tools/task_graph.py
tests/test_task_graph.py
```

### RuntimeToolRegistry

新增绑定：

```python
if tool_name == "task_graph":
    return self.create_task_graph_runner().run
```

并新增：

```python
def create_task_graph_runner(self) -> TaskGraphRunner:
    return TaskGraphRunner(
        subagent_runner_factory=self.create_subagent_runner,
        stream_callback=self.runtime.stream_callback,
        parent_session_id=self.runtime.session_id,
    )
```

### Tool metadata

```python
"execution": {
    "side_effects": "delegation",
    "concurrency": "serial",
    "timeout_seconds": 1800
}
```

`task_graph` 自身建议串行，因为它内部已经管理并发。

## Stream Events

为了让用户看到 DAG 进度，建议新增事件：

```text
task_graph_start
task_graph_node_start
task_graph_node_end
task_graph_node_failed
task_graph_end
```

控制台展示示例：

```text
@task_graph start 5 nodes
@explorer research ...
@architect design ...
@worker implement ...
@tester test ...
@security security ...
@task_graph completed
```

## Prompt 更新建议

主 agent system prompt 增加：

```text
For complex tasks with clear dependencies, use the task_graph tool after creating Task State.
Use task_graph to coordinate investigation, design, implementation, testing, and security review.
Do not use task_graph for simple one-step tasks.
Keep worker nodes serial unless the tasks touch clearly disjoint files.
After task_graph finishes, update todo memory with important decisions, changed files, tests, and risks.
```

## 测试计划

- 工具注册：`task_graph` 出现在 `TOOLS`，schema 包含 `tasks/context/max_concurrency/fail_fast`。
- DAG 校验：重复 id、未知依赖、循环依赖会失败。
- Ready 调度：无依赖节点先执行，依赖完成后再执行后续节点。
- 并发规则：只读角色可并发，`worker` 串行。
- 失败规则：`fail_fast=true` 时失败后跳过依赖节点。
- fake subagent 集成：模拟节点执行结果，确认汇总格式正确。
- stream events：开始、节点开始、节点结束、结束事件按顺序发出。
- 回归：现有 `subagent`、`todo`、工具并发调度不受影响。

## 推荐落地顺序

1. 新增 `agent/task_graph.py`，只实现纯 Python DAG 校验和调度，使用 fake executor 测试。
2. 新增 `tools/task_graph.py`，完成工具注册测试。
3. 在 `RuntimeToolRegistry` 绑定 `TaskGraphRunner`。
4. 接入 `SubagentRunner`，先同步执行。
5. 增加 stream events。
6. 更新主 agent prompt。
7. 设计更高级的 DAG 能力，例如持久化、暂停恢复、动态重规划。

