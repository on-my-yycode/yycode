# ACP 调研与 yoyoagent 实现方案

更新时间：2026-05-12

## 结论摘要

ACP（Agent Client Protocol）已经从 Zed + Gemini CLI 的早期集成，发展为主流 coding agent 与编辑器之间的开放协议方向。公开资料显示，Zed 已支持 Gemini CLI、Claude Agent、Codex、GitHub Copilot 等外部 agent；GitHub Copilot CLI 已提供 ACP server public preview；JetBrains 也宣布参与共建 ACP。对 yoyoagent 来说，ACP 的价值不是替代现有 TUI，而是把当前 agent core 暴露给 Zed、JetBrains、Neovim/Emacs 等 ACP client。

可行性判断：高。

原因：

- yoyoagent 已有 `Session`、`StreamEvent`、`ApprovalService`、`SessionStore`、`TodoManager`、工具 metadata 和 TUI timeline，ACP 需要的大部分语义已经存在。
- ACP 首版可以做成一个独立 stdio server，不破坏现有 CLI/TUI。
- 当前最大缺口是协议适配层：JSON-RPC transport、ACP schema 映射、permission request、session/prompt 生命周期、cancel 和 session/load replay。

建议路线：

1. ACP 兼容前置能力已先行实现：model switch、plan snapshot、changed-files snapshot、session replay view model、cancel controller、approval decision。
2. 下一步实现 ACP stdio MVP：`initialize`、`session/new`、`session/load`、`session/prompt`、`session/cancel`、`session/update`、`session/request_permission`。
3. 工具仍由 yoyoagent 本地执行，不依赖 client fs/terminal 能力。
4. 把 `StreamEvent` 转换为 ACP `session/update`，把 `ApprovalRequest` 转换为 ACP permission request。
5. 后续再实现 session list、slash commands、session modes、client fs/terminal、MCP servers 转发和 registry 发布。

## 信息来源

- ACP 官方 GitHub：ACP 标准化 code editor 与 coding agent 通信，并提供 Kotlin/Java/Python/Rust/TypeScript 官方库。
  <https://github.com/agentclientprotocol/agent-client-protocol>
- ACP Protocol Overview：ACP 基于 JSON-RPC 2.0，核心流程是 initialize、session/new 或 session/load、session/prompt、session/update、permission、cancel。
  <https://agentclientprotocol.com/protocol/overview>
- ACP Initialization：初始化阶段协商 protocol version、client/agent capabilities、prompt capabilities、MCP capabilities。
  <https://agentclientprotocol.com/protocol/initialization>
- ACP Session Setup：`session/new` 使用 cwd 创建会话，`session/load` 恢复会话并 replay history。
  <https://agentclientprotocol.com/protocol/session-setup>
- ACP Prompt Turn：prompt turn 通过 `session/update` 流式输出 plan、agent message chunk、tool_call、tool_call_update，并以 stop reason 结束。
  <https://agentclientprotocol.com/protocol/prompt-turn>
- ACP Tool Calls：工具调用包含 title、kind、status、content、locations、rawInput、rawOutput。
  <https://agentclientprotocol.com/protocol/tool-calls>
- ACP Agent Plan：plan 通过完整 entries 列表更新，client 每次替换当前 plan。
  <https://agentclientprotocol.com/protocol/agent-plan>
- ACP Transports：当前定义 stdio 和 streamable HTTP draft，建议优先支持 stdio；stdout 只能写 ACP JSON-RPC 消息。
  <https://agentclientprotocol.com/protocol/transports>
- Zed External Agents：Zed 通过 ACP 支持 Gemini CLI、Claude Agent、Codex、GitHub Copilot 等外部 agent。
  <https://zed.dev/docs/ai/external-agents>
- Zed / JetBrains ACP：JetBrains 宣布参与共建 ACP，目标是让 agent 实现一次协议即可进入多个编辑器。
  <https://zed.dev/blog/jetbrains-on-acp>
- GitHub Copilot CLI ACP server：Copilot CLI 可用 `copilot --acp --stdio` 或 TCP 启动 ACP server，目前为 public preview。
  <https://docs.github.com/en/enterprise-cloud@latest/copilot/reference/copilot-cli-reference/acp-server>
