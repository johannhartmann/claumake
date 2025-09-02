# claumake — Compose‑first build artifact synthesizer

claumake reads a repository, detects its language/tooling, and synthesizes a consistent, Docker Compose–first build setup. It outputs a deterministic plan plus ready‑to‑use Makefiles so you can build, start, and test most projects the same way — without hand‑crafting CI or local scripts.

## Why claumake?

**Problems it solves:**
- **Build inconsistency**: Every project has different build commands, scripts, and requirements
- **Environment chaos**: "Works on my machine" problems from different tool versions and dependencies  
- **Setup friction**: New team members spend hours figuring out how to build and run projects
- **CI/CD complexity**: Hand-crafting build scripts for each project's unique requirements

**The claumake approach:**
- Normalize build/run/test across diverse repositories using Docker Compose
- Keep environments reproducible with container-first workflows
- Bootstrap CI and local development workflows in minutes, not hours

## Installation and Setup

### Prerequisites
- Python 3.9+, Git, Docker Engine + Compose plugin, `make`
- Claude API key for AI-powered repository analysis
- Optional: `PyYAML` for richer Actions parsing

### Installation
```bash
# Install in editable mode with development dependencies
pip install -e .

# Set your Claude API key
export ANTHROPIC_API_KEY=sk-ant-...  # Required for AI features

# Verify installation
claumake --help
```

### Getting Started

**⭐ Recommended (One-shot setup):**
```bash
# AI analysis → build files → validation → self-healing
claumake init --repo .

# Use generated build system
make -f Makefile.build build    # Build containers via Docker Compose
make -f Makefile.build start    # Start services
make -f Makefile.build test     # Run tests in container
make -f Makefile.build stop     # Stop services
```

**Step-by-step (AI-driven):**
```bash
claumake plan --repo .          # Claude analyzes repo and creates files directly
# Files are ready - no generate step needed!
make -f Makefile.build build    # Use generated build system
```

**Verification and testing:**
```bash
claumake verify --repo .        # Test generated build system without modification
claumake validate --repo .      # Run static validation checks
```

### First Run Example
After running [`claumake init --repo .`](claumake/cli.py:72), you'll see:
```bash
[claumake] Planning…
[claumake] Bootstrapping files with Claude (streaming)…
[claumake] Validating…
[claumake] Verifying build/test…
[claumake] Running initial verification…
[claumake] Verification summary:
  - build: passed=1 failed=0 skipped=0 total=1
  - test: passed=1 failed=0 skipped=0 total=1
  - start: passed=1 failed=0 skipped=0 total=1
[claumake] All critical steps passed.
```

## What claumake generates

- **`.claude/plan.json`**: Machine‑readable BuildPlan with detected language, commands, and Docker configuration
- **`Makefile.build`**: Standard targets (`build`, `start`, `test`, `logs`, `stop`, `lint`, `fmt`, `clean`) that run via Docker Compose
- **`compose.claumake.yaml`**: Docker Compose configuration when missing (non‑invasive - won't overwrite existing files)
- **`Dockerfile.claumake`**: Container definition when missing (non‑invasive)
- **`Makefile.claude`** (optional): Headless prompts for re‑planning and regenerating artifacts

## How it works

claumake scans documentation, manifests, and GitHub Actions to derive heuristics about your project (language, ports, build commands). It uses Claude AI to synthesize a comprehensive BuildPlan, then generates standardized Makefiles and optional Docker configuration. The verification system can execute the plan and iteratively refine it until all targets work correctly.

**Architecture flow:** Repository Analysis → AI Planning → File Generation → Validation → Self-Healing

## Command Reference

### AI-Driven Commands (Require ANTHROPIC_API_KEY)

- **[`claumake init`](claumake/cli.py:72)** - Complete end-to-end workflow that generates all build files using AI and self-heals until working (uses same logic as `all` command)
- **[`claumake plan`](claumake/cli.py:21)** - Uses Claude AI to analyze your repository and generate all necessary build files directly
- **[`claumake all`](claumake/cli.py:72)** - Runs plan, validation, and self-healing in sequence for a complete setup

### Template-Based Commands (Work with existing plan.json)

- **[`claumake generate`](claumake/cli.py:35)** - Generates Makefiles and Docker files from an existing `.claude/plan.json` file

### Validation & Testing Commands

- **[`claumake validate`](claumake/cli.py:53)** - Runs static validation checks on your repository structure and configuration
- **[`claumake verify`](claumake/cli.py:158)** - Executes build and test commands from the plan and reports success/failure results

### Generated Makefile Targets

All targets run via Docker Compose for consistency:

```bash
make -f Makefile.build help     # Show all available targets
make -f Makefile.build build    # Build containers
make -f Makefile.build start    # Start services
make -f Makefile.build logs     # View service logs
make -f Makefile.build test     # Run tests
make -f Makefile.build lint     # Run linting
make -f Makefile.build fmt      # Format code
make -f Makefile.build clean    # Clean up
make -f Makefile.build stop     # Stop services
```

### Environment Variables

- **`ANTHROPIC_API_KEY`**: Required for Claude AI analysis and planning features
- **`CLAUMAKE_PERMISSION_MODE`**: Claude SDK permission mode (default: `bypassPermissions`)
- **`CLAUMAKE_MAX_HEAL`**: Maximum self-healing iterations for [`init`](claumake/cli.py:cmd_init) command (default: 20)

## Advanced Topics

## Troubleshooting

**"Plan not found" error:**
- The [`generate`](claumake/cli.py:35) command requires an existing `.claude/plan.json` file
- Use [`plan`](claumake/cli.py:21) or [`init`](claumake/cli.py:72) instead for AI-driven file generation

**API key issues:**
- Ensure `ANTHROPIC_API_KEY` is set in your environment
- AI-driven commands ([`init`](claumake/cli.py:72), [`plan`](claumake/cli.py:21), [`all`](claumake/cli.py:72)) require a valid Claude API key

**Build failures:**
- Use [`claumake verify --repo .`](claumake/cli.py:158) to test generated build system
- The [`init`](claumake/cli.py:72) command includes self-healing for common build issues

**Installation issues:**
- Ensure you're using Python 3.9+ with `python --version`
- If `pip install -e .` fails, try `python -m pip install -e .`
- For dependency conflicts, use a virtual environment: `python -m venv venv && source venv/bin/activate`

**Docker issues:**
- Ensure Docker Engine and Compose plugin are installed and running
- Test with `docker compose version` (should show v2.0+)
- Check Docker permissions: `docker run hello-world`

### Configuration Options

- **Non-invasive file generation**: Uses `.claumake` suffixes to avoid overwriting existing Docker files
- **Self-healing validation**: The [`init`](claumake/cli.py:cmd_init) command automatically fixes common configuration issues
- **Compose-first approach**: All build commands default to running in containers for reproducibility

## Development

**Local development:**
```bash
make setup    # Install in editable mode with dev/tools (uses uv if available)
make lint     # Run Ruff checks  
make type     # Run MyPy type checks on claumake
make fmt      # Auto-format and fix with Ruff
make test     # Run pytest quietly
make build    # Build the distribution
```

**Container-based development:**
```bash
make -f Makefile.build start    # Start development environment
make -f Makefile.build test     # Run tests in container
make -f Makefile.build logs     # View logs
make -f Makefile.build stop     # Stop services
```

**Quality assurance:**
```bash
make setup && make qa    # Full QA pipeline with uv-installed tools
```

## Fun fact

"claumake" is a playful nod to the German word "Klamauk" (slapstick, shenanigans) — the joke is that instead of chaos, it brings order to builds with Compose and Make.