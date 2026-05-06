# Full TUI Design

## 目标

把 yoyoagent 从普通 CLI 输出升级为完整的 Terminal UI，让用户在任务执行过程中能持续看到：

- 当前 agent 正在做什么
- 处在哪个阶段
- 哪些工具正在运行
- 哪些 subagent 正在工作
- 哪些文件发生了变化
- 是否正在等待模型、测试、审批或用户输入

这不是重写 agent core，而是把现有交互入口切换为新的 TUI 前端层。

核心边界：

```text
Agent core emits StreamEvent
TUI consumes StreamEvent and provides user input / approval decisions
Agent core does not import Textual or know about TUI widgets
```

## 总体架构

```text
main.py
  -> agent.tui.app.YoyoTuiApp
    -> agent.tui.runner.AgentTuiRunner
      -> Session.send(...)
        -> StreamEvent callback
          -> agent.tui.state.TuiState
            -> Textual widgets render state

approval flow:

ApprovalService
  -> approval_callback(request)
    -> TuiApprovalAdapter creates pending approval
    -> TuiState records approval_required
    -> ApprovalModal waits for user decision
    -> adapter resolves Future[bool]
    -> ApprovalService continues or raises ApprovalDenied
```

## 推荐技术选型

推荐使用 `textual`。

原因：

- 有完整布局系统
- 支持 widgets、modal、keyboard bindings
- 基于 Rich，终端渲染质量好
- 更适合长期维护的 TUI 应用

需要新增依赖：

```toml
dependencies = [
    "textual>=0.80.0",
]
```

备选方案：

- `rich` + `prompt_toolkit`：适合轻量 timeline，不适合复杂多面板 UI。
- `curses`：无新增依赖，但开发成本高，组件能力弱。

## 入口设计

TUI 是默认交互入口，不再设计 `--tui` 或旧 CLI fallback。

启动方式：

```bash
python main.py
```

`main.py` 保持轻量，只负责加载配置并启动 TUI：

```python
from agent.tui.app import run_tui

await run_tui(args)
```

不要把 Textual 代码塞进 `main.py`。

## 需要修改的现有文件

### `main.py`

改动：

- 移除 `input()` 驱动的主交互循环。
- 保留参数解析、dotenv、logging、silent mode 等启动配置。
- 默认调用 `agent.tui.app.run_tui(args)`。
- 把旧 CLI 中仍有价值的纯函数保留或迁移，例如 startup info、token formatting、approval formatting。

风险：

- 中。入口行为会改变，需要确保 TUI 覆盖输入、审批、取消、退出和历史显示。

### `agent/streaming.py`

当前已具备 `StreamEvent` 结构化字段。

可能继续补充：

- `timestamp`
- `event_id`
- `thread_id` 或 `run_id`

风险：

- 低。字段保持 optional。

### `agent/runtime/tool_events.py`

继续丰富工具到 timeline 的映射。

重点工具：

- `read_file`
- `read_many_files`
- `grep`
- `list_files`
- `workspace_state`
- `git_diff`
- `apply_patch`
- `write_file`
- `verify`
- `bash`
- `subagent`

目标：

- TUI 默认展示用户可读意图。
- 原始命令和参数放进 `metadata`，只在详情面板显示。

### `agent/runtime/tool_executor.py`

当前已发：

- enriched `tool_start`
- enriched `tool_end`
- `file_changed`
- `tool_result`

后续可补：

- `test_started`
- `test_finished`
- `tool_failed`
- 更准确的 stdout/stderr summary

### `agent/runtime/approval_service.py`

当前已发：

- `approval_required`
- `approval_resolved`

后续重点不是改业务逻辑，而是接入 TUI approval adapter。

### `agent/subagent.py`

当前已发：

- `subagent_started`
- `subagent_finished`

后续可补：

- subagent 当前工具状态
- subagent 最近输出摘要
- subagent failure reason

### `agent/llm_retry.py`

当前已有 heartbeat 事件。

后续建议增强：

- `phase="waiting"`
- `title="Waiting for model response"`
- `detail` 包含 source、role、attempt、elapsed、idle
- `elapsed_ms`

这样 TUI 可以在模型无 token 返回时显示更有上下文的等待状态。

## 建议新增文件

### `agent/tui/__init__.py`

TUI 包入口，导出公开 API：`AgentTuiRunner`, `TuiState`, `TuiApprovalAdapter`, `TimelineItem` 等。

