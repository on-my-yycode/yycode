# yoyoagent TUI 流程分析

## 一、整体架构概览

TUI 基于 [Textual](https://textual.textualize.io/) 框架构建，核心模块位于 `agent/tui/` 目录：

```
agent/tui/
├── __init__.py    # 公开导出
├── app.py         # Textual App 主入口 + 布局定义 + 键盘绑定 + 审批/历史弹窗
├── state.py       # 状态管理（TuiState / TimelineItem / PendingApproval / SubagentStatus）
├── renderers.py   # 渲染函数（顶部状态栏 / 时间线 / 审批文本 / diff 着色）
├── runner.py      # 异步桥接层（AgentTuiRunner），连接 Session 和 TuiState
├── approval.py    # 审批适配器（TuiApprovalAdapter），桥接运行时审批与 TUI 用户决策
└── styles.tcss    # Textual CSS 样式文件
```

## 二、启动流程

### 2.1 入口链

```
main.py: main()
  └─> agent/tui/app.py: run_tui(args)
        └─> YoyoTuiApp(args).run()
```

### 2.2 App 初始化

`YoyoTuiApp.__init__` 中创建:
- `self.runner = AgentTuiRunner(args, on_state_change=self._on_stream_event)` — 异步桥接器
- `self._session_ready = False` — 标记 session 未就绪
- `self._last_timeline_content = ""` — 用于去重刷新

### 2.3 UI 布局构建 (compose)

```
┌─────────────────────────────────────────────────┐
│  #top-panel (Static, height=9)                   │  ← 顶部状态面板
│  ┌──────────────────────┬─────────────────────┐  │
│  │ ⬡ yoyoagent          │ ● Task running      │  │
│  │ Model: claude-xxx    │ Elapsed: 3.2s       │  │
│  │ Context: 45k/128k    │ Tokens: 12,345      │  │
│  │ Dir: /path/to/proj   │ Goal: fix bug       │  │
│  └──────────────────────┴─────────────────────┘  │
├─────────────────────────────────────────────────┤
│  #timeline-panel (RichLog, height=1fr)           │  ← 中间时间线面板（可滚动）
│  ┌─────────────────────────────────────────────┐  │
│  │ [latest] showing 1-42 of 42 events | ...    │  │
│  │                                              │  │
│  │ 📋 Task Plan                                 │  │
│  │   ● 1 探索代码结构                            │  │
│  │                                              │  │
│  │ You                                          │  │
│  │   帮我修复这个 bug                             │  │
│  │                                              │  │
│  │ Yoyo                                         │  │
│  │   好的，让我先检查...                           │  │
│  │                                              │  │
│  │ ⏺ Tool call read_file                       │  │
│  │   Reading file                               │  │
│  │   /path/to/file.py                           │  │
│  │                                              │  │
│  │ ⏺ Tool returned read_file                   │  │
│  │   Tool finished                              │  │
│  │   elapsed 234ms                              │  │
│  └─────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────┤
│  #input-shell (height=7)                         │  ← 底部输入区
│  ─────────────────────────────────────────────── │  ← #input-top-rule
│  > [TextArea: 用户输入...          ]             │  ← #input-row
│  ─────────────────────────────────────────────── │  ← #input-bottom-rule
└─────────────────────────────────────────────────┘
```

布局层次：
```
Screen
└── #root-layout (Vertical)
    ├── #top-panel (Static)
    ├── #timeline-panel (RichLog)
    └── #input-shell (Container)
        ├── #input-top-rule (Static)
        ├── #input-row (Horizontal)
        │   ├── #input-prompt (Static: ">")
        │   └── #prompt-input (TextArea)
        └── #input-bottom-rule (Static)
```

### 2.4 会话初始化 (on_mount → _initialize_session)

```
on_mount()
  ├── _refresh_all()                          # 首次渲染（显示 "Starting..."）
  ├── TextArea.disabled = True                # 禁用输入
  └── run_worker(_initialize_session())       # 异步初始化

_initialize_session()
  └── await self.runner.start()
        ├── 创建 Session (含 provider, workdir, skills)
        ├── session.stream_callback = runner.handle_stream_event
        └── state.set_startup_info(...)       # 填入 session_id, model, skills 等
  └── _session_ready = True
  ├── TextArea.disabled = False               # 启用输入
  ├── TextArea.placeholder = "Ask yoyoagent..."
  ├── TextArea.focus()                        # 聚焦输入框
  └── _refresh_all()                          # 刷新显示
```

## 三、用户输入流程

### 3.1 键盘绑定

| 快捷键 | 动作 | 说明 |
|--------|------|------|
| `Ctrl+Enter` / `Ctrl+J` | `submit_prompt` | 提交输入 |
| `Ctrl+C` | `cancel_task` | 取消当前任务 |
| `Ctrl+Shift+C` | `copy_timeline` | 复制时间线内容 |
| `Ctrl+H` | `open_history` | 打开历史浏览弹窗 |
| `Ctrl+Q` | `quit` | 退出 |
| `PageUp/Down` | `timeline_page_up/down` | 滚动时间线 |
| `Home/End` | `timeline_home/end` | 跳到时间线顶部/底部 |
| `Esc` | `focus_input` | 聚焦输入框 |

### 3.2 提交输入流程

```
用户在 TextArea 输入文本 → Ctrl+Enter
  └── action_submit_prompt()
        ├── 检查 _session_ready（未就绪则提示 warning）
        ├── 获取文本，空则返回
        ├── 检查 "q"/"exit" → 退出
        ├── input_widget.load_text("")          # 清空输入框
        └── await self.runner.submit_nowait(text)
              ├── state.add_user_input(session_id, text)
              │     ├── end_active_task()       # 结束上一个任务
              │     ├── 创建 TimelineItem(event_type="user_message", title="You")
              │     ├── timeline.append(item)
              │     └── active_task = {...}     # 开始跟踪新任务
              ├── on_state_change(user_message event) → 刷新 UI
              ├── state.apply_event(agent_thinking event)  # 临时状态项
              ├── on_state_change(agent_thinking event)
              └── asyncio.create_task(_send_current(text))
                    └── await self.session.send(text)
                          └── 执行 agent graph，触发各种 stream events
                    └── finally:
                          ├── _remove_transient_items()    # 清除临时项
                          ├── end_active_task()            # 结束任务跟踪
                          └── on_state_change(task_finished)
```

## 四、事件流与状态更新

### 4.1 StreamEvent 类型

`StreamEvent` (定义在 `agent/streaming.py`) 是核心数据结构：

```python
@dataclass(frozen=True)
class StreamEvent:
    source: str              # "main" / "subagent" / "user"
    session_id: str
    event_type: str          # 见下表
    content: str
    role: str | None         # subagent 的 role
    title: str | None
    detail: str | None
    phase: str | None        # planning / executing / responding
    status: str | None       # running / completed / failed
    tool_name: str | None
    file_paths: list[str] | None
    elapsed_ms: int | None
    usage: dict[str, int] | None
    metadata: dict | None
```

关键事件类型：

| event_type | 触发时机 | 渲染行为 |
|---|---|---|
| `user_message` | 用户提交输入 | 显示 "You" + 用户文本 |
| `agent_thinking` | 任务开始时 | 临时项，任务完成时清除 |
| `thinking_start` | LLM 开始思考 | 显示 "Thinking..." |
| `thinking_delta` | 思考内容增量 | 合并到 thinking_start（不单独显示） |
| `thinking_end` | 思考结束 | 显示 "[done]" |
| `text_delta` | AI 回复文本增量 | 合并显示，title="Yoyo" |
| `tool_start` | 工具调用开始 | 显示 "⏺ Tool call {tool_name}" + 参数 |
| `tool_end` | 工具调用结束 | 显示 "⏺ Tool returned {tool_name}" + 耗时 |
| `tool_result` | 工具返回结果 | 显示着色 diff |
| `usage` | Token 使用更新 | 显示 "[usage] input=... output=..." |
| `llm_waiting` | 等待模型响应 | 显示 "[waiting] ..." |
| `llm_timeout` | 模型超时 | 黄色 "[timeout]" |
| `llm_retry` | 模型重试 | 蓝色 "[retry]" |
| `llm_error` | 模型错误 | 红色 "[error]" |
| `context_compressed` | 上下文压缩 | 显示 "[context] ..." |
| `file_changed` | 文件变更 | 显示 "+ modified {files}" |
| `approval_required` | 需要审批 | 触发弹窗 ApprovalScreen |
| `approval_resolved` | 审批已解决 | 更新审批状态 |
| `subagent_started` | 子代理启动 | 跟踪 subagent 状态 |
| `subagent_finished` | 子代理完成 | 更新 subagent 状态 |

### 4.2 事件回调链

```
Agent Graph 执行过程中产生事件
  └── session.stream_callback(event)
        = runner.handle_stream_event(event)
              ├── state.apply_event(event)      # 更新 TuiState
              │     ├── _update_active_task()   # 更新任务状态
              │     ├── thinking_start→thinking_end 自动配对
              │     ├── _remove_transient_items()     # 移除非临时的临时项
              │     ├── text_delta/thinking_delta 合并处理
              │     ├── _update_phase/status_line/usage/files/approvals/subagents
              │     └── timeline.append(item)
              └── on_state_change(event)
                    = app._on_stream_event(event)
                          └── call_after_refresh(_refresh_all)
```

### 4.3 TuiState 核心状态

```python
class TuiState:
    timeline: list[TimelineItem]        # 事件时间线 (最多 500 条)
    pending_approvals: dict[str, PendingApproval]  # 待审批项
    subagents: dict[str, SubagentStatus]          # 子代理状态
    changed_files: list[str]            # 已变更文件列表
    active_phase: str                   # 当前阶段
    status_line: str                    # 状态行文字
    model_name / session_id / workspace_path
    latest_usage: dict[str, int]        # 最新 token 统计
    todo_manager: TodoManager | None    # 任务计划管理器
    active_task: dict                   # 当前运行任务跟踪
```

## 五、渲染流程

### 5.1 刷新触发

每次事件到达后都会触发 `_refresh_all()`：

```python
def _refresh_all(self):
    # 1. 顶部状态面板
    self.query_one("#top-panel").update(render_status_text(state))

    # 2. 时间线面板（内容变化时才重写，避免闪烁）
    timeline_content = render_timeline_lines(state)
    if timeline_content != self._last_timeline_content:
        timeline_panel.clear()
        timeline_panel.write(timeline_content)
        scroll_to_end()

    # 3. 输入区自适应分割线
    _refresh_input_rules()

    # 4. 检测待审批 → 弹出 ApprovalScreen
    _maybe_show_approval_prompt()
```

### 5.2 顶部状态面板 (render_status_text)

双栏布局：

```
╭───────────────────────┬─────────────────────────╮
│ ⬡ yoyoagent           │ ● Task running          │
│ Model    claude-xxx    │ Elapsed  3.2s           │
│ Context  45k/128k(35%)│ Tokens   12,345         │
│ Dir      /path/to/proj │ Goal     帮我修复这个bug │
╰───────────────────────┴─────────────────────────╯
```

- 左侧：Logo、模型名、上下文窗口使用率、工作目录
- 右侧：任务运行状态（运行时）/ Ready 状态（空闲时）

### 5.3 时间线面板 (render_timeline_lines / render_main_timeline_lines)

主时间线（`header_mode="main"`）渲染内容包含：

1. **Todo 区域** （`_render_todo_section`）
   - 任务列表（pending ○ / in_progress ● / completed ✓）
   - 每个任务显示 id、描述、原因、优先级、备注
   - 任务记忆（memory）：目标、约束、文件、决策、测试结果、风险、下一步

2. **事件列表**
   - 每条事件根据 event_type 渲染为带颜色的文本：
     - 用户消息：`[bold white]You[/]\n  [gray]content[/]`
     - AI 回复：`[bold purple]Yoyo[/]\n  [gray]content[/]`
     - 工具调用：蓝色 `⏺ Tool call tool_name`
     - 工具返回：绿色 `⏺ Tool returned tool_name`
     - 文件变更：`+ modified {files}`
     - 审批：黄色 `? Approval required`
     - 错误：红色 `[error]`
     - 等待/超时/重试：对应颜色 `[waiting]` / `[timeout]` / `[retry]`

3. **Diff 着色** （`colorize_diff_for_tui`）
   - `+` 行 → 绿色 `#8fd6a3`
   - `-` 行 → 红色 `#ff8f8f`
   - `@@` 行 → 蓝色 `#61afef`
   - `diff --git` / `index` / `---` / `+++` → 灰色 `#7f8794`

### 5.4 历史浏览弹窗 (HistoryScreen)

按 `Ctrl+H` 打开，支持键盘翻页：
- `↑/↓` 逐条滚动
- `PageUp/PageDown` 跳页
- `Home/End` 跳到最早/最新

## 六、审批流程

```
agent 执行需审批的操作（如 apply_patch）
  └── approval_callback(request)
        = TuiApprovalAdapter.callback(request)
              ├── 创建 asyncio.Future
              └── await future (阻塞等待用户决策)

同时 StreamEvent("approval_required") 经由 state.apply_event 触发
  └── state.pending_approvals[approval_id] = PendingApproval(...)

UI 刷新 _maybe_show_approval_prompt()
  ├── 检测 state.next_pending_approval()
  └── push_screen(ApprovalScreen(approval), callback=handle_result)

用户交互：
  ┌──────────────────────────────────┐
  │ ⚠️ Apply Patch                  │
  │ Edit: agent/tui/app.py           │
  │ (See timeline for full diff)     │
  │                                  │
  │  [Y] Approve    [N] Deny        │
  └──────────────────────────────────┘
  Y / Enter → dismiss(True)
  N / Esc   → dismiss(False)

handle_result(approved):
  └── runner.resolve_approval(approval_id, approved)
        = TuiApprovalAdapter.resolve(id, approved)
              └── future.set_result(approved)  # 解除阻塞
```

## 七、会话生命周期

```
App.__init__
  └── App.on_mount
        └── _initialize_session
              └── runner.start() → Session 创建，回调绑定
                    ↓
              [session_ready = True, 输入框启用]
                    ↓
              用户提交 → submit_nowait → session.send()
                    ↓
              事件流 → handle_stream_event → apply_event → refresh_all
                    ↓
              用户退出 (Ctrl+Q)
                    ↓
              App.on_unmount → runner.close()
                                ├── cancel_current_task()
                                └── session.close()
```

## 八、关键设计要点

1. **异步非阻塞**：`submit_nowait` 将请求以 `asyncio.create_task` 后台执行，UI 不卡顿
2. **事件合并**：`text_delta` 和 `thinking_delta` 合并到前一条，避免时间线爆炸
3. **临时状态清理**：`agent_thinking` 标记 `is_transient=True`，任务完成时清除
4. **Diff 安全转义**：所有用户内容通过 `_safe_text` 将 `[` 转为 `\[`，防止 Rich 标记注入
5. **内容去重**：`_last_timeline_content` 只在内容变化时重写 RichLog，减少闪烁
6. **审批异步桥接**：`TuiApprovalAdapter` 用 `asyncio.Future` 在 TUI 用户决策和运行时审批回调之间建立同步点
7. **多会话支持**：TimelineItem 关联 `session_id`，支持子代理在独立 session 中运行

## 九、文件清单

| 文件 | 职责 |
|------|------|
| `agent/tui/app.py` | Textual App 类、布局构建、键盘绑定、审批/历史弹窗 |
| `agent/tui/state.py` | TuiState 状态管理、TimelineItem 数据结构、事件应用 |
| `agent/tui/renderers.py` | 状态面板渲染、时间线渲染、Diff 着色 |
| `agent/tui/runner.py` | 异步桥接，连接 Session 和 TUI 状态 |
| `agent/tui/approval.py` | 审批适配器，用 Future 桥接运行时和 UI |
| `agent/tui/styles.tcss` | Textual CSS 样式定义 |
| `agent/streaming.py` | StreamEvent 定义、ConsoleStreamRenderer |
| `agent/session.py` | Session 类，提供 send() 和 stream_callback |
| `main.py` | 入口点，启动 TUI |

---

> 作者：张磊
