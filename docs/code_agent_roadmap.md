# Code Agent 建设方案

## 目标

将 yoyoagent 从“能调用工具的 agent”升级为“能安全理解、修改、验证真实代码的 code agent”。

目标能力：

- 快速理解项目结构、代码入口和关键依赖。
- 安全编辑多文件代码，避免误覆盖用户改动。
- 自动运行验证命令，读懂失败并迭代修复。
- 对危险操作执行安全审批或阻断。
- 支持长任务上下文管理、subagent 协作和统一流式输出。
- 通过评测集持续判断 agent 能力是否变强。

## 当前基础

当前项目已经具备：

- 工具系统：`read_file`、`write_file`、`edit_file`、`bash`、`grep`、skills、todo。
- Code agent MVP 工具：`workspace_state`、`git_diff`、`apply_patch`、`verify`。
- 代码理解工具：`list_files`、`read_many_files`、`grep`、`git_show`，以及 Python 只读 LSP 语义导航工具。
- subagent：`explorer`、`architect`、`worker`、`tester`、`security`。
- 上下文窗口显示和轻度压缩。
- Provider/tokenizer token counting 与估算兜底。
- 主会话工具调用内部并发调度。
- 工具超时控制。
- 工具执行 metadata：副作用、并发策略、默认超时。
- 技能按需加载。
- TUI 时间流：结构化工具活动、Markdown/代码高亮、任务计划面板、文件变更摘要和 diff 查看器。
- TUI 审批交互：底部内联审批、审批前 diff preview、批准/拒绝快捷键提示。
- Task State 历史治理：任务完成后裁剪内部 todo 工具调用，降低后续上下文污染。
- Workspace / workdir 统一基础版：命令入口支持 `yoyoagent [workspace]`，runtime 为 workspace-bound 工具注入 `workdir`。
- Session messages 持久化与恢复首版：默认保存 messages，支持 `-r` 恢复、`-s` 列表、`-x` 删除、`-t` 临时会话。
- subagent 显式 skill 委派：`subagent` 工具支持 `skills` 参数，`@architect /plan ...` 可将 skill 隔离加载到 subagent 上下文。
- TUI 输入补全：支持 `/skill`、正文中间 `/skill`、`@role` subagent 角色补全。
- 长任务摘要记忆首版：任务完成后保存确定性 Task Summary Memory，并清理 todo artifacts，降低后续上下文污染。
- 本地 evals MVP：已有 `evals/run.py` 和 `context_session_baseline`，用于验证 context/session 基线。
- Timeline 搜索项语义化展示：`grep`/搜索类工具优先显示搜索范围、关键词数量、关键词预览和耗时。

主要欠缺：

- LSP / Message Token Manager 已有首版；后续欠缺主要是完整 diagnostics、配置化阈值、多步历史和模型生成式摘要等增强。
- 任务依赖图 / DAG 调度，设计见 [Task Graph DAG 调度设计](task_graph_dag_design.md)。
- 完整本地 eval suite，例如 bugfix、feature、refactor、tests、security review 任务集。
- subagent runtime 统一，减少主/子 agent 工具执行、审批和 runtime 行为差异。
- ACP 兼容前置能力首版：单 provider 模型切换、公共 plan snapshot、公共 changed-files/diff snapshot、session replay view model、统一 cancel controller、UI-independent approval adapter。

## MVP 实现状态

已完成：

