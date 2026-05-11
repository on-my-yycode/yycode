# 实现对照与待办清单

更新时间：2026-05-11

## 目的

本文档用于对照当前代码实现与 `docs/code_agent_roadmap.md`、相关设计文档，整理后续还需要开发、校准和验证的事项。

范围包括：

- 已经实现但路线图状态尚未同步的能力。
- 路线图已规划但代码仍缺失的能力。
- 当前实现可用但体验、稳定性或测试覆盖还需要收口的能力。
- 建议下一阶段优先级和验收标准。

## 当前实现对照

### 已完成或基本完成

以下能力已在当前代码中具备，路线图中应标记为已完成或首版已完成。

| 模块 | 当前状态 | 依据 |
| --- | --- | --- |
| 工具 metadata 与调度 | 已完成 | `agent/runtime/tool_registry.py`、`tool_scheduler.py`、`tool_executor.py` |
| workspace/git 保护 | 已完成 | `workspace_state`、`git_diff`、workflow guard |
| apply_patch / write 审批 | 已完成 v1 | `agent/approval.py`、`agent/runtime/approval_service.py` |
| verify 工具 | 已完成基础版 | `tools/verify.py` |
| 代码理解工具 | 已完成基础版 | `list_files`、`read_file`、`read_many_files`、`grep`、`git_show` |
| 结构化 timeline | 已完成并持续优化 | `agent/tui/renderers.py`、`agent/tui/state.py` |
| Task State 历史治理 | 已完成基础版 | `Session._prune_todo_artifacts()` |
| workspace / workdir 统一 | 主流程已完成 | `RuntimeToolRegistry` 注入 `workdir`，CLI 支持 `yoyoagent [WORKDIR]` |
| Session 持久化 | 首版已完成 | `agent/session_store.py`、CLI `-r/-s/-x/-t` |
| skills 应用目录收口 | 已完成基础版 | `Session._resolve_skill_dirs()` 默认 `{app_root}/skills` |
| subagent 显式 skill 委派 | 首版已完成 | `subagent(..., skills=[...])`、`@role /skill` prompt 约定 |
| TUI 输入补全 | 已完成基础版 | `/skill`、正文中 `/skill`、`@role`、`:` command 补全 |
| Message Token Manager | 首版已实现 | `agent/message_context_manager.py`、TUI `Ctrl+M` 面板、手动压缩 |
| LSP 语义导航 MVP | Python-only 首版已实现 | `agent/lsp/*`、`tools/lsp_*`、`tests/test_lsp_tools.py` |
| TUI command 系统 | 首版已实现 | `agent/tui/commands/*`，已有 `:help`、`:clear` |
| Markdown timeline 性能优化 | A+B 已完成 | item render cache、运行中轻量 Markdown、结束后完整渲染 |
| 启动参数帮助 | 已完成基础版 | `main.py::build_arg_parser()` 包含参数和 Environment |

### 部分实现，需要继续收口

| 模块 | 当前状态 | 主要缺口 |
| --- | --- | --- |
| Message Token Manager | 首版可用 | 需要压缩确认 UI 更细、undo/备份、策略配置、更多大 session 回归 |
| LSP | Python-only 可用 | 语言识别/多语言 registry 未实现；diagnostics 为 unsupported；workspace/symbol 依赖 server 支持 |
| Session 持久化 | 首版可用 | 不可写目录 fallback、损坏文件恢复、并发写、恢复后预压缩未完成 |
| workspace / workdir | 主链路可用 | 符号链接、绝对路径、嵌套 workspace、直接工具调用边界测试仍需补 |
| Timeline 性能 | 已降负载 | 尚未做真正虚拟化；RichLog 全量 clear/write 仍可能成为瓶颈 |
| 工具输出上下文治理 | 已压缩部分输出 | 中等大小 read/grep 输出仍可能占 1k-3k tokens；旧 sessions 需要清理/迁移策略 |
| 用户意图反馈 | prompt 已约束 | 需要实际观察模型是否稳定在首个工具前输出意图，必要时做运行时 guard |
| TUI command | 首版可用 | 命令数量少，缺少 `:sessions`、`:resume`、`:messages` 等统一入口 |

