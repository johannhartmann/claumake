from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_compose_commands_skipped_when_docker_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Force docker detection to False by making shutil.which return None
    from claumake import verifier

    monkeypatch.setenv("CLAUMAKE_ASSUME_DOCKER", "0")
    monkeypatch.setattr(verifier.shutil, "which", lambda _: None)

    plan = {
        "version": "1",
        "language": "unknown",
        "compose": {"present": True},
        "dockerfile": {"present": False},
        "commands": {
            "build": ["docker compose build"],
            "test": ["docker compose run --rm app echo ok"],
            "start": ["docker compose up -d"],
        },
        "notes": [],
    }
    plan_path = tmp_path / ".claude" / "plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    rep = verifier.verify_commands(tmp_path, plan_path)
    assert any(e.get("skipped") and e.get("reason") == "docker_missing" for e in rep.get("build", []))
    assert any(e.get("skipped") and e.get("reason") == "docker_missing" for e in rep.get("test", []))
    assert any(e.get("skipped") and e.get("reason") == "docker_missing" for e in rep.get("start", []))