- Phase 1：所有工具声明 `execution` metadata，`agent.graph` 根据 metadata 做并发和超时调度。
- Phase 2：新增 `workspace_state` 与 `git_diff`，用于修改前了解分支、工作区状态和差异。
- Phase 3：新增 `apply_patch`，当前支持 exact replacement 与 workspace 内 unified diff，默认阻断删除文件，且写入前需要显式授权。
- Phase 4：新增 `verify`，支持 `all`、`tests`、`lint`、`typecheck`。
- 主 agent prompt 已加入非简单修改前检查 workspace/git diff、优先 patch 编辑、改完验证的规则。
- 运行时 workflow guard 会在写入类工具执行前拦截未预检的写入，自动返回 `workspace_state` 与 `git_diff` 给模型，并要求它复核后重试。
- 写入类工具执行后，workflow guard 会追加验证提醒，推动模型先运行 `verify` 再最终回复。
- 测试覆盖工具注册、metadata、并发调度、git 状态、diff、patch、verify 和 subagent 回归。
- Phase 5 基础代码理解工具已实现：`list_files`、`read_many_files`、Python `grep`、`git_show`。
- Phase 5 LSP 只读 MVP 已实现：Python document/workspace symbols、definition、references、hover 和 diagnostics MVP fallback，支持 language server 缺失降级和 fake LSP 回归测试。
- Phase 7 v1 已实现：危险 bash/git 命令、删除 patch、文件创建/编辑会在 runtime 发起审批；主会话和 subagent 的写入工具会在用户批准后才临时注入 `approved=true` 执行。
- TUI 审批 UI 已实现：时间流中先展示完整 diff preview，底部输入区展示内联审批提示，用户可以用 `Y`/`Enter` 批准或 `N`/`Esc` 拒绝。
- 写入审批已补充目标文件校验：如果文件编辑请求无法识别目标文件，不弹出审批，也不阻塞整轮任务；系统会把可修正的工具结果返回给模型，让模型用明确路径或合法 diff 重试。
- 文件操作卡片功能已移除，当前 timeline 保持结构化工具活动聚合；文件修改结果主要通过最终文件变更摘要和 `Ctrl+D` diff 面板查看。
- `Ctrl+T` 任务计划面板、`Ctrl+D` 文件变更/diff 面板已实现；`Ctrl+L` 可打开可选择/复制的纯文本 timeline 视图；任务结束后会输出文件变更摘要，支持查看按文件拆分的 diff。
- 会话历史治理已实现基础版：任务正常完成后裁剪内部 todo 工具调用和工具结果，减少下一个任务被旧 Task State 污染。
- 长任务摘要记忆首版已实现：任务完成后写入结构化摘要，保留目标、约束、文件、决策、验证和风险等关键信息，再清理 todo artifacts。
- 本地 evals MVP 已实现：`context_session_baseline` 覆盖任务摘要、todo artifacts 裁剪、恢复 session 后 summary 可用和工具输出压缩链路。
- Timeline 搜索项语义化展示已实现：长 regex 不再作为主展示内容，完整 pattern 仍保留在 metadata 中。
- Workspace / workdir 统一已完成主要收口：命令入口支持位置参数 workspace，workspace-bound 工具使用 runtime 注入的 `workdir`，subagent 继承父 workdir。
- Session messages 持久化与恢复首版已实现，详见 [Session Messages 持久化与恢复设计](session_persistence_design.md)。
- subagent 显式 skill 委派首版已实现，详见 [Subagent 显式 Skill 委派设计](subagent_explicit_skill_design.md)。
- TUI 已支持 `@role` 补全，以及在已有正文中按光标 token 触发 `/skill` 补全。

待校准：

- Workspace / workdir 后续只剩增强项：继续补充发行前平台边界测试；当前已补绝对路径、符号链接逃逸、嵌套 workspace 作用域，以及 apply_patch path escape/absolute/symlink 边界测试。
- Session messages 持久化仍可继续增强 UI warning 展示；当前已补损坏 JSON、保存失败 memory-only fallback、列表命令腐坏元数据和删除缺失 session 的容错测试。
- Message Token Manager 首版已实现，已支持一次性压缩备份/撤销；后续增强包括多步 operation history、配置化阈值和模型生成式摘要压缩。

## 总体路线

推荐分阶段建设：

```text
1. 工具 metadata + 调度策略
2. workspace_state + git_diff
3. apply_patch 工具
4. verify 工具
5. 代码理解工具
6. 上下文任务摘要
7. 安全审批机制
8. Workspace / Workdir 统一
9. Session messages 持久化与恢复
10. Message Token Manager
11. ACP 兼容前置能力
12. 任务依赖图 / DAG 调度
13. evals
```

其中 MVP 建议先做前 4 项。

## Phase 1: 工具 Metadata 与调度策略

状态：已实现。

### 背景

并发、串行、超时规则最初硬编码在 `agent/graph.py` 中。当前已重构到 runtime 层：

- `agent/runtime/tool_registry.py` 读取工具 metadata。
- `agent/runtime/tool_scheduler.py` 根据 metadata 调度并发/串行批次。
- `agent/runtime/tool_executor.py` 负责单个工具生命周期。

### 目标

给每个工具声明执行属性，让调度器根据工具 metadata 决定：

- 是否可以并发。
- 是否有 workspace 写入副作用。
- 是否修改 session 状态。
- 默认超时时间。
- 是否属于长任务。

### 设计

每个 tool schema 增加可选 `execution` 字段：

```python
{
    "name": "read_file",
    "description": "Read file contents.",
    "input_schema": {...},
    "execution": {
        "side_effects": "read_only",
        "concurrency": "safe",
        "timeout_seconds": 30,
    },
}
```

