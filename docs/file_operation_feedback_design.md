# 文件操作视觉反馈增强设计

## 背景

当前项目中，`apply_patch`、`write_file`、`edit_file` 等文件操作工具在用户端的展示偏简单。用户在等待时可能只看到工具调用开始和结束，缺少“正在操作文件”“是否真的改了文件”“改了多少行”等视觉反馈。

本设计讨论的“安全感”不是审批审计意义上的安全，而是用户感知层面的确定感：

> 用户需要在等待过程中看到 agent 正在操作文件，并在完成后看到确实改了哪些文件、增删了多少行。

因此本方案只增强 TUI timeline 中的文件操作视觉反馈，不改变现有工具行为、审批流程、自动审批策略或 Changed Files viewer。

## 目标

- 文件操作开始时，timeline 立即显示正在执行的文件操作。
- 等待期间用户能看到正在操作哪个文件或正在应用 patch。
- 文件操作完成后，timeline 显示操作结果摘要。
- 摘要包括文件数量、路径、增加行数、删除行数和耗时。
- 无实际变更和失败场景也要有明确反馈。
- 完整 diff 仍通过现有 `Ctrl+D Changed Files` 查看。
- 不影响审批时的文件 diff preview 功能。

## 非目标

本方案不做：

- 不重做审批流程。
- 不做审批审计系统。
- 不修改自动审批策略。
- 不做高风险降级审批。
- 不改变工具返回 diff 的格式。
- 不修改 `approval_required` 事件。
- 不修改 `metadata["diff_preview"]`。
- 不修改审批弹窗或审批面板。
- 不新增 UI 区域。
- 不做实时 diff 流。
- 不做文件操作百分比进度。

## 核心原则

```text
自动审批 ≠ 静默执行
```

但这里的重点不是审计，而是视觉反馈：

```text
让文件操作从“黑盒等待”变成“可见过程”。
```

## ASCII 设计图

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ YOYOAGENT code assistant ─────────────────────────────────────────────────── │
│ Session sess-1   Mode AUTO   Restored 42 messages                           │
│ Dir ~/project                                                                │
├──────────────────────────────────────────────────────────────────────────────┤
│ Timeline / Transcript                                      RichLog           │
│                                                                              │
│  You                                                                         │
│  帮我更新 UI 设计文档                                                        │
│                                                                              │
│  Yoyo                                                                        │
│  我会检查文档，然后补充文件操作反馈卡片设计。                                │
│                                                                              │
│  ◇ Exploring                                                                 │
│    read_file docs/full_tui_design.md                                         │
│                                                                              │
│  ✎ Applying patch...                                                         │
│    docs/full_tui_design.md                                                   │
│    ━━━━━━━············                                                       │
│                                                                              │
│  ✎ Edited 1 file                                      +36  −4   0.8s          │
│    docs/full_tui_design.md                                                   │
│    Preview                                                                   │
│      + Added file operation feedback card ASCII design                        │
│      + Added changed line summary examples                                   │
│      − Removed vague placeholder wording                                     │
│    Ctrl+D View changed files                                                 │
│                                                                              │
│  ＋ Created 1 file                                    +120 −0   0.3s          │
│    docs/message_token_manager_design.md                                      │
│    Ctrl+D View changed files                                                 │
│                                                                              │
│  ○ No file changes detected                           0.2s                   │
│    apply_patch completed, but patch produced no workspace diff                │
│                                                                              │
│  × Edit failed                                        0.1s                   │
│    apply_patch could not match context in docs/usage.md                       │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ >                                                                            │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ running · Applying patch to docs/full_tui_design.md · Ctrl+D changed files   │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 文件操作卡片状态

### 操作开始

```text
✎ Applying patch...
  docs/full_tui_design.md
  ━━━━━━━············
```

或：

```text
✎ Editing file...
  agent/tui/renderers.py
  ━━━━━━━············
```

或：

```text
＋ Creating file...
  docs/new_design.md
  ━━━━━━━············
```

### 操作成功

```text
✎ Edited 2 files                                      +34  −8   1.2s
  agent/tui/app.py
  agent/tui/renderers.py
  Ctrl+D View changed files
```

### 新建文件

```text
＋ Created 1 file                                     +120 −0   0.3s
  docs/message_token_manager_design.md
  Ctrl+D View changed files
```

### 无实际变更

```text
○ No file changes detected                            0.2s
  apply_patch completed, but workspace diff did not change
```

### 操作失败

```text
× Edit failed                                         0.1s
  apply_patch could not match context in docs/usage.md
```

## 展示信息

文件操作反馈卡片应尽量展示：

- 操作类型：edit / create / patch。
- 当前状态：running / completed / no changes / failed。
- 文件路径或文件数量。
- 增加行数。
- 删除行数。
- 耗时。
- `Ctrl+D View changed files` 详情入口。

## 数据来源

首版优先复用现有事件和数据：

- `tool_start`
- `tool_end`
- `tool_result`
- `file_changed`
- `files_changed_summary`
- `TimelineItem.file_paths`
- `TimelineItem.metadata`
- `TimelineItem.elapsed_ms`
- 工具返回中的 unified diff
- Changed Files viewer 已使用的 diff 统计逻辑

