# claumake — Compose‑first build artifact synthesizer

claumake reads a repository, detects its language/tooling, and synthesizes a consistent, Docker Compose–first build setup. It outputs a deterministic plan plus ready‑to‑use Makefiles so you can build, start, and test most projects the same way — without hand‑crafting CI or local scripts.

## What it generates
- `.claude/plan.json`: A machine‑readable BuildPlan (language, commands, compose/dockerfile signals, notes).
- `Makefile.build`: Standard targets (`build`, `start`, `test`, `logs`, `stop`, `lint`, `fmt`, `clean`). Defaults run inside Compose.
- `Makefile.claude` (optional): Headless prompts to re‑plan/refine and regenerate artifacts.
- `compose.claumake.yaml` and `Dockerfile.claumake` when a Compose/Dockerfile is missing (non‑invasive).

## Why
- Normalize build/run/test across diverse repos.
- Prefer containers over host installs; keep environments reproducible.
- Bootstrap CI or local workflows in minutes.

## Requirements
- Python 3.9+, Git, Docker Engine + Compose plugin, `make`.
- Optional: `PyYAML` for richer Actions parsing; `claude` CLI for Makefile.claude.

## Install
```bash
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...  # required for planning via Claude SDK
```

## Quickstart
```bash
# From a repo root
claumake plan --repo .                 # write .claude/plan.json
claumake generate --repo .             # write Makefile.build / Makefile.claude (+compose if missing)
make -f Makefile.build build           # build via docker compose
make -f Makefile.build start           # start services
make -f Makefile.build test            # run tests inside the container

# One‑shot with validation and self‑healing
CLAUMAKE_MAX_HEAL=20 claumake all --repo .
```

## How it works (overview)
claumake scans docs/manifests and GitHub Actions, derives heuristics (language, ports, commands), synthesizes a BuildPlan, then generates Makefiles and optional Compose/Dockerfile. Verification can execute the plan and iteratively refine it until green.

## Fun fact
“claumake” is a playful nod to the German word “Klamauk” (slapstick, shenanigans) — the joke is that instead of chaos, it brings order to builds with Compose and Make.

## Development
- Lint: `ruff check .`  •  Types: `mypy claumake`  •  Security: `bandit -q -r claumake -x tests`  •  Dead code: `vulture claumake --min-confidence 80`
- Tests: `pytest -q`  •  Build: `python -m build`
- Full QA via uv-installed tools: `make setup && make qa`
