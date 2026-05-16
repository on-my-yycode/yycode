# YoyoAgent 项目结构分析

## 项目概述

YoyoAgent 是一个基于 LangGraph 的智能体项目，提供多工具调用和子代理功能。

## 目录结构

```
yoyoagent/
├── __init__.py
├── main.py                    # 项目入口文件
├── pyproject.toml            # 项目配置和依赖
├── uv.lock                   # 依赖锁定文件
├── .env                      # 环境变量配置
├── .env.example              # 环境变量示例
├── .gitignore                # Git忽略文件
│
├── agent/                    # 核心智能体逻辑
│   ├── __init__.py
│   ├── graph.py              # LangGraph薄编排层
│   ├── llm_retry.py          # LLM超时、心跳和重试
│   ├── logger.py             # 调试日志
│   ├── acp/                  # Agent Client Protocol stdio server 与协议适配层
│   ├── cancellation.py       # 共享取消控制器，供 TUI/后续 ACP 复用
│   ├── change_snapshot.py    # 共享文件变更/diff snapshot
│   ├── plan_snapshot.py      # 共享任务计划 snapshot
│   ├── session_replay.py     # 从 canonical messages 派生 replay view model
│   ├── subagent.py           # 子代理执行器
│   ├── todo_manager.py       # 任务管理器
│   ├── task_memory.py        # 长任务摘要记忆：从 Task State 生成可保留的任务摘要
│   ├── tool_retry.py         # 工具重试机制
│   ├── streaming.py          # 流式输出处理
│   ├── session.py             # 会话 facade：messages、graph、persistence、context/token 管理
│   ├── session_store.py       # Session messages 文件持久化与 workspace hash 隔离
│   ├── message_context_manager.py # 当前会话 token 统计、压缩建议和手动压缩辅助
│   ├── lsp/                   # Python 只读 LSP client/manager/types
│   │   ├── client.py          # stdio JSON-RPC LSP client
│   │   ├── manager.py         # language server 检测、懒启动、symbols/definition/hover 等封装
│   │   └── types.py           # Location/Symbol/Diagnostic 数据结构
│   ├── tui/                   # Textual TUI、commands、panels 和状态渲染
│   │   ├── app.py             # 主 TUI、Help/Task/Diff/Message Token modal screens
│   │   ├── runner.py          # TUI 与 Session 的异步桥接
│   │   ├── commands/          # `:` TUI-only 命令，每个命令一个文件
│   │   └── help_content.py    # `:help` 单页帮助内容
│   ├── nodes/                # LangGraph节点实现
│   │   ├── state.py          # AgentState定义
│   │   ├── llm_node.py       # LLM节点
│   │   ├── tools_node.py     # 工具节点
│   │   └── task_guard_node.py # Task State结束保护
│   ├── runtime/              # 运行时服务
│   │   ├── context.py        # AgentRuntimeContext
│   │   ├── tool_registry.py  # 工具绑定和metadata
│   │   ├── tool_scheduler.py # 工具并发/串行调度
│   │   ├── tool_executor.py  # 单工具执行流水线
│   │   ├── workflow_guard.py # workspace/verify guard
│   │   ├── approval_service.py # 运行时审批
│   │   └── tool_events.py    # 工具事件格式化
│   └── providers/            # LLM提供商抽象
│       ├── __init__.py
│       ├── base.py           # LLMProvider基类
│       ├── openai_provider.py
│       └── anthropic_provider.py
│
├── tools/                    # 工具集合
│   ├── __init__.py
│   ├── bash.py               # Shell命令执行
│   ├── edit_file.py          # 文件编辑
│   ├── read_file.py          # 文件读取
│   ├── write_file.py         # 文件写入
│   ├── todo.py               # 任务列表管理
│   ├── web_search.py         # 无需 key 优先的网络搜索
│   └── subagent.py           # 子代理工具
│
├── utils/                    # 工具函数
│   ├── __init__.py
│   └── retry.py              # 重试装饰器
│
├── tests/                    # 测试文件
│   ├── conftest.py
│   ├── test_main_input.py
│   └── test_subagent.py
│
├── examples/                 # 示例代码
│   ├── hello.py
│   ├── utils.py
│   ├── test_hello.py         # 单元测试
│   └── test_utils.py         # 单元测试
│
├── evals/                    # 本地行为评估基线，用于 context/session 等核心行为回归
│   ├── run.py                # eval runner
│   ├── common.py             # eval helper 和 fake provider
│   └── tasks/                # 具体 eval 任务，当前包含 context_session_baseline
│
└── docs/                     # 文档目录
    ├── usage.md                              # 日常启动、会话、TUI、审批、技能和工具使用说明
    ├── project_structure.md                  # 项目结构、模块职责、工作流和扩展建议（本文档）
    ├── code_agent_roadmap.md                 # 代码代理能力路线图、实施状态和后续计划
    ├── core_workflow.md                      # 当前核心工作流架构与 runtime 执行链路
    ├── core_workflow_refactor_design.md      # 核心工作流拆分重构的设计、迁移计划和风险控制
    ├── full_tui_design.md                    # Textual TUI 完整界面与交互设计
    ├── tui_flow_analysis.md                  # TUI 输入、事件流、渲染和审批流程分析
    ├── context_compression_design.md         # 长会话上下文压缩触发、裁剪和摘要策略
    ├── long_task_summary_memory_design.md    # 长任务摘要记忆、触发策略、压缩边界和实现阶段
    ├── session_persistence_design.md         # Session messages 保存、恢复、列表、删除和临时会话设计
    ├── structured_event_timeline_design.md   # 结构化事件时间线的数据模型和 UI 演进方案
    ├── task_graph_dag_design.md              # 复杂任务 DAG 调度、依赖关系和状态管理设计
    ├── lsp_integration_design.md             # LSP 集成目标、模块划分、诊断和符号能力设计
    ├── security_review_report.md             # 安全风险清单、已有防护和优先行动建议
    ├── confirmed_plan_changelog_update.md    # changelog 更新前确认的执行计划
    ├── workflow_diagram.mmd                  # 核心工作流 Mermaid 图源文件
    ├── workflow_diagram_art.txt              # 核心工作流 ASCII 图
    ├── yoyoagent_architecture.drawio(.png)   # 架构图源文件及导出 PNG
    ├── yoyoagent_core_workflow.drawio(.png)  # 核心工作流程图源文件及导出 PNG
    ├── structured_event_timeline_design.drawio / .png
    │                                         # 结构化事件时间线设计图源文件及导出 PNG
    └── structured_event_timeline_flowchart.drawio / .drawio.png
                                              # 结构化事件时间线流程图源文件及导出 PNG
```