### `agent/tui/app.py`

Textual App 主类及所有内嵌 widget。

职责：

- 定义 `YoyoTuiApp(App)` — 主应用，管理布局、键盘快捷键和生命周期
- 定义 `ApprovalScreen(ModalScreen[bool])` — 审批弹窗
- 定义 `HistoryScreen(ModalScreen[None])` — 全屏历史查看器
- 提供 `run_tui(args)` 公共入口函数
- 所有 Textual widget 均在此文件内定义为内部类（不需要单独的 `widgets.py`）

当前布局：

```text
Vertical(root-layout)
  ├── Static(top-panel)          # header：模型/会话/上下文/任务状态
  ├── RichLog(timeline-panel)    # 可滚动 timeline（全高）
  └── Container(input-shell)     # 底部输入区域
        ├── Static(input-top-rule)
        ├── Horizontal(input-row)
        │     ├── Static(input-prompt)   # ">" 提示符
        │     └── TextArea(prompt-input) # 用户输入框
        └── Static(input-bottom-rule)
```

快捷键：

| 快捷键 | 操作 |
|--------|------|
| `Ctrl+Enter` / `Ctrl+J` | 提交输入 |
| `Ctrl+C` | 取消当前任务 |
| `Ctrl+H` | 打开历史记录浏览器 |
| `Ctrl+Shift+C` | 复制 timeline 到剪贴板 |
| `Ctrl+Q` | 退出 |
| `PageUp` / `PageDown` | 滚动 timeline |
| `Home` / `End` | 跳到 timeline 顶部/底部 |
| `Esc` | 聚焦输入框 |

建议 class：

```python
class YoyoTuiApp(App):
    CSS_PATH = "styles.tcss"
```

### `agent/tui/runner.py`

连接 TUI 和 agent runtime。

职责：

- 管理 `Session` 生命周期（start / close）
- 接收用户输入，调用 `Session.send()` 作为后台 async task
- 把 `StreamEvent` 写入 `TuiState`
- 支持 task 取消（`cancel_current_task`）
- 防止同一 session 同时运行多个用户任务
- 当 provider 未流式输出文本时自动补发 `text_delta` 事件

建议对象：

```python
class AgentTuiRunner:
    async def start(self) -> None
    async def close(self) -> None
    async def submit(self, text: str) -> None
    async def submit_nowait(self, text: str) -> None
    async def cancel_current_task(self) -> bool
    async def handle_stream_event(self, event: StreamEvent) -> None
    def resolve_approval(self, approval_id: str, approved: bool) -> bool
```

### `agent/tui/state.py`

TUI 状态 store。

核心数据类：

```python
@dataclass
class TimelineItem:
    id: str
    session_id: str
    event_type: str
    title: str
    detail: str
    phase: str | None
    status: str | None
    source: str
    role: str | None
    tool_name: str | None = None
    file_paths: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: int | None = None
    content: str = ""                      # 原始事件 content
    start_time_ms: int | None = None       # 条目创建时间
    is_transient: bool = False             # 临时条目（如 agent_thinking），完成后删除
    usage: dict[str, int] | None = None    # token 用量快照

@dataclass
class PendingApproval:
    approval_id: str
    title: str
    detail: str
    request_text: str
    diff_preview: str = ""
    tool_name: str | None = None
    file_paths: list[str] = field(default_factory=list)
    status: str = "waiting_for_user"

@dataclass
class SubagentStatus:
    session_id: str
    role: str
    title: str
    detail: str
    status: str
    elapsed_ms: int | None = None
```

核心状态（`TuiState` 类）：

- `timeline: list[TimelineItem]` — 事件时间线，上限 MAX_TIMELINE_ITEMS (500)
- `pending_approvals: dict[str, PendingApproval]` — 等待审批的请求
- `subagents: dict[str, SubagentStatus]` — 子代理状态
- `changed_files: list[str]` — 已变更文件列表
- `active_phase: str` — 当前阶段 (planning/exploring/implementing/verifying/waiting)
- `status_line: str` — 当前状态摘要
- `model_name: str` — 模型名称
- `session_id: str` — 会话 ID
- `workspace_path: str` — 工作区路径
- `latest_usage: dict[str, int]` — 最新 token 用量
- `todo_manager: TodoManager | None` — 关联的任务管理器
- `active_task: dict` — 当前运行中的任务追踪（is_running, start_time_ms, intent, current_action, usage）

