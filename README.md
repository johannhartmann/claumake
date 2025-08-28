# claumake — Build any Git repo via Compose-first Makefiles

claumake scans a repository, infers language and workflows, and generates:

- .claude/plan.json (deterministic BuildPlan)
- Makefile.build (concrete build/start/test targets; Compose-first)
- Makefile.claude (headless prompts for refining the plan; optional)
- Optional compose.yaml and Dockerfile when missing

With these artifacts, you can build, start, and test most repos in a consistent, Docker Compose–driven way.

## Requirements

- Python 3.9+
- Git
- Docker Engine + Docker Compose plugin (i.e., `docker compose ...`)
- make
- Optional: `PyYAML` to improve GitHub Actions parsing (`pip install pyyaml`)
- Optional: `claude` CLI if you want to use Makefile.claude targets

## Install

In your current Conda or Python environment:

```bash
pip install -e .
# required: set your Anthropic API key for the Claude Code SDK
export ANTHROPIC_API_KEY=sk-ant-...
```

This installs the `claumake` command.

Using uv (optional):

```bash
# create a venv and install in editable mode
uv venv .venv
source .venv/bin/activate
uv pip install -e .

# install dev tools (pytest, ruff, mypy)
uv pip install -e .[dev]

# run tests
pytest -q
```

## Quickstart: Local Repository

From an already cloned repo:

```bash
# 1) Create plan.json
claumake plan --repo .

# 2) Generate Makefiles (and compose/Dockerfile if missing)
claumake generate --repo .

# 3) Run build/start/test via the generated Makefile
make -f Makefile.build build
make -f Makefile.build start
make -f Makefile.build test
```

Shortcut (self-healing included):

```bash
# Plan → Generate → Validate in one go
CLAUMAKE_MAX_HEAL=3 claumake all --repo .
```

## Quickstart: Any GitHub Repository

```bash
# Clone (shallow recommended)
git clone --depth 1 https://github.com/<owner>/<repo>.git
cd <repo>

# Generate artifacts
claumake all --repo .

# Build/Start/Test using Compose-first targets
make -f Makefile.build build
make -f Makefile.build start
make -f Makefile.build test
```

Private repos (token-in-URL form shown for simplicity):

```bash
git clone --depth 1 https://<TOKEN>@github.com/<owner>/<private-repo>.git
```

## What gets generated

- `.claude/plan.json`: BuildPlan with language, commands, compose/dockerfile signals, and notes
- `Makefile.build`: standardized targets
  - `build`: `docker compose build`
  - `start`: `docker compose up -d`
  - `test`: `docker compose run --rm app <test-command>`
  - plus `help`, `stop`, `logs`, `lint`, `fmt`, `clean`, `compose-up`, `compose-down`
- `Makefile.claude` (optional usage): headless targets to (re)generate/refine plan via Claude CLI
- `compose.yaml` and a basic `Dockerfile` if none were present (Compose-first default)

Notes:
- Service name defaults to `app`. Override with `SERVICE=...` when invoking `make` if needed.
- If no Compose is found, claumake proposes a minimal `compose.yaml` and a basic `Dockerfile` based on heuristics (language/ports).

## End-to-end on many repositories

If you have a list of Git URLs in `repos.txt`, one per line:

```bash
#!/usr/bin/env bash
set -euo pipefail
mkdir -p builds
while IFS= read -r url; do
  name=$(basename "$url" .git)
  echo "=== Processing $url ==="
  git clone --depth 1 "$url" "builds/$name" || { echo "clone failed: $url"; continue; }
  pushd "builds/$name" >/dev/null
  if claumake all --repo .; then
    make -f Makefile.build build || true
    make -f Makefile.build test  || true
  else
    echo "claumake failed for $url"
  fi
  popd >/dev/null
done < repos.txt
```

Tips:
- Add `timeout` around `make` calls if you want per-repo time budgets.
- Use `--branch` with `git clone` if you need non-default branches.

## Using Makefile.claude (optional)

If you have the `claude` CLI configured and want iterative refinement:

```bash
# Regenerate plan.json headlessly
make -f Makefile.claude plan

# Refine an existing plan.json
make -f Makefile.claude refine

# Regenerate the Makefiles from the plan
make -f Makefile.claude regenerate
```

These targets expect `claude` with appropriate permissions and environment variables (e.g., `ANTHROPIC_API_KEY`). They are not required for basic usage.

## Verification & Self-Healing

You can run static checks:

```bash
claumake validate --repo .  # static checks only

# Execute plan commands and self-heal (always runs within `claumake all`)
# If Docker is installed but not auto-detected, force it with CLAUMAKE_ASSUME_DOCKER=1
CLAUMAKE_ASSUME_DOCKER=1 CLAUMAKE_MAX_HEAL=3 claumake all --repo .
```

Static validation reports presence of `Makefile.build`, `Makefile.claude`, and Compose files.
The all-command executes build/test and, on failure, invokes the Claude CLI to refine `.claude/plan.json`, regenerates artifacts, and re-runs until success or `CLAUMAKE_MAX_HEAL` is reached. Detailed logs live in `.claude/verify/`.

## Development

- Lint: `ruff check .`
- Type-check: `mypy claumake`
- Test: `pytest -q`
- Build sdist/wheel: `python -m build` (install `build` with `pip install build` or `uv pip install build`)

## Troubleshooting

- Docker not found: ensure `docker` and `docker compose` are installed and accessible.
- Port conflicts: edit `compose.yaml` to adjust ports.
- Incorrect language/commands: open `.claude/plan.json` and tweak `commands` or re-run `claumake plan` after adjusting repo hints (README/Workflows).
- Lint/fmt targets: provided when detectable; otherwise they default to placeholders. You can edit `Makefile.build` to suit.

## Notes & Safety

- Building arbitrary repositories executes their build/test commands inside containers (Compose-first). Review generated Dockerfile/compose before running in sensitive environments.
- For private repositories or rate-limited environments, prefer local scans over remote API calls. claumake does not require network access beyond `git clone` and Docker image pulls triggered by builds.
