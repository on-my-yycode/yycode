# ACP 与 yoyohub 对接要求

更新时间：2026-05-16

## 目的

本文档用于约定 yoyoagent ACP server 与外部项目 `yoyohub` 的联调信息格式、兼容性测试范围和反馈要求。

`yoyohub` 侧完成接入或测试后，请按本文档填写结果并回传给 yoyoagent 项目，以便我们把真实 client 行为沉淀为 ACP compatibility matrix、contract tests 和后续修复计划。

## 当前 yoyoagent ACP 能力基线

yoyoagent 当前 ACP 入口：

```bash
yoyoagent --acp
# 或
yoyoagent acp
```

当前已实现的协议能力：

- `initialize`
- `session/new`
- `session/load`
- `session/prompt`
- `session/cancel`
- `session/update`
- `session/request_permission`
- `available_commands_update`
- todo / Task State 到 ACP plan update 的基础映射
- tool start/result/end 到 ACP tool update 的基础映射
- session replay 的基础映射

当前暂不作为强制能力的范围：

- client filesystem / terminal method 调用
- MCP servers intake / 转发
- session modes 状态机
- registry/package 发布
- streamable HTTP transport

## yoyohub 侧需要填写的信息

请在 yoyohub 项目中新增或维护一份对接报告，建议命名为：

```text
docs/yoyoagent_acp_compatibility_report.md
```

报告至少包含以下内容。

### 1. 环境信息

```markdown
## 环境信息

- yoyohub commit:
- yoyoagent commit:
- OS / arch:
- Python version:
- Node/Electron/前端运行环境版本，如适用:
- ACP transport: stdio / other
- yoyoagent 启动命令:
- 工作目录 cwd:
- 是否启用 auto approval:
- 使用的模型/provider:
```

### 2. 能力握手结果

记录 `initialize` 请求和响应的关键字段。

```markdown
## initialize 兼容性

- initialize 是否成功: yes/no
- protocolVersion:
- clientCapabilities:
- agentCapabilities:
- agentInfo:
- authMethods:
- 是否有未知字段导致 client/server 报错:
- 原始 JSON-RPC 样例，脱敏后:
```

要求：

- 如果 yoyohub 对某些字段有必填要求，请明确列出。
- 如果字段名称、类型、枚举值与 yoyoagent 当前输出不兼容，请提供最小复现 JSON。

### 3. Session 生命周期测试

请逐项填写：

| 场景 | 必测 | 结果 | 备注 / 日志 |
| --- | --- | --- | --- |
| `session/new` 使用 cwd 创建新会话 | yes | pass/fail |  |
| `session/prompt` 单轮普通问答 | yes | pass/fail |  |
| `session/prompt` 触发只读工具 | yes | pass/fail |  |
| `session/prompt` 触发编辑/审批工具 | yes | pass/fail |  |
| `session/cancel` 取消运行中 prompt | yes | pass/fail |  |
| `session/load` 恢复历史并 replay | yes | pass/fail |  |
| 同一 session 连续多轮 prompt | yes | pass/fail |  |
| 不同 session 并行或交错操作 | recommended | pass/fail/not tested |  |
| 同一 session 并发 prompt 的行为 | recommended | pass/fail/not tested |  |

### 4. Update 映射兼容性

请确认 yoyohub 是否能正确展示以下 `session/update` 类型：

| yoyoagent 内部事件 | ACP update 期望 | yoyohub 展示要求 | 结果 |
| --- | --- | --- | --- |
| assistant 文本流 | agent message chunk | 流式追加文本 |  |
| thinking / reasoning，如有 | agent message 或 meta | 可忽略但不能报错 |  |
| tool_start | tool call pending/in_progress | 展示工具名称和参数摘要 |  |
| tool_result | tool call update | 展示关键输出，长输出可折叠 |  |
| tool_end | tool call completed/failed | 展示完成状态和耗时 |  |
| todo tool result | plan update | 替换当前任务计划 |  |
| files_changed_summary | edit/location update | 展示文件变更列表 |  |
| approval request | request_permission | 弹出授权 UI |  |
| available_commands_update | commands list | 展示或缓存命令 |  |

