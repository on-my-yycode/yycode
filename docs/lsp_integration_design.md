# LSP 集成设计

## Summary

在 code agent 中集成 LSP 的核心目的，是为 agent 提供稳定、结构化、低幻觉的代码理解能力。LSP 不应该直接暴露给模型操作协议细节，而应该被封装成一组只读代码导航工具，让模型通过工具获取定义、引用、符号、类型信息和诊断。

MVP 建议先做只读语义导航，不做 rename、code action 等写入型能力。

## 为什么需要 LSP

当前 yoyoagent 已经有文本级代码理解工具：

- `list_files`
- `read_file`
- `read_many_files`
- `grep`
- `git_show`
- `git_diff`

这些工具适合快速查找文本和读取上下文，但对于大型代码库，单靠文本搜索容易出现：

- 找到同名但无关的符号。
- 漏掉动态 import 或跨文件引用。
- 不知道函数、类、变量的真实定义位置。
- 难以获取类型、签名和诊断。
- 重构前无法准确判断影响面。

LSP 可以补齐语义级理解：

- `definition`：跳到定义。
- `references`：找到真实引用。
- `hover`：获取类型、签名、docstring。
- `documentSymbol`：列出当前文件符号。
- `workspaceSymbol`：在项目内搜索符号。
- `diagnostics`：获取语法、类型或语言服务器诊断。

## 设计原则

- LSP 是代码理解层能力，不替代现有文件工具。
- 先做只读工具，避免把 rename/codeAction 的复杂写入风险提前引入。
- 模型不直接处理 JSON-RPC/LSP 协议，只调用高层工具。
- 工具输出必须模型友好，优先返回文件路径、行列、符号名和简短摘要。
- LSP 失败时要给出清晰错误，并允许 agent fallback 到 `grep` / `read_file`。
- 写入型 LSP 能力后续必须走审批、diff preview 和 workflow guard。

## 推荐架构

```text
Agent / Subagent
  -> LSP tools
      -> LspManager
          -> LspClient
              -> language server process
```

建议目录：

```text
agent/lsp/
  __init__.py
  manager.py
  client.py
  types.py

tools/
  lsp_document_symbols.py
  lsp_workspace_symbols.py
  lsp_definition.py
  lsp_references.py
  lsp_hover.py
  lsp_diagnostics.py
```

### `LspManager`

职责：

- 根据文件类型或语言懒启动 language server。
- 维护 workspace root。
- 缓存 client 实例。
- 管理 server 生命周期。
- 提供统一的高层方法。

示例接口：

```python
class LspManager:
    async def document_symbols(self, path: str) -> list[Symbol]:
        ...

    async def workspace_symbols(self, query: str) -> list[Symbol]:
        ...

    async def definition(self, path: str, line: int, character: int) -> list[Location]:
        ...

    async def references(self, path: str, line: int, character: int) -> list[Location]:
        ...

    async def hover(self, path: str, line: int, character: int) -> str:
        ...

    async def diagnostics(self, path: str | None = None) -> list[Diagnostic]:
        ...
```

### `LspClient`

职责：

- 启动 language server 子进程。
- 处理 JSON-RPC 消息头和 body。
- 发送 `initialize`、`initialized`。
- 根据需要发送 `textDocument/didOpen`。
- 封装 request/response correlation。
- 支持超时和关闭。

## MVP 工具设计

### `lsp_document_symbols`

列出单个文件中的类、函数、变量等符号。

输入：

```json
{
  "path": "agent/session.py"
}
```

输出：

```text
symbols:
- class Session agent/session.py:25
- method Session.send agent/session.py:296
- function infer_context_window_tokens agent/session.py:392
```

### `lsp_workspace_symbols`

在整个项目内按符号名搜索。

输入：

```json
{
  "query": "Session"
}
```

输出：

```text
symbols:
- class Session agent/session.py:25
- function create_session tests/test_main_input.py:...
```

### `lsp_definition`

根据文件位置跳到定义。

输入：

```json
{
  "path": "main.py",
  "line": 186,
  "character": 26
}
```

输出：

```text
definitions:
- agent/session.py:296:15 Session.send
```

### `lsp_references`

根据文件位置找引用。

输入：

```json
{
  "path": "agent/session.py",
  "line": 296,
  "character": 15,
  "include_declaration": false
}
```

输出：

```text
references:
- main.py:186:18
- tests/test_main_input.py:245:24
```

### `lsp_hover`

获取符号类型、签名和文档。

输入：

```json
{
  "path": "agent/session.py",
  "line": 296,
  "character": 15
}
```

输出：

```text
hover:
async def send(self, content: str) -> AIMessage
Send a user message and get response.
```

### `lsp_diagnostics`

获取语言服务器诊断。