建议枚举：

```text
side_effects:
- read_only
- workspace_write
- session_state
- process
- delegation

concurrency:
- safe
- serial
- role_based

long_running:
- true
- false
```

### 调度规则

```text
read_only + safe       -> 可并发
workspace_write        -> 串行
session_state          -> 串行
delegation worker      -> 串行
delegation review roles -> 可并发
process                -> 根据工具配置
```

### 测试

- read-only 工具并发。
- workspace write 工具串行。
- session state 工具串行。
- timeout 从 metadata 生效。
- subagent `worker` 串行。
- subagent `explorer/tester/security/architect` 可并发。

### 估算

工作量：小到中，约 `0.5-1 天`。

## Phase 2: Git 工作区保护

状态：已实现。

### 背景

Code agent 修改代码前必须知道当前工作区状态，避免覆盖用户已有改动。

### 新增工具

```text
workspace_state()
git_diff(paths?: list[str])
```

### workspace_state 返回示例

```text
branch: master
changed_files: 2
status:
 M agent/graph.py
?? tests/test_x.py
```

### git_diff 返回示例

```text
diff --git a/agent/graph.py b/agent/graph.py
...
```

### Prompt 规则

```text
Before non-trivial edits, inspect relevant files and be aware of existing git changes.
Never overwrite unrelated user changes.
```

### 测试

- 能读取当前分支。
- 能返回 short status。
- 能限制 diff 路径。
- workspace 外路径被拒绝。
- 无 git repo 时返回清晰错误。

### 估算

工作量：小，约 `0.5 天`。

## Phase 3: apply_patch 工具

状态：已实现。

### 背景

当前 `write_file` 和 `edit_file` 适合简单操作，但不适合作为主要代码编辑能力。Code agent 需要更可靠的 patch 级编辑。

### 目标

新增 `apply_patch` 工具，作为默认代码编辑入口。

### 能力

- 支持多文件 patch。
- 基于上下文匹配。
- 修改前验证 path 不逃逸 workspace。
- 失败时返回具体失败原因。
- 返回改动摘要。
- 可选返回 diff stat。

### 使用规则

```text
Prefer apply_patch for code edits.
Use write_file only for brand-new files.
Use edit_file only for small exact replacements.
```

### 工具输入示例

```json
{
  "patch": "diff --git a/agent/foo.py b/agent/foo.py\n--- a/agent/foo.py\n+++ b/agent/foo.py\n@@ -1,1 +1,1 @@\n-old\n+new\n"
}
```

也可以使用更稳的 exact replacement 模式：

```json
{
  "path": "agent/foo.py",
  "old_text": "old",
  "new_text": "new"
}
```

说明：`patch` 字段使用 `git apply`，因此输入格式是 unified diff，不是 Codex 内部 `*** Begin Patch` 格式。普通已有文件小改动优先使用 `path + old_text + new_text`，避免模型手写 diff 出错。

### 风险控制

- 禁止修改 workspace 外文件。
- 大文件/大量文件修改触发安全审批。
- patch 失败不做部分提交，返回错误。

### 测试

- 单文件修改。
- 多文件修改。
- 新增文件。
- 删除文件可选，默认需要审批。
- 上下文不匹配时失败。
- workspace escape 被拒绝。

### 估算

工作量：中，约 `1-2 天`。

## Phase 4: verify 工具

状态：已实现。

### 背景

Code agent 需要稳定的验证闭环，而不是每次自己猜命令。

### 新增工具

```text
verify(kind, target?)
```

### 输入示例

```json
{"kind": "tests", "target": "tests/test_subagent.py"}
{"kind": "all"}
{"kind": "lint"}
{"kind": "typecheck"}
```

### 内部映射

```text
tests     -> pytest target
all       -> pytest
lint      -> ruff check .，如果项目配置存在
typecheck -> mypy / pyright，如果项目配置存在
```

### 验证触发策略

写入工具成功后不应无条件要求运行代码测试。当前策略应按变更类型决定：

- 仅代码文件和明确的构建/测试配置文件变更：需要运行 `verify`，优先使用最窄目标。
- 其它文件变更：不要求运行代码测试。
- 混合变更：只要包含代码或明确配置变更，就需要针对相关代码区域运行 `verify`。

不会触发代码验证的示例：

```text
README.md
docs/*.md
*.drawio
*.png
*.jpg
*.svg
*.pdf
未知扩展名文件
```