请额外记录：

- yoyohub 是否要求每个 tool call 有稳定 `id`。
- yoyohub 是否要求 tool call update 必须引用已有 tool call。
- yoyohub 是否支持 partial update，还是要求每次完整替换。
- yoyohub 对 unknown update type 的处理方式。
- yoyohub 对 `_meta` 字段的处理方式。

### 5. Permission / Approval 测试

至少覆盖：

| 场景 | 结果 | 备注 |
| --- | --- | --- |
| 只读工具不请求审批 |  |  |
| `apply_patch` / `write_file` 请求审批 |  |  |
| `bash` 高风险命令请求审批 |  |  |
| 用户允许后继续执行 |  |  |
| 用户拒绝后返回清晰错误 |  |  |
| 请求超时或 client 关闭 |  |  |
| prompt cancel 时存在 pending approval |  |  |

请提供 permission request / response 的脱敏 JSON 示例，尤其是：

- request method 名称
- permission id / call id 字段
- 用户选择 allow/deny 后的 response shape
- deny reason 是否支持
- client 是否支持 `always allow` 或 session-level decision

### 6. 工具调用展示要求

请记录 yoyohub 对工具 UI 的要求：

```markdown
## Tool UI 要求

- tool call title 最大长度:
- content 最大长度:
- rawInput/rawOutput 是否显示:
- locations 字段是否用于跳转:
- diff 是否需要 unified diff:
- 文件路径是否必须为 cwd-relative:
- 是否需要 tool kind: read/search/edit/execute/think/other
- failed/cancelled 状态展示要求:
```

### 7. 错误与取消语义

请覆盖并填写：

| 场景 | 期望 | 实际 |
| --- | --- | --- |
| 无效 JSON-RPC | 返回 JSON-RPC parse error |  |
| 未知 method | 返回 method not found |  |
| 无效 params | 返回 invalid params |  |
| provider 报错 | prompt 返回 error 或 failed stopReason |  |
| tool 报错 | tool update failed，prompt 可继续或失败 |  |
| 用户 cancel | stopReason 为 cancelled |  |
| client 断开 stdio | yoyoagent 进程退出或清理 session |  |

请明确 yoyohub 希望的 stop reason 枚举和错误展示方式。

### 8. 日志与复现材料

每个 fail 项请提供：

```markdown
## 问题记录

### ACP-COMPAT-001: 简短标题

- 严重级别: blocker/high/medium/low
- 影响场景:
- yoyohub commit:
- yoyoagent commit:
- 复现步骤:
- 期望结果:
- 实际结果:
- 脱敏 JSON-RPC 请求/响应/notification:
- yoyoagent stderr 日志:
- yoyohub client 日志:
- 截图或录屏，如适用:
- 初步判断: yoyoagent bug / yoyohub bug / ACP schema 差异 / 待讨论
```

脱敏要求：

- 移除 API key、token、cookie、绝对用户目录隐私信息。
- 可保留相对路径、method、params shape、错误码、字段类型。
- 大段模型输出可截断，但不要删除导致 schema 错误的字段。

## yoyoagent 侧期望沉淀的结果

收到 yoyohub 报告后，yoyoagent 侧会优先把以下内容沉淀回来：

1. ACP compatibility matrix。
2. JSON-RPC contract tests 或 fixture。
3. permission request/response 兼容测试。
4. session lifecycle 回归测试。
5. update adapter 的 schema polish。
6. docs/usage.md 中面向 yoyohub 的启动和故障排查说明。

## 收到 yoyohub 报告后的 yoyoagent 处理规则

yoyohub 报告中的问题需要先区分归属，再进入 yoyoagent 待办：

