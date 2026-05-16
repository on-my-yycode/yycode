# yoyohub ACP Compatibility Report

更新时间：2026-05-16

## 环境信息

- yoyohub commit: `57de82b`
- yoyoagent commit: `1d8923b`
- OS / arch: macOS 26.3.1 (25D771280a), arm64
- Python version: `Python 3.11.8`
- yoyoagent Python: `/Users/yoyofx/Documents/github/yoyoagent/.venv/bin/python`, `Python 3.11.8`
- Node/Electron/前端运行环境:
  - 测试用 Node: `v24.14.1`
  - npm: `11.11.0`
  - Electron: `^42.0.1`
  - React: `^18.3.1`
  - Vite: `^6.0.5`
  - TypeScript: `^5.7.2`
- 默认 shell Node: `v14.18.1`。该版本无法运行当前 npm 11，需要通过 nvm 切换到 Node 24。
- ACP transport: stdio
- yoyoagent 启动命令:
  - smoke test: `/Users/yoyofx/Documents/github/yoyoagent/.venv/bin/python /Users/yoyofx/Documents/github/yoyoagent/main.py --acp`
  - 产品配置建议: `yoyoagent --acp` 或 `yoyoagent acp`
- 工作目录 cwd: `/Users/yoyofx/Documents/github/yoyoagent`
- 是否启用 auto approval: 本次 smoke 未启用；yoyohub 产品中通过 AgentProfile args 包含 `-a` 判断自动审批。
- 使用的模型/provider: 本次 smoke 未触发模型调用。yoyohub 默认 seed profile 为 provider `openai`，model `gpt-5.2`。

## initialize 兼容性

- initialize 是否成功: yes
- protocolVersion: `1`
- clientCapabilities: yoyohub 当前 initialize 请求只发送 `clientInfo`，未发送 clientCapabilities。
- agentCapabilities:
  - `loadSession: true`
  - `promptCapabilities.image: false`
  - `promptCapabilities.audio: false`
  - `promptCapabilities.embeddedContext: true`
  - `mcpCapabilities.http: false`
  - `mcpCapabilities.sse: false`
- agentInfo:
  - `name: yoyoagent`
  - `title: YoyoAgent`
  - `version: 0.3.2`
- authMethods: `[]`
- 是否有未知字段导致 client/server 报错: no
- yoyohub 当前必填要求:
  - `initialize` 请求必须返回成功 JSON-RPC response。
  - yoyohub 当前没有强制校验 `protocolVersion`、`agentCapabilities`、`agentInfo` 字段。若缺失，当前代码仍会继续启动 client。
- 当前差距:
  - yoyohub 没有保存 initialize result 到 runtime status / snapshot，UI 和报告只能通过脚本采集。

### 脱敏 JSON-RPC 样例

请求：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "clientInfo": {
      "name": "yoyohub",
      "version": "0.1.0"
    }
  }
}
```

响应：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
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
}
```

## Session 生命周期测试

| 场景 | 必测 | 结果 | 备注 / 日志 |
| --- | --- | --- | --- |
| `session/new` 使用 cwd 创建新会话 | yes | pass | `npm run smoke:acp` 通过，返回 `sessionId`。 |
| `session/prompt` 单轮普通问答 | yes | not tested | yoyohub 产品代码已调用 `session/prompt`，但本报告未跑独立 contract 脚本采样。 |
| `session/prompt` 触发只读工具 | yes | not tested | 待补兼容脚本。 |
| `session/prompt` 触发编辑/审批工具 | yes | not tested | 产品 UI 已接 `session/request_permission`，但需补 request/response fixture。 |
| `session/cancel` 取消运行中 prompt | yes | partial pass | `compat:acp` 已验证 idle session cancel 返回 `{ "status": "not_running" }`；运行中 prompt cancel 待测。 |
| `session/load` 恢复历史并 replay | yes | pass | `compat:acp` 已验证 `session/load` 对刚创建 session 返回成功；有历史内容的 replay 展示待测。 |
| 同一 session 连续多轮 prompt | yes | not tested | 待补兼容脚本。 |
| 不同 session 并行或交错操作 | recommended | not tested | 待补兼容脚本。 |
| 同一 session 并发 prompt 的行为 | recommended | not tested | yoyohub 当前没有同 session 并发 prompt guard 的显式测试。 |

### session/new 样例

当前 yoyohub smoke 发送的 params 包含产品语义字段 `mode` 和 `temporary`：

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "session/new",
  "params": {
    "cwd": "<WORKDIR>",
    "mode": "discussion",
    "temporary": true
  }
}
```

yoyoagent 当前兼容该 shape，并返回：

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "sessionId": "8686ddab-53b3-4f24-b7dd-2e08bc94bdf8"
  }
}
```

