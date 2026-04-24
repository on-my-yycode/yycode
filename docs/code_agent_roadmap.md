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
- 代码理解工具：`list_files`、`read_many_files`、`grep`、`git_show`。
- subagent：`explorer`、`architect`、`worker`、`tester`、`security`。
- 上下文窗口显示和轻度压缩。
- Provider/tokenizer token counting 与估算兜底。
- 主会话工具调用内部并发调度。
- 工具超时控制。
- 工具执行 metadata：副作用、并发策略、默认超时。
- 技能按需加载。

主要欠缺：

- 更强代码导航工具。
- 长任务摘要记忆。
- 安全审批机制。
- 安全审批机制的完整交互 UI。
- 本地 evals。

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
- Phase 7 v1 已实现：危险 bash/git 命令、删除 patch、文件创建/编辑返回 `approval_required` 阻断信息；主会话和 subagent 的写入工具会在控制台请求用户审批后才执行，用户拒绝后终止本轮任务。

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
8. evals
```

其中 MVP 建议先做前 4 项。

## Phase 1: 工具 Metadata 与调度策略

状态：已实现。

### 背景

当前并发、串行、超时规则主要硬编码在 `agent/graph.py` 中。随着工具增加，这种方式会越来越难维护。

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

### 目标

减少 agent 为建立项目地图而反复调用 bash，提高代码理解效率。

### 估算

工作量：小到中，约 `0.5-1 天`。

## Phase 6: 上下文任务摘要

### 背景

当前上下文压缩只压缩旧工具输出。长任务还需要保留任务级摘要，避免丢失关键决策。

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

- 上下文超过阈值。
- 完成一个大的 todo 阶段。
- subagent 返回大量信息后。

### 风险

摘要可能丢失细节，因此应先作为补充消息，不要过早删除关键最近消息。

### 估算

工作量：中到大，约 `1-2 天`。

## Phase 7: 安全审批机制

状态：v1 阻断和控制台交互式审批已实现，图形化审批 UI 未实现。

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

### v1 建议

当前已实现工具层阻断和运行时控制台审批：文件创建/编辑工具默认返回 `approval_required`；在主会话或 subagent 工具执行路径中，runtime 会先暂停并在控制台询问用户，用户批准后才临时注入 `approved=true` 执行；用户拒绝后抛出审批拒绝信号，由 Session 终止本轮任务。后续再升级为：

```text
agent 发起 approval_request
用户点击允许
工具继续执行
```

### 估算

工作量：中到大，约 `1-2 天`。

## Phase 8: Evals

### 目标

建立本地评测集，判断 code agent 是否真的变强。

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

工作量：中，约 `1-2 天`。

## MVP 范围

已完成：

```text
1. 工具 metadata + 调度策略
2. workspace_state + git_diff
3. apply_patch 工具
4. verify 工具
```

预计工作量：`2-4 天`。

MVP 完成后，yoyoagent 将具备更完整的代码任务闭环：

```text
理解代码 -> 安全编辑 -> 运行验证 -> 读取失败 -> 迭代修复 -> 总结结果
```

## 推荐第一步

先实现工具 metadata + 调度策略。

原因：

- 当前并发、串行、超时规则已经开始变多。
- 后续新增 `apply_patch`、`verify`、`git_diff` 都需要声明副作用和超时。
- metadata 能让调度策略从硬编码变成声明式配置。

第一步完成后，再推进 git 工作区保护和 apply_patch，会更稳。
