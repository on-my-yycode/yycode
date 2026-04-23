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
│   ├── graph.py              # LangGraph工作流定义 ⭐
│   ├── subagent.py           # 子代理执行器
│   ├── todo_manager.py       # 任务管理器
│   ├── tool_retry.py         # 工具重试机制
│   ├── streaming.py          # 流式输出处理
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
└── docs/                     # 文档目录
    └── project_structure.md  # 本文档
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
START → [LLM节点] ──(有工具调用)──→ [Tools节点]
    ↑                     ↓
    └─────────────────────┘
         (无工具调用)
         ↓
        END
```

**消息流转**：
1. 从 START 开始进入 LLM 节点
2. LLM 决定是否调用工具
3. 如果有工具调用，进入 Tools 节点执行
4. Tools 执行完后返回 LLM 节点继续
5. 如果没有工具调用，结束对话

### 核心节点

#### LLM 节点 (create_llm_node)
- 接收当前状态中的所有消息
- 转换为 provider 特定格式
- 调用 LLM 并获取响应
- 支持工具调用和流式输出

#### Tools 节点 (create_tools_node)
- 执行 LLM 请求的工具
- 集成 TodoManager 进行任务追踪
- 支持子代理执行
- 包含工具重试机制

## 依赖分析

### 主要依赖
- `anthropic>=0.40.0` - Anthropic AI API
- `openai>=1.0.0` - OpenAI API
- `langgraph>=0.2.0` - LangGraph 工作流框架
- `langchain-core>=0.3.0` - LangChain 核心库
- `python-dotenv>=1.0.0` - 环境变量管理

## 当前架构的问题

### 1. 上下文无限增长
- `AgentState` 中的 `messages` 列表会无限累积
- 没有 token 管理机制
- 可能导致超出模型上下文窗口限制

### 2. 缺乏上下文管理
- 没有自动压缩或摘要机制
- 长期对话会导致性能下降和成本增加

## 扩展建议

1. **添加上下文压缩机制** - 参考 `context_compression_design.md`
2. **增加状态持久化** - 支持对话历史保存和加载
3. **添加指标监控** - 监控 token 使用、响应时间等
4. **支持更多 LLM 提供商** - 扩展 provider 抽象层