关键方法：

- `apply_event(event: StreamEvent) -> TimelineItem` — 将流事件转换为 timeline item，支持合并和自动插入 thinking_end
- `add_user_input(session_id, text) -> TimelineItem` — 记录用户输入
- `next_pending_approval() -> PendingApproval | None` — 获取下一个待审批请求
- `_remove_transient_items()` — 清理临时状态项
- `get_elapsed_ms(item) -> int` — 计算条目耗时

### `agent/tui/renderers.py`

把 `TuiState` 渲染为 Textual Rich markup 文本。

核心渲染函数：

- `render_status_text(state, width) -> str` — 渲染 header 面板（双栏：左侧 logo/model/context/dir，右侧 task 运行态/就绪态）
- `render_timeline_lines(state, limit, ...) -> str` — 渲染 timeline（支持 main 模式和 history 模式）
- `_render_timeline_item(item, state) -> str | None` — 按事件类型分发渲染。所有事件类型均有专门的渲染逻辑：
  - `user_message` → `"You"` + content
  - `text_delta` → `"Yoyo"` + content
  - `thinking_start` / `thinking_end` / `thinking_delta` → 思考状态（thinking_delta 不单独显示）
  - `tool_start` → `"Tool call"` + tool_name + status + title/detail/args
  - `tool_end` → `"Tool returned"` + tool_name + status + elapsed
  - `tool_result` → diff 内容（带颜色高亮）
  - `usage` → token 统计
  - `file_changed` → 修改文件列表
  - `approval_required` / `approval_resolved` → 审批状态 + diff 高亮
  - `subagent_started` / `subagent_finished` → 子代理状态
  - `llm_waiting` / `llm_timeout` / `llm_retry` / `llm_error` → LLM 状态
- `_render_todo_section(todo_manager) -> str` — 渲染 Todo Task Plan 面板（含 items 和 memory）
- `colorize_diff_for_tui(diff) -> str` — diff 文本的 Rich 颜色标记
- `_format_duration(ms) -> str` — 毫秒 → 人类可读时长

注意：

- renderer 不应该调用 agent 工具。
- renderer 只消费 TuiState，不修改状态。
- 所有用户输入内容通过 `_safe_text()` 转义 `[` 字符，防止 Textual markup 解析错误。

### `agent/tui/styles.tcss`

Textual CSS 样式文件。

- 暗色配色方案（背景 `#101216`，前景 `#d7dae0`）
- 所有面板采用纯色背景，无边框
- 输入区域 7 行高度：上下分隔线 + 5 行输入区
- 审批弹窗使用 heavy border，紫色高亮

### `agent/tui/approval.py`

TUI approval adapter。

核心接口：

```python
class TuiApprovalAdapter:
    async def callback(self, request: ApprovalRequest) -> bool:
        ...

    def resolve(self, approval_id: str, approved: bool) -> None:
        ...
```

内部需要：

- pending dict: `approval_id -> Future[bool]`
- request dict: `approval_id -> ApprovalRequest`
- emit or state update hook

行为：

1. 收到 `ApprovalRequest`
2. 创建 `approval_id`
3. 写入 pending approval state
4. 等待 UI modal 调用 `resolve(...)`
5. 返回 bool 给 `ApprovalService`

### `tests/test_tui_state.py`

测试事件到状态的转换，包括渲染输出验证。

覆盖：

- `tool_start` / `tool_end` 创建并完成 timeline item
- `file_changed` 更新 changed files
- `approval_required` / `approval_resolved` 审批生命周期
- `subagent_started` 创建 subagent 状态
- `user_message` 记录用户输入
- `llm_waiting` 与 `agent_thinking` 的合并逻辑
- header panel 和 timeline 渲染输出验证
- tool args 的 Textual markup 转义
- renderer 在 session 未就绪时的初始状态

### `tests/test_tui_approval.py`

测试 approval adapter 的 Future 机制。

覆盖：

- `approval_id_for_request` 生成正确的 approval ID
- `TuiApprovalAdapter.callback` 等待并返回 approve/deny
- `resolve(approved=True)` 正确返回 True
- `resolve(approved=False)` 正确返回 False

### `tests/test_tui_runner.py`

测试 TUI runner 的异步行为。

覆盖：

- `submit_nowait` 在任务完成前记录用户输入
- provider 未流式输出时自动补发 `text_delta`
- 多轮对话中每轮 tool 和 text 事件都正确保留