仍应视为需要验证的配置文件示例：

```text
pyproject.toml
package.json
go.mod
Cargo.toml
pom.xml
*.csproj
```

### 返回格式

```text
status: passed
command: pytest tests/test_subagent.py
duration: 0.8s
summary:
10 passed
```

### 测试

- pytest 成功。
- pytest 失败摘要。
- target 限制。
- 未配置 lint/typecheck 时返回清晰信息。
- 命令超时。

### 估算

工作量：中，约 `1 天`。

## Phase 5: 代码理解工具

状态：基础版已实现。

### 建议工具

```text
list_files(path?, pattern?)
read_many_files(paths, limit?)
grep(pattern, path?, max_results?)
git_show(ref, path?)
git_diff(paths?)
```

后续高级工具：

```text
find_symbol(symbol)
references(symbol)
dependency_graph(path)
```

语义级代码导航建议通过 LSP 工具实现，设计见 [LSP 集成设计](lsp_integration_design.md)。

### 目标

减少 agent 为建立项目地图而反复调用 bash，提高代码理解效率。

### 估算

工作量：小到中，约 `0.5-1 天`。

## Phase 6: 上下文任务摘要

状态：已实现完成，可选体验增强待定。

当前已实现旧工具输出轻度压缩、任务正常完成后的内部 todo 工具调用裁剪，以及确定性的 Task Summary Memory。任务完成后会保留任务级摘要，再清理 todo artifacts，避免下一个任务被旧 Task State 重复污染；在上下文压力下也支持旧 summary 合并并保留最新/recent messages。核心长任务摘要记忆能力已完成，后续如果继续投入，应定位为可选体验或模型增强，例如 Message Token Manager 手动 summary 入口、summary undo、UI 统计展示和模型生成式补充。详细方案见 [长任务摘要记忆设计](long_task_summary_memory_design.md)。

### 背景

当前上下文压缩已能压缩旧工具输出，并在任务结束后保存确定性任务摘要。长任务摘要记忆核心链路已经完成；后续如有需要，重点不再是补齐核心摘要能力，而是优化可视化、手动操作、撤销和模型补充体验。

### 摘要内容

```text
user_goal
constraints
files_inspected
files_modified
decisions
test_results
open_risks
next_steps
```

### 触发时机

- 已实现：正常任务完成后生成任务级摘要。
- 已实现：上下文压力下合并旧 summary，并保留最新/recent messages。
- 可选增强：在 Message Token Manager 中提供手动 summary / undo 入口。
- 可选增强：用模型生成式摘要补充确定性字段之外的说明。

### 风险

摘要可能丢失细节，因此应先作为补充消息，不要过早删除关键最近消息。

### 估算

工作量：中到大，约 `1-2 天`。

## Phase 6.5: Message Token Manager

状态：首版已实现。详细设计见 [Message Token Manager 设计](message_token_manager_design.md)。

### 背景

当前已有 session messages 持久化、上下文窗口显示、provider/tokenizer token counting 和旧 tool output 自动压缩。用户仍缺少一个可见界面来判断：

- 当前上下文到底用了多少 token。
- token 主要被 system prompt、tools schema、user、assistant 还是 tool output 消耗。
- 哪些历史 tool output 最值得压缩。
- 手动压缩预计能节省多少 token，以及风险是什么。

### 首版目标

- 新增 `MessageContextManager`，分析 `Session.messages`、`system_prompt` 和 tools schema 的 token 占用。
- TUI 新增 `Ctrl+M` 只读统计面板。
- 展示整体 context usage、压力等级、按 role/type 分布和最大消息列表。
- 明确区分整体 exact/estimated token 与逐条 estimated token。
- 给出旧 `ToolMessage` 的压缩建议。
- 支持用户确认后手动压缩旧 tool output 为 compact marker。
- 支持最近一次手动压缩的内存备份和撤销，用于快速恢复误压缩内容。

### 后续增强

- 清除消息能力，但默认不物理删除，优先 replace with compact marker。
- 多步 operation history。
- 可配置 keep recent N、压缩阈值、tool output 最大长度。
- 模型生成式摘要压缩，用于高价值历史 assistant/tool 内容。
- `/messages` 命令入口。

### 风险

- 逐条 message token 首版只能估算，需要在 UI 明确标注。
- 物理删除消息容易破坏 assistant tool call / ToolMessage 配对，后续清除能力必须非常保守。
- 模型摘要可能丢失事实或引入幻觉，不应放入首版。

### 估算

只读统计 + 压缩建议：中，约 `1 天`。

