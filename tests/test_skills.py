"""Tests for skill loading."""

import os
import asyncio

from agent import app_paths
from agent.graph import create_tools_node
from agent.providers.base import ChatResponse, LLMProvider
from agent.session import Session
from agent.skills import SkillRegistry, discover_skills, load_skills, parse_skill_paths
from agent.subagent import build_subagent_system_prompt
from agent.todo_manager import TodoManager
from langchain_core.messages import AIMessage
from tools import TOOLS


class FakeProvider(LLMProvider):
    """Fake provider for constructing sessions."""

    async def chat(self, messages, tools, system_prompt=None, stream_callback=None):
        return ChatResponse(content="")

    async def close(self):
        return None


def test_parse_skill_paths_supports_common_separators():
    raw_paths = f"one,two\nthree{os.pathsep}four"

    assert parse_skill_paths(raw_paths) == ["one", "two", "three", "four"]


def test_skill_tools_are_registered():
    tool_names = {tool["name"] for tool in TOOLS}

    assert "list_skills" in tool_names
    assert "load_skill" in tool_names


def test_load_skills_reads_file_and_directory_skill_md(tmp_path):
    skill_file = tmp_path / "python.md"
    skill_file.write_text("Use pytest.")

    skill_dir = tmp_path / "review"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Review carefully.")
    (skill_dir / "ignored.md").write_text("This should not load.")

    skills = load_skills(["python.md", "review"], tmp_path)

    assert [skill.name for skill in skills] == ["python", "review"]
    assert [skill.content for skill in skills] == ["Use pytest.", "Review carefully."]
    assert [skill.description for skill in skills] == ["", ""]


def test_load_skills_parses_frontmatter_name_and_description(tmp_path):
    skill_file = tmp_path / "github.md"
    skill_file.write_text(
        "---\n"
        "name: github\n"
        'description: "Interact with GitHub using the `gh` CLI."\n'
        "---\n"
        "\n"
        "# GitHub\n"
        "\n"
        "Use gh issue and gh pr.\n"
    )

    skills = load_skills(["github.md"], tmp_path)

    assert len(skills) == 1
    assert skills[0].name == "github"
    assert skills[0].description == "Interact with GitHub using the `gh` CLI."
    assert skills[0].content == "# GitHub\n\nUse gh issue and gh pr."


def test_skill_files_are_read_as_utf8_with_backslash_replacement(tmp_path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "review.md").write_bytes(
        b"---\nname: review\ndescription: It\xe2\x80\x99s useful\n---\n\nBody \x92 text"
    )

    skills = discover_skills(tmp_path, [str(skill_root)])

    assert len(skills) == 1
    assert skills[0].description == "It\u2019s useful"
    assert skills[0].content == "Body \\x92 text"


def test_load_skills_resolves_named_skills_from_skill_dirs(tmp_path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "python.md").write_text("Use Python patterns.")
    testing_dir = skill_root / "testing"
    testing_dir.mkdir()
    (testing_dir / "SKILL.md").write_text("Use focused tests.")

    skills = load_skills(
        ["python", "testing"],
        workdir=tmp_path,
        skill_dirs=["skills"],
    )

    assert [skill.name for skill in skills] == ["python", "testing"]
    assert [skill.content for skill in skills] == [
        "Use Python patterns.",
        "Use focused tests.",
    ]


def test_load_skills_all_loads_every_skill_from_skill_dirs(tmp_path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "python.md").write_text("Use Python patterns.")
    review_dir = skill_root / "review"
    review_dir.mkdir()
    (review_dir / "SKILL.md").write_text("Review carefully.")

    skills = load_skills(["all"], workdir=tmp_path, skill_dirs=["skills"])

    assert [skill.name for skill in skills] == ["python", "review"]


def test_skill_registry_formats_skill_list(tmp_path):
    skill_file = tmp_path / "testing.md"
    skill_file.write_text(
        "---\n"
        "name: testing\n"
        'description: "Focused testing guidance."\n'
        "---\n"
        "\n"
        "Always run focused tests.\n"
    )

    registry = SkillRegistry(tmp_path, ["."])

    output = registry.format_skill_list()

    assert "Available skills:" in output
    assert "- testing: Focused testing guidance." in output


