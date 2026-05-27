"""Packaging checks for release artifacts."""

import subprocess
import sys
import zipfile
from pathlib import Path


def test_wheel_includes_tui_stylesheet(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    dist_dir = tmp_path / "dist"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--wheel-dir",
            str(dist_dir),
        ],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    wheels = list(dist_dir.glob("yycode-*.whl"))
    assert len(wheels) == 1

    with zipfile.ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())

    assert "agent/tui/styles.tcss" in names
    assert "yycode-0.3.4.data/data/skills/plan.md" in names
    assert "yycode-0.3.4.data/data/skills/drawio/SKILL.md" in names
    assert "yycode-0.3.4.data/data/skills/drawio/styles/built-in/default.json" in names