手动压缩旧 tool output：中，约 `0.5-1 天`。

## Phase 7: 安全审批机制

状态：v1 阻断、runtime 审批和 TUI 内联审批 UI 已实现。

### 定义

安全审批是指：当 agent 准备执行高风险操作时，不直接执行，而是先停下来向用户确认。

### 高风险动作

```text
删除文件或目录
覆盖已有文件的大段内容
执行 rm / mv / chmod / chown
git reset / git checkout / git clean
安装依赖
运行未知脚本
访问网络
修改大量文件
读取或输出疑似密钥
```

### 分层设计

```text
1. Prompt 层：告诉 agent 高风险动作必须确认。
2. Tool 层：bash/write/edit/apply_patch 检测高风险动作并拒绝或返回 approval_required。
3. Runtime 层：真正执行前统一做 policy check。
```

### ApprovalRequest

```python
@dataclass
class ApprovalRequest:
    action: str
    command: str | None
    path: str | None
    reason: str
    risk: str
```

### 返回示例

```text
Approval required:
action: destructive_git
command: git reset --hard
reason: This command discards local changes.
risk: User work may be lost.
```

### 当前实现

当前已实现工具层阻断、runtime 审批和 TUI 内联审批：

- 文件创建/编辑工具在执行前生成 `ApprovalRequest`，用户批准后才注入 `approved=true`。
- 时间流先展示审批前完整 diff preview，底部审批区只展示动作、文件和快捷键提示，避免重复显示 diff。
- 用户拒绝后会明确提示任务因审批拒绝而停止，不再静默失败。
- 如果写入请求无法识别目标文件，系统不会弹出审批，也不会阻塞整轮任务；该工具调用会返回可修正的失败消息给模型，模型可以用明确路径或合法 diff 重试。
- 危险 bash/git 命令仍按命令级审批处理，不要求文件路径。

后续可继续增强：

- 批量文件审批策略，例如一次审批多个明确文件。
- 更细粒度的高风险策略，例如大规模改动、依赖安装、网络访问。
- 审批记录审计和可导出日志。

### 估算

工作量：中到大，约 `1-2 天`。

## Phase 7.5: Workspace / Workdir 统一

状态：主链路已实现，后续只剩发行前增强测试。

已完成：

- 新增 `tools/workspace.py`，提供 `Workspace.safe_path()`、`relative_path()` 和 `resolve_workspace()`；`agent/runtime/workspace.py` 作为 runtime 侧兼容导出。
- 命令入口已支持位置参数 `yoyoagent [workspace]`，默认使用当前 cwd，并校验路径存在且为目录。
- `RuntimeToolRegistry` 会为 workspace-bound 工具注入 `runtime.workdir`，工具 schema 不向模型暴露 `workdir`。
- `read_file`、`read_many_files`、`write_file`、`apply_patch`、`grep`、`list_files`、`git_show`、`git_diff`、`workspace_state`、`verify`、`bash` 已支持显式 `workdir`。
- 审批 diff preview 和 subagent 工具审批路径已传入父 runtime 的 `workdir`。
- subagent 执行 workspace-bound 工具时会注入父 `workdir`。
- 已去除 workspace 工具中的模块级 `WORKDIR = Path.cwd()` fallback，默认 workspace 改为调用时 `Path.cwd()`。
- `edit_file` 保留为阻断占位工具，但已接受 runtime 注入的 `workdir`，避免工具执行签名错误。
- 已补充基础测试：位置参数解析、默认 cwd、拒绝文件路径、cwd 与 workspace 不一致时 read/git/bash 工具仍使用显式 workdir、subagent 继承父 workdir、所有 workspace-bound handler 接受 `workdir`。

后续增强：

- 继续扩展所有 workspace-bound 工具的直接调用边界测试，尤其是符号链接、绝对路径和嵌套 workspace。
- 若未来恢复 `edit_file` 的真实编辑能力，需要实现 workdir-aware 行为；当前仍推荐使用 `apply_patch`。

### 背景

发行版本需要支持用户在任意项目目录执行 `yoyoagent`。当前 `Session` 和 `AgentRuntimeContext` 已经显式携带 `workdir`，workspace-bound 工具由 runtime 注入该目录；直接调用工具时才回退到调用时的当前目录。

### 用户层行为

命令入口使用位置参数指定 workspace，不提供 `--workdir` flag：

```text
yoyoagent [workspace]
```

规则：

