# yoyoagent Agent SDK 评估与详细设计

## 背景

用户希望 yoyoagent 未来可以像 opencode SDK 一样，向外部程序提供对 Agent 的全面控制能力：创建会话、发送 prompt、监听流式事件、控制工具执行、处理审批、管理会话、取消任务、接入外部 UI 或服务，并在 Python/TypeScript 等语言中以 SDK 形式使用。

本文基于当前 yoyoagent 的系统实现情况，整理目标能力、差距、前置补全、分阶段计划和详细设计。

> 注意：前序调研时网络/搜索工具对 opencode SDK 官方页面的抓取不稳定，本文先依据已知 SDK 形态和当前项目静态分析形成设计。正式实现前应再次人工核对 <https://opencode.ai/docs/zh-cn/sdk/> 的具体 API、事件字段和生命周期语义。

## 目标

构建 yoyoagent Agent SDK，使外部程序可以完整控制 yoyoagent 的核心 Agent runtime。

目标能力包括：

1. 会话控制：创建、加载、列出、删除、恢复 session。
2. 对话控制：发送 prompt，接收 assistant 增量输出和完成状态。
3. 流事件订阅：统一接收文本、工具调用、审批、todo、文件变更、错误、完成等事件。
4. 工具控制：查看工具 metadata，控制工具可用范围，拦截工具调用，处理工具结果。
5. 审批控制：由 SDK 调用方处理 request_permission / approve / deny / cancel。
6. 取消与并发：取消运行中的 prompt，限制同 session 并发，支持多 session 并行。
7. 上下文与记忆：读取 message context、token 使用、Task Summary Memory、todo/task state。
8. Skills / subagent：列出和加载 skills，触发 subagent，追踪子任务事件。
9. 文件与 workspace：传入 workdir，观察文件变更，暴露 workspace 边界和 diff。
10. 多协议接入：提供 Python 进程内 SDK、JSON-RPC/stdio 或 HTTP/WebSocket API，并预留 TypeScript SDK。

## 当前实现基础

当前项目已经具备较多 SDK 化所需的底层能力。

### 已有核心能力

| 能力 | 当前实现 | SDK 化价值 |
| --- | --- | --- |
| Session | `agent/session.py` | 已有 run/prompt、messages、持久化、上下文管理基础 |
| Runtime context | `agent/runtime/context.py` | 可作为 SDK run 配置和生命周期容器 |
| Tool registry | `agent/runtime/tool_registry.py` | 支持工具 metadata、handler、workspace 注入、subagent runner 创建 |
| Tool executor/scheduler | `agent/runtime/tool_executor.py` 等 | 已有工具执行、审批、输出压缩、并发策略基础 |
| ApprovalService | runtime approval 相关模块 | 可对接 SDK 外部审批回调 |
| StreamEvent | `agent/streaming.py` | 可作为 SDK 统一事件模型基础 |
| ACP server | `agent/acp/server.py` 等 | 已有外部协议接入雏形，适合复用为 protocol layer |
| Subagent runtime 统一 | `agent/subagent.py` + tests | 子 agent 已复用主 runtime 工具/审批/上下文能力 |
| Task memory | `agent/task_memory.py` | 长任务摘要记忆可作为 SDK 可观测状态输出 |
| TUI state/renderers | `agent/tui/*` | 可借鉴事件到 UI 的映射，但不应与 SDK 耦合 |
| Tools package | `tools/*` | 已有自动发现、metadata 和只读/写入工具体系 |
| Skills | `agent/skills.py`, `skills/*` | SDK 可暴露 skill list/load 能力 |
| Evals | `evals/*` | 可用于后续 SDK contract/e2e 回归测试 |

### 已有外部控制雏形：ACP

ACP 相关实现已经提供：

- `initialize`
- `session/new`
- `session/load`
- `session/prompt`
- `session/cancel`
- update stream 映射
- permission request/response
- todo -> plan update
- tool call update
- available commands update

这说明 yoyoagent 已经不是纯 CLI/TUI 程序，而是具备了“被外部 client 驱动”的基础。

## 与目标 SDK 的主要差距

### 1. Core API 尚未稳定抽象

当前 Session、ACP、TUI 都能驱动 Agent，但缺少一个稳定的内部控制层。例如：

```text
AgentController
  create_session()
  load_session()
  run_prompt()
  cancel()
  list_tools()
  approve_permission()
  subscribe_events()
```

现在 ACP server 和 TUI 更像是直接调用现有模块，而不是通过一个面向外部控制的统一 facade。

### 2. 事件模型需要 SDK 级稳定化

