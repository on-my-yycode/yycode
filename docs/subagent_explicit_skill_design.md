# Subagent 显式 Skill 委派设计

## 背景

当前主 agent 已支持将任务委派给固定角色的 subagent，subagent 也能通过 `list_skills` / `load_skill` 发现和加载本地 skills。

但现有能力仍有一个明显缺口：用户无法稳定表达“让某个 subagent 带着某个 skill 去完成这段独立工作”。例如：

```text
@architect /plan 设计插件系统
@tester /code_review 检查测试覆盖
@security /code_review 审查认证模块风险
```

这不是单纯的语法糖。它的核心意图是让 skill 从“主 agent 的提示词插件”升级为“可以被 subagent 隔离执行的能力模块”。

## 设计意图

### 1. 避免 skill 污染主上下文

某些 skill 适合独立思考或专项审查，例如 `/plan`、`/code_review`、安全审查、设计图生成等。如果主 agent 直接加载这些 skill，后续实现阶段可能继续携带规划型、审查型或文档型约束，影响执行风格，也增加上下文噪音。

更理想的方式是：

```text
主 agent 负责调度和整合
subagent 加载指定 skill 并隔离执行
主 agent 只接收压缩后的结果
```

这样方案讨论、审查过程、专项推理都可以被限制在 subagent 上下文内。

### 2. 让用户明确指定“谁用什么能力做什么”

`@architect /plan 设计插件系统` 同时表达了三件事：

```text
执行者：architect subagent
能力：plan skill
任务：设计插件系统
```

这比自然语言里的“你找个架构师用 plan 讨论一下”更稳定，也更容易被系统、TUI 和测试识别。

### 3. 让 subagent 成为 skill 的执行容器

skill 不再只服务于主 agent。它可以和 subagent role 组合：

```text
@architect /plan ...
@tester /code_review ...
@security /code_review ...
@worker /code_workflow ...
```

长期看，这会自然演进到 profile 化 subagent：

```text
@frontend /react ...
@backend /database ...
@release-manager /changelog ...
```

本质是：

```text
role/profile + selected skills + scoped task + tool permissions
```

### 4. 减少主 agent 的认知负担

主 agent 不需要同时承担专项 skill 的长指令、完整讨论过程和最终实现。它可以把一段任务委派出去，再基于 subagent 返回的结果继续执行、确认或总结。

### 5. 支持重复讨论但不干扰执行上下文

这与 `/plan` skill 的设计目标一致：方案讨论可以多轮、发散、反复修订；真正执行时，主上下文应该拿到精炼后的结论，而不是被完整讨论过程拖累。

## 目标

- 支持用户表达 `@<subagent> /<skill> <task>` 这类显式委派意图。
- 第一版优先让 `subagent` 工具支持结构化 `skills` 参数。
- 让指定 skill 在 subagent 上下文内加载并执行。
- 主 agent 仍作为调度者，负责 Task State、最终决策和结果整合。
- subagent 执行完成后，将带来源信息的结果返回主 agent 上下文。
- 不破坏现有普通对话、根级 `/skill` 补全和 subagent 安全边界。

## 非目标

- 第一版不在 TUI/Session 层硬拦截用户输入。
- 第一版不绕过主 agent 直接启动 subagent。
- 第一版不开放任意动态 subagent role。
- 第一版不实现 skill 参数，例如 `/plan --depth=high`。
- 不允许 subagent 继续调用 `subagent` 或 `todo`。
- 不改变现有 skill 文件格式。

## 推荐协议

长期用户协议：

```text
@<subagent> /<skill> <task>
```

示例：

```text
@architect /plan 设计插件系统
```

多 skill 可作为后续扩展：

```text
@architect /plan /drawio-skill 设计架构并给出图示方案
```

第一版不一定要在输入层解析这个协议。可以先通过主 agent system prompt 约定：

```text
When the user writes "@architect /plan task", call the subagent tool with
role="architect", skills=["plan"], and task="task".
```

这样可以先复用现有主 agent 调度链路，避免硬编码 parser 破坏普通 `@` 文本、根级 `/skill` 或多语言输入。

## 第一版 MVP

状态：已实现。

第一版建议只做核心能力：

```text
subagent tool schema 增加 skills: string[]
SubagentRunner.run 增加 explicit_skills / skills 参数
runner 校验 skill 是否存在
runner 预加载指定 skill 内容并注入 subagent system prompt
subagent result 增加 skills 字段
主 agent system prompt 增加 @role /skill 调用约定
```

当前实现：

