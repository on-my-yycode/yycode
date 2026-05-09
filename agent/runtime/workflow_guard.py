"""Workspace workflow guardrails."""

from langchain_core.messages import HumanMessage

from agent.runtime.context import AgentRuntimeContext, WorkflowState
from agent.runtime.tool_events import file_paths_for_tool_call, tool_output_indicates_successful_write
from agent.runtime.tool_registry import RuntimeToolRegistry


CODE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".cxx",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".m",
    ".mm",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".scss",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}

VERIFY_CONFIG_EXTENSIONS = {
    ".gradle",
    ".kts",
    ".lock",
    ".toml",
    ".xml",
}

VERIFY_CONFIG_FILENAMES = {
    ".eslintrc",
    ".eslintrc.cjs",
    ".eslintrc.js",
    ".eslintrc.json",
    ".prettierrc",
    ".ruff.toml",
    "Cargo.lock",
    "Cargo.toml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "go.sum",
    "mypy.ini",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "pom.xml",
    "pyproject.toml",
    "pytest.ini",
    "requirements-dev.txt",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
    "tox.ini",
    "tsconfig.json",
    "yarn.lock",
}

VERIFY_CONFIG_SUFFIXES = {
    ".csproj",
    ".fsproj",
    ".props",
    ".sln",
    ".targets",
    ".vbproj",
}


class WorkflowGuard:
    """Enforce workspace safety and verification workflow rules."""

    def __init__(self, runtime: AgentRuntimeContext, registry: RuntimeToolRegistry):
        self.runtime = runtime
        self.registry = registry
        self.state: WorkflowState = runtime.workflow_state

    def has_preflight(self) -> bool:
        """Return whether workspace state and diff have been checked."""
        return self.state.workspace_state_checked and self.state.git_diff_checked

    def path_exists(self, path: str) -> bool:
        """Return whether a workspace-relative path exists."""
        if not path:
            return False
        return (self.runtime.workdir / path).resolve().exists()

    def should_require_apply_patch(self, tc) -> bool:
        """Return whether a tool call should be redirected to apply_patch."""
        if tc.name == "edit_file":
            return True
        if tc.name == "write_file":
            return self.path_exists(tc.args.get("path", ""))
        return False

    def apply_patch_required_message(self, tc) -> str:
        """Return a message explaining why apply_patch is required."""
        path = tc.args.get("path", "")
        if tc.name == "write_file":
            return (
                f"Code workflow guard blocked write_file for existing file: {path}\n\n"
                "Use apply_patch with path + old_text + new_text, or a unified diff, "
                "for existing file edits. "
                "write_file is only allowed for brand-new files or generated artifacts."
            )
        return (
            f"Code workflow guard blocked edit_file for: {path}\n\n"
            "Use apply_patch with path + old_text + new_text, or a unified diff, "
            "for code edits so the change is reviewable "
            "and the diff can be shown to the user."
        )

    async def run_preflight(self) -> str:
        """Collect workspace state and diff before allowing a write tool."""
        workspace_output = await self.runtime.run_tool(
            self.registry.resolve("workspace_state"),
            "workspace_state",
            max_retries=0,
            timeout_seconds=self.registry.timeout_for("workspace_state"),
        )
        diff_output = await self.runtime.run_tool(
            self.registry.resolve("git_diff"),
            "git_diff",
            max_retries=0,
            timeout_seconds=self.registry.timeout_for("git_diff"),
        )
        self.state.workspace_state_checked = True
        self.state.git_diff_checked = True
        return (
            "Code workflow guard blocked this write because workspace preflight "
            "had not been reviewed yet.\n\n"
            "workspace_state:\n"
            f"{workspace_output}\n\n"
            "git_diff:\n"
            f"{diff_output}\n\n"
            "Review the existing changes, then retry the write with the smallest safe patch."
        )

    def update_after_tool(self, tool_call, output: str) -> bool:
        """Update workflow state after a tool and return whether a diff event is needed."""
        tool_name = tool_call.name
        if tool_name == "workspace_state":
            self.state.workspace_state_checked = True
        if tool_name == "git_diff":
            self.state.git_diff_checked = True
        if tool_name == "verify":
            self.state.needs_verify = False
        if self.registry.is_workspace_write(tool_name) and tool_output_indicates_successful_write(output):
            self.state.needs_verify = paths_need_code_verification(file_paths_for_tool_call(tool_call))
            return True
        return False

    def after_batch_messages(self, tool_calls_data: list) -> list[HumanMessage]:
        """Return extra HumanMessages to append after a tools batch."""
        additional_messages = []
        todo_manager = self.runtime.todo_manager
        if todo_manager.needs_reminder():
            additional_messages.append(
                HumanMessage(
                    content=todo_manager.consume_reminder_message(),
                    additional_kwargs={
                        "context_ephemeral": True,
                        "ephemeral_kind": "task_reminder",
                    },
                )
            )
        if self.state.needs_verify and not any(tc.name == "verify" for tc in tool_calls_data):
            additional_messages.append(
                HumanMessage(
                    content=(
                        "Code changes were made. Run verify with the narrowest useful "
                        "target before providing the final answer."
                    ),
                    additional_kwargs={
                        "context_ephemeral": True,
                        "ephemeral_kind": "verify_reminder",
                    },
                )
            )
        return additional_messages


def paths_need_code_verification(paths: list[str]) -> bool:
    """Return whether changed paths should trigger code verification."""
    if not paths:
        return True
    return any(path_needs_code_verification(path) for path in paths)


def path_needs_code_verification(path: str) -> bool:
    """Return whether a single path is code or known build/test configuration."""
    normalized = path.replace("\\", "/").rstrip("/")
    name = normalized.rsplit("/", 1)[-1]
    if name in VERIFY_CONFIG_FILENAMES:
        return True
    if any(name.endswith(suffix) for suffix in VERIFY_CONFIG_SUFFIXES):
        return True
    extension = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return extension in CODE_EXTENSIONS or extension in VERIFY_CONFIG_EXTENSIONS
