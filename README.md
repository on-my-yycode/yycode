# Yoyo Agent

作者: yoyofx-g

一个基于 LangGraph 的智能编程助手，支持多 LLM 提供商。

## 快速开始

### 1. 获取代码并安装依赖

```bash
git clone <your-repo-url>
cd yoyoagent

# 推荐：使用 uv 创建环境并安装依赖
uv sync

# 或使用 pip 安装为可编辑包
pip install -e .
```

> 需要 Python 3.10 或更高版本。依赖声明在 `pyproject.toml` 中，包含 TUI、LLM Provider、LangGraph 和 dotenv 支持。

### 2. 配置模型

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 LLM Provider、API Key 和模型名称：

```dotenv
PROVIDER=openai
API_KEY=your-api-key
API_BASE=https://api.openai.com/v1
AI_MODEL=gpt-4o
```

常用配置：

| 变量 | 说明 | 示例 |
|------|------|------|
| `PROVIDER` | LLM 提供商，支持 `anthropic` 或 `openai` | `openai` |
| `API_KEY` | 对应提供商的 API 密钥 | `your-api-key` |
| `API_BASE` | 可选，自定义 API Base/Base URL | `https://api.openai.com/v1` |
| `AI_MODEL` | 模型名称 | `gpt-4o` |

不要把真实 API Key 提交到仓库；本地私密配置只放在 `.env`。

### 3. 启动 TUI

```bash
# 在当前目录启动，默认把当前目录作为被操作工作区
uv run python main.py

# 指定要让 agent 操作的项目目录
uv run python main.py ~/project

# 如果使用 pip 安装，也可以直接运行
python main.py ~/project
```

启动后会进入终端 TUI。你可以直接输入需求，例如：

```text
阅读这个项目并总结结构
修复测试失败的问题
给 README 增加安装说明
```

### 4. 常用运行方式

```bash
uv run python main.py -a              # 自动批准高风险操作
uv run python main.py --debug         # 输出调试日志
uv run python main.py --log-file      # 写入 agent_debug.log
uv run python main.py -s              # 查看当前工作区可恢复的 sessions
uv run python main.py -r <session-id> # 恢复指定 session
uv run python main.py -x <session-id> # 删除指定 session
uv run python main.py -t              # 临时会话，不保存 messages
uv run python main.py --acp           # 启动 ACP stdio server
uv run python main.py acp             # 同上，便于作为子命令使用
```

更多 TUI 快捷键、内置工具和会话说明见 [使用说明](docs/usage.md)。

## 功能特性

- 🖥️ **TUI 终端界面** - 基于 Textual 的现代终端 UI，支持紧凑 Transcript 风格时间线、工具活动摘要、审批弹窗和历史浏览
- 🤖 **多提供商支持** - Anthropic Claude、OpenAI GPT，兼容自定义 API Base
- 🛠️ **丰富的内置工具** - 代码导航 (grep/list_files/read_file/git_diff)、文件编辑 (apply_patch/write_file)、命令执行 (bash)、验证 (verify) 等 16 个自动注册工具
- 📚 **技能系统** - 可扩展的专业知识模块 (code_review、code_workflow、drawio 图表生成)
- 📋 **任务管理** - 自动跟踪 Todo 列表和任务状态，支持任务完成保护
- 🔄 **子代理系统** - 分解复杂任务，支持 explorer/architect/worker/tester/security 五种角色
- 💬 **流式输出** - 结构化事件流，支持实时交互和思考过程展示
- 🔒 **运行时安全审批** - 高风险操作 (文件编辑、命令执行) 需用户确认，静默模式可自动批准
- 🗜️ **上下文压缩** - 长会话自动压缩旧工具输出，避免超出上下文窗口
- 🔁 **智能重试** - LLM 调用和工具执行均支持自动重试

### 最新功能更新

- **更紧凑的 TUI 时间线**：连续工具调用会聚合为活动摘要，例如 `explored 1 file`、`Edited 1 file`，同时保留每个工具调用的关键目标和耗时。
- **更清晰的模型输出**：主时间线中的模型文本采用对话式 Transcript 风格展示，不再重复显示固定助手名称，阅读更接近常见代码代理体验。
- **独立使用说明**：常用启动命令、TUI 快捷键和内置工具清单已整理到 [使用说明](docs/usage.md)，README 保留概览与入口信息。

## 配置参考

### 依赖说明

