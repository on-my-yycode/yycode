# 🔒 YoyoAgent 安全检查报告

> 审查日期: 2025-07-17  
> 审查范围: 全项目 (tools/, agent/, agent/runtime/, agent/tui/, 配置文件, 测试)  
> 审查文件数: 35+

---

## 一、项目概览

| 项目 | 信息 |
|------|------|
| 代码语言 | Python 3 (LangChain + LangGraph) |
| 核心能力 | AI 编码代理：文件读写、Shell 命令、子代理委托、审批流、TUI 界面 |
| 风险等级 | 🔴 严重: 1 个 \| 🟠 高危: 2 个 \| 🟡 中危: 2 个 \| 🟢 低危/良好: 若干 |

---

## 🔴 严重 (Critical)

### 1. `.env.example` 包含真实 API 密钥且已提交 Git

**文件**: `.env.example` 第 6 行
```
API_KEY=<example-api-key>
API_BASE=<example-api-base>
```

**发现**:
- 该文件自第 1 个 commit (`9a70300`) 起即包含真实火山引擎 API 密钥，已存在于 **4 个 git commit** 中
- `.gitignore` 仅排除 `.env`，**未排除 `.env.example`**
- 密钥即便从文件中删除，仍可通过 `git log` 历史恢复
- `.env` 文件中也包含另一个真实 DeepSeek API 密钥（注释行中），但因在 `.gitignore` 中而未提交

**修复建议**:
1. 🔴 **立即**: 在火山引擎/DeepSeek 后台 **撤销这两个 API 密钥**
2. 将 `.env.example` 中的真实密钥替换为占位符：`API_KEY=your-api-key-here`
3. 使用 `git filter-branch` 或 `bfg-repo-cleaner` 清理 git 历史
4. 将 `.env.example` 也加入 `.gitignore` 或使用 `.env.example.template` 命名
5. 考虑添加 pre-commit hook 扫描敏感信息（如 `detect-secrets` 或 `trufflehog`）

---

## 🟠 高危 (High)

### 2. Bash 命令使用 `shell=True` 执行

**文件**: `tools/bash.py` 第 29-34 行
```python
r = subprocess.run(
    command,
    shell=True,
    cwd=WORKDIR,
    capture_output=True,
    text=True,
    timeout=120,
)
```

**风险分析**:
- `shell=True` 会将命令字符串传递给 `/bin/sh`，可导致 shell 注入（如 `&&`, `;`, `|`, `$()` 等）
- 当前依赖正则模式过滤 `DANGEROUS_COMMAND_PATTERNS` 中的 7 种模式（`sudo`, `rm -rf`, `git reset`, `git checkout`, `git clean`, `chmod/chown`, `>/dev/`）
- **绕过风险**: 正则匹配不覆盖所有注入向量（如反引号 `` `cmd` ``、`$()` 命令替换、URL 编码、环境变量注入 `$VAR` 等）
- 命令来源是 AI 模型输出，非直接用户输入，风险部分缓解但不能完全排除

**修复建议**:
1. 优先使用 `shell=False` + 列表参数：`subprocess.run(["bash", "-c", command], ...)`
2. 或增加命令白名单机制，只允许安全的工具命令
3. 添加命令长度限制（当前无限制）
4. 增加更严格的输入净化（如 `shlex.quote()`）

### 3. Bash 输出未过滤敏感信息

**文件**: `tools/bash.py` 第 12-20 行

Bash 命令的 stdout/stderr **原样返回**给 LLM，仅通过 `MAX_OUTPUT_CHARS=50_000` 截断。如果命令输出包含 API 密钥、密码、Token 等，会直接暴露给 LLM 上下文。

**修复建议**:
- 对 bash 输出做敏感信息脱敏（如正则过滤 `sk-`, `Bearer`, `password=` 等模式）
- 或设定敏感路径（如 `.env`）不得被读取

---

## 🟡 中危 (Medium)

### 4. 日志文件可能泄露会话信息

**文件**: `agent/runtime/tool_executor.py` 第 33-38 行

```python
logger.debug(f"Calling tool: {getattr(tc, 'name', 'unknown')}")
logger.debug(f"Full tc object: {tc!r}")
```