- Codex CLI：Codex CLI 可在本地 terminal 读取、修改、运行代码；公开功能包括 TUI、图片输入、代码 review、subagents、web search、MCP、approval modes。
  <https://developers.openai.com/codex/cli>
- Claude Code 功能概览：Claude Code 提供 CLAUDE.md、Skills、MCP、Subagents、Agent teams、Hooks、Plugins 等扩展能力。
  <https://code.claude.com/docs/en/features-overview>
- Gemini CLI 配置：Gemini CLI 支持 `--acp`、approval modes、MCP servers、allowed tools、sandbox、session list/delete 等。
  <https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/configuration.md>

## ACP 核心协议能力

| ACP 能力 | 协议语义 | yoyoagent 当前基础 | 当前差距 |
| --- | --- | --- | --- |
| JSON-RPC transport | stdio newline-delimited JSON-RPC；stdout 只能输出 ACP 消息 | 当前 CLI/TUI 是直接终端 UI，无 JSON-RPC server | 需要新增 `agent/acp/server.py`，日志走 stderr |
| `initialize` | 协商 protocol version、capabilities、agentInfo、authMethods | 项目已有版本、provider、能力配置 | 需要返回 ACP capabilities |
| `session/new` | 使用 `cwd` 创建 session，返回 sessionId | `Session.from_config(workdir=...)` 已完成 | 需要 ACP method handler |
| `session/load` | 恢复 session 并 replay conversation | `SessionStore`、`-r` 恢复已完成 | 需要把 messages 转为 `session/update` replay |
| `session/resume` | 无 replay 恢复会话 | 当前 CLI resume 会加载 messages | 可后续做；MVP 可不声明 |
| `session/prompt` | 接收 ContentBlock[]，运行一轮 agent，返回 stopReason | `Session.send()`、`send_stream()` 已有 | 需要把 prompt block 转纯文本/资源上下文，并把 StreamEvent 转 ACP update |
| `session/cancel` | 取消当前 turn，返回 `cancelled` stop reason | TUI runner 已有 cancel task；Session 内部无独立 cancellation API | ACP server 需持有 task 并 cancel，捕获 CancelledError |
| `session/update` | agent message、tool call、tool update、plan、commands、mode updates | `StreamEvent`、TUI timeline、todo state 已有 | 需要 event adapter |
| permission request | agent 请求 client 授权工具调用 | `ApprovalRequest`、`ApprovalService`、TUI approval 已有 | 需要 `AcpApprovalAdapter` 发 JSON-RPC request |
| tool calls | tool_call/tool_call_update 展示工具进度和结果 | `tool_start/tool_end/tool_result` 已有 semantic metadata | 需要 tool kind/location/rawInput/rawOutput 映射 |
| plan | 完整 plan entries 替换式更新 | `TodoManager` 有 items/status/memory；TUI Task Plan 已有 | 需要 todo -> ACP plan update |
| client fs/terminal | agent 可调用 client 的 fs/terminal methods | yoyoagent 目前本地工具直接访问 workspace | MVP 不声明 client fs/terminal；后续可选 |
| slash commands | agent 可 advertise commands | yoyoagent 有 skills、`:help/:clear`、`/plan` skill | 需要 `available_commands_update`，优先暴露 `/plan` 和 skills |
| session modes | ask/architect/code 等模式 | 有 auto approval、`/plan` skill、subagent roles | 需要模式状态机；MVP 可不声明 |
| MCP servers | session/new/load 可传 mcpServers | 当前没有 MCP client/runtime | 后续实现，不阻塞 ACP MVP |

## 主流 coding agent 公开能力对比

说明：下表只记录公开资料中明确能确认的能力，避免把社区传闻当事实。

