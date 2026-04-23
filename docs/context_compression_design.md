# 自动上下文压缩功能设计文档

## 概述

本文档描述了 yoyoagent 项目中自动上下文压缩功能的架构设计，用于解决 LLM 对话过程中上下文无限增长的问题。

## 问题分析

### 当前架构问题

在现有实现中，`AgentState` 只包含一个无限增长的 `messages` 列表：

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
```

**消息流转过程：**
```
START → llm节点 → (条件边) → tools节点 → llm节点
```

**存在的问题：**
- 无 token 管理机制
- 消息会无限累积
- 最终会超出模型上下文窗口限制
- 导致 API 调用失败或成本过高

## 设计方案

### 触发时机

在 LLM 节点执行**之前**进行压缩检查：

```python
async def llm_node(state: AgentState) -> AgentState:
    # 1. 检查并压缩上下文
    # 2. 调用 LLM
    # 3. 返回结果
```

**触发条件：**
- 基于 token 阈值触发（如：超过模型上下文窗口的 70%）
- 可配置的触发策略

### 压缩策略层次

#### 1. 轻度压缩 (Light Compression)
- **目标**：快速减少 token 使用
- **策略**：仅删除 ToolMessage 内容，保留 tool_call_id 引用
- **适用场景**：token 轻度超标

#### 2. 中度压缩 (Medium Compression)
- **目标**：平衡信息保留和 token 节省
- **策略**：将旧的 Human/AIMessage 对摘要为单条 SummaryMessage
- **适用场景**：token 中度超标

#### 3. 重度压缩 (Heavy Compression)
- **目标**：最大化 token 节省
- **策略**：除最近 K 条消息外全部摘要，保留 system prompt
- **适用场景**：token 严重超标

### 压缩级别配置

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class CompressionLevel:
    """压缩级别配置"""
    token_threshold: int      # 触发压缩的 token 数
    keep_recent: int         # 保留的最近消息数
    strategy: Literal["trim_tool", "summarize", "heavy"]
    description: str = ""

@dataclass
class CompressionConfig:
    """压缩功能配置"""
    enabled: bool = True
    levels: list[CompressionLevel] = field(default_factory=list)
    max_context_tokens: int = 128000  # 默认 Claude 3 Opus 限制
    compression_ratio: float = 0.7    # 触发压缩的比例
```

## 接口设计

### 新增文件结构

```
agent/
├── context_compressor.py  # 核心压缩逻辑
└── state.py               # 扩展 AgentState（可选）
```

### 核心接口定义

```python
from abc import ABC, abstractmethod
from typing import List, Tuple
from langchain_core.messages import BaseMessage
from agent.providers.base import LLMProvider

class ContextCompressor:
    """上下文压缩器"""
    
    def __init__(self, provider: LLMProvider, config: CompressionConfig):
        self.provider = provider
        self.config = config
        self.compression_history = []
    
    async def maybe_compress(
        self, 
        messages: List[BaseMessage]
    ) -> Tuple[List[BaseMessage], bool]:
        """
        检查并压缩上下文
        
        Args:
            messages: 原始消息列表
            
        Returns:
            (压缩后的消息列表, 是否进行了压缩)
        """
        token_count = await self._count_tokens(messages)
        
        if token_count < self._get_threshold():
            return messages, False
        
        level = self._select_compression_level(token_count)
        compressed = self._compress_messages(messages, level)
        
        self._record_compression(token_count, len(compressed), level)
        return compressed, True
    
    async def _count_tokens(self, messages: List[BaseMessage]) -> int:
        """
        使用 provider 计算 token 数
        
        如果 provider 不支持 token 计数，使用估算方法
        """
        pass
    
    def _get_threshold(self) -> int:
        """获取触发压缩的阈值"""
        return int(self.config.max_context_tokens * self.config.compression_ratio)
    
    def _select_compression_level(self, token_count: int) -> CompressionLevel:
        """根据 token 数量选择压缩级别"""
        pass
    
    def _compress_messages(
        self, 
        messages: List[BaseMessage], 
        level: CompressionLevel
    ) -> List[BaseMessage]:
        """执行实际压缩"""
        pass
    
    def _record_compression(
        self, 
        original_tokens: int, 
        compressed_count: int, 
        level: CompressionLevel
    ):
        """记录压缩历史用于监控"""
        pass
```

### 摘要消息类型

```python
from langchain_core.messages import BaseMessage

class SummaryMessage(BaseMessage):
    """摘要消息类型"""
    
    type: str = "summary"
    
    def __init__(self, content: str, original_range: Tuple[int, int]):
        """
        Args:
            content: 摘要内容
            original_range: 原始消息的索引范围 (start, end)
        """
        super().__init__(content=content)
        self.original_range = original_range
```

## 集成方案

### 修改点分析

**需要修改的文件：**
1. `agent/graph.py` - 在 LLM 节点中插入压缩逻辑
2. `agent/providers/base.py` - 可选添加 `count_tokens` 抽象方法

