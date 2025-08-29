## Contributing to claumake

Thanks for your interest in improving claumake! This guide helps you set up a dev environment, run quality checks, and open effective pull requests.

### Getting Started
- Prereqs: Python 3.9+, Git, Docker + Compose, `make`.
- Install with uv (recommended):
  - `make setup`
- Run the full quality gate locally:
  - `make qa` (ruff, mypy, bandit, vulture, pytest)

### Development Workflow
- Code style: Python 3.9+, 4‑space indent, Ruff-managed imports and formatting. Type hints encouraged for public APIs.
- Tests: Pytest under `tests/`. Name files `test_*.py`. Keep tests fast and isolated.
- Coverage: CI enforces a minimum coverage threshold; please add tests with behavior changes.

### Commits & PRs
- Commit messages: Conventional prefixes (e.g., `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`) with concise, imperative subjects.
- Pull requests must include:
  - Clear description and rationale
  - Linked issues (if applicable)
  - Passing `make qa`
  - Docs updates for user-visible changes (`README.md`, `AGENTS.md`, or `docs/`)

### Project Context
- What claumake does: synthesizes Compose‑first build artifacts (Makefiles, plan.json, optional compose/Dockerfile) for arbitrary repos.
- Architecture & agent roles: see `AGENTS.md`.

### Reporting Issues
- Include repro steps, expected vs. actual behavior, and environment details.
- If a generated plan is incorrect, attach `.claude/plan.json` and any logs under `.claude/verify/`.

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.

