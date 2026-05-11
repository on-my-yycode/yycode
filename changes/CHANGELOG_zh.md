# 变更日志

本项目的所有重要变更都将记录在此文件中。

## [0.3.2] - 2026-05-11

### 新功能
- 新增 Python 只读 LSP 语义导航工具，支持 document/workspace symbols、definition、references、hover、diagnostics fallback，并在时间流中标记语义导航活动
- 新增 Message Token Manager 上下文分析、旧工具输出手动压缩，以及最近一次手动压缩撤销能力
- 新增 TUI 命令与帮助体验，包括 `:help`、`:clear`、`?` 打开帮助，以及命令补全
- 增强 session 持久化容错，覆盖损坏 session 文件、保存失败、删除缺失 session 和列表腐坏元数据场景

### 改进
- 通过 timeline item 渲染缓存、任务运行中轻量 Markdown、任务结束后完整 Markdown/代码高亮，降低 TUI Markdown 渲染成本
- 增强 workspace/workdir 安全边界，补充绝对路径、符号链接逃逸、嵌套 workspace 和 apply_patch 边界覆盖
- 过滤 LSP 噪声符号，并忽略 workspace 外部 LSP location
- 刷新路线图、使用说明和项目结构文档，使其与当前实现保持一致

### 测试
- 扩展 LSP、session store、workspace 边界、apply_patch 安全、TUI runner、token manager 和 subagent 回归覆盖

## [0.3.1] - 2026-05-08

### 新功能
- 新增 CLI 会话管理快捷参数：`-s` 列出会话、`-r <id>` 恢复会话、`-x <id>` 删除会话、`-t` 启动临时会话
- 新增更紧凑的 Transcript 风格 TUI 时间线，可将连续工具调用聚合为易读的活动摘要，同时保留工具目标、状态和耗时等关键细节
- 新增 TUI Changed Files 查看器，支持 `Ctrl+D` 打开、按文件查看 diff、显示增删行数，并可折叠/展开单个文件差异
- 新增 TUI 助手输出的轻量 Markdown 渲染，支持标题、列表、任务项、引用、代码块，以及常见语言的语法高亮

### 改进
- 将审批提示移入输入区域，提供更清晰的批准/拒绝文案、键盘优先交互，以及聚焦命令或文件变更的说明
- 增强文件编辑审批安全性：当 `apply_patch` 或 `write_file` 无法识别目标文件时会阻止执行，并返回可操作的修正提示
- 改进 unified diff 与 Begin Patch 风格新增/更新/删除/移动头部的路径解析
- 在任务正常完成后裁剪会话历史中的内部 todo 工具调用记录，让后续对话更干净
- 在 TUI 顶部展示当前 session id 和已恢复消息数，让恢复状态更清晰
- 更新 README 和设计文档，补充完整 `docs/` 目录索引，说明每个文档和图表产物的用途

### 测试
- 扩展 apply_patch 目标校验、审批安全、子代理阻止编辑、任务守卫、工具并发、TUI runner/state 行为，以及 changed-file diff 渲染相关测试覆盖

## [0.2.0] - 2026-04-23

### 新功能
- 添加子代理系统，包含探索者、架构师、工程师和测试者角色
- 实现技能管理系统，包含 list_skills 和 load_skill 工具
- 添加流式使用支持
- 添加工具重试机制
- 添加新工具：list_skills、load_skill、subagent

### 改进
- 更新代理提供商（Anthropic 和 OpenAI）
- 增强会话管理
- 改进待办事项管理系统
- 添加全面的测试
- 添加文档

## [0.1.0] - 2026-04-22

### 新功能
- Yoyo Agent 初始提交
- 基于图执行的核心代理框架
- 待办事项管理系统
- 工具重试机制
- 支持 OpenAI 和 Anthropic 提供商
- 基础示例和工具函数