不要求首版新增独立审计模型。

## 建议 metadata

如果现有事件不足以准确渲染增删行数，可在后续阶段补充 metadata：

```python
{
    "operation_kind": "patch",      # patch | edit | create | delete
    "changed_files_count": 2,
    "changed_paths": ["README.md", "docs/usage.md"],
    "added_lines": 34,
    "removed_lines": 8,
    "has_changes": True,
}
```

这些 metadata 仅用于 UI 展示，不改变工具行为和审批逻辑。

## 与 Changed Files viewer 的关系

Timeline 只展示 L1 摘要：

```text
✎ Edited 2 files +34 −8
```

完整 diff 继续通过现有：

```text
Ctrl+D Changed Files
```

因此本方案不会替代 Changed Files viewer，也不在 timeline 中展示完整 diff。

## 与审批 diff 的关系

审批 diff 链路保持不变：

```text
tools/apply_patch.py / write_file
  -> diff_preview
  -> approval_required
  -> TUI approval 展示 diff
```

文件操作反馈卡片只影响 timeline 视觉展示，不改变 diff 的生成、传递或审批 UI。

实施时必须保持以下边界：

- 不改工具返回 diff 格式。
- 不改 `approval_required` 事件结构。
- 不改 `metadata["diff_preview"]`。
- 不改审批弹窗或审批面板。
- 不拦截或隐藏审批事件。
- 只对 `tool_start`、`tool_end`、`tool_result`、`files_changed_summary`、`file_changed` 做视觉增强。

## 推荐修改范围

### 最小必改

```text
agent/tui/renderers.py
tests/test_tui_state.py
```

`agent/tui/renderers.py`：

- 增强文件写入类工具在 timeline 中的渲染。
- 对 `apply_patch`、`write_file`、`edit_file` 输出文件操作反馈卡片。
- 显示运行中、成功、无变更、失败等状态。

`tests/test_tui_state.py`：

- 增加 timeline 渲染测试。
- 覆盖文件操作运行中、成功、无变更、失败等状态。

### 视情况补充

```text
agent/tui/runner.py
tests/test_tui_runner.py
```

仅当现有 timeline item 中缺少准确增删行统计时，再在 runner 中补充 metadata。

### 不建议修改

```text
tools/apply_patch.py
tools/write_file.py
tools/edit_file.py
agent/tui/app.py
agent/approval.py
agent/tui/approval.py
```

原因：本方案只增强 timeline 视觉反馈，不改变工具、审批、自动模式或 UI 结构。

## 推荐实施阶段

### Phase 1：轻量 UI 增强

只增强 TUI 对已有事件的渲染：

- 写工具 `tool_start` 显示：
  - `Applying patch...`
  - `Editing file...`
  - `Creating file...`
- 写工具完成后显示：
  - `Edited N files +X −Y`
  - `Created 1 file +N −0`
  - `No file changes detected`
  - `Edit failed`
- timeline 显示：
  - `Ctrl+D View changed files`

### Phase 2：补充 metadata

如果统计不够准确，再补充：

- `changed_files_count`
- `changed_paths`
- `added_lines`
- `removed_lines`
- `has_changes`
- `operation_kind`

### Phase 3：微交互

可选增强：

- 运行中 pulse。
- 完成瞬间高亮。
- 多文件摘要折叠。
- 大 diff 截断提示。

## 测试建议

### 渲染测试

覆盖：

- `apply_patch` 启动时显示 `Applying patch`。
- `edit_file` 启动时显示 `Editing file`。
- `write_file` 启动时显示 `Creating file`。
- 完成后显示 `+N −M`。
- 无变更显示 `No file changes detected`。
- 失败显示 `Edit failed`。
- 显示 `Ctrl+D View changed files`。

### 审批 diff 保护测试

覆盖：

- `approval_required` 带 `diff_preview` 时仍保留审批 diff。
- 文件操作反馈卡片不吞掉 `diff_preview`。
- Changed Files viewer 仍能解析完整 diff。
- 自动模式下 timeline 有反馈，`Ctrl+D` 仍能查看完整 diff。

## 风险与边界

### UI 噪音过多

风险：timeline 中连续文件操作过多可能变吵。

缓解：多文件操作合并为一张卡片，完整 diff 放在 Changed Files viewer。

### 增删行统计不准确

风险：只从工具结果解析 diff 时，某些情况可能拿不到准确统计。

缓解：首版可以显示路径和状态；后续通过 runner metadata 补准确统计。

### 影响审批 diff

风险：如果误改审批事件或 diff_preview，会影响审批体验。

缓解：实现边界明确为只改 timeline 渲染，不改审批链路。

## 推荐结论

首版建议只实现文件操作反馈卡片：

```text
✎ Applying patch...
↓
✎ Edited 2 files  +34 −8  1.2s
Ctrl+D View changed files
```

这样可以在不改变现有工具、审批和 Changed Files viewer 的前提下，显著提升用户等待期间的确定感。
