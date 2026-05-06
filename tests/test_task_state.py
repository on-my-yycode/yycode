"""Tests for todo-backed Task State."""

from agent.todo_manager import TodoManager
from tools.todo import todo_tool


def test_todo_schema_includes_task_memory():
    properties = todo_tool["input_schema"]["properties"]
    memory = properties["memory"]

    assert "items" in properties
    assert "memory" in properties
    assert "user_goal" in memory["properties"]
    assert "files_inspected" in memory["properties"]
    assert "files_modified" in memory["properties"]
    assert "decisions" in memory["properties"]
    assert "test_results" in memory["properties"]
    assert "open_risks" in memory["properties"]
    assert "next_steps" in memory["properties"]


def test_todo_handler_updates_items_and_memory():
    manager = TodoManager()
    handler = manager.create_todo_handler()

    output = handler(
        items=[
            {"id": "1", "text": "Inspect", "status": "completed"},
            {"id": "2", "text": "Patch", "status": "in_progress"},
        ],
        memory={
            "user_goal": "Restore task state",
            "files_inspected": ["tools/todo.py"],
            "files_modified": ["agent/todo_manager.py"],
            "decisions": ["Keep reminder one-shot"],
            "test_results": ["not run yet"],
            "open_risks": ["prompt drift"],
            "next_steps": ["run tests"],
        },
    )

    assert "Task State:" in output
    assert "Goal: Restore task state" in output
    assert "Files inspected: tools/todo.py" in output
    assert manager.get_items()[1]["status"] == "in_progress"
    assert manager.get_memory()["files_modified"] == ["agent/todo_manager.py"]


def test_todo_handler_outputs_completed_item_details_before_clearing():
    manager = TodoManager()
    handler = manager.create_todo_handler()

    output = handler(
        items=[
            {"id": "1", "text": "Inspect", "status": "completed"},
            {"id": "2", "text": "Patch", "status": "completed"},
        ],
        memory={"user_goal": "Finish task"},
    )

    assert "[X] [1] Inspect" in output
    assert "[X] [2] Patch" in output
    assert "All tasks completed! Todo list has been cleared." in output
    assert manager.get_items() == []


def test_task_memory_merges_lists_without_duplicates():
    manager = TodoManager()
    manager.set_memory(
        {
            "user_goal": "Initial goal",
            "files_inspected": ["a.py", "b.py"],
            "decisions": ["Use apply_patch"],
        }
    )
    manager.set_memory(
        {
            "user_goal": "Updated goal",
            "files_inspected": ["b.py", "c.py"],
            "decisions": ["Use apply_patch", "Run focused tests"],
        }
    )

    memory = manager.get_memory()
    assert memory["user_goal"] == "Updated goal"
    assert memory["files_inspected"] == ["a.py", "b.py", "c.py"]
    assert memory["decisions"] == ["Use apply_patch", "Run focused tests"]


def test_task_state_clears_for_new_input():
    manager = TodoManager()
    manager.set_items([{"id": "1", "text": "Work", "status": "in_progress"}])
    manager.set_memory({"user_goal": "Keep this only for current input"})

    manager.prepare_for_new_input()

    assert manager.get_items() == []
    assert manager.get_memory()["user_goal"] == ""


def test_reminder_contains_memory_and_resets_counter():
    manager = TodoManager()
    manager.set_items([{"id": "1", "text": "Long task", "status": "in_progress"}])
    manager.set_memory(
        {
            "user_goal": "Finish long task",
            "files_inspected": ["main.py"],
            "next_steps": ["continue implementation"],
        }
    )
    manager.record_tool_call("read_file")
    manager.record_tool_call("grep")
    manager.record_tool_call("read_file")

    reminder = manager.consume_reminder_message()

    assert "Current task state" in reminder
    assert "Goal: Finish long task" in reminder
    assert "Files inspected: main.py" in reminder
    assert "Next steps: continue implementation" in reminder
    assert manager.consecutive_non_todo_rounds == 0


def test_repeated_incomplete_todo_update_returns_no_progress_warning():
    manager = TodoManager()
    items = [{"id": "1", "text": "Verify game", "status": "in_progress"}]

    manager.set_items(items)
    assert manager.has_repeated_incomplete_update() is False

    manager.set_items(items)
    assert manager.has_repeated_incomplete_update() is True

    message = manager.consume_repeated_incomplete_message()

    assert "Task State did not change" in message
    assert "Do not call todo again" in message
    assert manager.has_repeated_incomplete_update() is False