`StreamEvent` 已经存在，但 SDK 需要更严格的 schema：

- event id
- session id
- run id
- sequence number
- event type enum
- timestamp
- payload schema
- parent/subagent/tool correlation id
- final/error/cancel 状态

否则外部 UI 很难可靠 replay、去重、恢复和调试。

### 3. Session/run 生命周期需要明确分层

建议区分：

```text
Session: 长期对话容器
Run: 一次 prompt 执行
Turn: 一轮用户输入与 assistant 响应
ToolCall: run 内的一次工具调用
Approval: tool call 或危险操作的审批请求
```

当前代码中 session 已明确，但 run/turn/tool/approval 的外部可见生命周期还需要统一 ID 和状态。

### 4. 并发与取消需要 SDK contract

ACP/yoyohub 对接分析中已经指出：

- 同 session prompt 需要 busy guard 或队列策略。
- cancel 要明确影响哪个 run。
- pending approval cancel/timeout 要清理干净。
- 多 session 并发应与同 session 串行策略区分。

SDK 需要把这些行为写成 contract。

### 5. 外部审批能力需要标准化

当前审批服务已有基础，但 SDK 应提供：

- 同步 callback 模式
- 异步 await approval 模式
- 外部 `approve(id)` / `deny(id)` / `cancel(id)` 模式
- timeout 策略
- 默认策略，例如 ask/deny/auto-approve read-only

### 6. 工具能力需要可配置化

SDK 使用方需要能控制：

- 启用/禁用工具
- 按 side_effects、workspace_bound、approval_required 过滤工具
- 注入自定义工具
- 包装/拦截工具调用
- 限制 command/network/file 访问

当前 ToolRegistry 已有基础，但 SDK-facing API 仍需设计。

### 7. 协议层和进程内 SDK 需要解耦

建议不要让 Python SDK 直接绑定 ACP schema，也不要让 ACP server 直接成为唯一 SDK 实现。

推荐分层：

```text
SDK Layer
  Python SDK
  TypeScript SDK
  CLI/client helpers

Protocol Layer
  JSON-RPC stdio
  HTTP + WebSocket/SSE
  ACP adapter

Core Control Layer
  AgentController
  SessionStore
  RunManager
  EventBus
  Tool/Approval adapters
```

## 推荐架构

### 总体结构

```text
external app / IDE / yoyohub / tests
        |
        | Python SDK / TS SDK / JSON-RPC / ACP
        v
Protocol & SDK Adapters
        |
        v
AgentController  <---- EventBus
        |
        +-- SessionManager / SessionStore
        +-- RunManager / CancellationRegistry
        +-- RuntimeToolRegistry
        +-- ToolExecutor / ApprovalService
        +-- SkillRegistry
        +-- TaskMemory / MessageContextManager
        +-- WorkspaceContext
```

### 新增建议模块

```text
agent/sdk/
  __init__.py
  client.py              # Python in-process SDK facade
  controller.py          # AgentController
  config.py              # SDK/Agent config dataclasses
  events.py              # stable SDK event schema
  models.py              # SessionInfo, RunInfo, ToolInfo, ApprovalInfo
  run_manager.py         # run lifecycle, cancellation, same-session guard
  event_bus.py           # subscribe/replay/sequence
  errors.py              # SDK-specific exceptions
  adapters/
    acp.py               # ACP <-> SDK event/model mapping
    http.py              # future HTTP/SSE/WebSocket adapter
```

可选后续：

```text
packages/typescript-sdk/
  src/client.ts
  src/types.ts
```

## Core Control Layer 详细设计

### AgentController

核心 facade，供进程内 SDK 和协议层共同使用。

建议接口：

```python
class AgentController:
    async def initialize(self, config: AgentConfig | None = None) -> AgentInfo: ...

    async def create_session(self, options: CreateSessionOptions | None = None) -> SessionInfo: ...
    async def load_session(self, session_id: str) -> SessionInfo: ...
    async def list_sessions(self) -> list[SessionInfo]: ...
    async def delete_session(self, session_id: str) -> None: ...

    async def run_prompt(
        self,
        session_id: str,
        prompt: str,
        *,
        options: RunOptions | None = None,
    ) -> RunHandle: ...

    async def cancel_run(self, session_id: str, run_id: str) -> None: ...
    async def get_run(self, session_id: str, run_id: str) -> RunInfo: ...

    async def list_tools(self, session_id: str | None = None) -> list[ToolInfo]: ...
    async def list_skills(self) -> list[SkillInfo]: ...
    async def load_skill(self, name: str) -> SkillContent: ...

    async def respond_approval(self, approval_id: str, decision: ApprovalDecision) -> None: ...

    def subscribe(self, session_id: str | None = None) -> AsyncIterator[SdkEvent]: ...
```