## 事件渲染策略

实际实现中，事件渲染规则如下：

- `user_message` → 追加到 timeline，显示 `"You"` + content
- `text_delta` → 合并到同一个 `text_delta` item（连续 deltas 拼接 content），显示 `"Yoyo"` + content
- `thinking_start` / `thinking_delta` / `thinking_end` → thinking_start 显示 `"Thinking..."`，thinking_delta 不单独显示（只更新内容），thinking_end 在下一个非 thinking 事件时自动插入
- `tool_start` → 新建 item，显示 tool_name、status、title、detail、args
- `tool_end` → 新建 item，显示 tool_name、status、elapsed
- `tool_result` → 新建 item，diff 内容带颜色高亮
- `usage` → 新建 item，显示 input/output/total tokens
- `file_changed` → 新建 item，追加到 changed_files 列表
- `approval_required` → 新建 item + 创建 PendingApproval，触发审批弹窗。diff 内容带颜色高亮
- `approval_resolved` → 更新 PendingApproval 状态，关闭弹窗
- `subagent_started` / `subagent_finished` → 新建 item，更新 subagents dict
- `llm_waiting` / `llm_timeout` / `llm_retry` / `llm_error` → 各新建 item
- `agent_thinking` → 临时 item（is_transient=True），任务完成后自动移除
- `task_finished` → 内部事件，触发 UI 刷新但不追加 item

去噪音规则：

- `thinking_delta` 不逐条渲染
- `agent_thinking` 完成后移除
- 连续 `text_delta` 合并为一个条目
- heartbeat `llm_waiting` 更新同一个 status，不刷屏
- 同一个 tool 的 start/end 记录为两个独立 item（便于追踪耗时）

## UI 布局草图

当前第一版采用的单栏布局（header → 可滚动 timeline → 输入框），比早期设计更简洁，优先保证稳定性和可读性：

```text
+----------------------------------------------------------------------------+
| ╭──────────────────────────────┬──────────────────────────────╮             |
| │  ⬡ yoyoagent                 │  ⏺ Task running              │             |
| │  Model    deepseek-reasoner  │  Elapsed  12.3s               │             |
| │  Context  45,200 / 128,000   │  Tokens   8,421               │             |
| │  Dir      /home/proj         │  Goal      inspect TUI files  │             |
| ╰──────────────────────────────┴──────────────────────────────╯             |
|                                                                            |
| [latest] showing 1-12 of 12 events | PageUp/PageDown scroll | Ctrl+Enter...|
|                                                                            |
| You                                                                        |
|   Please inspect the TUI startup flow                                      |
|                                                                            |
| ⏺ Tool call read_file running                                              |
|   Read file                                                                |
|   agent/tui/app.py                                                         |
|                                                                            |
| ⏺ Tool returned read_file completed                                       |
|   Read file                                                                |
|   agent/tui/app.py                                                         |
|   elapsed 42ms                                                             |
|                                                                            |
| Yoyo                                                                       |
|   The TUI starts via run_tui() which creates YoyoTuiApp...                 |
|                                                                            |
| [usage] input=1024 output=256 total=1280                                   |
|                                                                            |
| ───────────────────────────────────────────────────────────────────────     |
| >  Ask yoyoagent... Ctrl+Enter send | Ctrl+Shift+C=Copy                   |
| ───────────────────────────────────────────────────────────────────────     |
+----------------------------------------------------------------------------+
```

审批 modal：

```text
+-------------------- Approval Required --------------------+
| ⚠️ Approve file edit                                       |
| Editing agent/tui/app.py                                   |
| (See timeline for full diff)                               |
|                                                            |
| [Y] Approve              [N] Deny                          |
+------------------------------------------------------------+
```

全屏历史查看器（Ctrl+H 打开）：

```text
+-----------------------------------------------------------+
| History  Esc/Ctrl+H back | Up older | Down newer | ...    |
|                                                            |
| You                                                        |
|   Please inspect the startup flow                          |
| ...                                                        |
+-----------------------------------------------------------+
```

> **注意：** 当前第一版是单栏布局。设计文档中早期的多面板布局（subagent panel、changed files panel、detail pane）可能在后续版本中回归，但目前所有信息都通过 timeline + header 面板 + todo 面板 + 历史查看器呈现。

## 输入模型

TUI 替代当前 `input()` 主循环。

建议：

