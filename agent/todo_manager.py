"""TodoManager - Manages task state and tracking logic."""

import logging
from typing import List, Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)


class TodoManager:
    """Manages task state and provides the todo tool handler."""

    MAX_ITEMS = 20  # Maximum allowed todo items
    MEMORY_LIST_FIELDS = (
        "constraints",
        "files_inspected",
        "files_modified",
        "decisions",
        "test_results",
        "open_risks",
        "next_steps",
    )

    def __init__(self):
        self.todo_items: List[Dict[str, Any]] = []
        self.memory: Dict[str, Any] = self._empty_memory()
        self.consecutive_non_todo_rounds: int = 0
        self.task_state_started: bool = False
        self.task_completed: bool = False
        self.last_incomplete_signature: Optional[tuple] = None
        self.repeated_incomplete_updates: int = 0

    def _empty_memory(self) -> Dict[str, Any]:
        """Return an empty task memory shape."""
        memory = {"user_goal": ""}
        for field in self.MEMORY_LIST_FIELDS:
            memory[field] = []
        return memory

    def get_items(self) -> List[Dict[str, Any]]:
        """Get current todo items."""
        return self.todo_items

    def get_memory(self) -> Dict[str, Any]:
        """Get current compact task memory."""
        return {
            key: list(value) if isinstance(value, list) else value
            for key, value in self.memory.items()
        }

    def get_task_state(self) -> Dict[str, Any]:
        """Get the complete task state."""
        return {
            "items": list(self.todo_items),
            "memory": self.get_memory(),
        }

    def set_items(self, items: List[Dict[str, Any]]) -> None:
        """Set todo items and check if all are completed or over limit."""
        # Check for maximum items limit
        if len(items) > self.MAX_ITEMS:
            logger.warning(f"Todo list exceeds maximum of {self.MAX_ITEMS} items. Truncated.")
            items = items[:self.MAX_ITEMS]

        signature = self._items_signature(items)
        is_incomplete = bool(items) and not self._items_all_completed(items)
        if is_incomplete and signature == self.last_incomplete_signature:
            self.repeated_incomplete_updates += 1
        else:
            self.repeated_incomplete_updates = 0
        self.last_incomplete_signature = signature if is_incomplete else None

        self.todo_items = items
        if items:
            self.task_state_started = True
            self.task_completed = False
        # Check if all items are completed - if yes, clear the list
        if items and self._all_completed():
            self._clear_on_completion()

    def set_memory(self, memory: Optional[Dict[str, Any]]) -> None:
        """Merge compact task memory into the current state."""
        if not memory:
            return

        user_goal = memory.get("user_goal")
        if isinstance(user_goal, str) and user_goal.strip():
            self.memory["user_goal"] = user_goal.strip()

        for field in self.MEMORY_LIST_FIELDS:
            values = memory.get(field)
            if values is None:
                continue
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list):
                continue
            current = self.memory.setdefault(field, [])
            for value in values:
                if not isinstance(value, str):
                    continue
                normalized = value.strip()
                if normalized and normalized not in current:
                    current.append(normalized)

    def _all_completed(self) -> bool:
        """Check if all todo items are completed."""
        return self._items_all_completed(self.todo_items)

    def _items_all_completed(self, items: List[Dict[str, Any]]) -> bool:
        """Check if all provided todo items are completed."""
        if not items:
            return False
        return all(item.get("status") == "completed" for item in items)

    def _items_signature(self, items: List[Dict[str, Any]]) -> tuple:
        """Return a stable signature for detecting repeated incomplete updates."""
        return tuple(
            (
                str(item.get("id", "")),
                str(item.get("text", "")),
                str(item.get("status", "")),
            )
            for item in items
        )

    def _clear_on_completion(self) -> None:
        """Clear todo list when all items are completed."""
        logger.info("All tasks completed! Todo list has been cleared.")
        self.todo_items = []
        self.task_completed = True
        self.consecutive_non_todo_rounds = 0

    def reset(self) -> None:
        """Reset todo state."""
        self.todo_items = []
        self.memory = self._empty_memory()
        self.consecutive_non_todo_rounds = 0
        self.task_state_started = False
        self.task_completed = False
        self.last_incomplete_signature = None
        self.repeated_incomplete_updates = 0

    def clear(self) -> None:
        """Explicitly clear todo list."""
        self.todo_items = []
        self.memory = self._empty_memory()
        self.consecutive_non_todo_rounds = 0
        self.task_state_started = False
        self.task_completed = False
        self.last_incomplete_signature = None
        self.repeated_incomplete_updates = 0

    def prepare_for_new_input(self) -> None:
        """Prepare for a new user input - clear previous tasks for new planning."""
        if self.todo_items and not self._all_completed():
            logger.info("Starting new task, previous todo list cleared.")
        self.todo_items = []
        self.memory = self._empty_memory()
        self.consecutive_non_todo_rounds = 0
        self.task_state_started = False
        self.task_completed = False
        self.last_incomplete_signature = None
        self.repeated_incomplete_updates = 0

    def can_finish_task(self) -> bool:
        """Return whether the current task may finish normally."""
        return self.task_state_started and self.task_completed

    def has_incomplete_task_state(self) -> bool:
        """Return whether task state is missing or has unfinished items."""
        return not self.can_finish_task()

    def get_finish_blocker_message(self) -> str:
        """Return a message that forces task state creation/completion before exit."""
        if not self.task_state_started:
            return (
                "Task State is required before you can finish this user request. "
                "Call todo now, even if the task only decomposes into one item. "
                "Create a concise checklist and set exactly one item in_progress."
            )
        return (
            "You cannot finish yet because Task State still has unfinished work. "
            "Continue executing the remaining todo items. When all work and verification "
            "are complete, call todo with every item marked completed so the task can exit."
        )

    def record_tool_call(self, tool_name: str) -> None:
        """Record a tool call for tracking."""
        if tool_name == "todo":
            self.consecutive_non_todo_rounds = 0
        else:
            self.consecutive_non_todo_rounds += 1

    def needs_reminder(self) -> bool:
        """Check if todo reminder is needed (3 rounds without todo)."""
        return self.consecutive_non_todo_rounds >= 3 and len(self.todo_items) > 0

    def get_reminder_message(self) -> str:
        """Get the reminder message with current task status."""
        if not self.todo_items:
            return ""

        status_list = []
        for item in self.todo_items:
            status_icon = {
                "pending": "[ ]",
                "in_progress": "[~]",
                "completed": "[X]",
            }.get(item["status"], "[ ]")
            status_list.append(f"{status_icon} [{item['id']}] {item['text']}")

        task_status = "\n".join(status_list)
        memory_status = self._format_memory()

        return (f"\n\n[Reminder: You haven't updated your task list in "
                f"{self.consecutive_non_todo_rounds} rounds. Current task state:\n"
                f"{task_status}\n"
                f"{memory_status}\n"
                f"Consider using the todo tool to update progress and memory.]")

    def consume_reminder_message(self) -> str:
        """Return one reminder and reset the reminder counter."""
        reminder = self.get_reminder_message()
        if reminder:
            self.consecutive_non_todo_rounds = 0
        return reminder

    def has_repeated_incomplete_update(self) -> bool:
        """Return whether the same incomplete todo state was repeated."""
        return self.repeated_incomplete_updates >= 1 and bool(self.todo_items)

    def consume_repeated_incomplete_message(self) -> str:
        """Return a no-progress warning and reset the repeated update counter."""
        if not self.has_repeated_incomplete_update():
            return ""
        self.repeated_incomplete_updates = 0
        return (
            "Task State did not change: you repeated the same incomplete todo list. "
            "Do not call todo again with the same in_progress item. Take the next concrete "
            "action now, such as running a verification tool or inspecting the relevant "
            "file. If the work is already verified or no further automated verification is "
            "possible, call todo with all items marked completed and then provide the final answer."
        )

    def create_todo_handler(self) -> Callable:
        """Create a todo handler bound to this manager."""
        def todo(items, memory=None):
            """Update task state and display current progress."""
            self.set_items(items)
            self.set_memory(memory)

            if not self.todo_items:  # Cleared on completion
                return "All tasks completed! Todo list has been cleared."

            result = []
            result.append("Task State:")
            result.append("-" * 40)

            for item in self.todo_items:
                status_icon = {
                    "pending": "[ ]",
                    "in_progress": "[~]",
                    "completed": "[X]",
                }.get(item["status"], "[ ]")
                result.append(f"{status_icon} [{item['id']}] {item['text']}")

            result.append("-" * 40)
            memory_text = self._format_memory()
            if memory_text:
                result.append(memory_text)
            output = "\n".join(result)
            logger.info(f"Task state updated:\n{output}")
            print(f"\n{output}\n")  # Keep for user interface
            return output
        return todo

    def _format_memory(self) -> str:
        """Format compact memory for reminders and tool output."""
        lines = []
        user_goal = self.memory.get("user_goal", "")
        if user_goal:
            lines.append(f"Goal: {user_goal}")
        labels = {
            "constraints": "Constraints",
            "files_inspected": "Files inspected",
            "files_modified": "Files modified",
            "decisions": "Decisions",
            "test_results": "Test results",
            "open_risks": "Open risks",
            "next_steps": "Next steps",
        }
        for field, label in labels.items():
            values = self.memory.get(field, [])
            if values:
                lines.append(f"{label}: " + "; ".join(values))
        return "\n".join(lines)