### 尚未实现

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 长任务摘要记忆 | 未实现完整版本 | 还没有对旧 Human/AI 对话做稳定摘要压缩 |
| Task Graph / DAG 调度 | 未实现 | 设计见 `docs/task_graph_dag_design.md` |
| 本地 evals | 未实现 | 缺少 `evals/` 任务集和自动评分脚本 |
| 多语言 LSP | 未实现 | 当前 `LspManager` 只接受 `.py`，languageId 固定 `python` |
| LSP 启动状态提示 | 未实现 | TUI 启动时未显示 `pyright/pylsp/unavailable` |
| LSP 生命周期清理 | 未完全收口 | 需要在 Session/TUI 退出时统一 shutdown cached managers |
| 自动恢复最近 session | 未实现 | `--resume-latest` 仍是后续增强 |

## 路线图需要更新的地方

`docs/code_agent_roadmap.md` 当前整体方向仍正确，但以下状态已落后：

1. `Message Token Manager` 不应再写“已完成设计，尚未实现”。当前应改为“首版已实现，待增强”。
2. LSP 不应再只作为“推荐下一步”。当前应改为“Python-only MVP 已实现，待多语言和稳定性增强”。
3. TUI command 系统需要新增到当前基础与后续路线。
4. Markdown 渲染性能优化需要记录到 TUI timeline 已完成项。
5. 推荐下一步顺序需要从“workspace -> Message Token Manager -> LSP”更新为“LSP/MTM 收口 -> timeline 虚拟化 -> session 容错 -> evals/DAG”。

## 下一阶段建议优先级

### P0：先收口当前已实现但未稳定的能力

#### 1. LSP 可用性与可见性收口

目标：

- 让用户和模型都能明确知道当前 LSP 是否可用、用了哪个 server。
- 避免 LSP 工具偶发卡住或遗留进程。
- 把 Python-only MVP 的边界表达清楚。

待办：

- [ ] 增加轻量 LSP server 检测函数，不启动进程，只检测 `pyright-langserver` / `pylsp`。
- [ ] TUI 顶部或启动 timeline 显示：`LSP Python: pyright-langserver` / `pylsp` / `unavailable`。
- [ ] 在 `:help` 或 docs/usage 中补充 LSP 状态说明。
- [ ] TUI/Session 关闭时调用 `shutdown_lsp_managers()`。
- [ ] 给 `workspace/symbol Method Not Found` 写明确文档：fallback 到 `grep/read_file` 属于正常降级。
- [ ] 增加真实环境 smoke test 文档，不要求 CI 安装 language server。

验收：

- 启动后用户能看到 LSP 状态。
- 调用 `lsp_document_symbols` 后 timeline 出现 `Semantic Navigation`。
- 退出 TUI 后无遗留 `pylsp` / `pyright-langserver` 进程。

#### 2. Message Token Manager 收口

目标：

- 让 `Ctrl+M` 成为稳定的上下文治理入口。
- 防止压缩破坏 tool call 链路。

待办：

- [ ] 增加压缩前确认视图，展示 affected indexes、预计节省和风险。
- [ ] 压缩后 timeline 输出明确摘要：压缩了几条消息、节省估算 tokens。
- [ ] 保存 session 后刷新 header context usage。
- [ ] 增加大 session fixtures，覆盖 read/grep/write/verify/tool policy 元数据。
- [ ] 增加“无可压缩项”的空状态。
- [ ] 评估是否需要压缩后备份，至少在 session JSON 中保留 `original_chars` / `estimated_original_tokens`。

验收：

- `Ctrl+M` 可查看 system/tools/messages 分布。
- 选择压缩后消息顺序、`tool_call_id`、`name` 保持不变。
- 压缩后恢复 session 不报 provider payload 错。

#### 3. 当前文档同步

目标：

- 让路线图与当前实现一致，避免后续重复设计已完成能力。

待办：