调试日志输出完整的 `tc` 对象，若开启 `--debug` 或 `--log-file`，工具参数（可能包含文件内容、路径等）会被写入 `agent_debug.log` 或控制台。

`log.txt` 文件存在于仓库中，包含早期开发时的项目 tree（无敏感内容，但建议清理）。

**修复建议**:
- 对 debug 日志中的工具参数做脱敏处理
- 将 `log.txt` 加入 `.gitignore`

### 5. 审批机制覆盖范围有限

**文件**: `agent/approval.py` 第 59-81 行

审批仅覆盖 3 种工具调用：
- `bash` — 仅当匹配 `DANGEROUS_COMMAND_PATTERNS` 时触发
- `apply_patch` — 始终触发
- `write_file` — 始终触发

未覆盖但可能产生副作用的操作：
- `bash` 的非匹配模式命令（如 `curl | sh`, `pip install` 等）
- `subagent` 内部可写文件（子代理有独立的审批流程，依赖父级 `approval_callback`）

**修复建议**:
- 扩展 `DANGEROUS_COMMAND_PATTERNS` 覆盖更多高风险命令（`curl`, `wget`, `pip install`, `npm install -g` 等）
- 考虑对子代理的文件写入操作增加额外审批层

---

## 🟢 良好实践 (Already Good)

| 防护措施 | 实现位置 | 说明 |
|----------|----------|------|
| **路径穿越防护** | `tools/read_file.py:safe_path()` | `Path.is_relative_to()` 防止 `../` 逃逸 |
| **路径验证 (patch)** | `tools/apply_patch.py:_validate_paths()` | 拒绝绝对路径和 `..` |
| **文件删除拦截** | `tools/apply_patch.py:_changed_paths()` | 检测 `deleted file mode`，抛出 `ApprovalRequired` |
| **edit_file 完全禁用** | `tools/edit_file.py` | 始终返回错误，强制使用 `apply_patch` |
| **write_file 防覆盖** | `tools/write_file.py` | 已存在文件返回错误 |
| **apply_patch 大小限制** | `tools/apply_patch.py` | MAX_PATCH_CHARS=100k, MAX_REPLACEMENT_LINES=80 |
| **全文件替换防护** | `tools/apply_patch.py:_looks_like_whole_file()` | 检测整文件替换并拒绝 |
| **子代理工具过滤** | `agent/subagent.py:filter_subagent_tool()` | 禁止 `subagent` 和 `todo` 递归/逃逸 |
| **Bash 超时保护** | `tools/bash.py` | 120s 超时，50k 字符限制 |
| **文件读取大小限制** | `tools/read_file.py` | 50k 字符上限 |
| **自动审批模式明确提示** | `main.py` | `-a` / `--auto` 参数打印明确警告 |
| **安全测试覆盖** | `tests/test_safety.py` | 8 个测试覆盖危险命令检测、审批流程、diff 预览 |
| **子代理安全角色** | `agent/subagent.py:ROLE_PROMPTS` | `security` 角色专门用于安全审查 |

---

## 📊 风险汇总

| 风险等级 | 数量 | 关键项 |
|----------|------|--------|
| 🔴 严重 | 1 | API 密钥泄露到 Git |
| 🟠 高危 | 2 | shell=True 注入风险、输出未脱敏 |
| 🟡 中危 | 2 | 日志泄露、审批覆盖面 |
| 🟢 良好 | 13 | 路径安全、文件操作守卫、隔离机制 |

---

## 🎯 优先行动建议

| 优先级 | 行动 | 预计工作量 |
|--------|------|-----------|
| 🔴 P0 | 撤销泄露的 API 密钥 + 清理 `.env.example` + 清理 git 历史 | 2h |
| 🟠 P1 | 为 `bash` 增加命令净化 / 敏感信息过滤 | 3h |
| 🟡 P2 | 扩展 `DANGEROUS_COMMAND_PATTERNS` 覆盖 curl/wget/pip 等 | 1h |
| 🟡 P2 | 日志脱敏 + `log.txt` 加入 `.gitignore` | 30min |
| 🟢 P3 | 添加 pre-commit 密钥扫描 hook | 1h |
| 🟢 P3 | 添加子代理文件写入的额外审批层 | 2h |