**无需修改的文件：**
- `AgentState` 定义
- 图结构
- 条件边逻辑

### 集成代码示例

在 `agent/graph.py` 的 LLM 节点中集成：

```python
def create_llm_node(
    provider: LLMProvider,
    system_prompt: str,
    session_id: str,
    stream_callback: StreamEventCallback = None,
    compression_config: CompressionConfig = None,
):
    """创建带上下文压缩的 LLM 节点"""
    
    compressor = None
    if compression_config and compression_config.enabled:
        compressor = ContextCompressor(provider, compression_config)
    
    async def llm_node(state: AgentState) -> AgentState:
        """调用 LLM，带上下文压缩"""
        
        # 1. 检查并压缩上下文
        messages_to_use = state["messages"]
        if compressor:
            messages_to_use, did_compress = await compressor.maybe_compress(
                state["messages"]
            )
            if did_compress and stream_callback:
                stream_callback("context_compressed", {
                    "session_id": session_id,
                    "original_count": len(state["messages"]),
                    "compressed_count": len(messages_to_use),
                })
        
        # 2. 构建 provider 格式消息
        anthropic_messages = []
        for msg in messages_to_use:
            # ... 现有消息转换逻辑 ...
        
        # 3. 调用 LLM
        response = await provider.chat(
            messages=anthropic_messages,
            tools=TOOLS,
            system_prompt=system_prompt,
            stream_callback=provider_stream_callback,
        )
        
        # ... 现有返回逻辑 ...
    
    return llm_node
```

### LLMProvider 扩展

可选地在基类中添加 token 计数支持：

```python
class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def chat(...):
        pass
    
    @abstractmethod
    async def close(self) -> None:
        pass
    
    async def count_tokens(self, messages: list[dict]) -> int:
        """
        计算消息的 token 数（可选实现）
        
        默认使用简单估算，子类可以覆盖提供精确计算
        """
        # 简单估算：按字符数估算
        total_chars = sum(len(str(msg)) for msg in messages)
        return total_chars // 4  # 粗略估计：4 字符 ≈ 1 token
```

## 关键考虑

### 向后兼容

```python
# 默认配置禁用压缩，不影响现有功能
default_compression_config = CompressionConfig(
    enabled=False,
    max_context_tokens=128000,
    compression_ratio=0.7,
    levels=[
        CompressionLevel(
            token_threshold=89600,  # 70% of 128k
            keep_recent=10,
            strategy="trim_tool",
            description="轻度压缩：仅修剪工具消息"
        ),
        CompressionLevel(
            token_threshold=102400,  # 80% of 128k
            keep_recent=5,
            strategy="summarize",
            description="中度压缩：摘要旧消息"
        ),
        CompressionLevel(
            token_threshold=115200,  # 90% of 128k
            keep_recent=2,
            strategy="heavy",
            description="重度压缩：最大化压缩"
        ),
    ]
)
```

### 可观测性

通过 `stream_callback` 发出压缩事件：

```python
if stream_callback:
    stream_callback("context_compressed", {
        "session_id": session_id,
        "original_tokens": original_tokens,
        "compressed_tokens": compressed_tokens,
        "compression_ratio": compression_ratio,
        "level_used": level_name,
    })
```

### 扩展性

支持自定义压缩策略：

```python
class CustomCompressionStrategy(ABC):
    """自定义压缩策略接口"""
    
    @abstractmethod
    def should_compress(self, messages: List[BaseMessage], token_count: int) -> bool:
        pass
    
    @abstractmethod
    def compress(self, messages: List[BaseMessage]) -> List[BaseMessage]:
        pass
```

## 实施计划

### Phase 1: 基础框架
- [ ] 创建 `context_compressor.py`
- [ ] 实现 token 计数（估算版本）
- [ ] 实现轻度压缩策略

### Phase 2: 核心功能
- [ ] 实现中度压缩策略
- [ ] 实现重度压缩策略
- [ ] 集成到 graph.py

### Phase 3: 增强功能
- [ ] 精确 token 计数（provider 特定实现）
- [ ] 压缩历史记录
- [ ] 性能监控

### Phase 4: 优化
- [ ] 自定义压缩策略支持
- [ ] 智能压缩级别选择
- [ ] A/B 测试框架

## 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 压缩导致信息丢失 | 高 | 中 | 保守的压缩策略，可配置的保留消息数 |
| 压缩增加延迟 | 中 | 低 | 异步执行，token 估算优化 |
| 摘要质量不稳定 | 中 | 中 | 使用专门的摘要 prompt，可回退 |

## 总结

本设计方案提供了一个灵活、可扩展的自动上下文压缩功能，具有以下优势：

✅ 对现有 LangGraph 流程的改动最小  
✅ 支持多级压缩策略  
✅ 保持向后兼容  
✅ 提供良好的可观测性  
✅ 支持自定义扩展  

通过这个设计，yoyoagent 可以有效地管理上下文长度，避免超出模型限制，同时保持对话的连贯性。
