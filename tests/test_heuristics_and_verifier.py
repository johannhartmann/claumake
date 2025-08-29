from __future__ import annotations

import json
from pathlib import Path

from claumake.heuristics import derive_heuristics
from claumake.scan.context import scan_context
from claumake.verifier import verify_commands


def _write_tmp_repo(tmp: Path) -> None:
    (tmp / "README.md").write_text(
        """
        # Demo

        ```bash
        pytest -q
        ```
        """.strip(),
        encoding="utf-8",
    )
    (tmp / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")


def test_scan_context_and_heuristics(tmp_path: Path) -> None:
    _write_tmp_repo(tmp_path)
    ctx = scan_context(tmp_path)
    assert "README.md" in "\n".join(ctx["readme_files"]) or ctx["readme_files"]
    actions = {"run_commands": ["pytest -q"]}
    heur = derive_heuristics(tmp_path, ctx, actions)
    assert heur["language"] in {"python", "unknown"}
    assert "commands" in heur and "test" in heur["commands"]


def test_verify_commands_with_safe_plan(tmp_path: Path) -> None:
    plan = {
        "version": "1",
        "language": "unknown",
        "compose": {"present": False},
        "dockerfile": {"present": False},
        "commands": {
            "build": ["echo build-ok"],
            "test": ["echo test-ok"],
            "start": ["echo start-skip"],
        },
        "notes": [],
    }
    plan_path = tmp_path / ".claude" / "plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    rep = verify_commands(tmp_path, plan_path)
    s = rep.get("summary", {})
    assert s.get("build", {}).get("failed", 1) == 0
    assert s.get("test", {}).get("failed", 1) == 0
    assert s.get("build", {}).get("passed", 0) >= 1
    assert s.get("test", {}).get("passed", 0) >= 1

