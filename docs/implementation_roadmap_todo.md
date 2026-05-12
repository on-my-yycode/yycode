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
| Timeline 搜索项语义化展示 | 已完成 | `grep` metadata 已提供 keywords/range/preview，TUI 不再把长 regex 作为主信息 |
| 启动参数帮助 | 已完成基础版 | `main.py::build_arg_parser()` 包含参数和 Environment |
| 长任务摘要记忆 | 已实现完成 | `agent/task_memory.py`、任务完成后保留摘要并清理 todo artifacts，上下文压力下合并旧 summary |
| Timeline 可选择文本视图 | 已实现 | `Ctrl+L` 打开只读纯文本视图，`Ctrl+Shift+C` 复制输出纯文本 |
| 本地 evals MVP | 首版已实现 | `evals/run.py`、`context_session_baseline` 本地行为基线 |

### 部分实现，需要继续收口

| 模块 | 当前状态 | 主要缺口 |
| --- | --- | --- |
| Message Token Manager | 首版可用 | 已有最近一次压缩备份/撤销；仍需策略配置、多步 history、更多大 session 回归 |
| LSP | Python-only 可用 | 已有生命周期清理、噪声符号过滤、workspace 外 location 过滤；多语言 registry 和完整 diagnostics 未实现 |
| Session 持久化 | 首版可用 | 已有损坏文件/保存失败 memory-only fallback、列表容错、删除缺失容错和原子写；不可写 app_root 用户数据目录 fallback、并发写恢复策略仍需增强 |
| workspace / workdir | 主链路可用 | 已补绝对路径、符号链接逃逸、嵌套 workspace、apply_patch path escape/absolute/symlink 边界测试；发行前仍需平台回归 |
| Timeline 性能 | 已降负载 | 尚未做真正虚拟化；RichLog 全量 clear/write 仍可能成为瓶颈 |
| 工具输出上下文治理 | 已压缩部分输出 | 中等大小 read/grep 输出仍可能占 1k-3k tokens；旧 sessions 需要清理/迁移策略 |
| 用户意图反馈 | prompt 已约束 | 需要实际观察模型是否稳定在首个工具前输出意图，必要时做运行时 guard |
| TUI command | 首版可用 | 命令数量少，缺少 `:sessions`、`:resume`、`:messages` 等统一入口 |
| 本地 evals | MVP 可用 | 已有 context/session baseline；完整 bugfix/feature/refactor/tests/security review eval suite 待做 |
| ACP 兼容前置能力 | 待实现 | 先补项目内部通用能力：model 切换、plan snapshot、changed-files snapshot、session replay view model、cancel controller、approval adapter |

### 尚未实现

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| Task Graph / DAG 调度 | 未实现 | 设计见 `docs/task_graph_dag_design.md` |
| 多语言 LSP | 未实现 | 当前 `LspManager` 只接受 `.py`，languageId 固定 `python` |
| LSP 启动状态提示 | 后续增强 | 当前先从近期 P0/P1 移除，待 subagent runtime 统一后再排期 |
| 自动恢复最近 session | 未实现 | `--resume-latest` 仍是后续增强 |

### 近期已收口事项

以下事项已从待办中移除，后续只保留增强项：

- LSP 生命周期清理：`Session.close()` 已调用 `shutdown_lsp_managers()`，且 shutdown 失败不会阻断 provider close。
- LSP symbol 输出降噪：`document_symbols` 已过滤 module/file/package/namespace 等噪声符号。
- LSP workspace 边界：definition/references 等 location 已过滤 workspace 外路径。
- Session 容错：损坏 JSON 恢复、保存失败 memory-only fallback、列表腐坏元数据容错、删除缺失 session no-op 已有测试覆盖。
- Session 写入：`SessionStore` 已使用临时文件 + replace 的原子写入。
- Message Token Manager：最近一次手动压缩已支持内存备份和撤销。
- Workspace 边界测试：已覆盖绝对路径、符号链接逃逸、嵌套 workspace 作用域和 apply_patch 路径逃逸。
- Task Summary Memory 首版：任务完成后生成确定性摘要，保留关键目标/决策/文件/验证信息，并清理 todo 工具调用和 ToolMessage。
- 本地 evals MVP：`context_session_baseline` 已覆盖 todo artifacts 清理、summary 可恢复、工具输出压缩链路和未完成任务保留 todo artifacts。
- Timeline 搜索项语义化：`Search code` 现在优先显示搜索范围、关键词数量、关键词预览和耗时，完整 pattern 仅保留在 metadata 中。
- Timeline 可选择文本视图：`Ctrl+L` 打开只读纯文本 timeline，便于用户选择/复制；`Ctrl+Shift+C` 复制也使用同一纯文本转换。
- 文档同步：`docs/code_agent_roadmap.md`、`docs/usage.md`、`docs/project_structure.md` 已补充近期实现状态。

