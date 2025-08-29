from __future__ import annotations

from pathlib import Path

from claumake.gen.compose import maybe_generate_compose
from claumake.gen.makefile import generate_makefiles
from claumake.scan.actions import parse_actions
from claumake.validator import validate_repo
from claumake.cli import build_parser


def test_generate_makefiles_defaults(tmp_path: Path) -> None:
    plan = {
        "version": "1",
        "language": "unknown",
        "compose": {"present": False, "file": "compose.yaml", "services": []},
        "dockerfile": {"present": False},
        # no explicit test command provided to force default placeholder
        "commands": {"build": ["docker compose build"], "start": ["docker compose up -d"], "test": []},
        "notes": [],
    }
    generate_makefiles(plan, tmp_path)
    mf = (tmp_path / "Makefile.build").read_text(encoding="utf-8")
    # Default test command should be wrapped and be a no-op false (failing placeholder)
    assert "$(COMPOSE) run --rm $(SERVICE) false" in mf


def test_maybe_generate_compose_outputs(tmp_path: Path) -> None:
    plan = {
        "language": "python",
        "compose": {"present": False, "services": [{"name": "app", "ports": ["8000:8000"], "env": []}]},
    }
    maybe_generate_compose(plan, tmp_path, force=True)
    assert (tmp_path / "compose.claumake.yaml").exists()
    dockerfile = (tmp_path / "Dockerfile.claumake").read_text(encoding="utf-8")
    assert dockerfile.lstrip().startswith("FROM ")


def test_parse_actions_reads_setup_and_runs(tmp_path: Path) -> None:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    yml = wf / "ci.yml"
    yml.write_text(
        """
        name: CI
        jobs:
          build:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - uses: actions/setup-node@v4
                with:
                  node-version: 20
              - name: Run
                run: npm ci && npm test
        """.strip(),
        encoding="utf-8",
    )
    sig = parse_actions(tmp_path)
    runs = sig.get("run_commands", [])
    assert any("npm ci" in r for r in runs)
    assert any("npm test" in r for r in runs)


def test_validator_reports_files(tmp_path: Path) -> None:
    # initially empty
    rep = validate_repo(tmp_path)
    assert any("not found" in w for w in rep.get("warnings", []))
    # create files
    (tmp_path / "Makefile.build").write_text("help:\n\t@echo ok\n", encoding="utf-8")
    (tmp_path / "Makefile.claude").write_text("help:\n\t@echo ok\n", encoding="utf-8")
    (tmp_path / "compose.claumake.yaml").write_text("services:{}\n", encoding="utf-8")
    rep2 = validate_repo(tmp_path)
    assert any("present" in i for i in rep2.get("info", []))


def test_cli_build_parser_commands_exist() -> None:
    p = build_parser()
    # basic commands registered
    for name in ("plan", "generate", "validate", "all", "init", "verify"):
        assert name in p._subparsers._group_actions[0]._name_parser_map  # type: ignore[attr-defined]
