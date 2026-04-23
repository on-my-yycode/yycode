# yoyoagent 核心工作流架构

## 组件工作流图

```
┌─────────────────┐
│  User Input     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                    Session Management                    │
│  (session_id, stream_callback, workdir, system_prompt)   │
└─────────────────────────────┬───────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
     ┌──────────────────┐          ┌──────────────────────┐
     │  LangGraph       │          │   TodoManager        │
     │  (StateGraph)    │◄─────────┤   (Task Tracking)    │
     └────────┬─────────┘          └──────────────────────┘
              │
    ┌─────────┴─────────┐
    │                   │
    ▼                   ▼
┌─────────┐      ┌───────────┐
│ LLM Node│      │Tools Node │
└────┬────┘      └─────┬─────┘
     │                 │
     │         ┌───────┴───────┐
     │         │               │
     │         ▼               ▼
     │  ┌────────────┐  ┌──────────────┐
     │  │  Regular   │  │   Subagent   │
     │  │   Tools    │  │   Runner     │
     │  └────────────┘  └──────┬───────┘
     │                         │
     │                         ▼
     │              ┌─────────────────────┐
     │              │  Subagent Graph     │
     │              │  (Isolated State)   │
     │              └─────────────────────┘
     │                         │
     └─────────────────────────┘
```

## 核心组件说明

### 1. Session管理
- 每个会话有独立的session_id
- 维护stream_callback用于流式输出
- 隔离工作目录(workdir)和系统提示词
- TodoManager实例与会话绑定

### 2. LangGraph工作流 (graph.py)
```
START → llm_node ──┬──→ tools_node → llm_node
                   │
                   └──→ END
```
- `AgentState`: 消息列表状态，使用`add_messages` reducer
- `llm_node`: 调用LLM提供商，支持工具调用和流式输出
- `tools_node`: 执行工具，集成TodoManager和Subagent
- `should_continue`: 条件边判断是否继续工具执行

### 3. LLM节点流程
- 转换消息格式为provider兼容格式
- 调用LLM提供商API (支持流式)
- 解析工具调用返回AIMessage
- 存储原始响应和工具调用数据

### 4. Tools节点流程
- 提取最后的AIMessage中的工具调用
- 根据工具类型分发到不同处理器：
  - `todo`: TodoManager绑定的处理器
  - `subagent`: SubagentRunner
  - 其他: 注册的TOOL_HANDLERS
- 执行工具并生成ToolMessage
- 检查是否需要todo提醒

### 5. Subagent执行器 (subagent.py)
- 四种角色: explorer, architect, tester, worker
- 隔离的对话历史和状态
- 有限的回合数(max_turns)
- 禁用subagent和todo工具防止递归
- 返回格式化结果给父代理

### 6. TodoManager (todo_manager.py)
- 维护todo列表状态(最多20项)
- 跟踪连续非todo轮次
- 3轮无todo调用时触发提醒
- 自动清空已完成的任务列表
- 提供todo工具处理器

## 消息流转详细过程

1. **用户输入** → HumanMessage → AgentState
2. **llm_node**: 
   - 状态消息 → provider格式
   - LLM响应 → AIMessage(含tool_calls)
   - 更新状态
3. **条件判断**:
   - 有tool_calls → 进入tools_node
   - 无tool_calls → 结束
4. **tools_node**:
   - 执行工具 → ToolMessage(s)
   - 可选: todo提醒 → HumanMessage
   - 更新状态
5. **循环**回到llm_node继续处理

## 关键数据流

- `AgentState.messages`: 累积的对话历史
- `tool_calls_data`: 存储在AIMessage.additional_kwargs中
- `TodoManager.todo_items`: 任务列表状态
- `SubagentRunner`: 隔离的消息列表和工具集

这个架构实现了一个灵活的多代理协作系统，支持任务分解、子代理执行和任务跟踪。