## 路线图需要更新的地方

`docs/code_agent_roadmap.md` 当前整体方向仍正确，但以下状态已落后：

1. `Message Token Manager` 不应再写“已完成设计，尚未实现”。当前应改为“首版已实现，待增强”。
2. LSP 不应再只作为“推荐下一步”。当前应改为“Python-only MVP 已实现，待多语言和稳定性增强”。
3. TUI command 系统需要新增到当前基础与后续路线。
4. Markdown 渲染性能优化需要记录到 TUI timeline 已完成项。
5. 推荐下一步顺序需要从“workspace -> Message Token Manager -> LSP”更新为“ACP 兼容前置能力 -> subagent runtime 统一 -> ACP stdio MVP -> LSP 增强 -> MTM 收口 -> 完整 eval suite / DAG”。

## 下一阶段建议优先级

### P0：先收口当前已实现但未稳定的能力

#### 1. ACP 兼容前置能力

目标：

- 为后续 ACP server 先补齐 yoyoagent 项目内部通用能力。
- 不直接做协议层，先让 TUI/CLI/未来 ACP 共用同一份状态和控制语义。

待办：

- [ ] 单 provider model 切换：只切换当前 provider 的 `model` 字符串，不做跨 provider 切换。
- [ ] 公共 plan snapshot：从 `TodoManager` 导出 entries/memory/updated_at。
- [ ] 公共 changed-files/diff snapshot：从 TUI runner 抽出文件变更汇总逻辑。
- [ ] Session replay view model：从 canonical `Session.messages` 派生可展示历史。
- [ ] 统一 cancel controller：TUI current task 和未来 ACP prompt task 共用取消语义。
- [ ] UI-independent approval adapter：审批请求与 TUI/ACP 展示解耦。

验收：

- model 切换后下一轮请求使用新 model。
- TUI Task Plan、文件变更表格和 `Ctrl+D` 行为不回退。
- replay view model 能识别 user/assistant/summary/tool/context。
- cancel 结果有明确状态：`cancelled`、`not_running`、`already_finished`。
- approval metadata 保留 action、tool、paths、reason、risk、diff preview。

#### 2. Timeline 可选择文本视图

状态：已实现。

完成内容：

- [x] 保留 RichLog 主 timeline，不改变现有结构化事件展示。
- [x] 增加 `Ctrl+L` 只读纯文本 timeline 视图，便于终端选择/复制。
- [x] `Ctrl+Shift+C` 复制 timeline 时复用同一 Rich markup -> plain text 转换。
- [x] 增加对应 TUI 样式。

验收：

- 主 timeline 仍保持 RichLog 彩色渲染。
- `Ctrl+L` 可打开纯文本视图并聚焦文本区域。
- `Ctrl+Shift+C` 输出纯文本内容，不再依赖脆弱的正则去除 Rich markup。

#### 3. subagent runtime 统一

目标：

- 让 subagent 复用主 runtime 的 ToolRegistry、ToolExecutor 和 ApprovalService。
- 减少主/子 agent 工具执行、安全审批和 workspace 行为差异。

待办：

- [ ] 梳理当前 `SubagentRunner` 与主 `Session` runtime 初始化差异。
- [ ] 复用主 runtime 的工具注册、审批服务和 workspace-bound 配置。
- [ ] 保持 subagent 独立 conversation history，不引入父 agent todo ownership。
- [ ] 增加主/子 agent 工具行为一致性测试。

验收：

- subagent 使用与主 agent 一致的工具 metadata、审批和 workspace 约束。
- 现有 `@architect /plan`、`@worker`、`@tester` 委派行为保持不变。

#### 3. Message Token Manager 收口

目标：

- 让 `Ctrl+M` 成为稳定的上下文治理入口。
- 防止压缩破坏 tool call 链路。

待办：

- [ ] 增加压缩前确认视图，展示 affected indexes、预计节省和风险。
- [ ] 压缩后 timeline 输出明确摘要：压缩了几条消息、节省估算 tokens。
- [ ] 保存 session 后刷新 header context usage。
- [ ] 增加大 session fixtures，覆盖 read/grep/write/verify/tool policy 元数据。
- [ ] 增加“无可压缩项”的空状态。
- [x] 支持最近一次手动压缩的内存备份和撤销。
- [ ] 评估是否需要在 session JSON 中保留 `original_chars` / `estimated_original_tokens`。

验收：

- `Ctrl+M` 可查看 system/tools/messages 分布。
- 选择压缩后消息顺序、`tool_call_id`、`name` 保持不变。
- 压缩后恢复 session 不报 provider payload 错。

#### 3. 当前文档同步

目标：

- 让路线图与当前实现一致，避免后续重复设计已完成能力。

待办：

