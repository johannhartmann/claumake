from __future__ import annotations

import json
from pathlib import Path

from claumake.verifier import verify_commands


def test_start_non_compose_is_marked_unsupported(tmp_path: Path) -> None:
    plan = {
        "version": "1",
        "language": "unknown",
        "compose": {"present": False},
        "dockerfile": {"present": False},
        "commands": {
            "build": ["echo build"],
            "test": ["echo test"],
            "start": ["echo not-really-start"],
        },
        "notes": [],
    }
    plan_path = tmp_path / ".claude" / "plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    rep = verify_commands(tmp_path, plan_path)
    starts = rep.get("start", [])
    assert any(e.get("skipped") and e.get("reason") == "unsupported" for e in starts)