备注：ACP 文档中的最小 `session/new` 输入更偏 `{ "cwd": "...", "mcpServers": [] }`。建议 yoyoagent 明确是否长期容忍 `mode` / `temporary` 扩展字段；yoyohub 会继续把 discussion / execution / review 的 persistence 作为产品语义保存。

## Update 映射兼容性

| yoyoagent 内部事件 | ACP update 期望 | yoyohub 展示要求 | 结果 |
| --- | --- | --- | --- |
| assistant 文本流 | agent message chunk | 流式追加文本 | partial pass。yoyohub 会 buffer `agent_message_chunk`，execution/review 会汇总为 Agent message；discussion 不持久化原始 chunk。 |
| thinking / reasoning，如有 | agent message 或 meta | 可忽略但不能报错 | not tested。unknown update 当前会落为 `ACP` state JSON，理论上不报错。 |
| tool_start | tool call pending/in_progress | 展示工具名称和参数摘要 | partial pass。`tool_call` 会映射为 tool timeline event。 |
| tool_result | tool call update | 展示关键输出，长输出可折叠 | partial pass。yoyohub 已新增通用 normalized event 支持并映射到 timeline；真实 tool fixture 待测。 |
| tool_end | tool call completed/failed | 展示完成状态和耗时 | partial pass。yoyohub 已新增 `tool_call_update` timeline 映射；聚合 tool card 待做。 |
| todo tool result | plan update | 替换当前任务计划 | partial pass。`plan` update 会映射为 `PLAN` timeline event，但 yoyohub 还没有独立 plan view model。 |
| files_changed_summary | edit/location update | 展示文件变更列表 | partial pass。yoyohub 目前主要通过 git diff capture 生成 changed files，不依赖 ACP files_changed_summary。 |
| approval request | request_permission | 弹出授权 UI | partial pass。yoyohub 已接 `session/request_permission` 并创建 PendingApproval；需补完整 fixture 验证。 |
| available_commands_update | commands list | 展示或缓存命令 | pass。yoyohub 已缓存到 runtime status，并映射为 timeline event；UI 输入辅助待做。 |

额外记录：

- yoyohub 是否要求每个 tool call 有稳定 `id`: 当前 UI 不强制，因为未构建 tool call 聚合 view model；如果后续要把 `tool_call_update` 合并到对应 tool，建议要求稳定 id。
- yoyohub 是否要求 tool call update 必须引用已有 tool call: 当前不要求；后续建议要求，便于更新同一个 tool card。
- yoyohub 是否支持 partial update，还是要求每次完整替换: 当前 timeline 是 append-only；plan 语义上应完整替换，但尚未实现独立 plan state。
- yoyohub 对 unknown update type 的处理方式: 当前 `acpUpdateToTimelineEvent` 会把 unknown update 作为 `ACP` state，并 JSON.stringify body。
- yoyohub 对 `_meta` 字段的处理方式: 当前没有专门处理 `_meta`，unknown body 可能被整体 JSON 化展示。

### available_commands_update 样例

yoyoagent 在 `session/new` 后会发送：

```json
{
  "jsonrpc": "2.0",
  "method": "session/update",
  "params": {
    "sessionId": "<SESSION_ID>",
    "update": {
      "sessionUpdate": "available_commands_update",
      "commands": [
        {
          "name": "/plan",
          "description": "Discuss requirements and produce an implementation plan without executing changes."
        },
        {
          "name": "/code_review",
          "description": "Perform comprehensive code reviews focused on code quality, error handling, testing, documentation, and actionable feedback."
        }
      ]
    }
  }
}
```

yoyohub 当前未缓存或展示 commands list。

## Permission / Approval 测试

| 场景 | 结果 | 备注 |
| --- | --- | --- |
| 只读工具不请求审批 | not tested | 待补 prompt fixture。 |
| `apply_patch` / `write_file` 请求审批 | not tested | 产品代码有 PendingApproval UI，但本报告未采集真实 payload。 |
| `bash` 高风险命令请求审批 | not tested | 待补 prompt fixture。 |
| 用户允许后继续执行 | partial pass by code review | yoyohub 会对 pending request `respond(id, { optionId: "approve" })`。需实测。 |
| 用户拒绝后返回清晰错误 | partial pass by code review | yoyohub 会 `respond(id, { optionId: "deny" })` 并 resolve pending approval。需实测 agent 输出。 |
| 请求超时或 client 关闭 | fail / yoyohub gap | 当前 pending approval 没有 timeout 处理。 |
| prompt cancel 时存在 pending approval | fail / yoyohub gap | Stop Task 当前未确认会调用 ACP cancel，也没有统一清理 pending approval。 |