- 底部输入框支持单行提交。
- `Ctrl+Enter` 或 `/paste` 支持多行输入。
- `Esc` 关闭 modal 或 detail。
- `Ctrl+C` 请求取消当前任务。
- `Ctrl+L` 清屏或清 timeline。
- `Tab` 在 timeline/detail/subagent 面板之间切换焦点。

运行约束：

- 同一 session 默认只允许一个 active agent task。
- 用户提交新输入时，如果当前任务还在跑，提示等待或取消。
- approval modal 打开时，输入框暂时不可提交普通任务。

## 审批模型

TUI 中审批不能使用 `input()`。

使用 adapter：

```text
Session.from_config(approval_callback=tui_approval_adapter.callback)
```

流程：

```text
ApprovalService
  -> callback(request)
    -> TuiApprovalAdapter creates PendingApproval
    -> TuiState shows ApprovalModal
    -> user presses Approve or Deny
    -> TuiApprovalAdapter.resolve(...)
    -> callback returns bool
```

结构化事件仍然保留：

- `approval_required`
- `approval_resolved`

这些事件用于 timeline 和审计。真正的等待由 adapter 的 Future 完成。

## 完整实施阶段

### Phase 1: TUI Skeleton ✅ **已完成**

目标：

- 新增 `agent/tui/*`
- `python main.py` 能启动空 TUI
- 能输入文本并调用 `Session.send()`
- 能把 `StreamEvent` 加到 timeline

验收：

- 默认入口进入 TUI。✅
- TUI 能跑一次简单任务。✅
- 退出 TUI 时能关闭 session 和后台任务。✅

### Phase 2: Timeline State ✅ **已完成**

目标：

- 完成 `TuiState`
- tool/subagent/approval/file events 能更新状态
- timeline 能显示 running/done/failed

验收：

- 工具调用不是原始刷屏，而是 timeline item。✅
- changed files 有追踪。✅

### Phase 3: Approval Modal ✅ **已完成**

目标：

- TUI approval adapter 可用
- approval modal 支持 approve/deny
- denied 后任务按现有逻辑停止

验收：

- 文件写入审批不再走 terminal input。✅
- 审批事件能出现在 timeline。✅

### Phase 4: Details and Diff Viewer 🟡 **部分完成**

目标：

- timeline item 可选中
- detail pane 显示 metadata/stdout/diff
- diff preview 有基本高亮

当前状态：

- diff 内容已通过 `colorize_diff_for_tui` 在内联 timeline 中带颜色高亮 ✅
- 审批弹窗提示 "See timeline for full diff" ✅
- HistoryScreen（Ctrl+H）支持全屏浏览历史 ✅
- 独立 detail pane / item 选中交互 ❌ 未实现

### Phase 5: Subagent Panel 🟡 **部分完成**

目标：

- subagent started/finished 显示为角色状态
- 多 subagent 并行时 UI 不乱
- parent/child session 可关联

当前状态：

- subagent 事件在 timeline 中渲染 ✅
- `subagents` dict 在 state 中维护 ✅
- 独立 subagent panel ❌ 未实现（信息在 timeline 中内联显示）

### Phase 6: Cancellation and Polish ✅ **已完成**

目标：

- 支持取消当前任务
- 处理 app 退出时正在运行的 task
- 支持历史滚动和快捷键
- 状态栏显示 model/session/token

验收：

- 长任务中断可靠（`Ctrl+C` 取消）。✅
- 退出不会留下悬挂任务（`on_unmount` → `runner.close()`）。✅
- 历史滚动：`PageUp/PageDown`、`Home/End`。✅
- `Ctrl+H` 全屏历史查看器。✅
- 状态栏显示 model、context 窗口使用率、session、workspace 路径。✅
- `Ctrl+Shift+C` 复制 timeline 到剪贴板。✅
- 完整的键盘快捷键体系。✅

## 风险与缓解

### 风险：TUI 阻塞 agent 执行

缓解：

- agent run 放在 background async task。
- TUI 只通过 queue/state 接事件。

### 风险：approval modal 和 agent callback 死锁

缓解：

- approval adapter 使用 Future。
- modal resolve 必须总是设置 Future。
- session cancel 时清理 pending approvals。

### 风险：事件太多导致 UI 卡顿

缓解：

- heartbeat 更新 active status，不追加 timeline。
- thinking delta 不逐条渲染。
- timeline 限制内存条目，旧条目可折叠或分页。

### 风险：入口切换后无法使用