| 包名 | 最低版本 | 用途 |
|---|---|---|
| **anthropic** | 0.40.0 | Anthropic Claude API 调用 |
| **openai** | 1.0.0 | OpenAI API 调用 |
| **tiktoken** | 0.12.0 | Token 计数与估算 |
| **langgraph** | 0.2.0 | LangGraph 状态图编排 |
| **langchain-core** | 0.3.0 | LangChain 消息类型 (AIMessage, HumanMessage, ToolMessage) |
| **python-dotenv** | 1.0.0 | 加载 `.env` 环境变量 |
| **textual** | 0.80.0 | TUI 终端界面框架 |

> 以上依赖均声明在 `pyproject.toml` 中，`pip install -e .` 会一次性安装所有依赖。

### 环境变量

| 变量 | 说明 | 默认值/示例 |
|------|------|-------------|
| `PROVIDER` | LLM 提供商，支持 `anthropic` 或 `openai` | `anthropic` |
| `API_KEY` | 对应提供商的 API 密钥 | `sk-...` |
| `API_BASE` | 可选，自定义 API Base/Base URL | `https://api.openai.com/v1` |
| `AI_MODEL` | 模型名称 | Anthropic 默认 `claude-3-5-sonnet-20241022`，OpenAI 默认 `gpt-4o` |
| `YOYO_CONTEXT_WINDOW_TOKENS` | 可选，覆盖上下文窗口大小，用于 TUI/CLI 提示符统计；未设置时会按模型推断 | Claude `200000`，Doubao Code `224000`，GPT-4o/4.1/5 `128000` |
| `YOYO_APP_ROOT` | 可选，覆盖 yoyoagent 应用根目录；默认是源码/发行目录 | `/path/to/yoyoagent` |
| `YOYO_RUNTIME_DATA_DIR` | 可选，覆盖运行数据目录；默认等于 `app_root` | `/path/to/yoyoagent` |
| `YOYO_SESSION_DIR` | 可选，覆盖 session messages 保存目录 | `~/.yoyoagent/sessions` |
| `YOYO_SKILL_DIRS` | 可选，额外技能目录，多个目录用逗号分隔；默认技能目录是 `{app_root}/skills` | `../shared-skills` |
| `YOYO_SILENT` / `YOYO_AUTO_APPROVE` | 可选，启用后自动批准高风险操作 | `true` |

高级重试配置：

| 变量 | 说明 | 默认值/示例 |
|------|------|-------------|
| `YOYO_LLM_TIMEOUT_SECONDS` | LLM 单次调用超时时间 | `120` |
| `YOYO_LLM_HEARTBEAT_SECONDS` | LLM 等待期间的心跳提示间隔 | `5` |
| `YOYO_LLM_MAX_RETRIES` | LLM 调用失败后的最大重试次数 | `2` |

> 请勿把真实 API 密钥提交到仓库；建议在 `.env` 中只保存本地私密配置。`.env.example` 也应使用占位符（如 `API_KEY=your-api-key`），避免提交真实或专属密钥。

### 完整命令参考

```bash
python main.py                 # 默认以当前目录作为工作区启动 TUI
python main.py ~/project       # 指定工作区目录启动
python main.py -a              # 自动批准高风险操作
python main.py --debug         # 调试模式，输出详细日志
python main.py --log-file      # 将日志写入 agent_debug.log
python main.py --acp           # 启动 ACP stdio server
python main.py acp             # 同上，便于作为子命令使用
python main.py -s              # 列出当前工作区可恢复的 sessions
python main.py -r abc          # 恢复指定 session 的历史 messages
python main.py -x abc          # 删除指定 session
python main.py -t              # 临时会话，不保存 session messages
```

当前默认入口会启动 TUI 界面。工作区使用位置参数指定；如果不传，则使用启动命令时所在目录。上述 `/p` / `/paste` 多行粘贴辅助函数保留在控制台输入实现中，但默认 TUI 路径不直接使用。

会话 messages 默认保存到 yoyoagent 应用目录下的 `sessions/{workspace_hash}/{session_id}.json`，不会写入被操作项目。默认会保存但不会自动恢复；需要继续旧上下文时先用 `-s` / `--sessions` 查看，再用 `-r <id>` / `--resume <id>` 恢复；不再需要的历史可用 `-x <id>` / `--delete <id>` 删除。

## 项目结构

