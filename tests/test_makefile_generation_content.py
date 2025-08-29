from __future__ import annotations

from pathlib import Path

from claumake.gen.makefile import generate_makefiles


def test_generate_wraps_test_command_with_compose(tmp_path: Path) -> None:
    plan = {
        "version": "1",
        "language": "python",
        "compose": {"present": False},
        "dockerfile": {"present": False},
        "commands": {"build": ["echo build"], "start": ["echo start"], "test": ["pytest"]},
        "notes": [],
    }
    generate_makefiles(plan, tmp_path)
    text = (tmp_path / "Makefile.build").read_text(encoding="utf-8")
    # test command should be wrapped to run inside compose
    assert "$(COMPOSE) run --rm $(SERVICE) pytest" in text
    # COMPOSE var should reference compose.claumake.yaml by default
    assert "COMPOSE ?= docker compose -f compose.claumake.yaml" in text

