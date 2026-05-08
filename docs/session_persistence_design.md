# Session Messages 持久化与恢复设计

## 背景

当前 `Session` 已经有稳定的 `session_id`，并在内存中维护 `Session.messages: list[BaseMessage]`。每轮 `send()` / `send_stream()` 会把用户输入加入 `messages`，调用 LangGraph，并用 `result["messages"]` 更新会话历史。

问题是这些消息只存在进程内存中：

- 进程退出后无法恢复同一会话上下文。
- TUI/CLI 重新启动后，即使知道旧 `session_id`，也没有历史消息可加载。
- 当前 TUI timeline 只适合展示，不应作为模型上下文恢复来源。

## 目标

- 将 `Session.messages` 本地持久化，作为模型上下文恢复来源。
- 支持通过 `session_id` 恢复历史 messages，继续上一轮对话。
- 保持首版实现简单、可测试、低侵入。
- 与现有上下文压缩、Task State 历史治理、workspace/workdir 隔离兼容。

## 非目标

首版不做：

- 持久化 TUI timeline、审批队列、运行中 task 状态。
- 保存流式响应的中间半成品。
- 跨设备同步、远端存储或数据库查询。
- 自动恢复最近会话的复杂选择 UI。
- LangGraph checkpoint 级别的完整图状态恢复。

## 当前实现状态

状态：首版已实现。

已完成：

- 新增 `agent/app_paths.py`，集中解析 `app_root` 和 `runtime_data_dir`。
- 新增 `agent/session_store.py`，实现 `FileSessionStore`、`SessionStoreError` 和 `workspace_hash()`。
- `Session` 支持 `app_root`、`runtime_data_dir`、`persist_messages`、`resume` 和 `message_store`。
- CLI/TUI 支持 `-r` / `--resume <id>`、`-s` / `--sessions`、`-x` / `--delete <id>`、`-t` / `--temp`。
- `send()` / `send_stream()` 在任务结束并裁剪 todo artifacts 后保存 canonical messages。
- `clear()` / `reset()` 会保存空历史。
- 默认 skills 已迁移到 `{app_root}/skills`；`YOYO_SKILL_DIRS` 作为额外技能目录追加。

仍未实现：

- `--resume-latest`。
- `app_root/sessions` 不可写时 fallback 到 `~/.yoyoagent/sessions`。
- 恢复后预压缩。
- 多进程同 session 文件并发写协调。

## 推荐方案

新增独立的 `SessionStore` / `MessageStore` 抽象，负责消息文件的读写、删除和列表。`Session` 只依赖接口，不直接关心文件格式。

### 目录模型

需要明确区分三个目录：

```text
app_root
  yoyoagent 应用/发行版本所在目录，用于保存 yoyoagent 自身资源和运行数据。

workdir
  用户让 yoyoagent 操作的目标项目目录，用于 read_file、apply_patch、bash、git、verify、LSP 等工具。

runtime_data_dir
  yoyoagent 的运行数据目录，首版默认放在 app_root 下。
```

`sessions` 应属于 yoyoagent 应用自身，而不是被操作项目的一部分。因此首版不再建议写入：

```text
{workdir}/.yoyoagent/sessions/
```

推荐默认路径：

```text
{app_root}/sessions/{workspace_hash}/{session_id}.json
```

其中：

```text
workspace_hash = sha256(resolve(workdir))[:16]
```

这样 session 数据由 yoyoagent 应用管理，同时仍按被操作的 workspace 隔离，避免不同项目历史上下文混用。

如果未来支持 pip/系统安装，`app_root/sessions` 可能不可写，可以再增加 fallback：

```text
~/.yoyoagent/sessions/{workspace_hash}/{session_id}.json
```

也可以通过环境变量覆盖：

```text
YOYO_SESSION_DIR=/custom/session/dir
```

首版实现时，应先定义 `app_root` 的解析规则。源码/便携发行下可以用仓库/发行目录作为 `app_root`。

### 与 skills 目录的关系

我们讨论后的目标模型是：

```text
{app_root}/skills
{app_root}/sessions
```

也就是说，默认 skills 和 sessions 都是 yoyoagent 应用自身的一部分，而不是用户 `workdir` 的一部分。

当前代码已经按这个模型收口：