def test_skill_registry_formats_skill_catalog_prompt(tmp_path):
    skill_file = tmp_path / "testing.md"
    skill_file.write_text(
        "---\n"
        "name: testing\n"
        'description: "Focused testing guidance."\n'
        "---\n\n"
        "Always run focused tests.\n"
    )

    registry = SkillRegistry(tmp_path, ["."])
    output = registry.format_skill_catalog_prompt()

    assert "Available local skills:" in output
    assert "Call load_skill to load the full instructions" in output
    assert "- testing: Focused testing guidance." in output
    assert "Always run focused tests." not in output


def test_skill_registry_formats_loaded_skills(tmp_path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "testing.md").write_text(
        "---\n"
        "name: testing\n"
        'description: "Focused testing guidance."\n'
        "---\n"
        "\n"
        "Always run focused tests.\n"
    )

    registry = SkillRegistry(tmp_path, ["skills"])
    output = registry.format_loaded_skills(["testing"])

    assert "Loaded skills:" in output
    assert "## testing" in output
    assert "Description: Focused testing guidance." in output
    assert "Always run focused tests." in output


def test_session_initializes_user_data_skills_from_bundled_defaults(tmp_path):
    app_root = tmp_path / "app"
    runtime_data_dir = tmp_path / "runtime"
    workdir = tmp_path / "workspace"
    bundled_skill_root = app_root / "skills"
    user_skill_root = runtime_data_dir / "skills"
    workdir.mkdir()
    app_root.mkdir()
    bundled_skill_root.mkdir()
    (bundled_skill_root / "testing.md").write_text(
        "---\n"
        "name: testing\n"
        'description: "Bundled skill copied into user data."\n'
        "---\n\n"
        "Use focused tests.\n"
    )
    project_skill_root = workdir / "skills"
    project_skill_root.mkdir()
    (project_skill_root / "project.md").write_text(
        "---\nname: project\ndescription: \"Should not load by default.\"\n---\n\nProject only.\n"
    )

    session = Session(
        provider=FakeProvider(),
        workdir=workdir,
        app_root=app_root,
        runtime_data_dir=runtime_data_dir,
        persist_messages=False,
    )

    assert session.skill_dirs == [str(user_skill_root)]
    assert (user_skill_root / "testing.md").is_file()
    assert "Available local skills:" in session.system_prompt
    assert "- testing: Bundled skill copied into user data." in session.system_prompt
    assert "Should not load by default" not in session.system_prompt
    assert "Use focused tests." not in session.system_prompt


def test_session_keeps_existing_user_data_skills_without_overwrite(tmp_path):
    app_root = tmp_path / "app"
    runtime_data_dir = tmp_path / "runtime"
    workdir = tmp_path / "workspace"
    (app_root / "skills").mkdir(parents=True)
    user_skill_root = runtime_data_dir / "skills"
    user_skill_root.mkdir(parents=True)
    (app_root / "skills" / "testing.md").write_text(
        "---\nname: bundled\ndescription: \"Bundled default.\"\n---\n\nBundled.\n"
    )
    (user_skill_root / "custom.md").write_text(
        "---\nname: custom\ndescription: \"User custom skill.\"\n---\n\nCustom.\n"
    )
    workdir.mkdir()

    session = Session(
        provider=FakeProvider(),
        workdir=workdir,
        app_root=app_root,
        runtime_data_dir=runtime_data_dir,
        persist_messages=False,
    )

    assert session.skill_dirs == [str(user_skill_root)]
    assert "- custom: User custom skill." in session.system_prompt
    assert "Bundled default" not in session.system_prompt
    assert not (user_skill_root / "testing.md").exists()


def test_session_appends_explicit_extra_skill_dirs(tmp_path):
    app_root = tmp_path / "app"
    runtime_data_dir = tmp_path / "runtime"
    workdir = tmp_path / "workspace"
    extra = tmp_path / "extra-skills"
    (app_root / "skills").mkdir(parents=True)
    workdir.mkdir()
    extra.mkdir()
    (extra / "extra.md").write_text(
        "---\nname: extra\ndescription: \"Extra skill.\"\n---\n\nExtra body.\n"
    )

    session = Session(
        provider=FakeProvider(),
        workdir=workdir,
        app_root=app_root,
        runtime_data_dir=runtime_data_dir,
        skill_dirs=[str(extra)],
        persist_messages=False,
    )

    assert session.skill_dirs == [str(runtime_data_dir / "skills"), str(extra)]
    assert "- extra: Extra skill." in session.system_prompt