## 核心架构分析

### AgentState 状态定义

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
```

**特点**：
- 只包含一个无限增长的 `messages` 列表
- 使用 `add_messages` reducer 进行消息合并
- 无token管理机制

### 工作流图 (LangGraph)

```
START → [LLM节点] ──(有工具调用)──→ [Tools节点] ──→ [LLM节点]
                 └─(无工具调用)──→ [Task Guard] ──→ END 或 LLM节点
```

**消息流转**：
1. 从 START 开始进入 LLM 节点
2. LLM 决定是否调用工具
3. 如果有工具调用，进入 Tools 节点执行
4. Tools 执行完后返回 LLM 节点继续
5. 如果没有工具调用，进入 Task Guard
6. Task State 完成后结束，否则追加提醒并回到 LLM 节点

### 核心节点

#### LLM 节点 (create_llm_node)
- 接收当前状态中的所有消息
- 转换为 provider 特定格式
- 调用 LLM 并获取响应
- 支持工具调用和流式输出

#### Tools 节点
- 从 AIMessage 中提取工具调用
- 使用 RuntimeToolRegistry 解析工具
- 使用 ToolScheduler 调度并发/串行执行
- 使用 ToolExecutor 执行单个工具调用
- 使用 WorkflowGuard 追加验证提醒

#### Runtime 层
- `ToolRegistry`: 绑定 todo、skills、subagent 和普通工具
- `ToolScheduler`: 保持顺序的并发/串行调度
- `ToolExecutor`: 审批、执行、事件、ToolMessage
- `WorkflowGuard`: workspace preflight、写入保护、verify reminder
- `ApprovalService`: 审批缓存、diff preview、approved=true 注入

## 依赖分析

### 主要依赖
- `anthropic>=0.40.0` - Anthropic AI API
- `openai>=1.0.0` - OpenAI API
- `langgraph>=0.2.0` - LangGraph 工作流框架
- `langchain-core>=0.3.0` - LangChain 核心库
- `python-dotenv>=1.0.0` - 环境变量管理

## 当前架构的问题

### 1. 更复杂的异步 DAG 尚未实现
- 当前工具调度支持批次并发
- 还不是完整 task graph / dependency graph
- 后续可在 ToolScheduler 基础上扩展依赖关系

### 2. Git worktree 任务隔离尚未实现
- 当前 runtime 已统一 workspace/workdir 约束
- 后续可为单个任务创建独立 worktree/branch，降低主工作区污染风险

## 扩展建议

1. **实现 Git worktree 任务隔离执行模式** - 支持任务级独立工作区、diff 收集和清理/合并语义
2. **实现任务依赖图调度** - 在 ToolScheduler 基础上支持 DAG
3. **补齐完整本地 eval suite** - 覆盖 bugfix、feature、refactor、tests、security review
4. **添加指标监控** - 监控 token 使用、响应时间等