```text
默认技能目录：{app_root}/skills
额外技能目录：YOYO_SKILL_DIRS 指定
```

也就是说，项目内的 `workdir/skills` 不再被默认扫描。如果某个项目确实需要自定义技能，应通过 `YOYO_SKILL_DIRS` 或后续配置文件显式指定。

## 数据格式

建议 JSON 顶层结构：

```json
{
  "version": 1,
  "session_id": "...",
  "created_at": "2026-05-08T12:00:00Z",
  "updated_at": "2026-05-08T12:30:00Z",
  "workdir": "/abs/path/to/workspace",
  "workspace_hash": "16-char-hash",
  "app_root": "/abs/path/to/yoyoagent",
  "model": "...",
  "messages": []
}
```

消息序列化需要保留 LangChain `BaseMessage` 的关键信息：

- message type / role。
- `content`。
- `additional_kwargs`。
- `response_metadata`。
- `tool_calls`。
- `tool_call_id`。
- `name`、`id` 等可用字段。

优先使用 LangChain 官方 message serialization 工具；如果项目中自定义实现，不能只保存 `role/content`，否则工具调用上下文可能丢失。

## SessionStore 接口

建议新增文件：

```text
agent/session_store.py
```

核心接口：

```python
class SessionStore:
    def load(self, session_id: str) -> list[BaseMessage]: ...
    def save(self, session_id: str, messages: list[BaseMessage], metadata: dict | None = None) -> None: ...
    def delete(self, session_id: str) -> None: ...
    def list_sessions(self) -> list[SessionRecord]: ...
```

首版已实现文件版：

```text
FileSessionStore(app_root: Path, workdir: Path, root: Path | None = None)
```

其中 `root` 默认为 `{app_root}/sessions`，测试或高级用户可覆盖。

## Session 生命周期集成

`Session.__init__` 建议增加参数：

```python
persist_messages: bool = True
resume: bool = False
message_store: SessionStore | None = None
```

行为：

1. 初始化：
   - 如果 `persist_messages=True`，创建默认 `FileSessionStore(app_root, workdir)`。
   - 如果 `resume=True` 且存在同 `session_id` 历史，加载到 `self.messages`。
   - 如果 `resume=True` 但文件不存在，使用空历史并继续使用该 `session_id`。
   - 如果历史文件中的 `workdir` 与当前 `Session.workdir.resolve()` 不一致，拒绝恢复并返回清晰错误，避免跨项目混用上下文。
2. 每轮完成：
   - `send()` / `send_stream()` 正常得到最终 `self.messages` 后保存。
   - 建议在 `_prune_todo_artifacts()` 之后保存，避免把已裁剪的内部 todo 工具调用重新落盘。
3. 异常场景：
   - 审批拒绝或 LLM 调用失败时，当前代码会追加终止消息；是否保存该终止消息建议保留，方便用户恢复时知道上轮中断原因。
   - 运行中取消或进程崩溃不保存半成品。
4. `clear()` / `reset()`：
   - 需要明确磁盘语义。推荐首版：`clear()` 只清空内存并保存空历史；`reset()` 清空内存、重置 todo，并删除或覆盖 session 文件。
   - 如果担心误删，可另增显式 `delete_persisted_session()`。

## CLI / TUI 行为

建议参数：

```text
-r, --resume <id>   从指定 session id 的持久化文件恢复 messages
-s, --sessions      列出当前 workdir 下可恢复的 sessions
-x, --delete <id>   删除当前 workdir 下指定 session
-t, --temp          临时会话，不保存 messages
```

推荐默认：

- 默认开启保存。
- 默认不自动恢复历史，必须显式 `-r <id>` / `--resume <id>`。
- 未指定 `--resume` 时生成新 id。
- 指定 `--resume <id>` 时恢复已有历史；如果历史不存在，则以该 id 开始新会话。

后续增强：

```text
--resume-latest
```

TUI 启动信息可以继续显示 `Session ID`，并在恢复成功时补充一行：

```text
Restored messages: N
```

## 与上下文压缩的关系

恢复 messages 后仍需走现有上下文压缩逻辑：

- 发送新用户消息前或后检查 token 压力。
- 如果恢复历史过大，触发 `_compress_context_if_needed()`。
- 后续可增加“恢复后预压缩”，避免第一轮请求时上下文过大。