输入：

```json
{
  "path": "agent/session.py"
}
```

输出：

```text
diagnostics:
- agent/session.py:120:8 warning reportOptionalMemberAccess ...
- agent/session.py:240:4 error ...
```

## 语言支持顺序

### Phase 1: Python

优先接入 Python，因为当前 yoyoagent 主体是 Python。

候选 language server：

- `pyright-langserver`
- `python-lsp-server`

建议优先级：

- 如果环境有 `pyright-langserver`，优先使用。
- 否则检测 `pylsp`。
- 都不存在时返回清晰错误，并建议 fallback 到 grep/read_file。

### Phase 2: TypeScript / JavaScript

候选 language server：

- `typescript-language-server`

适合后续支持前端项目、React 项目和 Node 项目。

### Phase 3: 多语言扩展

后续可按项目需要增加：

- Go: `gopls`
- Rust: `rust-analyzer`
- Java: `jdtls`

## 与 Subagent 的关系

LSP 特别适合 `explorer` 和 `architect`：

- `explorer` 优先用 LSP 找定义、引用和符号图，减少盲目 grep。
- `architect` 用 LSP 判断影响面和模块边界。
- `worker` 在改代码前可用 LSP 定位修改点。
- `tester` 可用 diagnostics 辅助定位类型/语法问题。
- `security` 可用 references 追踪输入、权限和命令执行链路。

建议在 prompt 中加入：

```text
For semantic code navigation, prefer LSP tools when available:
lsp_workspace_symbols, lsp_document_symbols, lsp_definition, lsp_references,
lsp_hover, and lsp_diagnostics. Fall back to grep/read_file when LSP is unavailable
or when plain text search is more appropriate.
```

## 与现有工具的分工

```text
list_files/read_file/read_many_files  -> 文件和上下文读取
grep                                 -> 文本搜索
git_show/git_diff                    -> 历史和变更理解
LSP tools                            -> 语义导航
verify                               -> 测试和检查
apply_patch                          -> 修改代码
```

LSP 工具通常返回位置，agent 仍应配合 `read_file` 或 `read_many_files` 读取附近代码。

## 错误与降级

常见失败：

- language server 未安装。
- language server 启动失败。
- 项目依赖未安装，导致索引不完整。
- 文件不在 workspace 内。
- 符号位置无结果。
- 请求超时。

工具返回示例：

```text
status: unavailable
reason: pyright-langserver not found
fallback: use grep and read_file for text-based navigation
```

或者：

```text
status: no_results
query: SessionManager
fallback: try grep with the symbol name
```

## 安全边界

MVP 只读 LSP 工具不需要审批。

后续如果引入写入型能力：

- `rename`
- `codeAction`
- `organizeImports`
- `formatDocument`

必须接入：

- workspace path 校验。
- 写入前 diff preview。
- 用户审批。
- `apply_patch` 或等价 patch 执行路径。
- 修改后 verify reminder。

## 测试计划

- 工具注册测试：所有 LSP 工具出现在 `TOOLS`。
- manager 测试：按语言懒启动 client。
- client 测试：使用 fake JSON-RPC server 验证 request/response。
- path 安全测试：workspace 外路径被拒绝。
- timeout 测试：server 无响应时返回清晰错误。
- fallback 测试：language server 不存在时返回 `status: unavailable`。
- Python 集成测试：在小型 fixture 项目中验证 document symbols、definition、references、diagnostics。
- 回归测试：现有 grep/read_file/apply_patch/verify 行为不受影响。

## 落地顺序

1. 新增 `agent/lsp/types.py`，定义 `Location`、`Symbol`、`Diagnostic`。
2. 新增 `agent/lsp/client.py`，实现最小 JSON-RPC client。
3. 新增 `agent/lsp/manager.py`，支持 Python language server 检测和懒启动。
4. 新增 `lsp_document_symbols` 和 `lsp_workspace_symbols`，先跑通符号查询。
5. 新增 `lsp_definition` 和 `lsp_references`。
6. 新增 `lsp_hover` 和 `lsp_diagnostics`。
7. 更新主 agent 和 subagent prompt，引导优先使用 LSP 做语义导航。
8. 后续支持 TypeScript / JavaScript。

## 工作量评估

MVP 只读 Python LSP：

```text
预计 2-4 天
```

原因：

- JSON-RPC client 和 language server 生命周期需要较细测试。
- LSP 初始化和文件打开流程容易有边界问题。
- 需要兼容 language server 未安装的情况。

如果后续加 TypeScript：

```text
额外 1-2 天
```

如果加入 rename/codeAction 写入能力：

```text
额外 2-4 天
```

建议在当前阶段先把只读导航做扎实，不急着做写入型 LSP 操作。