```
yoyoagent/
├── agent/                    # 核心代理模块
│   ├── graph.py              # LangGraph 状态机编排
│   ├── session.py            # 会话管理 (消息历史、token 统计、上下文压缩)
│   ├── skills.py             # 技能发现与加载
│   ├── subagent.py           # 子代理执行器
│   ├── todo_manager.py       # 任务状态管理器
│   ├── context_compressor.py # 上下文压缩器
│   ├── streaming.py          # 结构化流式事件
│   ├── approval.py           # 运行时审批模型
│   ├── llm_retry.py          # LLM 超时/心跳/重试
│   ├── tool_retry.py         # 工具执行重试
│   ├── message_format.py     # 消息格式转换
│   ├── nodes/                # LangGraph 节点实现
│   │   ├── state.py          # AgentState 定义
│   │   ├── llm_node.py       # LLM 调用节点
│   │   ├── tools_node.py     # 工具执行节点
│   │   └── task_guard_node.py # Task State 完成保护
│   ├── runtime/              # 运行时服务层
│   │   ├── context.py        # AgentRuntimeContext
│   │   ├── tool_registry.py  # 工具注册与绑定
│   │   ├── tool_scheduler.py # 工具并发/串行调度
│   │   ├── tool_executor.py  # 单工具执行流水线
│   │   ├── workflow_guard.py # workspace/git diff 检查
│   │   ├── approval_service.py # 运行时审批服务
│   │   └── tool_events.py    # 工具事件格式化
│   ├── tui/                  # Textual TUI 界面
│   │   ├── app.py            # TUI 应用主入口
│   │   ├── runner.py         # Agent 运行器
│   │   ├── state.py          # TUI 状态管理
│   │   ├── renderers.py      # 时间线渲染
│   │   ├── approval.py       # 审批 UI
│   │   └── styles.tcss       # Textual CSS 样式
│   └── providers/            # LLM 提供商抽象
│       ├── base.py           # LLMProvider 基类
│       ├── anthropic_provider.py
│       └── openai_provider.py
├── tools/                    # 内置工具实现 (16 个工具)
│   ├── apply_patch.py        # 精确文件补丁
│   ├── bash.py               # Shell 命令执行
│   ├── read_file.py / read_many_files.py  # 文件读取
│   ├── write_file.py / edit_file.py       # 文件写入/编辑
│   ├── grep.py               # 正则搜索
│   ├── list_files.py         # 文件列表
│   ├── git_diff.py / git_show.py          # Git 操作
│   ├── workspace_state.py    # 工作区状态
│   ├── verify.py             # 代码验证
│   ├── todo.py               # 任务管理工具
│   ├── subagent.py           # 子代理工具
│   ├── list_skills.py / load_skill.py     # 技能工具
│   └── safety.py             # 安全工具
├── skills/                   # 技能文件目录
│   ├── code_review.md        # 代码审查技能
│   ├── code_workflow.md      # 通用开发工作流
│   ├── plan.md               # 规划/需求澄清技能
│   └── drawio/SKILL.md       # draw.io 图表生成
├── tests/                    # 测试文件 (100+ 测试用例)
├── examples/                 # 示例项目 (贪吃蛇、塔防、数学游戏)
├── docs/                     # 设计文档
├── changes/                  # 变更日志
├── main.py                   # 入口文件 (默认启动 TUI)
└── pyproject.toml            # 项目配置
```

## 使用指南

### 启动

```bash
python main.py                 # 默认启动 TUI 界面
python main.py -a              # 自动批准高风险操作
python main.py --debug         # 调试模式，输出详细日志
python main.py --log-file      # 将日志写入 agent_debug.log
```

### TUI 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Enter` / `Ctrl+J` | 提交输入 |
| `Ctrl+C` | 取消当前任务 |
| `Ctrl+H` | 打开历史记录浏览器 |
| `Ctrl+Shift+C` | 复制时间线内容 |
| `Ctrl+Q` | 退出 |
| `PageUp` / `PageDown` | 滚动时间线 |
| `Home` / `End` | 跳转到时间线顶部/底部 |
| `Esc` | 聚焦输入框 |

### 可用工具