```text
yoyoagent              -> workdir = 当前 shell cwd
yoyoagent .            -> workdir = 当前 shell cwd
yoyoagent ~/project    -> workdir = ~/project
yoyoagent ../project   -> workdir = 相对当前 cwd 解析后的目录
```

启动时需要校验：

- workspace 必须存在。
- workspace 必须是目录。
- workspace 使用 `expanduser().resolve()` 后的真实路径。

如果用户要切换项目，可以直接传位置参数，也可以先 `cd` 到目标目录再启动。

### 内部规则

- `Session.workdir` 是唯一工作目录来源。
- `AgentRuntimeContext.workdir` 继承 `Session.workdir`。
- `RuntimeToolRegistry` 负责给需要 workspace 的工具注入 `runtime.workdir`。
- `subagent` 继承父 runtime 的 `workdir`。
- 文件、git、bash、verify、patch、grep、list/read 工具都必须使用注入的 `workdir`。
- 工具 schema 不暴露 `workdir`，模型不能指定或覆盖工作目录。
- 所有文件路径必须通过统一 `safe_path` 限制在 workdir 内。

### 建议实现

新增 workspace 基础对象：

```text
agent/runtime/workspace.py
```

职责：

```text
Workspace.root
Workspace.safe_path(path)
Workspace.relative_path(path)
Workspace.validate()
```

迁移工具时可以先保留模块级 `WORKDIR` 作为兼容 fallback，但 runtime 路径必须显式注入：

```text
def read_file(path, ..., workdir=None):
    workspace = Workspace(workdir or WORKDIR)
```

最终目标是去除工具 import 时固定 `Path.cwd()` 的行为。

### 需要迁移的工具

```text
read_file
read_many_files
write_file
edit_file
apply_patch
grep
list_files
git_show
git_diff
workspace_state
verify
bash
```

### 与 LSP 的关系

LSP manager 的基础 workspace 来自 `runtime.workdir`。目标文件必须先经过 workspace `safe_path` 校验；LSP root 可以从目标文件向上查找 `.git`、`pyproject.toml`、`package.json` 等项目标记，但不能越过 `runtime.workdir`。

### 测试计划

- 无位置参数启动时使用 `Path.cwd().resolve()`。
- 位置参数支持相对路径、绝对路径和 `~`。
- 不存在路径和文件路径会返回清晰错误。
- `Session(workdir=tmp_path)` 后所有文件/git/bash/verify 工具都使用 `tmp_path`。
- 从另一个 cwd 启动测试进程，但传入 workspace 后工具仍操作 workspace。
- `../` 路径逃逸被拒绝。
- subagent 继承父 workdir。

## Phase 7.6: Session Messages 持久化与恢复

状态：首版已实现。详细设计见 [Session Messages 持久化与恢复设计](session_persistence_design.md)。

### 背景

`Session` 有稳定的 `session_id`，并维护 `Session.messages`。每轮 `send()` / `send_stream()` 会把用户输入加入 messages，调用 LangGraph 后用 `result["messages"]` 更新会话历史。

该阶段解决的问题是：messages 如果只存在内存中，进程退出或 TUI/CLI 重启后，即使用户知道旧 session id，也无法恢复上一轮模型上下文。当前首版已将 canonical messages 持久化到 yoyoagent 应用目录下的 `sessions/`，恢复时仍不依赖 TUI timeline。

### 目标

- 将 `Session.messages` 本地持久化，作为模型上下文恢复来源。
- 支持通过 `session_id` 恢复历史 messages，继续上一轮对话。
- 首版保持低侵入：只恢复最终消息历史，不恢复运行中状态、审批队列或 TUI timeline。
- 与现有上下文压缩、Task State 历史治理和 workspace/workdir 隔离兼容。

### 推荐方案

已新增 `SessionStore` 抽象，由 `Session` 在生命周期中调用：

```text
agent/session_store.py
{app_root}/sessions/{workspace_hash}/{session_id}.json
```

建议行为：

- `Session.__init__` 已增加 `app_root`、`runtime_data_dir`、`persist_messages`、`resume`、`message_store` 参数。
- `SessionStore` 默认使用 yoyoagent 应用目录下的 `sessions/`，不写入被操作的 `workdir`。
- session 文件按 `workspace_hash = sha256(resolve(workdir))[:16]` 分组，并保存原始 `workdir`。
- 恢复时必须校验 session 文件中的 `workdir` 与当前 `Session.workdir` 一致。
- `resume=True` 且存在同 session id 文件时，加载历史 messages。
- `send()` / `send_stream()` 正常完成并裁剪内部 todo artifacts 后保存最终 `self.messages`。
- 默认开启保存，但默认不自动恢复；恢复需显式传入 `-r <id>` / `--resume <id>`。
- CLI/TUI 已增加 `-r` / `--resume <id>`、`-s` / `--sessions`、`-x` / `--delete <id>`、`-t` / `--temp`。