def test_resource_root_uses_installed_tool_prefix_for_bundled_skills(tmp_path, monkeypatch):
    fake_source_root = tmp_path / "site-packages"
    fake_agent_dir = fake_source_root / "agent"
    fake_prefix = tmp_path / "tool-env"
    fake_agent_dir.mkdir(parents=True)
    (fake_prefix / "skills").mkdir(parents=True)

    monkeypatch.setattr(app_paths, "__file__", str(fake_agent_dir / "app_paths.py"))
    monkeypatch.setattr(app_paths.sys, "prefix", str(fake_prefix))

    assert app_paths.resolve_resource_root() == fake_prefix.resolve()


def test_resource_root_uses_source_root_for_development_checkout(tmp_path, monkeypatch):
    fake_source_root = tmp_path / "checkout"
    fake_agent_dir = fake_source_root / "agent"
    fake_prefix = tmp_path / "tool-env"
    fake_agent_dir.mkdir(parents=True)
    (fake_source_root / "skills").mkdir()
    (fake_prefix / "skills").mkdir(parents=True)

    monkeypatch.setattr(app_paths, "__file__", str(fake_agent_dir / "app_paths.py"))
    monkeypatch.setattr(app_paths.sys, "prefix", str(fake_prefix))

    assert app_paths.resolve_resource_root() == fake_source_root.resolve()


def test_runtime_data_dir_defaults_to_user_data_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(app_paths.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(app_paths.sys, "platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    assert app_paths.resolve_runtime_data_dir(tmp_path / "app") == (
        tmp_path / "home" / ".local" / "share" / "yycode"
    ).resolve()


def test_subagent_prompt_mentions_skill_tools_without_parent_prompt(tmp_path):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "testing.md").write_text(
        "---\n"
        "name: testing\n"
        'description: "Prefer narrow verification."\n'
        "---\n\n"
        "Use focused tests.\n"
    )

    registry = SkillRegistry(tmp_path, ["skills"])

    prompt = build_subagent_system_prompt(
        role="tester",
        workdir=tmp_path,
        parent_prompt="NOISY PARENT PROMPT",
        skill_catalog_prompt=registry.format_skill_catalog_prompt(),
    )

    assert "NOISY PARENT PROMPT" not in prompt
    assert "Use list_skills to discover skills" in prompt
    assert "Available local skills:" in prompt
    assert "- testing: Prefer narrow verification." in prompt
    assert "Use focused tests." not in prompt


def test_tools_node_executes_skill_tools(tmp_path, monkeypatch):
    skill_root = tmp_path / "skills"
    skill_root.mkdir()
    (skill_root / "testing.md").write_text(
        "---\nname: testing\ndescription: \"Focused tests.\"\n---\n\nUse focused tests.\n"
    )

    monkeypatch.setattr(
        "agent.graph.TOOL_HANDLERS",
        {},
    )
    monkeypatch.setattr(
        "agent.graph.TOOLS",
        [
            {
                "name": "list_skills",
                "description": "list",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "name": "load_skill",
                "description": "load",
                "input_schema": {
                    "type": "object",
                    "properties": {"names": {"type": "array"}},
                    "required": ["names"],
                },
            },
        ],
    )

    tools_node = create_tools_node(
        provider=FakeProvider(),
        system_prompt="parent prompt",
        todo_manager=TodoManager(),
        workdir=tmp_path,
        session_id="parent-1",
        skill_dirs=["skills"],
    )

    ai_msg = AIMessage(content="")
    ai_msg.additional_kwargs["tool_calls_data"] = [
        type("TC", (), {"id": "1", "name": "list_skills", "args": {}})(),
        type("TC", (), {"id": "2", "name": "load_skill", "args": {"names": ["testing"]}})(),
    ]

    result = asyncio.run(tools_node({"messages": [ai_msg]}))
    contents = [msg.content for msg in result["messages"]]

    assert any("Available skills:" in content for content in contents)
    assert any("Loaded skills:" in content and "## testing" in content for content in contents)
