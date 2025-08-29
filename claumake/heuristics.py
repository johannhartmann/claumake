from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional


LANG_DEFAULT_PORTS = {
    "node": 3000,
    "python": 8000,
    "java": 8080,
    "go": 8080,
    "rust": 8080,
}


def _detect_language(manifests: List[str]) -> str:
    mset = set(m.lower() for m in manifests)
    if any(m.endswith("package.json") for m in mset):
        return "node"
    if any(m.endswith("pyproject.toml") or m.endswith("requirements.txt") or m.endswith("pipfile") for m in mset):
        return "python"
    if any(m.endswith("pom.xml") or m.endswith("build.gradle") or m.endswith("build.gradle.kts") for m in mset):
        return "java"
    if any(m.endswith("go.mod") for m in mset):
        return "go"
    if any(m.endswith("cargo.toml") for m in mset):
        return "rust"
    return "unknown"


def _compose_presence(repo_root: Path, manifests: List[str]) -> Tuple[Dict[str, Any], List[str]]:
    notes: List[str] = []
    compose: Dict[str, Any] = {"present": False}
    for fname in ["compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"]:
        p = repo_root / fname
        if p.exists():
            compose = {"present": True, "file": fname}
            break
    if not compose["present"]:
        notes.append("compose.yaml not found; will propose minimal compose")
    return compose, notes


def _dockerfile_presence(repo_root: Path) -> Dict[str, Any]:
    for p in [repo_root / "Dockerfile", *repo_root.glob("Dockerfile.*")]:
        if p.exists():
            return {"present": True, "path": str(p.name)}
    return {"present": False}


def _commands_from_actions(actions: Dict[str, Any]) -> List[str]:
    cmds = []
    for c in actions.get("run_commands", []) or []:
        s = c.strip()
        if s:
            cmds.append(s)
    return cmds


def _guess_test_command(language: str, commands: List[str]) -> Optional[str]:
    # Prefer explicit test commands found in workflows
    for c in commands:
        if re.search(r"\b(npm|pnpm|yarn)\b.*\btest\b", c):
            return c
        if re.search(r"\bpytest\b", c):
            return c
        if re.search(r"\bmvn\b.*\btest\b", c) or re.search(r"\bgradle\b.*\btest\b", c):
            return c
        if re.search(r"\bgo\b.*\btest\b", c):
            return c
        if re.search(r"\bcargo\b.*\btest\b", c):
            return c
    # Fallbacks by language
    return {
        "node": "npm test",
        "python": "pytest",
        "java": "mvn -B test",
        "go": "go test ./...",
        "rust": "cargo test",
    }.get(language)


def _guess_build_command(language: str, commands: List[str]) -> Optional[str]:
    for c in commands:
        if re.search(r"\b(npm|pnpm|yarn)\b.*\b(build|compile)\b", c):
            return c
        if re.search(r"\bmvn\b.*\bpackage\b", c) or re.search(r"\bgradle\b.*\b(build|assemble)\b", c):
            return c
        if re.search(r"\bgo\b.*\bbuild\b", c):
            return c
        if re.search(r"\bcargo\b.*\bbuild\b", c):
            return c
        if re.search(r"\bpytest\b", c):  # sometimes only tests exist
            return None
    return {
        "node": "npm run build",
        "python": None,
        "java": "mvn -B package",
        "go": "go build ./...",
        "rust": "cargo build",
    }.get(language)


def _guess_lint_fmt(language: str, commands: List[str]) -> tuple[list[str], list[str]]:
    lint: List[str] = []
    fmt: List[str] = []
    for c in commands:
        if re.search(r"\b(eslint|npm run lint|ruff|flake8|pylint|golangci-lint|cargo clippy)\b", c):
            lint.append(c)
        if re.search(r"\b(prettier|npm run fmt|black|gofmt|cargo fmt)\b", c):
            fmt.append(c)
    return lint[:3], fmt[:3]


def _extract_exposed_port(repo_root: Path) -> Optional[int]:
    dfile = repo_root / "Dockerfile"
    if dfile.exists():
        try:
            text = dfile.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"^\s*EXPOSE\s+(\d+)", text, re.MULTILINE)
            if m:
                return int(m.group(1))
        except (OSError, UnicodeDecodeError, ValueError):
            return None
    return None


def derive_heuristics(repo_root: Path, context: Dict[str, Any], actions: Dict[str, Any]) -> Dict[str, Any]:
    manifests = context.get("manifests", [])
    language = _detect_language(manifests)
    compose, notes = _compose_presence(repo_root, manifests)
    dockerfile = _dockerfile_presence(repo_root)
    action_cmds = _commands_from_actions(actions)

    test_cmd = _guess_test_command(language, action_cmds)
    build_cmd = _guess_build_command(language, action_cmds)
    lint_cmds, fmt_cmds = _guess_lint_fmt(language, action_cmds)

    # Compose-first commands
    commands: Dict[str, List[str]] = {"build": [], "start": [], "test": []}
    if compose.get("present"):
        commands["build"].append("docker compose build")
        commands["start"].append("docker compose up -d")
        if test_cmd:
            commands["test"].append(f"docker compose run --rm app {test_cmd}")
    else:
        # No compose: plain commands fallbacks
        if build_cmd:
            commands["build"].append(build_cmd)
        if language in ("node", "python", "java", "go", "rust"):
            commands["start"].append("docker compose up -d")  # will generate minimal compose
        if test_cmd:
            commands["test"].append(test_cmd)

    # Port heuristic
    port = _extract_exposed_port(repo_root)
    if port is None:
        port = LANG_DEFAULT_PORTS.get(language)
        if port:
            notes.append(f"Using default port {port} for language {language}")
    else:
        notes.append(f"Detected EXPOSE {port} from Dockerfile")

    compose_info: Dict[str, Any] = compose
    if not compose.get("present") and port:
        compose_info = {
            "present": False,
            "file": "compose.yaml",
            "services": [
                {"name": "app", "build": "./", "ports": [f"{port}:{port}"], "env": []}
            ],
        }

    heur: Dict[str, Any] = {
        "language": language,
        "compose": compose_info,
        "dockerfile": dockerfile,
        "commands": commands,
        "notes": notes,
    }

    if lint_cmds:
        heur.setdefault("commands_extra", {})["lint"] = lint_cmds
    if fmt_cmds:
        heur.setdefault("commands_extra", {})["fmt"] = fmt_cmds

    return heur