### RunHandle

一次 prompt 执行的句柄。

```python
class RunHandle:
    session_id: str
    run_id: str

    async def wait(self) -> RunResult: ...
    async def cancel(self) -> None: ...
    def events(self) -> AsyncIterator[SdkEvent]: ...
```

### RunManager

负责：

- 分配 run id。
- 记录 run 状态：queued/running/waiting_approval/completed/failed/cancelled。
- 同 session 并发控制。
- cancel token 管理。
- pending approval cleanup。
- run result 聚合。

同 session 策略建议：

| 策略 | 行为 | MVP 建议 |
| --- | --- | --- |
| reject | 同 session 正在运行时拒绝新 prompt | MVP 推荐，简单可靠 |
| queue | 同 session prompt 排队 | 后续可选 |
| parallel | 同 session 并行 | 不建议，messages 顺序复杂 |

### EventBus

负责统一事件发布和订阅。

要求：

- 每个 session 维护递增 sequence。
- 每个 run 维护 run-local sequence。
- 支持 subscribe all / subscribe session / subscribe run。
- 支持有限 replay，例如最近 N 条。
- 支持 backpressure 策略，避免慢 client 阻塞 agent。

事件 envelope：

```python
@dataclass
class SdkEvent:
    id: str
    sequence: int
    session_id: str | None
    run_id: str | None
    type: str
    timestamp: str
    payload: dict[str, Any]
```

推荐事件类型：

```text
session.created
session.loaded
session.updated
run.started
run.output.delta
run.output.completed
run.completed
run.failed
run.cancelled
tool.call.started
tool.call.delta
tool.call.completed
tool.call.failed
approval.requested
approval.resolved
todo.updated
memory.updated
context.updated
file.changed
error
```

### Tool control

SDK 需要暴露工具 metadata，同时允许调用方配置工具策略。

```python
@dataclass
class ToolPolicy:
    enabled_tools: list[str] | None = None
    disabled_tools: list[str] = field(default_factory=list)
    allow_write_tools: bool = False
    allow_network_tools: bool = False
    require_approval: bool = True
    max_tool_output_chars: int | None = None
```

工具注入建议后置，但接口预留：

```python
controller.register_tool(name, schema, handler, metadata)
controller.unregister_tool(name)
```

### Approval control

审批可同时支持 callback 和外部响应。

```python
@dataclass
class ApprovalRequest:
    id: str
    session_id: str
    run_id: str
    tool_name: str
    arguments: dict[str, Any]
    reason: str | None
    risk: str | None
    timeout_seconds: float | None
```

```python
class ApprovalDecision(Enum):
    APPROVE = "approve"
    DENY = "deny"
    CANCEL = "cancel"
```

外部 client 模式：

1. Agent 发送 `approval.requested`。
2. SDK 调用方展示 UI。
3. 调用 `respond_approval(approval_id, decision)`。
4. Agent 继续/拒绝/取消。

## Python SDK MVP 设计

### 安装与使用形态

进程内使用：

```python
from yoyoagent.sdk import AgentClient

client = AgentClient(workdir="/path/to/repo")
session = await client.create_session()

async for event in client.run(session.id, "请分析这个项目"):
    print(event.type, event.payload)
```

或：

```python
handle = await client.run_prompt(session.id, "修复测试失败")
async for event in handle.events():
    ...
result = await handle.wait()
```

### Client 配置

```python
@dataclass
class AgentClientConfig:
    workdir: str | None = None
    model: str | None = None
    provider: str | None = None
    system_prompt: str | None = None
    skill_dirs: list[str] = field(default_factory=list)
    tool_policy: ToolPolicy = field(default_factory=ToolPolicy)
    approval_mode: Literal["callback", "manual", "deny", "auto_readonly"] = "manual"
    max_event_buffer: int = 1000
```

### MVP 范围

MVP 只做 Python in-process SDK，不先做 HTTP/TS。

包含：

- create/load/list session
- run prompt
- stream events
- cancel run
- list tools/skills
- manual approval response
- same-session busy guard
- run result/error/cancel 状态

不包含：

- 自定义工具注入
- HTTP server
- TypeScript SDK
- 分布式 session store
- 长期事件持久化
- 多进程 worker

## Protocol Layer 设计

### 与 ACP 的关系

ACP 已有实现，不建议推倒重来。建议改造为：

