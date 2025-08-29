from __future__ import annotations

from pathlib import Path
from typing import Dict, List


def validate_repo(repo_root: Path) -> Dict:
    errors: List[str] = []
    warnings: List[str] = []
    info: List[str] = []

    # Check Makefiles presence
    if not (repo_root / "Makefile.build").exists():
        warnings.append("Makefile.build not found")
    else:
        info.append("Makefile.build present")
    if not (repo_root / "Makefile.claude").exists():
        warnings.append("Makefile.claude not found")
    else:
        info.append("Makefile.claude present")

    # Compose syntax cannot be fully validated without docker; just check file presence
    compose_files = [
        "compose.claumake.yaml",
        "compose.yaml",
        "compose.yml",
        "docker-compose.yml",
        "docker-compose.yaml",
    ]
    present = [f for f in compose_files if (repo_root / f).exists()]
    if present:
        info.append(f"Compose present: {present[0]}")
    else:
        warnings.append("Compose file not found")

    return {"errors": errors, "warnings": warnings, "info": info}