- [ ] 更新 `docs/code_agent_roadmap.md` 的当前基础、MVP 状态和推荐下一步。
- [ ] 更新 `docs/lsp_integration_design.md`，加入当前 Python-only 实现状态与已知限制。
- [ ] 更新 `docs/message_token_manager_design.md`，加入首版实现状态。
- [ ] 更新 `docs/project_structure.md`，补充 `agent/lsp/`、`agent/tui/commands/`。
- [ ] 更新 `docs/usage.md`，补充 `Ctrl+M`、`:help`、`:clear`、LSP 可见性。

验收：

- 新读者能从 docs 判断哪些能力已经可用，哪些还在计划中。

### P1：提升长任务稳定性和性能

#### 4. Timeline 虚拟化 / 增量渲染

目标：

- 解决长任务运行时 TUI 卡顿和 RichLog 长内容压力。

当前已完成：

- item 渲染缓存。
- 运行中轻量 Markdown。
- 任务结束后完整 Markdown。

后续待办：

- [ ] 避免 `RichLog.clear()` + `write(full timeline)` 全量重写，改成增量 append/update。
- [ ] 只渲染可见窗口，先切片 timeline item，再渲染 item。
- [ ] 对超长 code fence 设置高亮行数上限。
- [ ] 对动态动画 item 与静态历史 item 分离刷新。
- [ ] 增加性能基准测试：500/1000 timeline items、长 markdown、长 diff。

验收：

- 运行中无新 token 时 UI 不应持续重渲染整条 timeline。
- 1000 条 timeline item 下滚动和输入仍可响应。

#### 5. 工具输出上下文治理继续收紧

目标：

- 降低 sessions 中中等大小工具输出对后续上下文的污染。

待办：

- [ ] 将 read/search 类压缩阈值从统一 12k chars 改为 per-tool 阈值。
- [ ] 建议阈值：`grep=4k`、`read_many_files=5k`、`read_file=6k-8k`、`git_show=6k`。
- [ ] 对 verify 成功输出做 marker/summary 策略。
- [ ] 为旧 session 文件提供可选 cleanup/migration 命令或文档。
- [ ] Message Token Manager 中显示 `context_policy` 和是否可进一步压缩。

验收：

- 新产生 session 中不再频繁出现 2k+ token 的普通 read/grep ToolMessage。
- 用户可通过 `Ctrl+M` 找到并压缩历史大工具输出。

#### 6. Session 持久化容错

目标：

- 让发行版本在不可写 app_root、损坏 session、并发写场景下表现可控。

待办：

- [ ] `app_root/sessions` 不可写时 fallback 到用户数据目录，例如 `~/.yoyoagent/sessions`。
- [ ] session JSON 损坏时给出清晰错误，不崩溃。
- [ ] 列表命令忽略损坏文件并提示 warning。
- [ ] 增加原子写入：临时文件 + rename。
- [ ] 多进程同 session id 写入时至少避免半写文件。
- [ ] 恢复后如 context pressure high，提示用户打开 `Ctrl+M` 或自动预压缩旧 tool outputs。

验收：

- 损坏 session 不影响新会话启动。
- 不可写目录下仍能运行或明确提示 fallback 路径。

### P2：扩展代码理解和任务编排能力

#### 7. 多语言 LSP 设计与实现

目标：

- 从 Python-only LSP 演进为按语言/文件类型选择 server。

待办：

- [ ] 新增 language registry：extension -> languageId -> server command candidates。
- [ ] 支持 TypeScript/JavaScript：`typescript-language-server --stdio`。
- [ ] 支持 Go：`gopls`。
- [ ] 支持 Java：`jdtls` 的启动策略需要单独设计。
- [ ] 支持 C#：`csharp-ls` 或 Roslyn-based server。
- [ ] `did_open` 使用真实 languageId。
- [ ] LSP root 可按项目标记推导，但不能越过 runtime workdir。
- [ ] 工具错误中显示当前语言和缺失 server 安装建议。

验收：

