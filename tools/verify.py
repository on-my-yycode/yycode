"""Verification tool for common code-agent checks."""

import shlex
import subprocess
import time

from .read_file import WORKDIR, safe_path

MAX_OUTPUT_CHARS = 50_000
VERIFY_TIMEOUT_SECONDS = 300


def _target_args(target: str) -> list[str]:
    if not target:
        return []
    path_part = target.split("::", 1)[0]
    if path_part:
        safe_path(path_part)
    return [target]


def _has_file(*names: str) -> bool:
    return any((WORKDIR / name).exists() for name in names)


def _pyproject_contains(marker: str) -> bool:
    pyproject = WORKDIR / "pyproject.toml"
    return pyproject.exists() and marker in pyproject.read_text()


def _command_for(kind: str, target: str) -> list[str] | None:
    extra = _target_args(target)
    if kind in {"all", "tests"}:
        return ["pytest", *extra]
    if kind == "lint":
        if _has_file("ruff.toml", ".ruff.toml") or _pyproject_contains("[tool.ruff"):
            return ["ruff", "check", *(extra or ["."])]
        return None
    if kind == "typecheck":
        if _has_file("mypy.ini", ".mypy.ini") or _pyproject_contains("[tool.mypy"):
            return ["mypy", *(extra or ["."])]
        if _has_file("pyrightconfig.json"):
            return ["pyright", *(extra or ["."])]
        return None
    raise ValueError(f"unsupported verify kind: {kind}")


def verify(kind: str = "all", target: str = "") -> str:
    """Run a verification check and return command output."""
    try:
        kind = (kind or "all").strip().lower()
        command = _command_for(kind, target or "")
        if command is None:
            return f"No {kind} configuration found."

        started = time.monotonic()
        result = subprocess.run(
            command,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=VERIFY_TIMEOUT_SECONDS,
        )
        elapsed = time.monotonic() - started
        output = (result.stdout + result.stderr).strip()
        rendered_command = " ".join(shlex.quote(part) for part in command)
        status = "passed" if result.returncode == 0 else "failed"
        return (
            f"verify {status}: {rendered_command}\n"
            f"exit_code: {result.returncode}\n"
            f"duration: {elapsed:.1f}s\n"
            f"output:\n{output or '(no output)'}"
        )[:MAX_OUTPUT_CHARS]
    except subprocess.TimeoutExpired:
        return f"Error: Timeout ({VERIFY_TIMEOUT_SECONDS}s)"
    except Exception as exc:
        return f"Error: {exc}"


verify_tool = {
    "name": "verify",
    "description": "Run common verification checks such as tests, lint, or typecheck.",
    "execution": {
        "side_effects": "process",
        "concurrency": "serial",
        "timeout_seconds": VERIFY_TIMEOUT_SECONDS,
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["all", "tests", "lint", "typecheck"],
                "description": "Verification type to run. Defaults to all.",
            },
            "target": {
                "type": "string",
                "description": "Optional workspace-relative target, such as a test file.",
            },
        },
        "required": [],
    },
}
