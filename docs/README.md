# claumake Docs

## Overview
claumake synthesizes a Compose‑first build setup for arbitrary repositories. It scans docs and manifests (and optionally GitHub Actions), derives heuristics (language, ports, commands), produces a BuildPlan (`.claude/plan.json`), and generates Makefiles plus optional `compose.claumake.yaml`/`Dockerfile.claumake`.

## Key Artifacts
- `.claude/plan.json`: Deterministic BuildPlan; source of truth for generation.
- `Makefile.build`: Standard `build/start/test/logs/stop/lint/fmt/clean` targets.
- `Makefile.claude`: Optional headless targets (`plan`, `refine`, `regenerate`).

## Usage
```bash
claumake plan --repo .
claumake generate --repo .
make -f Makefile.build build start test
```

## Architecture
High‑level agent roles and orchestration are described in the repository root `AGENTS.md`.

