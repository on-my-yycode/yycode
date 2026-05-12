"""Run local yoyoagent eval tasks."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.common import EvalResult


ROOT = Path(__file__).resolve().parent
TASKS_DIR = ROOT / "tasks"


def _load_task(path: Path):
    spec = importlib.util.spec_from_file_location(f"evals.tasks.{path.parent.name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load eval task: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_tasks(tasks_dir: Path = TASKS_DIR) -> list[Path]:
    """Return eval task modules in stable order."""
    if not tasks_dir.exists():
        return []
    return sorted(tasks_dir.glob("*/eval.py"))


def run_all(task_paths: list[Path] | None = None) -> list[tuple[str, EvalResult]]:
    """Run all discovered eval tasks."""
    results: list[tuple[str, EvalResult]] = []
    for task_path in task_paths or discover_tasks():
        module = _load_task(task_path)
        task_name = getattr(module, "TASK_NAME", task_path.parent.name)
        evaluate = getattr(module, "evaluate", None)
        if evaluate is None:
            raise RuntimeError(f"Eval task has no evaluate() function: {task_path}")
        for result in evaluate():
            results.append((task_name, result))
    return results


def main() -> int:
    """CLI entrypoint."""
    results = run_all()
    if not results:
        print("No eval tasks found.")
        return 1

    passed = sum(1 for _, result in results if result.passed)
    total = len(results)
    print(f"yoyoagent evals: {passed}/{total} passed")
    print()
    for task_name, result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {task_name} :: {result.name}")
        if result.error:
            print(result.error)
            print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