- `.py/.ts/.js/.go` 至少能各自走对应 languageId。
- server 不存在时快速返回 unavailable，不阻塞任务。

#### 8. 长任务摘要记忆

目标：

- 长任务超过多轮后，稳定保留关键决策，减少旧消息污染。

待办：

- [ ] 基于 Task State memory 生成任务级 summary block。
- [ ] 压缩旧 Human/AI 对话时保留 user_goal、constraints、decisions、files_modified、test_results、open_risks。
- [ ] 防止 summary 与 todo 结果重复进入上下文。
- [ ] 任务完成后清理 todo artifacts，但保留最终任务摘要。
- [ ] 增加恢复 session 后摘要仍可用的测试。

验收：

- 长任务上下文压缩后，agent 仍能正确说出已做、未做、风险和验证结果。

#### 9. Task Graph / DAG 调度

目标：

- 支持复杂任务拆成可并行/串行依赖图，而不是仅靠线性 todo。

待办：

- [ ] 复核 `docs/task_graph_dag_design.md`，确认是否仍符合当前 runtime。
- [ ] 设计 task graph tool 的权限和审批边界。
- [ ] 首版只做只读/规划型 DAG，暂不自动执行写入。
- [ ] 与 subagent role 并发策略结合。
- [ ] TUI timeline 增加 DAG 状态视图。

验收：

- agent 能把复杂任务拆成依赖图，并并发执行安全的 read-only 子任务。

#### 10. 本地 evals

目标：

- 用任务集判断 yoyoagent 是否真的变强。

待办：

- [ ] 新建 `evals/` 目录结构。
- [ ] 添加 5 类任务：fix bug、add feature、refactor、add tests、security review。
- [ ] 每个任务提供 `prompt.md`、`setup.sh`、`checks.sh`。
- [ ] 记录是否通过测试、是否满足目标、改动范围是否合理。
- [ ] 增加人工复核报告模板。

验收：

- 一条命令可跑基础 eval suite。
- 每次核心能力改动后能比较结果。

## 建议近期执行顺序

建议按以下顺序推进：

```text
1. 更新主路线图和相关设计文档状态
2. LSP 启动状态提示 + 生命周期 cleanup
3. Message Token Manager 压缩确认和大 session 回归
4. 工具输出压缩阈值 per-tool 收紧
5. Timeline 增量渲染 / 可见窗口渲染
6. Session 持久化容错和 fallback
7. 多语言 LSP registry
8. 长任务摘要记忆
9. evals
10. Task Graph / DAG
```

原因：

- 1-4 都是在收口当前已经实现的能力，风险低、收益直接。
- 5 解决用户已经观察到的长任务 TUI 卡顿问题。
- 6 是发行版本稳定性要求。
- 7-10 是能力扩展，适合在基础稳定后推进。

## 当前风险清单

- 当前工作区有较多未提交变更，后续提交前需要按功能拆分或整体确认。
- LSP 当前只支持 Python，且不同 server 能力差异明显；不能把 `no_results` 等同于代码没有问题。
- Message Token Manager 的逐条 token 仍是估算，UI 和文档必须持续强调 estimated。
- Timeline 已有缓存和轻量 Markdown，但 RichLog 全量写仍可能成为性能瓶颈。
- Session messages 持久化会保存敏感上下文，需要在发行文档中提醒用户。

## 文档更新待办

- [ ] `docs/code_agent_roadmap.md`：同步当前实现状态和推荐下一步。
- [ ] `docs/lsp_integration_design.md`：补当前实现状态、限制、启动提示计划。
- [ ] `docs/message_token_manager_design.md`：标记首版已实现，拆出增强项。
- [ ] `docs/session_persistence_design.md`：补 fallback、损坏文件、并发写待办。
- [ ] `docs/structured_event_timeline_design.md`：补 timeline cache、轻量 markdown、未来虚拟化。
- [ ] `docs/project_structure.md`：补 `agent/lsp/`、`agent/tui/commands/`。
- [ ] `docs/usage.md`：补 TUI command、Ctrl+M、LSP timeline 标识。

