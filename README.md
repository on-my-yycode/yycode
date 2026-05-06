# Yoyo Agent

一个基于 LangGraph 的智能编程助手，支持多 LLM 提供商。

## 功能特性

- 🖥️ **TUI 终端界面** - 基于 Textual 的现代终端 UI，支持流式事件时间线、审批弹窗和历史浏览
- 🤖 **多提供商支持** - Anthropic Claude、OpenAI GPT，兼容自定义 API Base
- 🛠️ **丰富的内置工具** - 代码导航 (grep/list_files/read_file/git_diff)、文件编辑 (apply_patch/write_file)、命令执行 (bash)、验证 (verify) 等 16 个自动注册工具
- 📚 **技能系统** - 可扩展的专业知识模块 (code_review、code_workflow、drawio 图表生成)
- 📋 **任务管理** - 自动跟踪 Todo 列表和任务状态，支持任务完成保护
- 🔄 **子代理系统** - 分解复杂任务，支持 explorer/architect/worker/tester/security 五种角色
- 💬 **流式输出** - 结构化事件流，支持实时交互和思考过程展示
- 🔒 **运行时安全审批** - 高风险操作 (文件编辑、命令执行) 需用户确认，静默模式可自动批准
- 🗜️ **上下文压缩** - 长会话自动压缩旧工具输出，避免超出上下文窗口
- 🔁 **智能重试** - LLM 调用和工具执行均支持自动重试

## 快速开始

### 安装依赖

```bash
# 使用 uv
uv sync

# 或使用 pip
pip install -e .
```

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

### 配置环境

```bash
cp .env.example .env
# 编辑 .env 文件，配置你的提供商、API 密钥、API Base 和模型
```

常用环境变量：

| 变量 | 说明 | 默认值/示例 |
|------|------|-------------|
| `PROVIDER` | LLM 提供商，支持 `anthropic` 或 `openai` | `anthropic` |
| `API_KEY` | 对应提供商的 API 密钥 | `sk-...` |
| `API_BASE` | 可选，自定义 API Base/Base URL | `https://api.openai.com/v1` |
| `AI_MODEL` | 模型名称 | Anthropic 默认 `claude-3-5-sonnet-20241022`，OpenAI 默认 `gpt-4o` |
| `YOYO_CONTEXT_WINDOW_TOKENS` | 可选，覆盖上下文窗口大小，用于 TUI/CLI 提示符统计；未设置时会按模型推断 | Claude `200000`，Doubao Code `224000`，GPT-4o/4.1/5 `128000` |
| `YOYO_SKILL_DIRS` | 可选，额外技能目录，多个目录用逗号分隔 | `skills,../shared-skills` |
| `YOYO_SILENT` / `YOYO_AUTO_APPROVE` | 可选，启用后自动批准高风险操作 | `true` |

高级重试配置：

| 变量 | 说明 | 默认值/示例 |
|------|------|-------------|
| `YOYO_LLM_TIMEOUT_SECONDS` | LLM 单次调用超时时间 | `120` |
| `YOYO_LLM_HEARTBEAT_SECONDS` | LLM 等待期间的心跳提示间隔 | `5` |
| `YOYO_LLM_MAX_RETRIES` | LLM 调用失败后的最大重试次数 | `2` |

> 请勿把真实 API 密钥提交到仓库；建议在 `.env` 中只保存本地私密配置。`.env.example` 也应使用占位符（如 `API_KEY=your-api-key`），避免提交真实或专属密钥。

### 运行

```bash
python main.py                 # 默认启动 TUI 界面
python main.py --silent        # 静默模式，自动批准高风险操作
python main.py --debug         # 调试模式，输出详细日志
python main.py --log-file      # 将日志写入 agent_debug.log
```

在命令行输入中，可使用 `/p` 或 `/paste` 进入多行粘贴模式，并用单独一行 `/end` 提交。

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
python main.py --silent        # 静默模式，自动批准高风险操作
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

详细文档请查看 `docs/` 目录：

- [项目结构](docs/project_structure.md)
- [代码代理路线图](docs/code_agent_roadmap.md)
- [核心工作流](docs/core_workflow.md)
- [核心工作流重构设计](docs/core_workflow_refactor_design.md)
- [TUI 设计文档](docs/full_tui_design.md)
- [TUI 流程分析](docs/tui_flow_analysis.md)
- [上下文压缩设计](docs/context_compression_design.md)
- [结构化事件时间线设计](docs/structured_event_timeline_design.md)
- [Task Graph DAG 设计](docs/task_graph_dag_design.md)
- [LSP 集成设计](docs/lsp_integration_design.md)
- [安全审查报告](docs/security_review_report.md)
- [架构图 (draw.io)](docs/yoyoagent_architecture.drawio)
- [核心工作流程图 (draw.io)](docs/yoyoagent_core_workflow.drawio)

变更日志请查看 `changes/` 目录。

## 许可证

MIT License

Copyright (c) 2025 Yoyo Agent

作者: 张磊, zlhxd, yoyofx, zl.hxd@hotmail.com

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
