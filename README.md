# Yoyo Agent

一个基于 LangGraph 的智能编程助手，支持多 LLM 提供商。

## 功能特性

- 🤖 多提供商支持 (Anthropic Claude, OpenAI GPT)
- 🛠️ 内置工具集 (文件操作、命令执行、代码编辑)
- 📚 技能系统 - 可扩展的专业知识模块
- 📋 任务管理 - 自动跟踪和提醒
- 🔄 子代理系统 - 分解复杂任务
- 💬 流式输出 - 实时交互体验

## 快速开始

### 安装依赖

```bash
# 使用 uv
uv sync

# 或使用 pip
pip install -e .
```

### 配置环境

```bash
cp .env.example .env
# 编辑 .env 文件，配置你的 API 密钥
```

### 运行

```bash
python main.py
```

## 项目结构

```
yoyoagent/
├── agent/           # 核心代理模块
│   ├── graph.py     # LangGraph 状态机定义
│   ├── session.py   # 会话管理
│   ├── skills.py    # 技能系统
│   └── providers/   # LLM 提供商抽象
├── tools/           # 工具实现
├── skills/          # 技能文件目录
├── tests/           # 测试文件
├── docs/            # 设计文档
└── main.py          # 入口文件
```

## 使用指南

### 基本命令

- `/p` 或 `/paste` - 粘贴多行输入
- `/end` - 结束多行输入
- `clear` - 清空历史
- `q` 或 `exit` - 退出

### 可用工具

- `bash` - 执行 shell 命令
- `read_file` - 读取文件内容
- `write_file` - 写入文件
- `edit_file` - 编辑文件内容
- `list_skills` - 列出可用技能
- `load_skill` - 加载技能
- `todo` - 任务管理
- `subagent` - 委派子任务

## 开发

### 运行测试

```bash
pytest tests/
```

### 代码规范

项目使用 ruff 进行代码检查：

```bash
ruff check .
```

## 文档

详细文档请查看 `docs/` 目录：

- [项目结构](docs/project_structure.md)
- [核心工作流](docs/core_workflow.md)
- [代码审查报告](docs/code_review_report_20250423.md)

## 许可证

MIT License