| 能力 | Codex CLI | Claude Code / Claude Agent | Gemini CLI | GitHub Copilot CLI | yoyoagent 当前状态 |
| --- | --- | --- | --- | --- | --- |
| ACP server / 外部 agent 集成 | Zed 文档列出 Codex external agent；Zed 安装 `codex-acp` | Zed 文档列出 Claude Agent | Gemini CLI 是 Zed 初始参考 ACP 实现，配置含 `--acp` | 官方 public preview，`copilot --acp --stdio` / TCP | 未实现 ACP server |
| 本地代码读写执行 | 可读、改、运行代码 | 内置文件、搜索、执行、web 等工具 | 文件/工具/命令体系 | Copilot CLI agentic tasks | 已实现 read/write/apply_patch/bash/verify |
| 审批/权限模式 | approval modes | settings/hooks/permissions 体系 | default/auto_edit/yolo/plan approval modes | ACP permission request | 已实现 runtime approval、TUI approval、auto mode |
| Sandbox | Codex 默认/模式化 sandbox，网络默认受控 | 依 Claude Code 环境/配置 | Docker/custom sandbox，可 `--sandbox` | 未在已查资料中展开 | 未实现 OS/container sandbox；仅 workflow guard + approval |
| MCP | Codex CLI 文档列出 MCP | Claude Code 明确支持 MCP | Gemini CLI 支持 MCP servers | ACP use case 包含 agent coordination；Copilot CLI 细节需进一步查 | 未实现 MCP client |
| Skills / 可复用工作流 | Codex docs 有 skills 相关入口 | Skills 是核心扩展能力 | Gemini CLI 有 skills 管理开关 | 未在已查资料中展开 | 已有 local skills、`/plan` skill、load_skill/list_skills |
| Subagents / isolated context | Codex 文档列出 subagents | Subagents、agent teams | 公开配置中未充分展开，近期可能演进 | 未在已查资料中展开 | 已有 explorer/architect/worker/tester/security，显式 skill 委派 |
| Hooks / lifecycle automation | 未在已查资料中展开 | Hooks 是公开核心能力 | 未在已查资料中展开 | 未在已查资料中展开 | 未实现通用 hooks |
| Session persistence | CLI/IDE 具备会话体验，Zed 注明 Codex ACP 部分 history 功能限制 | Claude Code 读取自身配置/记忆；会话能力依产品 | Gemini CLI 有 list/delete session | ACP server 重点用例之一 | 已有 SessionStore、list/resume/delete/temp |
| Plan mode / planning | Codex 有 plan-like workflows，Zed 兼容工作流 | Claude Code 有 plan/subagent/skills | approval mode 有 `plan`，文档注明仍在开发 | 未在已查资料中展开 | Task State + `/plan` skill；没有 ACP mode |
| IDE 外部 agent | Codex in Zed / IDE extension | Claude Agent in Zed | Gemini CLI in Zed | Copilot ACP server | 未实现 |
| LSP / semantic code nav | 未在已查资料中展开 | 未在已查资料中展开 | 未在已查资料中展开 | IDE 可提供上下文 | Python-only LSP MVP 已实现 |
| 长上下文治理 | Codex/Claude 等产品有成熟压缩体验，但公开细节有限 | 有 context cost 文档 | 有 memory/context 文件层级 | 未在已查资料中展开 | 已实现 Task Summary Memory、summary merge、Message Token Manager |

## yoyoagent 已有能力与 ACP 的匹配度

### 强匹配

- `Session` 对应 ACP session。
- `SessionStore` 对应 `session/load` 和后续 `session/resume`。
- `StreamEvent` 对应 `session/update`。
- `ApprovalRequest` 对应 `session/request_permission`。
- `TodoManager` 对应 ACP plan entries。
- `RuntimeToolRegistry` / `ToolExecutor` / `ToolScheduler` 对应 tool call lifecycle。
- `ToolEvent metadata` 可映射 tool title/kind/locations/rawInput。
- `workdir` 已统一，可直接使用 ACP `cwd`。
- `skills` 和 TUI commands 可映射 slash commands。

### 中等匹配

- subagent 已实现，但 ACP 不要求暴露 subagent 语义；可作为普通 tool_call 显示。
- LSP 是内部工具，不需要 ACP client 支持。
- Message Token Manager 是 yoyoagent 本地增强，可通过 `_meta` 暴露 context stats，但不是 ACP 标准要求。

