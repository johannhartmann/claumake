from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List


README_GLOBS = ["README*", "docs/**/*.md", "CONTRIBUTING*", "INSTALL*"]
MANIFESTS = [
    "compose.yaml",
    "compose.yml",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Dockerfile",
    "Dockerfile.*",
    "Makefile",
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "requirements.txt",
    "poetry.lock",
    "Pipfile",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "Cargo.toml",
]


def _list_files(root: Path, patterns: List[str]) -> List[str]:
    out: List[str] = []
    for pat in patterns:
        for p in root.glob(pat):
            if p.is_file():
                try:
                    out.append(str(p.relative_to(root)))
                except ValueError:
                    out.append(str(p))
    return sorted(set(out))


def _extract_commands_from_text(text: str) -> List[str]:
    # Naive extraction of shell-like lines in fenced blocks or inline
    cmds: List[str] = []
    # fenced code blocks
    code_blocks = re.findall(r"```[a-zA-Z0-9]*\n([\s\S]*?)```", text, re.MULTILINE)
    for block in code_blocks:
        for line in block.splitlines():
            s = line.strip()
            if s and not s.startswith("#") and re.search(r"(npm|pnpm|yarn|pytest|pip|mvn|gradle|go|cargo|make)\b", s):
                cmds.append(s)
    # inline commands (simple heuristic)
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("$"):
            s2 = s[1:].strip()
            if re.search(r"(npm|pnpm|yarn|pytest|pip|mvn|gradle|go|cargo|make)\b", s2):
                cmds.append(s2)
    return cmds[:50]


def scan_context(repo_root: Path) -> Dict:
    root = Path(repo_root)
    readmes = _list_files(root, README_GLOBS)
    manifests = _list_files(root, MANIFESTS)

    candidates: List[str] = []
    for rel in readmes:
        p = root / rel
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            candidates.extend(_extract_commands_from_text(text))
        except (OSError, UnicodeDecodeError):
            continue

    # Extract simple Makefile targets that run tests/build
    if (root / "Makefile").exists():
        try:
            mk = (root / "Makefile").read_text(encoding="utf-8", errors="ignore")
            for line in mk.splitlines():
                s = line.strip()
                if s and not s.startswith("#") and re.search(r"(npm|pnpm|yarn|pytest|pip|mvn|gradle|go|cargo)\b", s):
                    candidates.append(s)
        except (OSError, UnicodeDecodeError):
            # If Makefile cannot be read, skip without failing
            pass

    return {
        "readme_files": readmes,
        "manifests": manifests,
        "readme_commands": candidates[:100],
    }
