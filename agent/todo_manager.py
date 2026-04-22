"""TodoManager - Manages todo list state and tracking logic."""

from typing import List, Dict, Any, Optional, Callable


class TodoManager:
    """Manages todo list state and provides todo tool handler."""

    MAX_ITEMS = 20  # Maximum allowed todo items

    def __init__(self):
        self.todo_items: List[Dict[str, Any]] = []
        self.consecutive_non_todo_rounds: int = 0

    def get_items(self) -> List[Dict[str, Any]]:
        """Get current todo items."""
        return self.todo_items

    def set_items(self, items: List[Dict[str, Any]]) -> None:
        """Set todo items and check if all are completed or over limit."""
        # Check for maximum items limit
        if len(items) > self.MAX_ITEMS:
            print(f"\n[Warning: Todo list exceeds maximum of {self.MAX_ITEMS} items. Truncated.]\n")
            items = items[:self.MAX_ITEMS]

        self.todo_items = items
        # Check if all items are completed - if yes, clear the list
        if items and self._all_completed():
            self._clear_on_completion()

    def _all_completed(self) -> bool:
        """Check if all todo items are completed."""
        if not self.todo_items:
            return False
        return all(item.get("status") == "completed" for item in self.todo_items)

    def _clear_on_completion(self) -> None:
        """Clear todo list when all items are completed."""
        print("\n[All tasks completed! Todo list has been cleared.]\n")
        self.todo_items = []
        self.consecutive_non_todo_rounds = 0

    def reset(self) -> None:
        """Reset todo state."""
        self.todo_items = []
        self.consecutive_non_todo_rounds = 0

    def clear(self) -> None:
        """Explicitly clear todo list."""
        self.todo_items = []
        self.consecutive_non_todo_rounds = 0

    def prepare_for_new_input(self) -> None:
        """Prepare for a new user input - clear previous tasks for new planning."""
        if self.todo_items and not self._all_completed():
            print("\n[Starting new task, previous todo list cleared.]\n")
        self.todo_items = []
        self.consecutive_non_todo_rounds = 0

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

        return (f"\n\n[Reminder: You haven't updated your task list in "
                f"{self.consecutive_non_todo_rounds} rounds. Current task status:\n"
                f"{task_status}\n"
                f"Consider using the todo tool to update progress.]")

    def create_todo_handler(self) -> Callable:
        """Create a todo handler bound to this manager."""
        def todo(items):
            """Update todo list and display current tasks."""
            self.set_items(items)

            if not self.todo_items:  # Cleared on completion
                return "All tasks completed! Todo list has been cleared."

            result = []
            result.append("Task List:")
            result.append("-" * 40)

            for item in items:
                status_icon = {
                    "pending": "[ ]",
                    "in_progress": "[~]",
                    "completed": "[X]",
                }.get(item["status"], "[ ]")
                result.append(f"{status_icon} [{item['id']}] {item['text']}")

            result.append("-" * 40)
            output = "\n".join(result)
            print(f"\n{output}\n")
            return output
        return todo