### 弱匹配或缺口

- 没有 JSON-RPC server。
- 没有 ACP schema 类型和兼容测试。
- 没有 client fs/terminal method 调用能力。
- 没有 MCP server injection。
- 没有 ACP session mode 状态。
- 没有 session list protocol handler。
- 没有 ACP registry/package metadata。

## ACP 实现可行性分析

### 技术可行性

高。首版可以作为独立入口运行：

```text
yoyoagent --acp
yoyoagent acp
```

或者单独模块：

```text
python -m agent.acp.server
```

内部仍复用：

```text
ACP JSON-RPC
  -> AcpServer
  -> AcpSessionManager
  -> Session
  -> StreamEvent callback
  -> AcpUpdateAdapter
  -> JSON-RPC notifications
```

### 产品可行性

高。yoyoagent 的 TUI 做得越丰富，越容易和 Zed/JetBrains 等编辑器 UI 形成重复；ACP 可以让 yoyoagent 专注 agent core，让外部 client 承担 UI。现有 TUI 仍保留为本地 first-party UI。

### 兼容风险

中等。

主要风险：

- ACP 仍在快速变化，GitHub Copilot CLI 文档也标注 ACP support 是 public preview。
- Zed 对不同外部 agent 的功能支持不完全一致，例如 Zed 文档提到 Codex 部分 agent panel 功能还不可用。
- `session/load` 要 replay conversation，但 yoyoagent 当前 session 保存的是 provider-oriented messages，不等于 UI timeline；需要选择 replay 粒度。
- stdout 必须严格只输出 JSON-RPC，现有 `StreamPrinter` 不能用于 ACP server。
- approval 必须从 `ApprovalCallback` 变成 client JSON-RPC request，需要处理 cancel、timeout、拒绝。

## 推荐架构

新增目录：

```text
agent/acp/
  __init__.py
  server.py              # stdio JSON-RPC loop
  jsonrpc.py             # request/response/notification encode/decode
  types.py               # light typed dict/dataclass for ACP payloads
  session_manager.py     # session id -> Session/runtime task
  update_adapter.py      # StreamEvent -> session/update
  approval_adapter.py    # ApprovalRequest -> session/request_permission
  content_adapter.py     # ACP ContentBlock[] <-> yoyo prompt text
  command_adapter.py     # skills/commands -> available_commands_update
```

入口层：

```text
main.py
  yoyoagent --acp
```

首版只支持 stdio transport。所有日志写 stderr，绝不写 stdout。

## ACP MVP 详细方案

### 1. JSON-RPC stdio server

职责：

- 按行读取 stdin。
- 每行解析一个 JSON-RPC object。
- request 返回 response。
- notification 不返回 response。
- 所有异常转换为 JSON-RPC error。
- 日志只写 stderr。

必要方法：

```text
initialize
session/new
session/load
session/prompt
session/cancel
```

首版暂不实现：

```text
session/resume
session/set_mode
client fs/terminal methods
MCP server connection
```

### 2. initialize

返回建议：

```json
{
  "protocolVersion": 1,
  "agentCapabilities": {
    "loadSession": true,
    "promptCapabilities": {
      "image": false,
      "audio": false,
      "embeddedContext": true
    },
    "mcpCapabilities": {
      "http": false,
      "sse": false
    }
  },
  "agentInfo": {
    "name": "yoyoagent",
    "title": "YoyoAgent",
    "version": "0.3.2"
  },
  "authMethods": []
}
```

是否声明 `embeddedContext=true`：建议首版支持，因为 ACP prompt 可能带 resource block，可转成文本上下文追加到 prompt 中。

### 3. session/new

输入：

```json
{
  "cwd": "/abs/project",
  "mcpServers": []
}
```

行为：

- 校验 `cwd` 是绝对路径且存在。
- 创建 `Session.from_config(workdir=Path(cwd), persist_messages=true)`。
- 设置 `stream_callback=AcpUpdateAdapter.callback`。
- 保存到 session manager。
- 返回 `sessionId`。
- 发送 `available_commands_update`，列出 `/plan` 和可发现 skills。

### 4. session/load

行为：