```text
ACP server request
  -> ACP adapter
  -> AgentController
  -> SdkEvent
  -> ACP update adapter
  -> ACP client
```

这样 ACP、未来 HTTP、Python SDK 都共用 AgentController。

### JSON-RPC/stdio

可在 ACP 之外提供 yoyoagent 自有 JSON-RPC：

```text
initialize
session.create
session.load
session.list
run.prompt
run.cancel
tools.list
skills.list
approval.respond
events.subscribe
```

但短期如果 ACP 已满足 yoyohub 接入，优先把 ACP 适配到 AgentController，而不是新增重复协议。

### HTTP/WebSocket/SSE

后续可选：

- REST: session/tool/skill/approval 管理
- WebSocket or SSE: event stream
- POST `/sessions/{id}/runs`
- POST `/runs/{id}/cancel`
- POST `/approvals/{id}/respond`

## TypeScript SDK 设计

TypeScript SDK 建议建立在 HTTP/WebSocket 或 JSON-RPC 上，不直接嵌入 Python。

示例：

```ts
const client = new YoyoAgentClient({ baseUrl: "http://localhost:8787" })
const session = await client.sessions.create({ workdir: "/repo" })

for await (const event of client.runs.stream(session.id, { prompt: "分析项目" })) {
  console.log(event.type, event.payload)
}
```

TypeScript SDK 应由协议 schema 生成类型，避免 Python/TS 类型漂移。

## 前置补全清单

### P0：必须先补

1. **AgentController facade**
   - 把 Session/run/tool/approval/skill 的外部控制入口统一起来。
   - ACP 和 Python SDK 共用。

2. **Run lifecycle 与 run id**
   - 明确 run 状态和结果。
   - 所有事件携带 run_id。

3. **Event schema 稳定化**
   - SDK 事件 envelope。
   - sequence/timestamp/correlation id。
   - StreamEvent 到 SdkEvent 的映射。

4. **同 session prompt guard**
   - MVP 采用 reject 策略。
   - 多 session 允许并发。

5. **CancellationRegistry**
   - cancel 指向 session_id + run_id。
   - 取消时清理 pending approval 和 event stream。

6. **Approval bridge**
   - 支持 manual approval response。
   - 支持 timeout/cancel cleanup。

7. **Contract tests**
   - create session。
   - run prompt stream。
   - tool call event。
   - approval flow。
   - cancel flow。
   - same-session busy。

### P1：SDK MVP

1. Python `AgentClient`。
2. `RunHandle`。
3. session list/load/delete。
4. tools/skills list/load。
5. event subscription/replay。
6. error model。
7. docs + examples。

### P2：协议统一与 ACP 重构

1. ACP server 改为通过 AgentController。
2. yoyoagent JSON-RPC 或 HTTP/WebSocket server。
3. yoyohub compatibility fixtures。
4. schema versioning。
5. cwd-relative path polish。

### P3：高级控制

1. 自定义工具注入。
2. 外部 tool executor。
3. policy sandbox。
4. multi-agent orchestration API。
5. TypeScript SDK。
6. event persistence/replay。
7. remote worker / multi-process。

## 分阶段实施计划

### Phase 0：官方 SDK 二次核对与 API 对齐

目标：确认 opencode SDK 的真实 API 和事件语义。

任务：

- 人工阅读官方文档。
- 记录 opencode 的 session/run/event/tool/permission 模型。
- 与本文 API 做一次对齐。
- 形成 `docs/opencode_sdk_comparison.md` 或补充到本文。

产出：

- SDK 能力对照表。
- yoyoagent SDK API 最终草案。

### Phase 1：Core Control Layer MVP

目标：先不暴露外部协议，只在内部建立稳定控制层。

任务：

- 新增 `agent/sdk/controller.py`。
- 新增 `agent/sdk/events.py`。
- 新增 `agent/sdk/run_manager.py`。
- 实现 create/load session、run prompt、cancel、subscribe events。
- 接入现有 Session。
- 补同 session busy guard。

验证：

- unit tests for AgentController。
- fake provider stream tests。
- cancel tests。
- approval tests。

### Phase 2：Python SDK MVP

目标：让 Python 代码可以直接控制 yoyoagent。

任务：

- 新增 `AgentClient`。
- 封装 `RunHandle`。
- 提供 examples。
- 提供 docs。
- 加入工具/skills/session APIs。

验证：

- `tests/test_sdk_client.py`
- examples smoke test。

### Phase 3：ACP 适配到 AgentController

目标：减少 ACP 与主实现分叉。

任务：