- **yoyoagent 必须处理**：协议响应不符合 ACP、JSON-RPC shape 不稳定、同 session prompt 并发破坏状态、`session/cancel`/permission 清理不完整、`session/load` replay 不可用、tool/update 字段缺失或难以稳定消费。
- **yoyoagent 应文档化兼容策略**：`session/new` 中 `mode` / `temporary` 等 client 扩展字段、未知 update/client capability 的容忍策略、stopReason 与错误码语义。
- **yoyoagent 可做 polish**：tool locations 路径相对化、tool title/content 截断策略、rawInput/rawOutput 是否进入 debug 信息、permission timeout 默认值。
- **yoyohub 侧处理**：initialize result 持久化、commands UI suggestion、tool card 聚合展示、产品 Stop Task 到 ACP cancel 的 UI 状态收敛。

进入 yoyoagent 实现前，应优先把 yoyohub 提供的 JSON-RPC 样例沉淀为 contract fixture。没有 fixture 的兼容问题，只能先作为待确认项，不应直接改协议行为。

## yoyoagent 当前建议跟进项

基于 `docs/yoyoagent_acp_compatibility_report.md` 的首轮结果，yoyoagent 侧建议跟进：

1. **P0：ACP/yoyohub contract fixtures**
   - 固化 `initialize`、`session/new`、`available_commands_update`、`session/load`、idle `session/cancel` 的已通过样例。
   - 后续补 `session/prompt` 文本流、只读工具、编辑/审批工具、running cancel、多轮 prompt 的 fixture。

2. **P0：同 session prompt 串行 guard**
   - 同一 `sessionId` 同时收到第二个 prompt 时，应排队或返回明确 busy/error。
   - 避免并发修改 `Session.messages`、`TodoManager`、graph 状态和 approval 状态。

3. **P1：`session/new` 扩展字段兼容策略**
   - 明确长期容忍 `mode` / `temporary` 等未知字段。
   - yoyoagent 不应把这些字段作为核心语义执行，除非后续 ACP 或产品协议显式扩展。

4. **P1：permission / cancel 边界硬化**
   - 补 pending approval 时 cancel 的清理语义。
   - 评估默认 permission timeout 或 client disconnect 后的 pending request 清理。

5. **P1：tool/update schema polish**
   - 保持 stable `toolCallId`。
   - 保留 `kind`、`status`、`content`、`rawInput`、`rawOutput`、`locations`。
   - 优先提供 cwd-relative path，或在绝对路径中避免泄露用户目录。

6. **P2：ACP 多 session 生命周期硬化**
   - 不同 session 可并行执行。
   - 单个 session close/cancel 不影响其它 session。
   - LSP manager 生命周期不应被某个 session close 全局 shutdown。

## 优先级建议

当前优先级：

1. **P0：协议兼容阻塞项**  
   任何导致 yoyohub 无法 initialize、创建 session、发送 prompt、收到文本更新的问题。

2. **P1：审批与工具展示**  
   任何导致编辑、bash、apply_patch 等风险操作无法正确授权或展示的问题。

3. **P1：cancel / error / replay 语义**  
   任何导致用户取消、恢复会话、工具失败状态不清晰的问题。

4. **P2：多 session 与并发硬化**  
   不同 session 并行、同 session 串行 guard、LSP 生命周期隔离等。

5. **P2：体验 polish**  
   tool title、diff 展示、plan entries、commands list、长输出折叠等。

## 建议给 yoyohub 的最小测试脚本

建议 yoyohub 至少覆盖以下手动或自动场景：

```text
1. 启动 yoyoagent --acp
2. initialize
3. session/new cwd=<测试项目>
4. session/prompt: “简单介绍这个项目”
5. session/prompt: “读取 README 并总结”
6. session/prompt: “创建一个临时文档文件” -> 触发 permission
7. 拒绝一次 permission，确认错误展示
8. 允许一次 permission，确认 tool completed 和文件变更展示
9. session/cancel 一个长任务
10. session/load 恢复刚才 session，确认 replay 可显示
```

## 非目标

本轮 yoyohub 对接不要求：

- 实现 web UI 全量等价 yoyoagent TUI。
- 暴露 yoyoagent 内部所有工具细节。
- 支持所有未来 ACP draft 能力。
- 支持 MCP 或 client fs/terminal。
- 支持 HTTP transport。

重点是先把 stdio ACP 的核心链路稳定跑通，并把真实 client 差异沉淀为可回归的兼容性测试。