- 使用 `Session.from_config(workdir=cwd, session_id=id, resume=True)`。
- 将 `Session.messages` replay 成 `session/update`。
- replay 粒度首版建议保守：
  - `HumanMessage` -> `user_message_chunk`
  - `AIMessage` with content -> `agent_message_chunk`
  - `Task Summary Memory` -> `agent_message_chunk` 或 `_meta.yoyo.context_summary`
  - `ToolMessage` 首版可略过，或作为 compact tool update；因为现有 session 已经压缩/裁剪 tool artifacts。
- replay 完成后返回 `null`。

### 5. session/prompt

行为：

1. 将 ACP `ContentBlock[]` 转成 yoyoagent prompt：
   - text: 直接拼接。
   - resource link: 转成 `Context resource: file://...`。
   - embedded resource: 转成 fenced block，限制长度。
   - image/audio: 首版不声明支持。
2. 启动 `asyncio.Task(session.send(prompt_text))`。
3. `StreamEvent` 通过 adapter 发 `session/update`。
4. 正常结束返回：

```json
{"stopReason": "end_turn"}
```

异常映射：

- `ApprovalDenied` / policy refusal -> `stopReason: "refusal"` 或 `end_turn` + agent message。
- cancellation -> `stopReason: "cancelled"`。
- max turns -> `max_turn_requests`。
- token/context fail -> `max_tokens` 或 JSON-RPC error，按具体错误决定。

### 6. session/cancel

ACP server 需要记录：

```python
active_turns: dict[session_id, asyncio.Task]
```

收到 cancel：

- cancel task。
- 取消 pending approval request。
- 尽可能发未完成 tool_call 的 `cancelled` update。
- `session/prompt` request 最终返回 `{"stopReason": "cancelled"}`。

### 7. StreamEvent -> ACP update 映射

| StreamEvent | ACP update |
| --- | --- |
| `text_delta` | `agent_message_chunk` |
| `thinking_start/thinking_delta/thinking_end` | 可选 `agent_message_chunk` with thought 或 `_meta`；首版可不发送 thinking_delta |
| `tool_start` | `tool_call`，status `pending` 或 `in_progress` |
| `tool_end` | `tool_call_update`，status `completed` |
| `tool_result` | `tool_call_update`，status `completed`，content text，rawOutput |
| `usage` | `_meta.yoyo.usage` 或忽略 |
| `context_compressed/context_summarized` | `agent_message_chunk` 简短 context notice 或 `_meta.yoyo.context` |
| `approval_required` | 不直接 update；通过 `session/request_permission` request |
| `approval_resolved` | `tool_call_update` 或 context notice |
| `subagent_started/subagent_finished` | `tool_call` / `tool_call_update` kind `think` 或 `other` |
| `files_changed_summary` | `tool_call_update` kind `edit` with locations |

Tool kind 映射：

| yoyo tool | ACP kind |
| --- | --- |
| `read_file/read_many_files/list_files/git_show/workspace_state` | `read` |
| `grep/lsp_*` | `search` |
| `apply_patch/write_file/edit_file` | `edit` |
| destructive delete/move if later added | `delete` / `move` |
| `bash/verify` | `execute` |
| `todo` | `think` or plan update |
| `subagent` | `think` or `other` |

### 8. ApprovalRequest -> ACP permission

新增 `AcpApprovalAdapter`：

```text
ApprovalService
  -> AcpApprovalAdapter.callback(request)
  -> JSON-RPC request: session/request_permission
  -> wait client response
  -> return True/False
```

必须处理：

- client cancel。
- request timeout。
- missing target file。
- diff preview。
- file paths / tool name / risk reason。

首版 permission payload 应带：

```json
{
  "sessionId": "...",
  "toolCall": {
    "title": "Apply patch",
    "kind": "edit",
    "locations": [{"path": "/abs/file.py"}],
    "rawInput": {...}
  },
  "options": [
    {"optionId": "approve", "name": "Approve", "kind": "allow"},
    {"optionId": "deny", "name": "Deny", "kind": "reject"}
  ]
}
```

具体字段需按 ACP schema 最终核对。