### yoyohub 当前 permission response shape

允许：

```json
{
  "jsonrpc": "2.0",
  "id": "<REQUEST_ID>",
  "result": {
    "optionId": "approve"
  }
}
```

拒绝：

```json
{
  "jsonrpc": "2.0",
  "id": "<REQUEST_ID>",
  "result": {
    "optionId": "deny"
  }
}
```

当前不支持：

- deny reason
- always allow
- session-level decision
- pending approval timeout

## Tool UI 要求

- tool call title 最大长度: 建议 80 字符以内；UI 会在窄布局中截断。
- content 最大长度: timeline/log 可展示摘要；长输出应折叠或截断到 4,000 字符左右。当前 Agent message buffer 会截断到 4,000 字符。
- rawInput/rawOutput 是否显示: 默认不直接展开；建议作为 Log 详情或 debug 信息保留。
- locations 字段是否用于跳转: 需要。后续可用于打开 Workspace IDE Lite 的文件。
- diff 是否需要 unified diff: 需要。yoyohub 的 diff viewer 使用 unified inline diff，不使用 side-by-side。
- 文件路径是否必须为 cwd-relative: UI 最适合 cwd-relative；绝对路径可接收，但展示时建议脱敏/相对化。
- 是否需要 tool kind: 需要 `read/search/edit/execute/think/other`，用于图标、颜色和过滤。
- failed/cancelled 状态展示要求: 必须能在 timeline/log 中显示状态；后续 tool card 应支持 failed/cancelled/completed。

## 错误与取消语义

| 场景 | 期望 | 实际 |
| --- | --- | --- |
| 无效 JSON-RPC | 返回 JSON-RPC parse error | not tested。yoyohub transport 收到非 JSON line 会 emit parseError，但当前没有产品 UI 展示。 |
| 未知 method | 返回 method not found | not tested。 |
| 无效 params | 返回 invalid params | not tested。 |
| provider 报错 | prompt 返回 error 或 failed stopReason | partial pass。yoyohub 会把 request reject 标记为 blocked/failed，但未细分 provider error。 |
| tool 报错 | tool update failed，prompt 可继续或失败 | fail / yoyohub gap。`tool_call_update` 当前忽略，failed tool 状态不可见。 |
| 用户 cancel | stopReason 为 cancelled | fail / yoyohub gap。AcpClient 支持 cancel，但产品 Stop Task 未完整接入 ACP cancel。 |
| client 断开 stdio | yoyoagent 进程退出或清理 session | partial pass。JsonRpcTransport 监听 exit，会 reject pending request 并把 runtime 状态置 disconnected。 |

yoyohub 希望的 stop reason 枚举：

- `end_turn`: 正常结束。注意这不是 Implementation Result。
- `cancelled`: 用户取消。
- `refusal`: 权限拒绝或策略拒绝。
- `max_turn_requests`: 达到最大轮次。
- `max_tokens`: 上下文/token 限制。
- 其它未知 stopReason: 不应导致崩溃，展示为 agent turn ended with unknown stop reason。

## 问题记录

### ACP-COMPAT-001: yoyohub lacks aggregated tool card state for `tool_call_update`

- 严重级别: medium
- 影响场景: tool_result / tool_end / failed / cancelled 工具状态目前可进入 timeline，但还没有按 tool call id 聚合成 card。
- yoyohub commit: `57de82b`
- yoyoagent commit: `1d8923b`
- 复现步骤:
  1. 触发任意会产生 tool_call_update 的 prompt。
  2. 观察 yoyohub timeline/log。
- 期望结果: yoyohub 展示工具输出、完成/失败/取消状态和关键摘要，并可按 tool call id 聚合。
- 实际结果: 已新增 normalized event 和 timeline 映射；聚合 UI 待做。
- 脱敏 JSON-RPC 请求/响应/notification: 待补真实 fixture。
- yoyoagent stderr 日志: 待补。
- yoyohub client 日志: 待补。
- 截图或录屏，如适用: 未采集。
- 初步判断: yoyohub enhancement。

### ACP-COMPAT-002: yoyohub does not display command suggestions yet

