from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


BUILD_TEMPLATE = """SHELL := /bin/bash
COMPOSE ?= docker compose -f compose.claumake.yaml
SERVICE ?= app

.PHONY: help build start stop logs test lint fmt clean compose-up compose-down

help:
	@echo "Targets: build start stop logs test lint fmt clean compose-up compose-down"

build:
	{build_cmd}

start:
	{start_cmd}

stop:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f $(SERVICE)

test:
	{test_cmd}

lint:
	{lint_cmd}

fmt:
	{fmt_cmd}

clean:
	git clean -xfd -e node_modules -e .venv

compose-up: start
compose-down: stop
"""


CLAUDE_TEMPLATE = """SHELL := /bin/bash
CLAUDE ?= claude
ALLOWED := "Read,WebSearch,Write,Bash"
PERM := acceptEdits
CWD := $(PWD)

.PHONY: plan refine regenerate update-compose explain

plan:
	$(CLAUDE) -p "Erstelle einen BuildPlan als valides JSON (Schema BuildPlan). \\\n+	Lies README/docs und .github/workflows, bevorzuge Docker Compose." \\\n+	 --output-format json --allowedTools $(ALLOWED) --permission-mode $(PERM) --cwd $(CWD) \\\n+	 | jq -r '.result // . | tostring' > .claude/plan.json

refine:
	$(CLAUDE) -p "Überarbeite den vorliegenden BuildPlan (.claude/plan.json) auf Basis \\\n+	neuer Erkenntnisse. Liefere nur JSON." \\\n+	 --output-format json --allowedTools $(ALLOWED) --permission-mode $(PERM) --cwd $(CWD) \\\n+	 | jq -r '.result // . | tostring' > .claude/plan.json

regenerate:
	python -m claumake.gen.makefile --plan .claude/plan.json --out .

update-compose:
	$(CLAUDE) -p "Wenn kein compose.yaml existiert, generiere eine minimal lauffähige Compose-Datei \\\n+	(services: app, ports, env). Schreibe die Datei und erkläre kurz die Annahmen." \\\n+	 --allowedTools $(ALLOWED) --permission-mode $(PERM) --cwd $(CWD)

explain:
	$(CLAUDE) -p "Erkläre kurz die Build-/Test-Ströme aus Workflows & README." \\\n+	 --print --allowedTools "Read" --cwd $(CWD)
"""


def _first_or_default(cmds: List[str], default: str) -> str:
    return cmds[0] if cmds else default


def _compose_wrapped(cmd: str) -> str:
    # If the command already starts with docker compose, keep it; else run inside compose
    c = cmd.strip()
    if c.startswith("docker compose"):
        return c
    return f"$(COMPOSE) run --rm $(SERVICE) {c}"


def generate_makefiles(plan: Dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    commands = plan.get("commands", {}) or {}
    build_cmd = _first_or_default(commands.get("build", []), "$(COMPOSE) build")
    start_cmd = _first_or_default(commands.get("start", []), "$(COMPOSE) up -d")
    # Default: require Claude to provide a test command; fail fast if missing
    test_cmd = _compose_wrapped(_first_or_default(commands.get("test", []), "false"))

    # extras
    lint_cmd = _compose_wrapped("echo 'no lint configured' || true")
    fmt_cmd = _compose_wrapped("echo 'no fmt configured' || true")

    mf_build = BUILD_TEMPLATE.format(
        build_cmd=build_cmd,
        start_cmd=start_cmd,
        test_cmd=test_cmd,
        lint_cmd=lint_cmd,
        fmt_cmd=fmt_cmd,
    )
    (out_dir / "Makefile.build").write_text(mf_build, encoding="utf-8")

    (out_dir / "Makefile.claude").write_text(CLAUDE_TEMPLATE, encoding="utf-8")


def main() -> None:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Generate Makefiles from plan.json")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", default=".")
    ns = ap.parse_args()
    with open(ns.plan, "r", encoding="utf-8") as f:
        plan = json.load(f)
    generate_makefiles(plan, Path(ns.out))


if __name__ == "__main__":
    main()