目录归属需要和 skills 一起收口：

- 目标发行模型中，`skills/` 和 `sessions/` 都属于 yoyoagent 应用目录 `app_root`。
- 当前代码已迁移为默认读取 `{app_root}/skills`；`YOYO_SKILL_DIRS` 作为额外技能目录追加，项目内 `workdir/skills` 不再默认扫描。

### 风险与测试重点

- 消息序列化必须保留 `tool_calls`、`additional_kwargs`、`response_metadata`、`tool_call_id` 等字段，避免恢复后 provider payload 不合法。
- 持久化文件可能包含敏感上下文，需要文档提示；因为 sessions 不写入用户 workdir，首版不应自动修改用户项目 `.gitignore`。
- `app_root/sessions` 如果不可写，需要继续增强为 fallback 到用户数据目录；当前保存失败会进入 memory-only fallback 并在 TUI 给出 warning。
- 恢复大量历史可能导致 token 超窗，需要继续配合现有上下文压缩。
- 测试需要覆盖消息序列化、同 session id 恢复、workspace hash 隔离、workdir 不一致拒绝恢复、禁用持久化、损坏文件容错、路径逃逸和 `clear()` / `reset()` 语义。

## Phase 8: Evals

状态：MVP 已实现，完整 suite 待做。

### 目标

建立本地评测集，判断 code agent 是否真的变强。

当前已有 `evals/run.py` 和 `context_session_baseline`，用于在上下文治理和 session 持久化相关改动前后做确定性基线检查。

### 建议目录

```text
evals/
  tasks/
    fix_simple_bug/
    add_feature/
    refactor_module/
    add_tests/
    security_review/
```

### 每个任务包含

```text
prompt.md
setup.sh
checks.sh
expected.patch 可选
```

### 指标

- 是否通过测试。
- 是否覆盖用户目标。
- 是否改动范围合理。
- 是否避免无关修改。
- 是否正确使用工具/subagent。

### 估算

MVP 已完成。完整 bugfix/feature/refactor/tests/security review suite 工作量：中，约 `1-2 天`。

## Phase 8.5: ACP 兼容前置能力

状态：首版已实现。详细协议调研见 [ACP 调研与 yoyoagent 实现方案](acp_research_and_implementation_plan.md)。

### 背景

ACP 最终需要把 yoyoagent 作为编辑器外部 agent 暴露出去。但在实现协议适配前，应先补齐一组项目内部通用能力，让 TUI、CLI、后续 ACP server 共享同一份状态和控制语义，而不是在 ACP 层重复实现。

该阶段不直接实现 ACP JSON-RPC server，目标是先把 yoyoagent 自身抽象收口。

### 目标

- 支持单 provider 下的模型字符串切换。
- 提供标准化 plan snapshot，供 TUI/ACP/日志复用。
- 提供标准化 changed-files/diff snapshot，避免文件变更逻辑只存在于 TUI runner。
- 提供 session replay view model，让外部 UI 能恢复展示历史。
- 提供统一 cancel controller，TUI/CLI/ACP 共用取消语义。
- 抽象 UI-independent approval adapter，TUI/ACP 都能挂接同一审批请求。

### 已完成

- [x] 单 provider model 切换：`Session.set_model(model)` 更新 provider model，重建 graph，并重新推断 context window。
- [x] 公共 plan snapshot：`agent/plan_snapshot.py` 从 `TodoManager` 导出 entries、memory、updated_at。
- [x] 公共 changed-files/diff snapshot：`agent/change_snapshot.py` 负责 diff 提取、文件统计和 changed path 汇总，TUI runner 已复用。
- [x] Session replay view model：`agent/session_replay.py` 从 canonical `Session.messages` 派生 user/assistant/summary/tool replay events。
- [x] 统一 cancel controller：`agent/cancellation.py` 提供 `cancelled`、`not_running`、`already_finished` 结果。
- [x] UI-independent approval adapter：`ApprovalDecision` 提供 `approved`、`denied`、`cancelled` 决策语义，TUI adapter 保持 bool callback 兼容。

### 后续增强