## 安全与隐私

持久化文件可能包含：

- 用户输入。
- 模型回复。
- 工具输出中的代码片段、路径、diff。
- 可能的敏感信息。

因此需要：

- 在文档中说明 `{app_root}/sessions/` 或 `YOYO_SESSION_DIR` 可能包含敏感上下文。
- 不自动修改用户项目 `.gitignore`。sessions 不应默认写入用户 `workdir`。
- 读写路径必须限制在 yoyoagent 应用数据目录或明确的用户配置目录内。
- 恢复时必须校验 session 文件中的 `workdir` 与当前 `workdir` 一致。
- 文件损坏、版本不兼容时返回清晰错误，不应导致启动崩溃。

## 测试计划

### SessionStore 单元测试

- 保存并恢复 `HumanMessage`。
- 保存并恢复带 `tool_calls` 的 `AIMessage`。
- 保存并恢复 `ToolMessage` 的 `tool_call_id`。
- 空历史保存/加载。
- 文件不存在时返回空历史或清晰状态。
- 损坏 JSON、未知版本、未知 message type 的容错。
- session id 路径逃逸被拒绝。
- 同一个 `workdir` 生成稳定 `workspace_hash`。
- 不同 `workdir` 的同名 session id 不会互相覆盖。
- session 文件 `workdir` 与当前 `workdir` 不一致时拒绝恢复。

### Session 集成测试

- `send()` 正常完成后生成 session 文件。
- 新建同 `session_id` 且 `resume=True` 的 Session 能恢复历史。
- `persist_messages=False` 不写文件。
- `_prune_todo_artifacts()` 后落盘内容不包含已裁剪 todo 工具调用。
- 审批拒绝 / LLM 失败终止消息的保存行为符合预期。
- `clear()` / `reset()` 与磁盘状态一致。

### CLI / TUI 测试

- `-r` / `--resume <id>` 传入 `Session.from_config(session_id=id, resume=True)`。
- `-s` / `--sessions` 输出当前 workdir 下的 session 列表并退出。
- `-x` / `--delete <id>` 删除当前 workdir 下指定 session 文件并退出。
- `-t` / `--temp` 禁止写入。
- TUI startup info 展示恢复状态。

## 实施步骤

1. 新增 `agent/session_store.py`，实现文件版 store 和消息序列化。已完成。
2. 在 `Session` 构造函数和 `from_config()` 中接入 `persist_messages`、`resume`、`message_store`。已完成。
3. 在 `send()` / `send_stream()` 的最终消息更新和 todo artifact 裁剪后保存。已完成。
4. 明确并实现 `clear()` / `reset()` 的持久化语义。已完成，当前语义为保存空历史。
5. 在 `main.py` 和 `agent/tui/runner.py` 增加 CLI/TUI 参数传递。已完成。
6. 更新 README / usage 文档，说明 session id、恢复方式、存储路径和隐私提醒。已完成。
7. 补充单元测试和集成测试。已完成首版。

## 风险

- 简化序列化导致 tool call 上下文丢失，恢复后 provider payload 不合法。
- 历史过大导致恢复后的第一轮请求超上下文窗口。
- 默认持久化可能写入敏感信息。
- `{app_root}/sessions/` 或用户配置的 session 目录如果被误同步/备份，可能泄露对话历史。
- 多进程同时写同一 session 文件可能互相覆盖；首版可不支持并发写，但应采用临时文件 + 原子替换降低损坏概率。
- 如果 `app_root/sessions` 不可写，需要提供清晰错误或 fallback 到用户数据目录。
- 旧行为中默认扫描 `workdir/skills`；当前已迁移到 `{app_root}/skills`，项目级技能需要通过显式额外目录配置。

## 待确认

- 默认是否开启持久化：建议开启保存，但恢复必须显式 `-r <id>` / `--resume <id>`。
- `clear()` / `reset()` 对磁盘文件的精确定义。
- 是否需要 `--resume-latest`。
- `app_root` 如何解析：源码运行、便携发行和未来 pip 安装是否使用不同规则。
- `app_root/sessions` 不可写时是否首版 fallback 到 `~/.yoyoagent/sessions`。
- 是否增加配置文件形式的项目级技能扩展入口。