### 9. Plan update

`TodoManager` 已有 items/status。首版实现：

- 在 todo `tool_result` 或 `tool_end` 后读取 `todo_manager.get_task_state()`。
- 转成 ACP plan entries：

```text
pending -> pending
in_progress -> in_progress
completed -> completed
```

priority 首版可以统一 `medium`，或把当前 active item 标为 `high`。

ACP 要求每次发送完整 plan entries，client 会替换当前 plan；这和当前 Task Plan 实时显示一致。

### 10. Slash commands

首版发送：

- `/plan`：讨论需求、列出可能改动文件、只规划不执行。
- skills：从 `SkillRegistry` 读取，转为 available commands。

注意 ACP slash commands 是普通 prompt text，不是 TUI `:` 命令。现有 `:help/:clear` 属于 yoyoagent TUI local command，不建议暴露给 ACP client。

### 11. Session modes

建议第二阶段再做。

候选模式：

| mode | 行为 |
| --- | --- |
| `ask` | 默认审批，读可自动，写/执行需 approval |
| `auto_edit` | 文件编辑自动，bash/高风险需 approval |
| `plan` | 只读规划；可内部走 `/plan` skill 或系统约束 |
| `code` | 类似当前 normal mode |

当前 yoyoagent 有 auto approval 和 `/plan` skill，但没有完整 per-session mode 状态机，所以 MVP 不声明 mode capability 更稳。

## 与现有 TUI 的关系

ACP server 不应该复用 TUI renderer。TUI 是本地 UI，ACP 是协议 UI。

应复用：

- `Session`
- `StreamEvent`
- `ApprovalRequest`
- `TodoManager`
- `SessionStore`
- `ToolEvent metadata`

不复用：

- Rich/Textual renderer
- TUI keybinding
- TUI modal screens
- TUI local commands

但 TUI 的实现经验可以反向帮助 ACP adapter：timeline 的语义化工具标题、搜索摘要、文件变更 summary、diff summary 都可以映射到 ACP tool title/content。

## 测试计划

### 单元测试

- JSON-RPC parse/response/error。
- `initialize` capability response。
- `session/new` 创建 workdir-bound Session。
- `session/load` 恢复并 replay user/assistant summary。
- `ContentBlock[]` 转 prompt 文本。
- `StreamEvent` 到 ACP update 的映射。
- `ApprovalRequest` 到 permission request 的映射。
- cancel active prompt 返回 `cancelled` stopReason。
- stdout 不输出非 JSON-RPC 内容。

### 集成测试

- 用 fake provider 跑完整 `initialize -> session/new -> session/prompt`。
- 捕获 stdout，验证每行都是 JSON。
- 模拟工具调用，验证 tool_call/tool_call_update。
- 模拟 todo，验证 plan update。
- 模拟 approval，验证 server 发 request，client approve 后继续。
- 模拟 client cancel，验证 prompt response stopReason。

### 手工兼容测试

- Zed custom agent：

```json
{
  "agent_servers": {
    "YoyoAgent": {
      "type": "custom",
      "command": "yoyoagent",
      "args": ["--acp"],
      "env": {}
    }
  }
}
```

- 在 Zed agent panel 中：
  - 新建线程。
  - 发送只读问题。
  - 发送需要编辑文件的问题。
  - 验证 permission UI。
  - 验证 plan/tool/file 更新。
  - 取消正在执行的任务。
  - 关闭后 load session。

## 分阶段交付

### Phase 0：协议依赖与 schema 决策

目标：确定用官方 Python SDK 还是轻量自实现。

建议：

- 优先评估 `agentclientprotocol` Python SDK。
- 如果 SDK 引入成本小，用 SDK 保持 schema 兼容。
- 如果 SDK 还不成熟，先做内部 minimal JSON-RPC + TypedDict，并把 schema 映射集中在 `agent/acp/types.py`。

产出：

- `docs/acp_research_and_implementation_plan.md`
- SDK 选型记录。

### Phase 1：stdio ACP MVP

目标：能被 Zed custom agent 拉起，完成一轮 prompt。

范围：

