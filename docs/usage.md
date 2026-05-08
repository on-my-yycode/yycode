# 使用说明

作者：张磊

本文档整理 Yoyo Agent 的日常使用入口、TUI 交互和内置工具清单。README 保留项目概览，本页作为更完整的使用参考。

## 启动

```bash
python main.py                 # 默认以当前目录作为工作区启动 TUI
python main.py ~/project       # 指定工作区目录启动
python main.py --silent        # 静默模式，自动批准高风险操作
python main.py --debug         # 调试模式，输出详细日志
python main.py --log-file      # 将日志写入 agent_debug.log
python main.py --session-id abc --resume   # 恢复同一工作区下指定 session 的历史 messages
python main.py --no-persist                # 禁用本地 session messages 持久化
```

工作区使用位置参数指定，不提供 `--workdir`。如果不传工作区，Yoyo Agent 会使用启动命令时所在的当前目录。所有文件、Git、Shell、验证和审批 diff 都会限制在该工作区内。

`sessions` 属于 yoyoagent 应用自身，而不是被操作项目的一部分。默认保存路径为：

```text
{app_root}/sessions/{workspace_hash}/{session_id}.json
```

其中 `workspace_hash = sha256(resolve(workdir))[:16]`。恢复时会校验 session 文件中的 `workdir` 与当前工作区一致，避免跨项目混用上下文。

默认会保存会话 messages，但不会自动恢复旧历史；恢复需要显式传入 `--resume`。如果需要完全关闭落盘，使用 `--no-persist`。

也可以通过环境变量启用静默审批：

```bash
YOYO_SILENT=true python main.py
# 或
YOYO_AUTO_APPROVE=true python main.py
```

会话与技能相关环境变量：

| 变量 | 功能 |
|------|------|
| `YOYO_APP_ROOT` | 覆盖 yoyoagent 应用根目录，默认是源码/发行目录 |
| `YOYO_RUNTIME_DATA_DIR` | 覆盖运行数据目录，默认等于 `app_root` |
| `YOYO_SESSION_DIR` | 覆盖 session messages 保存目录 |
| `YOYO_SKILL_DIRS` | 追加额外技能目录，多个目录用逗号、换行或系统 path 分隔符分隔 |

默认技能目录是 `{app_root}/skills`。项目内的 `workdir/skills` 不再默认扫描，如需项目级技能请通过 `YOYO_SKILL_DIRS` 显式加入。

当前默认入口会启动 TUI 界面。`/p` / `/paste` 多行粘贴辅助函数保留在控制台输入实现中，但默认 TUI 路径不直接使用。

## TUI 快捷键

TUI 主界面默认展示紧凑 Transcript 风格时间线：

- 连续工具调用会先显示摘要，例如 `explored 1 file`、`Edited 1 file`、`ran 1 command`。
- 每个工具活动仍会保留关键目标和耗时，例如 `Read agent/tui/state.py`、`Edited README.md`、`42ms`。
- 完整 diff 结果下方会追加文件变更摘要，例如 `2 files changed +3 -3`，便于先浏览整体影响再展开细节。
- 可通过 `Ctrl+D` 打开文件变更 / diff 面板；左侧按文件展示变更并合并同一文件的重复 diff 区块，右侧 diff 内容支持自动换行，便于阅读长行。
- 模型文本以对话式内容直接展示，不重复显示固定助手名称，便于快速阅读。
- `todo` 工具调用不会作为普通工具活动刷屏，任务计划可通过任务面板查看。
- 需要审批时，审批提示会以内联方式显示在输入区域上方；输入框暂时隐藏，审批完成后自动恢复。

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Enter` / `Ctrl+J` | 提交输入 |
| `Ctrl+C` | 取消当前任务 |
| `Ctrl+T` | 打开任务计划面板；在任务计划/审批提示中也可返回或查看计划 |
| `Ctrl+D` | 打开文件变更 / diff 面板；在该面板中也可返回主界面 |
| `Ctrl+H` | 打开历史记录浏览器 |
| `Ctrl+Shift+C` | 复制时间线内容 |
| `Ctrl+Q` | 退出 |
| `Up` / `Down` | 按行滚动时间线；技能补全打开时切换候选项 |
| `PageUp` / `PageDown` | 滚动时间线 |
| `Home` / `End` | 跳转到时间线顶部/底部 |
| `Esc` | 聚焦输入框 |

## 审批交互

高风险操作（例如编辑文件、创建文件或执行命令）会触发运行时审批，除非已启用 `--silent`、`YOYO_SILENT=true` 或 `YOYO_AUTO_APPROVE=true`。

| 按键 | 功能 |
|------|------|
| `Y` / `Enter` | 批准当前操作 |
| `N` / `Esc` | 拒绝当前操作 |
| `Ctrl+T` | 查看任务计划 |

## 技能补全

输入技能引用时，TUI 会显示最多 8 个候选项。补全列表打开时可使用以下按键：

| 按键 | 功能 |
|------|------|
| `Up` / `Ctrl+P` | 选择上一个技能 |
| `Down` / `Ctrl+N` | 选择下一个技能 |
| `Enter` / `Tab` | 插入当前技能 |
| `Esc` | 关闭补全列表 |

## 可用技能

| 技能 | 适用场景 |
|------|----------|
| `code_review` | 进行代码质量、错误处理、测试和文档等方面的综合审查 |
| `code_workflow` | 执行通用开发工作流：确认需求、保存计划、协调子代理、实现与验证 |
| `drawio` | 生成架构图、流程图、关系图等 draw.io 图表 |
| `plan` | 用户输入 `/plan`，或希望先澄清需求、讨论方案、产出项目相关计划且暂不实现时使用 |

## 可用工具

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

`verify` 通常只在代码文件或明确的构建/测试配置文件变更后运行。修改文档、图片、图表、资源或其它非代码文件时，系统不会要求运行项目代码测试。