- `tools/subagent.py` schema 已增加 `skills: string[]`。
- `SubagentRunner.run(..., skills=None)` 已支持显式 skills。
- runner 会规范化 `/skill` / `skill` 写法，去重并忽略空值。
- runner 会在 provider 调用前加载指定 skills，并注入 subagent system prompt。
- unknown skill 会返回明确错误，不启动 provider 调用。
- `Subagent result` 已包含 `skills: ...`。
- `subagent_started` / `subagent_finished` 事件 metadata 已包含 `skills`。
- 主 agent system prompt 已加入 `@role /skill` 的调度约定。

### 为什么不先做硬 parser

硬 parser 会带来很多边界：

- 普通文本里的 `@someone`。
- 根级 `/plan` 与 `@role /plan` 的区别。
- 中文/英文空格和标点。
- skill 名称中可能有 `-`、数字或路径式引用。
- 多 skill、未来参数、profile 等扩展。

第一版让主 agent 根据提示词调用结构化工具，改动更小，也不会绕开 Task State 和审批流程。

### 为什么由 runner 预加载 skill

旧方案中考虑让 subagent 自己调用 `load_skill`。这有可审计性，但存在三个问题：

- 模型可能忘记调用。
- 会多一轮工具调用。
- 测试只能验证 prompt 提醒，无法保证行为。

第一版建议 `SubagentRunner` 在启动前做确定性加载：

```text
validate selected skills
load selected skills from SkillRegistry
append loaded skill instructions to subagent system prompt
```

这样行为稳定、测试简单，也更符合“skill 在 subagent 上下文内执行”的目标。主 agent 不加载完整 skill 内容，只传 skill 名称；加载发生在 subagent runner 内部。

审计信息可通过以下方式保留：

- `subagent_started` 事件 metadata 增加 `skills`。
- `format_subagent_result` 输出 `skills: ...`。
- TUI 时间线显示 `@architect using /plan`。

## Subagent Tool Schema

当前 `subagent` 工具参数类似：

```text
role
task
context
max_turns
```

建议增加：

```json
{
  "skills": {
    "type": "array",
    "items": {"type": "string"},
    "description": "Optional skill names to load into the subagent context before it starts."
  }
}
```

示例工具调用：

```json
{
  "role": "architect",
  "task": "设计插件系统",
  "skills": ["plan"]
}
```

第一版仍只允许已有固定 role：

```text
explorer
architect
tester
security
worker
```

## SubagentRunner API

建议扩展为：

```python
async def run(
    role: str,
    task: str,
    context: str = "",
    max_turns: int = DEFAULT_MAX_TURNS,
    skills: list[str] | None = None,
) -> str:
    ...
```

内部行为：

1. 校验 role 是否在 `ROLE_PROMPTS`。
2. 规范化 `skills`，去重并忽略空字符串。
3. 用 `SkillRegistry` 加载指定 skills。
4. 如果任何 skill 不存在，返回明确错误，不启动 provider 调用。
5. 将 loaded skill 内容注入 subagent system prompt。
6. 执行 subagent。
7. 结果中包含 role、skills、session_id、status。

错误示例：

```text
Error: Unknown skill: /foo
Available skills: code_review, code_workflow, drawio-skill, plan
```

## Prompt 注入建议

当指定 skills 非空时，在 subagent system prompt 后追加：

```text
Explicit skills selected by the parent:
- plan

Loaded skill instructions:

## plan
Source: ...
Description: ...

...

You must follow the loaded skill instructions for this delegated task.
If a selected skill is not suitable for the task, mention that in your result.
```

注意：

- 这段内容只进入 subagent system prompt。
- 主 agent system prompt 不注入完整 skill。
- subagent 返回结果后，主 agent 只看到总结结果和来源信息。

## 主 Agent 调度约定

主 agent system prompt 增加轻量规则：

```text
If the user writes a request like "@architect /plan design X", interpret it as an explicit subagent delegation:
- role = architect
- skills = ["plan"]
- task = "design X"
Call the subagent tool with those fields instead of loading the skill in the main context.
```

主 agent 仍必须：

- 维护 Task State。
- 判断是否需要继续实现、询问用户或只返回 subagent 结果。
- 尊重审批和工作区安全规则。
- 在最终回复中说明结果来自哪个 subagent 和 skill。

## 结果回传格式

建议扩展现有 `format_subagent_result`：

```text
Subagent result
role: architect
skills: plan
session_id: xxx
status: completed

...
```

如果没有显式 skill：

```text
skills: none
```

主 agent 最终回复可以引用：

```text
@architect /plan 给出的方案是...
```

## TUI 交互设计

TUI 交互不是第一版阻塞项，但长期建议支持。

### `@` 触发 subagent completion