- ACP server 内部调用 AgentController。
- ACP update adapter 从 SdkEvent 映射。
- 保持现有 ACP tests 通过。
- 增加 yoyohub compatibility fixtures。

验证：

- `tests/test_acp.py`
- yoyohub contract fixtures。
- multi-session prompt/cancel/approval tests。

### Phase 4：HTTP/WebSocket API

目标：支持非 Python 进程控制。

任务：

- 选择轻量 server 方案。
- REST 管理 session/tool/approval。
- WebSocket/SSE 输出事件。
- auth/token 暂可本地开发模式，后续强化。

验证：

- HTTP integration tests。
- event stream tests。

### Phase 5：TypeScript SDK

目标：服务 web UI、IDE、yoyohub 等前端/Node 环境。

任务：

- 从 schema 生成 TS 类型。
- 实现 client。
- examples。
- 发布策略。

## 测试策略

### 单元测试

- AgentController create/load/list session。
- RunManager 状态转换。
- EventBus subscribe/replay。
- Approval bridge。
- Tool policy filter。

### 集成测试

- run prompt with fake provider。
- tool call stream。
- approval approve/deny/cancel。
- cancellation during model stream。
- cancellation during pending approval。
- same-session busy rejection。
- multi-session parallel prompt。

### Contract tests

- ACP contract。
- Python SDK examples。
- future HTTP/TS schema。
- yoyohub compatibility fixtures。

### Evals

将 SDK 控制能力加入 evals：

```text
evals/tasks/sdk_control_baseline/
  prompt.md
  eval.py
  checks.sh
```

覆盖：

- 外部创建 session。
- 外部触发 prompt。
- 外部接收 tool event。
- 外部处理 approval。
- 外部 cancel。

## 文档计划

建议新增或更新：

```text
docs/yoyoagent_agent_sdk_design.md       # 本文
docs/sdk_usage.md                        # SDK 使用指南
docs/sdk_event_schema.md                 # 事件 schema
docs/sdk_protocol.md                     # JSON-RPC/HTTP 协议
docs/opencode_sdk_comparison.md          # 与 opencode SDK 对照
docs/acp_research_and_implementation_plan.md # 补充 ACP 与 AgentController 关系
```

## 风险与注意事项

1. **不要让 SDK 与 TUI 耦合**
   - SDK 应基于 core events。
   - TUI 只是 SDK/core events 的一个 consumer。

2. **不要让 ACP 成为唯一内部抽象**
   - ACP 是外部协议之一。
   - Core Control Layer 应比 ACP 更通用。

3. **事件 schema 必须稳定**
   - 一旦外部 client 使用，事件字段变化成本很高。

4. **取消和审批是最容易出错的部分**
   - 需要明确 run_id。
   - 需要清理 pending approval。
   - 需要保证 final event 一定发出。

5. **多 session 与同 session 并发要分开设计**
   - 同 session 建议串行。
   - 多 session 可并发。

6. **工具策略涉及安全边界**
   - SDK 默认不应自动放开写文件/执行命令。
   - 外部调用方必须显式配置高风险能力。

7. **官方 opencode SDK 需二次核对**
   - 目前设计是面向 yoyoagent 的合理 SDK 架构，不保证字段与 opencode 完全一致。

## 推荐近期执行顺序

1. 二次核对 opencode SDK 官方 API。
2. 新增 `AgentController`、`SdkEvent`、`RunManager` 设计骨架。
3. 实现 Python in-process SDK MVP。
4. 增加同 session prompt guard、run_id、cancel/approval contract tests。
5. 将 ACP server 逐步适配到 AgentController。
6. 沉淀 yoyohub ACP compatibility fixtures。
7. 再考虑 HTTP/WebSocket 和 TypeScript SDK。

## 结论

yoyoagent 已经具备实现“全面控制 Agent SDK”的大部分底层能力：Session、ToolRegistry、ToolExecutor、ApprovalService、StreamEvent、ACP、subagent runtime、skills、task memory 都已经存在。真正缺少的是一层稳定的 **Core Control Layer**，把这些能力统一成可被 SDK 和协议层消费的 API。

因此推荐不要直接从外部 SDK 或 HTTP API 开始，而是先实现：

```text
AgentController + RunManager + SdkEvent + EventBus
```

然后在其上叠加：

```text
Python SDK -> ACP adapter 重构 -> HTTP/WebSocket -> TypeScript SDK
```

这样可以避免 TUI、ACP、未来 SDK 各自重复驱动 Agent，最终形成一个统一、可测试、可扩展的 agent control runtime。