- 严重级别: medium
- 影响场景: `/plan` 和 skills commands 无法在 yoyohub UI 中展示或用于输入辅助。
- yoyohub commit: `57de82b`
- yoyoagent commit: `1d8923b`
- 复现步骤:
  1. 启动 yoyoagent ACP。
  2. 调用 initialize。
  3. 调用 session/new。
  4. yoyoagent 发送 `available_commands_update`。
- 期望结果: yoyohub 缓存 commands list，并在输入框中作为 slash command suggestion 展示。
- 实际结果: 已缓存到 runtime status；UI suggestion 待做。
- 脱敏 JSON-RPC notification: 见本文 `available_commands_update` 样例。
- 初步判断: yoyohub enhancement。

### ACP-COMPAT-003: Running prompt cancel needs full fixture coverage

- 严重级别: high
- 影响场景: 用户停止任务时，yoyoagent 侧 prompt 可能仍在运行；pending approval 也可能残留。
- yoyohub commit: `57de82b`
- yoyoagent commit: `1d8923b`
- 复现步骤:
  1. 启动长任务。
  2. 在 yoyohub 点击 Stop Task。
  3. 观察 yoyoagent prompt 是否收到 `session/cancel`。
- 期望结果: yoyohub 调用 `session/cancel`，prompt 返回 `{"stopReason":"cancelled"}`，pending approval 被清理。
- 实际结果: yoyohub Stop Task 已先调用 AcpClient.cancel 再收敛本地任务；`compat:acp` 已验证 idle cancel，运行中 prompt cancel 待测。
- 初步判断: yoyohub bug / 待适配。

### ACP-COMPAT-004: initialize result is not persisted in yoyohub runtime status

- 严重级别: low
- 影响场景: UI 和兼容报告无法直接看到 protocolVersion、agentCapabilities、agentInfo。
- yoyohub commit: `57de82b`
- yoyoagent commit: `1d8923b`
- 复现步骤:
  1. 启动 yoyohub。
  2. 连接 yoyoagent ACP。
  3. 查看 snapshot runtimeStatuses。
- 期望结果: runtime status 或 agent capability cache 包含 initialize result。
- 实际结果: 当前只保存 connected/error 等连接状态。
- 初步判断: yoyohub enhancement。

## 本次已执行命令

```bash
source ~/.nvm/nvm.sh && nvm use 24.14.1 >/dev/null && npm run smoke:acp
source ~/.nvm/nvm.sh && nvm use 24.14.1 >/dev/null && npm run compat:acp
```

结果：

- `smoke:acp`: pass。构建成功，`initialize + session/new` 成功，返回 `sessionId`。
- `compat:acp`: pass。构建成功，`initialize`、`session/new`、`available_commands_update`、`session/load`、idle `session/cancel` 均通过；prompt/model/tool/permission 场景默认跳过，可通过 `ACP_COMPAT_RUN_PROMPTS=1` 开启。

## 建议下一步

### yoyoagent 侧

1. **沉淀 ACP/yoyohub contract fixtures**：把本报告中已经通过的 `initialize`、`session/new`、`available_commands_update`、`session/load`、idle `session/cancel` 样例固化到 yoyoagent 测试中；后续用 yoyohub 提供的真实 prompt/tool/permission JSON-RPC 样例扩展 fixture。
2. **明确 `session/new` 扩展字段策略**：长期容忍 `mode` / `temporary` 等未知字段，但不把它们作为 yoyoagent 核心执行语义；如果未来需要执行 discussion/execution/review 模式，应另行设计 ACP extension。
3. **增加同 session prompt 串行 guard**：同一 `sessionId` 同时收到第二个 prompt 时，应排队或返回明确 busy/error，避免并发修改 `messages`、todo、graph 和 approval 状态。
4. **硬化 permission / cancel 边界**：补 pending approval 时 cancel 的清理语义；评估 permission timeout 和 client disconnect 后 pending request 的清理行为。
5. **打磨 tool/update schema**：保持 stable `toolCallId`，继续输出 `kind/status/content/rawInput/rawOutput/locations`；优先让 file locations 使用 cwd-relative path，或在展示面避免泄露用户目录。
6. **ACP 多 session 生命周期硬化**：确保不同 session 可并行执行，单个 session close/cancel 不影响其它 session；LSP manager 生命周期不能被某个 session close 全局 shutdown。

### yoyohub 侧

1. yoyohub 扩展 ACP compat script，继续覆盖 prompt/read/edit/permission/running cancel/multi-turn。
2. yoyohub 增加 tool call 聚合展示，按 stable tool call id 更新同一个 tool card。
3. yoyohub 增加 commands 输入辅助 UI。
4. yoyohub 保存 initialize result 到 runtime status，便于 UI 和报告复用。