- `--acp` 启动。
- stdio JSON-RPC。
- `initialize`。
- `session/new`。
- `session/prompt`。
- text/tool updates。
- stopReason。

不做：

- approval。
- load replay。
- cancel。
- slash commands。

### Phase 2：审批与取消

目标：可安全执行写入任务。

范围：

- `AcpApprovalAdapter`。
- permission request。
- cancel active prompt。
- pending approval cancellation。
- tool status cancelled/failed/completed。

### Phase 3：session persistence

目标：编辑器重启后可以恢复。

范围：

- `session/load`。
- replay canonical messages。
- session list 如果 ACP client 需要。
- session warning/error 映射。

### Phase 4：plan / commands / modes

目标：接近主流外部 agent 体验。

范围：

- todo -> ACP plan。
- skills -> available slash commands。
- `/plan` command。
- session modes：ask / auto_edit / plan / code。

### Phase 5：高级集成

目标：跟上生态完整能力。

范围：

- MCP servers from ACP `mcpServers`。
- client fs/terminal methods。
- richer file locations/diff updates。
- ACP registry metadata。
- JetBrains/Zed/OpenCode 等多 client 兼容测试。

## 当前缺口清单

按优先级排序：

1. ACP stdio JSON-RPC server。
2. StreamEvent -> ACP update adapter。
3. AcpSessionManager。
4. ApprovalRequest -> `session/request_permission` adapter。
5. `session/cancel` task cancellation。
6. `session/load` replay。
7. todo -> ACP plan update。
8. skills -> available_commands_update。
9. session modes。
10. MCP server config intake。
11. client fs/terminal capability support。
12. ACP registry packaging。

## 不建议首版做的事情

- 不要一开始就实现 HTTP transport。stdio 是 ACP 推荐优先支持的路径。
- 不要把 TUI renderer 直接输出给 ACP client。ACP client 需要结构化更新。
- 不要让 ACP client fs/terminal 替代现有工具系统。先保持 yoyoagent 自己执行，减少变量。
- 不要首版做 MCP server injection。它会引入另一个协议生命周期，适合 ACP MVP 稳定后再做。
- 不要声明不完整的 session modes。未实现完整行为前，不如不声明 capability。

## 最小可用里程碑

当以下场景可通过，即可认为 yoyoagent ACP MVP 成立：

1. Zed custom agent 能启动 `yoyoagent --acp`。
2. Zed 能创建 session，并发送普通 prompt。
3. yoyoagent 能流式返回 assistant text。
4. 工具调用能在 Zed 中显示为 tool_call/tool_call_update。
5. 写文件时能弹出 Zed permission UI。
6. 用户 approve 后继续，deny 后停止并给明确提示。
7. cancel 能让当前 prompt 返回 `cancelled`。
8. session/load 能恢复上一轮 summary/history。

## 对路线图的建议

ACP 值得进入 P1/P2 之间，但不建议立刻从协议 server 开始。建议先实现一组 yoyoagent 项目内部兼容能力，再实现 ACP stdio server。

原因：

- ACP 主要是协议适配，不要求重写 agent core。
- 但 ACP 需要稳定复用 model、plan、diff、replay、cancel、approval 等内部能力；这些能力先在项目内部收口，后续协议层会更薄。
- 但它会暴露 runtime 行为差异，尤其是 subagent、approval、tool events；先统一 subagent runtime 会降低 ACP adapter 的复杂度。
- ACP 一旦完成，会让 yoyoagent 进入主流编辑器生态，收益明显高于继续只优化自有 TUI。

建议路线图新增：

```text
P1 ACP compatibility prerequisites（已实现首版）
  - single-provider model switching
  - public plan snapshot
  - public changed-files/diff snapshot
  - session replay view model
  - shared cancel controller
  - UI-independent approval adapter

P1.5 ACP stdio server MVP
  - initialize/session/new/session/prompt
  - StreamEvent -> session/update
  - ApprovalRequest -> session/request_permission
  - session/cancel
  - session/load replay
```

随后：

```text
P2 ACP ecosystem integration
  - slash commands
  - session modes
  - MCP server config
  - client fs/terminal
  - registry packaging
```