```text
@
```

候选：

```text
@explorer    investigate codebase
@architect   design technical approach
@worker      implement focused changes
@tester      verify and test
@security    review security risks
```

### `@role /` 触发 skill completion

```text
@architect /
```

候选：

```text
/plan           planning-only solution
/code_review    code quality review
/code_workflow  coding workflow
/drawio-skill   diagrams and visualizations
```

### 状态预览

输入区或状态栏可以显示解析结果：

```text
Delegate: @architect · skills: /plan
```

根级 `/plan` 保持现有行为，不被 subagent 委派解析污染。

## 分阶段实施

### Phase 1：工具级显式 skill

状态：已完成。

- 扩展 `tools/subagent.py` schema，增加 `skills`。
- 扩展 `SubagentRunner.run(...)`，支持 `skills`。
- runner 校验并加载 skills。
- 将 loaded skill 内容注入 subagent system prompt。
- 结果格式增加 `skills`。
- 主 agent system prompt 增加 `@role /skill` 调度约定。

### Phase 2：事件与 TUI 展示

状态：部分完成。

- `subagent_started` / `subagent_finished` 事件 metadata 增加 skills。
- 时间线显示 `@architect using /plan`。
- subagent 详情中展示 loaded skills。

### Phase 3：TUI 补全与预览

- `@` role completion。
- `@role /` skill completion。
- delegated preview。
- unknown role / unknown skill inline feedback。

### Phase 4：输入层 parser

- 如果模型侧约定不够稳定，再新增轻量 parser。
- parser 只负责将明显的 `@role /skill task` 转成主 agent 可理解的上下文或直接工具意图。
- 不应绕过主 agent 的 Task State 和最终决策。

### Phase 5：Profile 化 subagent

- 支持配置化 subagent profile。
- profile 映射到 base role、默认 skills、额外 prompt 和工具权限。
- 支持 `@frontend`、`@backend`、`@designer` 等项目级或内置 profile。

### Phase 6：高级能力

- 多 skill：`@architect /plan /drawio-skill ...`
- skill 参数：`@worker /code_workflow --scope=tests ...`
- profile 默认 skill。
- artifact 返回，例如设计文档、drawio、PNG、测试报告等。

## 测试建议

### Tool Schema Tests

- `subagent` schema 包含 `skills`。
- `skills` 是字符串数组。
- 旧调用不带 `skills` 仍兼容。

### Runner Tests

- `skills=["plan"]` 会加载 plan skill 并注入 subagent prompt。
- unknown skill 返回明确错误，不调用 provider。
- result 中包含 `skills: plan`。
- 未传 skills 时结果包含 `skills: none` 或保持兼容格式。
- 多 skill 参数虽然第一版不暴露语法，但 runner 可接受 list。

### Prompt Tests

- 主 agent system prompt 描述 `@role /skill` 调度约定。
- subagent prompt 中只包含指定 skill 的完整内容。
- 主 agent prompt 不注入完整 skill 内容。

### Integration Tests

模拟主 agent 调用：

```json
{
  "role": "architect",
  "task": "设计插件系统",
  "skills": ["plan"]
}
```

期望：

- 启动 architect subagent。
- subagent prompt 中包含 plan skill。
- 结果回到主 agent。
- 主 agent 最终回复中引用 subagent 来源。

### TUI Tests（后续）

- `@` 显示 role completion。
- `@architect /` 显示 skill completion。
- 根级 `/` completion 保持原行为。
- unknown role / unknown skill 有提示。

## 风险与边界

- role 和 skill 概念容易混淆，需要在 UI 和错误提示中明确区分。
- 不建议第一版开放任意动态 role，避免安全边界复杂化。
- skill 内容可能较长；只应注入显式选择的 skills。
- `@role /skill` 不应破坏现有根级 `/skill` 补全。
- 如果 skill 会创建文件、执行命令或生成 artifact，仍必须走现有审批流程。
- runner 预加载 skill 后，时间线不会出现 subagent 自己调用 `load_skill` 的工具事件；需要用 subagent metadata 和 result 字段补足审计信息。

## 推荐结论

将能力设计为通用显式委派协议：

```text
@<subagent> /<skill> <task>
```

但第一版不要先做输入层硬解析，也不要依赖 subagent 自己调用 `load_skill`。推荐先实现工具级能力：

```text
subagent(role, task, skills=["plan"])
```

这样可以最小改动地实现核心目标：

- skill 在 subagent 上下文中隔离执行。
- 主 agent 不被完整 skill 污染。
- 用户意图可以结构化表达。
- 后续 TUI 补全、parser、profile 化 subagent 都有稳定基础。