| 工具 | 功能 |
|------|------|
| `read_file` / `read_many_files` | 读取文件内容 |
| `write_file` | 创建新文件 |
| `apply_patch` | 精确编辑已有文件 (推荐) |
| `edit_file` | 文本替换编辑；已有文件编辑优先使用 `apply_patch` |
| `bash` | 执行 Shell 命令 |
| `grep` | 正则搜索文件 |
| `list_files` | 列出工作区文件 |
| `git_diff` / `git_show` | 查看 Git 变更 |
| `workspace_state` | 查看工作区状态 |
| `verify` | 运行测试/检查 |
| `todo` | 任务状态管理 |
| `subagent` | 委派子代理 |
| `list_skills` / `load_skill` | 技能管理 |

## 开发

### 运行测试

```bash
pytest tests/
# 或
uv run pytest tests/
```

### 代码规范

项目使用 ruff 进行代码检查：

```bash
ruff check .
# 或
uv run ruff check .
```

## 文档

详细文档请查看 `docs/` 目录。顶层文档和图表作用如下：

| 文档 | 作用和说明 |
|------|------------|
| [使用说明](docs/usage.md) | 日常启动参数、会话恢复/删除、TUI 快捷键、审批交互、技能与工具清单。 |
| [项目结构](docs/project_structure.md) | 项目目录、核心模块、LangGraph 工作流、runtime 层和当前架构扩展建议。 |
| [代码代理路线图](docs/code_agent_roadmap.md) | 代码代理能力演进路线、已完成项、后续计划和里程碑记录。 |
| [核心工作流](docs/core_workflow.md) | 当前核心执行链路说明，覆盖 Session、graph、nodes、runtime、Task State 和测试覆盖。 |
| [核心工作流重构设计](docs/core_workflow_refactor_design.md) | 将 `graph.py` 拆分为 nodes/runtime 服务的设计背景、目标结构、迁移计划和风险控制。 |
| [完整 TUI 设计](docs/full_tui_design.md) | Textual TUI 的界面布局、交互设计、组件职责和实现方案。 |
| [TUI 流程分析](docs/tui_flow_analysis.md) | TUI 从输入到 Agent 执行、流式事件、渲染和审批的流程梳理。 |
| [上下文压缩设计](docs/context_compression_design.md) | 长会话上下文压缩策略、触发条件、消息裁剪和摘要保留方案。 |
| [会话持久化设计](docs/session_persistence_design.md) | Session messages 本地保存、恢复、列表、删除、临时会话和后续增强设计。 |
| [结构化事件时间线设计](docs/structured_event_timeline_design.md) | 结构化事件时间线的数据模型、事件类型、渲染行为和 UI 演进方案。 |
| [Task Graph DAG 设计](docs/task_graph_dag_design.md) | 面向复杂任务的 DAG 调度、依赖关系、并发执行和状态管理设计。 |
| [LSP 集成设计](docs/lsp_integration_design.md) | Language Server Protocol 集成目标、模块划分、诊断/符号/补全能力和演进计划。 |
| [安全审查报告](docs/security_review_report.md) | 项目安全风险清单、严重程度分级、已有防护和优先行动建议。 |
| [变更日志更新确认计划](docs/confirmed_plan_changelog_update.md) | 更新 changelog 前确认过的执行计划和范围说明。 |
| [工作流 Mermaid 图](docs/workflow_diagram.mmd) | 核心工作流的 Mermaid 源文件，可用于生成流程图。 |
| [工作流 ASCII 图](docs/workflow_diagram_art.txt) | 核心工作流的纯文本图示，便于在终端或 Markdown 中快速查看。 |
| [架构图源文件](docs/yoyoagent_architecture.drawio) / [PNG](docs/yoyoagent_architecture.drawio.png) | Yoyo Agent 架构图的 draw.io 源文件和导出图片。 |
| [核心工作流程图源文件](docs/yoyoagent_core_workflow.drawio) / [PNG](docs/yoyoagent_core_workflow.drawio.png) | 核心工作流 draw.io 源文件和导出图片。 |
| [结构化事件时间线图源文件](docs/structured_event_timeline_design.drawio) / [PNG](docs/structured_event_timeline_design.png) | 结构化事件时间线设计图源文件和导出图片。 |
| [结构化事件时间线流程图源文件](docs/structured_event_timeline_flowchart.drawio) / [PNG](docs/structured_event_timeline_flowchart.drawio.png) | 结构化事件时间线流程图源文件和导出图片。 |

变更日志请查看 `changes/` 目录。

## 许可证

MIT License

Copyright (c) 2025 Yoyo Agent

作者: 张磊, zlhxd, yoyofx, zl.hxd@hotmail.com, vvvv

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