- [x] 更新 `docs/code_agent_roadmap.md` 的当前基础、MVP 状态和推荐下一步。
- [ ] 更新 `docs/lsp_integration_design.md`，加入当前 Python-only 实现状态与已知限制。
- [ ] 更新 `docs/message_token_manager_design.md`，加入首版实现状态。
- [x] 更新 `docs/project_structure.md`，补充 `agent/lsp/`、`agent/tui/commands/`。
- [x] 更新 `docs/usage.md`，补充 `Ctrl+M`、`:help`、`:clear`、LSP 基础说明。

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
- [x] session JSON 损坏时给出清晰错误，不崩溃。
- [x] 列表命令忽略损坏文件并提示 warning。
- [x] 增加原子写入：临时文件 + rename。
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

#### 8. Task Summary Memory 可选体验增强

目标：

- 核心长任务摘要记忆已实现完成；如后续继续投入，重点放在可视化、手动操作和模型补充体验。
- 详细方案见 `docs/long_task_summary_memory_design.md`。

待办：

- [x] 建立摘要前置 evals MVP：`evals/run.py` 和 `context_session_baseline`。
- [x] 基于 Task State memory 生成确定性任务级 summary block。
- [x] 防止 summary 与 todo 结果重复进入上下文。
- [x] 任务完成后清理 todo artifacts，但保留最终任务摘要。
- [x] 增加恢复 session 后摘要仍可用的测试。
- [x] 上下文压力下合并旧 summary，避免摘要块越积越多。
- [ ] 在 Message Token Manager 中展示 summary memory 统计。
- [ ] 增加可选手动 summary / undo 入口。
- [ ] 增加模型生成式摘要补充，用于解释确定性字段之外的高价值背景。

验收：

- 长任务上下文压缩后，agent 仍能正确说出已做、未做、风险和验证结果。
- 可选入口不会破坏现有确定性 summary 和 provider tool call 链路。

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

当前已完成：

- [x] 新建 `evals/` 目录结构。
- [x] 增加 `evals/run.py` 本地 runner。
- [x] 增加 `context_session_baseline`，覆盖 context/session 行为基线。

待办：

- [ ] 添加完整 5 类任务：fix bug、add feature、refactor、add tests、security review。
- [ ] 每个任务提供 `prompt.md`、`setup.sh`、`checks.sh`。
- [ ] 记录是否通过测试、是否满足目标、改动范围是否合理。
- [ ] 增加人工复核报告模板。

验收：

- 一条命令可跑基础 eval suite。
- 每次核心能力改动后能比较结果。

## 建议近期执行顺序

建议按以下顺序推进：

```text
1. ACP 兼容前置能力
2. subagent runtime 统一
3. ACP stdio server MVP
4. Message Token Manager 压缩确认和大 session 回归
5. 工具输出压缩阈值 per-tool 收紧
6. Timeline 增量渲染 / 可见窗口渲染
7. Session 持久化不可写 app_root fallback
8. 多语言 LSP registry 与 LSP 增强
9. 完整 eval suite
10. Task Graph / DAG
```

原因：

- 1 先补项目内部通用能力，后续 ACP 只做协议包装。
- 2 能减少主/子 agent 工具执行和审批差异，为 ACP tool/approval 映射降复杂度。
- 4-5 都是在收口当前已经实现的能力，风险低、收益直接。
- Timeline 可选择文本视图已完成；后续 timeline 工作转向增量渲染和可见窗口渲染。
- LSP 启动状态提示本轮从近期 P0/P1 移除，后续并入 LSP 增强整体排期。
- 6-7 是发行版本稳定性要求。
- 8-10 是能力扩展，适合在基础稳定后推进。

## 当前风险清单

- 当前工作区有较多未提交变更，后续提交前需要按功能拆分或整体确认。
- LSP 当前只支持 Python，且不同 server 能力差异明显；不能把 `no_results` 等同于代码没有问题。
- Message Token Manager 的逐条 token 仍是估算，UI 和文档必须持续强调 estimated。
- Timeline 已有缓存和轻量 Markdown，但 RichLog 全量写仍可能成为性能瓶颈。
- Session messages 持久化会保存敏感上下文，需要在发行文档中提醒用户。

## 文档更新待办

- [x] `docs/code_agent_roadmap.md`：同步当前实现状态和推荐下一步。
- [ ] `docs/lsp_integration_design.md`：补当前实现状态、限制、启动提示计划。
- [ ] `docs/message_token_manager_design.md`：标记首版已实现，拆出增强项。
- [ ] `docs/session_persistence_design.md`：补不可写 app_root fallback、并发写增强待办。
- [ ] `docs/structured_event_timeline_design.md`：补 timeline cache、轻量 markdown、未来虚拟化。
- [x] `docs/project_structure.md`：补 `agent/lsp/`、`agent/tui/commands/`。
- [x] `docs/usage.md`：补 TUI command、Ctrl+M、LSP timeline 标识。
