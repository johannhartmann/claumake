from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure project root on sys.path for direct imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
os.environ.setdefault("CLAUMAKE_DEV_ALLOW_HEURISTIC_FALLBACK", "1")
import pytest
try:
    from claude_sdk import ClaudeSDKClient  # type: ignore
    SDK_AVAILABLE = True
except Exception:
    SDK_AVAILABLE = False

from claumake.cli import cmd_generate


def write_minimal_repo(tmp: Path, language: str = "python") -> None:
    tmp.mkdir(parents=True, exist_ok=True)
    if language == "python":
        (tmp / "pyproject.toml").write_text("""
[project]
name = "sample"
version = "0.0.0"
""".strip(), encoding="utf-8")
    elif language == "node":
        (tmp / "package.json").write_text(json.dumps({"name": "sample", "version": "0.0.0"}), encoding="utf-8")


def test_generate_from_minimal_plan(tmp_path: Path) -> None:
    write_minimal_repo(tmp_path, language="python")
    # Create a minimal plan.json (simulate Claude output)
    plan = {
        "version": "1",
        "language": "python",
        "compose": {"present": False, "file": "compose.yaml", "services": [{"name": "app", "build": "./", "ports": ["8000:8000"], "env": []}]},
        "dockerfile": {"present": False},
        "commands": {"build": ["docker compose build"], "start": ["docker compose up -d"], "test": ["docker compose run --rm app pytest"]},
        "notes": [],
    }
    plan_path = tmp_path / ".claude" / "plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    # generate
    args_gen = type("Args", (), {"repo": str(tmp_path), "plan": str(plan_path), "out": str(tmp_path)})
    rc = cmd_generate(args_gen)
    assert rc == 0

    # artifacts
    assert (tmp_path / "Makefile.build").exists()
    assert (tmp_path / "Makefile.claude").exists()
    # a compose file and Dockerfile should be generated since none existed
    assert (tmp_path / "compose.yaml").exists()
    assert (tmp_path / "Dockerfile").exists()

import os as _os
_sdk_and_key = SDK_AVAILABLE and bool(_os.environ.get("ANTHROPIC_API_KEY"))

@pytest.mark.skipif(not _sdk_and_key, reason="Claude SDK or ANTHROPIC_API_KEY not available")
def test_plan_with_sdk(tmp_path: Path) -> None:
    # Sanity: Ensure plan command runs when SDK is available (does not assert its contents)
    write_minimal_repo(tmp_path, language="python")
    from claumake.cli import cmd_plan
    args_plan = type("Args", (), {"repo": str(tmp_path), "out": str(tmp_path)})
    rc = cmd_plan(args_plan)
    assert rc == 0
