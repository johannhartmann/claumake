# Repository Guidelines

## Project Structure & Module Organization
- `claumake/`: Python CLI source (entrypoint `claumake.cli:main`).
- `tests/`: Pytest suite; mirrors package layout.
- `.claude/`: Generated artifacts (e.g., `plan.json`).
- `Makefile`, `Makefile.build`, `Makefile.claude`: Dev, container, and generator targets.
- Optional runtime assets: `compose.yaml`, `Dockerfile`.

## Build, Test, and Development Commands
- `make setup`: Install in editable mode with dev/tools (uses `uv` if available).
- `make lint`: Run Ruff checks.
- `make type`: Run MyPy type checks on `claumake`.
- `make fmt`: Auto-format and fix with Ruff.
- `make test`: Run pytest quietly; see `pyproject.toml` for defaults.
- `make build`: Build the distribution via `python -m build`.
- Container helpers: `make -f Makefile.build start|test|logs|stop` (Compose-based).

## Coding Style & Naming Conventions
- Python 3.9+, 4-space indent, line length 100 (Ruff config).
- Prefer type hints for public APIs; keep interfaces strict but pragmatic.
- Naming: modules/functions `snake_case`, classes `CamelCase`, constants `UPPER_SNAKE_CASE`.
- Imports sorted and linted by Ruff; run `make fmt` before committing.

## Testing Guidelines
- Framework: Pytest with `tests/` as root; name files `test_*.py`.
- Write fast, isolated unit tests; use fixtures for IO/process boundaries.
- Run locally via `make test` or `pytest -q`; add tests with behavior changes.

## Commit & Pull Request Guidelines
- Commits: Conventional style (e.g., `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`) with imperative, concise subjects.
- PRs: Clear description, rationale, linked issues, and screenshots/logs when UX/CLI output changes.
- Include docs updates for user-visible changes; keep PRs focused and small when possible.

## Agent & Artifact Notes
- Generator flow: `make -f Makefile.claude plan | refine | regenerate` to synthesize `.claude/plan.json` and derive Makefiles/Compose.
- Treat generated files as build outputs; prefer regeneration over manual edits.

## Security & Configuration Tips (Optional)
- Do not commit secrets; use environment variables for SDK keys.
- Keep tests offline/deterministic; avoid network calls in unit tests.