- model 切换当前只覆盖同 provider 的 model 字符串；跨 provider 切换后续再设计。
- changed-files snapshot 当前基于 unified diff；后续 ACP 可继续补 locations/ranges。
- replay view model 当前从 canonical messages 派生，不持久化独立 timeline；如外部 UI 需要更完整 replay，可增加事件落盘。

### 验收标准

- 不引入 ACP server，也能通过单元测试验证上述公共能力。
- TUI 现有行为不回退。
- 新 snapshot 不依赖 Rich/Textual。
- changed-files 逻辑从 TUI runner 抽出后，现有文件变更摘要和 `Ctrl+D` 仍可用。
- model 切换后下一轮请求使用新 model。
- cancel 在 TUI 中保持原行为，并为外部 runner 留出复用入口。

### 后续与 ACP 的映射

| 项目内部能力 | 后续 ACP 映射 |
| --- | --- |
| model switch | `session/set_model` 或 model config option |
| plan snapshot | `session/update` plan |
| changed-files snapshot | `tool_call_update` locations/content |
| replay view model | `session/load` replay |
| cancel controller | `session/cancel` |
| approval adapter | `session/request_permission` |

## 当前待办优先级

P0-P2 收口后，近期待办更新为：

### P1

1. subagent runtime 统一：让 subagent 复用主 runtime 的 ToolRegistry、ToolExecutor 和 ApprovalService。

### P2

2. ACP stdio server MVP：基于已完成的内部兼容能力实现 `initialize/session/new/session/prompt/approval/cancel/load`。
3. ACP compatibility polish：根据首个 ACP client 兼容测试补齐 replay 细节、file locations 和 command/mode 暴露。
4. LSP 增强：完整 diagnostics、references/definition 去重、输出 limit、多 workspace cleanup 和多语言 registry。
5. Message Token Manager 后续：多步 operation history、配置化阈值和模型生成式摘要压缩。

### P3

7. 完整本地 eval suite：建立 `evals/tasks/*`，覆盖 bugfix、feature、refactor、tests、security review 等核心任务。
8. DAG / task dependency graph：任务依赖图、复杂并发调度和后台 subagent 编排。

近期明确暂缓：Help modal 额外手动微调，`:messages`/`:plan`/`:diff` 等新 TUI 命令，以及 Message Token Manager 多步 history/config 的立即实现。

## MVP 范围

已完成：

```text
1. 工具 metadata + 调度策略
2. workspace_state + git_diff
3. apply_patch 工具
4. verify 工具
5. 基础代码理解工具
6. 安全审批 v1 + TUI 审批 UI
7. 结构化 TUI 时间流和文件变更视图
8. 基础上下文治理
```

MVP 已完成。P0-P2 收口后，workspace/workdir、Session persistence、LSP 只读 MVP、Message Token Manager 首版、TUI 命令/帮助、长任务摘要记忆首版、本地 evals MVP 和 ACP 兼容前置能力都已进入可用状态。后续重点转为 subagent runtime 统一、ACP stdio MVP、完整 eval suite 和 DAG 调度。

MVP 完成后，yoyoagent 已具备更完整的代码任务闭环：

```text
理解代码 -> 安全编辑 -> 运行验证 -> 读取失败 -> 迭代修复 -> 总结结果
```

## 推荐下一步

当前推荐按增强阶段推进：

1. **subagent runtime 统一**：让 subagent 复用主 runtime 的 ToolRegistry、ToolExecutor 和 ApprovalService，减少主/子 agent 行为差异。
2. **ACP stdio server MVP**：基于已完成的兼容前置能力，实现 `initialize/session/new/session/prompt`，再补 approval、cancel 和 session/load replay。
3. **ACP compatibility polish**：根据 Zed/ACP client 兼容测试补齐 replay 细节、file locations 和 command/mode 暴露。
4. **LSP 增强**：在只读 MVP 基础上继续完善 diagnostics、references/definition 去重、输出 limit、多 workspace cleanup 和多语言 registry。
5. **Message Token Manager 增强**：在最近一次 undo 基础上继续做多步 operation history、配置化阈值和模型生成式摘要压缩。
6. **完整本地 eval suite**：在 `context_session_baseline` 之外增加 bugfix、feature、refactor、tests、security review 任务集。
7. **DAG / task dependency graph**：实现任务依赖图、复杂并发调度和后台 subagent 编排。

已丢弃/暂缓的近期项：

- 不新增 `:messages`、`:plan`、`:diff` 等 TUI 命令。
- 不做 Help modal 额外手动微调。
- 不在近期实现 Message Token Manager 多步 history/config。