缓解：

- 保持 `Session.send()` 和 agent core 不变。
- TUI 先复用当前 `StreamEvent` 和 approval callback 机制。
- 保留 `ConsoleStreamRenderer` 作为测试/debug renderer，但不作为用户-facing 旧方案。
- 入口切换前完成手动验收：启动、输入、审批、取消、退出。

### 风险：Textual 依赖引入体积

缓解：

- 作为可选功能引入。
- 后续可使用 extras，例如 `yoyoagent[tui]`。

## 测试计划

单元测试：

- `tests/test_tui_state.py`
- `tests/test_tui_approval.py`
- `tests/test_streaming_events.py`

集成测试：

- fake `Session` + fake events 驱动 TUI state。
- fake approval request 测试 approve/deny。
- fake long-running task 测试 cancellation。

手动验收：

- 启动 `python main.py`
- 输入简单读文件任务
- 触发写文件审批
- 运行测试命令
- 启动 subagent
- 取消长任务

## 不建议直接做的事

- 不要把 Textual import 到 `agent/runtime/*`。
- 不要让 tools 直接写 TUI state。
- 不要删除现有 console renderer。
- 不要让 Web/TUI 审批逻辑进入 `ApprovalService`。
- 不要在第一版重做 `Session.send()` 的核心语义。

## 结论

完整 TUI 对当前 agent core 的破坏不大，但会替换现有终端交互入口。

推荐用新增前端层的方式推进：

```text
main.py starts TUI
TUI consumes StreamEvent
Approval stays callback-based
Agent core stays UI-agnostic
```

这样未来可以同时支持：

- TUI
- Web UI
- event log replay

## 本次关键改动总结

第一版完整 TUI 主链路已经接入，重点先完成“默认入口切到 TUI”和“事件/审批/状态能够驱动 TUI”。

已完成：

- `main.py` 默认启动 TUI，不再保留旧 CLI 作为用户入口。
- `pyproject.toml` 新增 `textual` 依赖。
- 新增 `agent/tui/` 包：
  - `app.py`: Textual 应用入口、布局（header + timeline + 输入区）、审批弹窗（`ApprovalScreen`）、全屏历史查看器（`HistoryScreen`）
  - `runner.py`: `Session.send()` 与 TUI 状态桥接，支持 `submit_nowait`/`cancel_current_task`/自动补发 text_delta
  - `state.py`: timeline（含事件合并、transient item 清理）、subagent、审批、changed files、active_task 追踪、todo_manager 集成
  - `approval.py`: callback/Future 形式的审批适配层
  - `renderers.py`: 状态到面板文本的渲染辅助，含双栏 header、timeline、todo task plan、diff 颜色高亮
  - `styles.tcss`: TUI 暗色样式
- `agent/llm_retry.py` 的等待事件现在补充了 `title/detail/phase/status/elapsed_ms/metadata`，便于 TUI 展示等待中的上下文。
- `agent/runtime/tool_events.py` 的 bash 工具现在识别 draw.io 命令，给出专用 title/phase。
- `agent/runtime/approval_service.py` 的审批事件现在 `include_diff=True`，在 timeline 中直接展示完整 diff 内容。

测试已补充：

- `tests/test_tui_state.py` — 10 个测试，覆盖状态追踪、渲染输出、markup 转义
- `tests/test_tui_approval.py` — 2 个测试，覆盖 approval adapter 的 Future 流程
- `tests/test_tui_runner.py` — 3 个测试，覆盖异步行为、自动 text_delta、多轮对话
- `tests/test_streaming_events.py` — 补充 waiting 事件序列化断言
- `tests/test_main_input.py` — 补充 `main()` 函数测试

当前范围内没有改动：

- LangGraph 路由
- provider 协议
- tool 执行语义
- `ApprovalService` 的业务规则

当前已知限制：

- 单栏布局：subagent panel、changed files panel、detail pane 暂未作为独立面板实现，信息通过 timeline 内联展示。
- timeline 无 item 选中/聚焦交互，无法单独展开某个工具的完整 metadata。
- 审批 diff 在弹窗中仅提示 "See timeline for full diff"，用户需要回到 timeline 查看。
- `textual` 依赖需要预先安装（已在 `pyproject.toml` 中声明）。
- 对于极高频率的事件洪流（如大量 thinking_delta），虽然已通过合并策略缓解，但在极端场景下 UI 刷新仍可能产生延迟。
