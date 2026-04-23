"""Skill discovery and loading utilities."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


MAX_SKILL_CHARS = 8_000
ALL_SKILLS_TOKENS = {"all", "*"}
DEFAULT_SKILL_DIRS = ["skills"]


@dataclass(frozen=True)
class LoadedSkill:
    """A loaded skill document."""

    name: str
    description: str
    path: Path
    content: str


def parse_skill_paths(raw_paths: Optional[str]) -> list[str]:
    """Parse a comma, newline, or os.pathsep separated string."""
    if not raw_paths:
        return []

    paths = []
    for chunk in raw_paths.replace("\n", ",").replace(os.pathsep, ",").split(","):
        path = chunk.strip()
        if path:
            paths.append(path)
    return paths


class SkillRegistry:
    """Discover and load skills for a workspace."""

    def __init__(self, workdir: Path, skill_dirs: Optional[Iterable[str]] = None):
        self.workdir = workdir
        dirs = list(skill_dirs) if skill_dirs is not None else DEFAULT_SKILL_DIRS
        self.search_dirs = [_resolve_path(path, workdir) for path in dirs]

    def list_skills(self) -> list[LoadedSkill]:
        """Return metadata for all discoverable skills."""
        skills: list[LoadedSkill] = []
        seen_names: set[str] = set()
        seen_paths: set[Path] = set()

        for skill_file in _iter_all_skill_files(self.search_dirs):
            if skill_file in seen_paths:
                continue
            skill = _load_skill_file(skill_file)
            if not skill or skill.name in seen_names:
                continue
            skills.append(skill)
            seen_names.add(skill.name)
            seen_paths.add(skill_file)

        return sorted(skills, key=lambda skill: skill.name)

    def load_skills(self, refs: Iterable[str]) -> list[LoadedSkill]:
        """Load skills by name, path, or all token."""
        loaded: list[LoadedSkill] = []
        seen_paths: set[Path] = set()

        for ref in refs:
            for skill_file in _resolve_skill_files(ref, self.workdir, self.search_dirs):
                if skill_file in seen_paths:
                    continue
                skill = _load_skill_file(skill_file)
                if skill:
                    loaded.append(skill)
                    seen_paths.add(skill_file)

        return loaded

    def format_skill_list(self) -> str:
        """Format skill metadata for tool output."""
        skills = self.list_skills()
        if not skills:
            return "No skills found."

        lines = ["Available skills:"]
        for skill in skills:
            description = skill.description or "(no description)"
            lines.append(f"- {skill.name}: {description}")
        return "\n".join(lines)

    def format_skill_catalog_prompt(self) -> str:
        """Format skill metadata for prompt injection without full content."""
        skills = self.list_skills()
        if not skills:
            return ""

        lines = [
            "Available local skills:",
            "You only have skill names and descriptions by default.",
            "Call load_skill to load the full instructions for any skill you want to use.",
        ]
        for skill in skills:
            description = skill.description or "(no description)"
            lines.append(f"- {skill.name}: {description}")
        return "\n".join(lines)

    def format_loaded_skills(self, refs: Iterable[str]) -> str:
        """Format full loaded skills for tool output."""
        skills = self.load_skills(refs)
        if not skills:
            return "No matching skills found."

        sections = ["Loaded skills:"]
        for skill in skills:
            content = skill.content
            if len(content) > MAX_SKILL_CHARS:
                content = content[:MAX_SKILL_CHARS] + "\n\n[Skill content truncated.]"
            sections.append(f"## {skill.name}")
            sections.append(f"Source: {skill.path}")
            if skill.description:
                sections.append(f"Description: {skill.description}")
            sections.append("")
            sections.append(content)
            sections.append("")
        return "\n".join(sections).rstrip()


def load_skills(
    skill_paths: Iterable[str],
    workdir: Path,
    skill_dirs: Optional[Iterable[str]] = None,
) -> list[LoadedSkill]:
    """Backward-compatible wrapper for loading skills."""
    return SkillRegistry(workdir, skill_dirs).load_skills(skill_paths)


def discover_skills(workdir: Path, skill_dirs: Optional[Iterable[str]] = None) -> list[LoadedSkill]:
    """Discover all skills visible to the workspace."""
    return SkillRegistry(workdir, skill_dirs).list_skills()


def _resolve_path(raw_path: str, workdir: Path) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = workdir / path
    return path.resolve()


def _resolve_skill_files(raw_ref: str, workdir: Path, search_dirs: list[Path]) -> list[Path]:
    ref = raw_ref.strip()
    if ref.lower() in ALL_SKILLS_TOKENS:
        return _iter_all_skill_files(search_dirs)

    explicit_path = _resolve_path(ref, workdir)
    if explicit_path.exists():
        return _iter_skill_files(explicit_path)

    for search_dir in search_dirs:
        for candidate in _named_skill_candidates(ref, search_dir):
            if candidate.exists():
                return _iter_skill_files(candidate)
    return []


def _named_skill_candidates(name: str, search_dir: Path) -> list[Path]:
    return [
        search_dir / name,
        search_dir / f"{name}.md",
        search_dir / name / "SKILL.md",
    ]


def _iter_all_skill_files(search_dirs: list[Path]) -> list[Path]:
    skill_files: list[Path] = []
    seen_paths: set[Path] = set()

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for skill_file in _iter_skill_files(search_dir):
            if skill_file not in seen_paths:
                skill_files.append(skill_file)
                seen_paths.add(skill_file)
        for child in sorted(search_dir.iterdir()):
            if not child.is_dir():
                continue
            for skill_file in _iter_skill_files(child):
                if skill_file not in seen_paths:
                    skill_files.append(skill_file)
                    seen_paths.add(skill_file)
    return skill_files


def _iter_skill_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []

    skill_md = path / "SKILL.md"
    if skill_md.is_file():
        return [skill_md]
    return sorted(p for p in path.glob("*.md") if p.is_file())


def _load_skill_file(path: Path) -> Optional[LoadedSkill]:
    content = _read_skill_file(path)
    if not content:
        return None
    metadata, body = _parse_skill_content(content)
    return LoadedSkill(
        name=metadata.get("name") or _skill_name(path),
        description=metadata.get("description", ""),
        path=path,
        content=body,
    )


def _read_skill_file(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _skill_name(path: Path) -> str:
    if path.name == "SKILL.md":
        return path.parent.name
    return path.stem


def _parse_skill_content(content: str) -> tuple[dict[str, str], str]:
    if not content.startswith("---\n"):
        return {}, content

    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, re.DOTALL)
    if not match:
        return {}, content

    raw_metadata, body = match.groups()
    metadata: dict[str, str] = {}
    for line in raw_metadata.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = _strip_quotes(value.strip())
    return metadata, body.strip()


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
