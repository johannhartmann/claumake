from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List


def _safe_yaml_load(text: str) -> Any:
    try:
        import yaml  # noqa: F401

        return yaml.safe_load(text)
    except Exception:
        return None


def _parse_runs_from_yaml(doc: Any) -> List[str]:
    runs: List[str] = []
    if not isinstance(doc, dict):
        return runs
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return runs
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if isinstance(step, dict):
                run = step.get("run")
                if isinstance(run, str):
                    # split by lines and '&&' to get individual commands
                    parts = re.split(r"\n|&&", run)
                    for part in parts:
                        s = part.strip()
                        if s:
                            runs.append(s)
    return runs


def _parse_setups_from_yaml(doc: Any) -> List[str]:
    setups: List[str] = []
    if not isinstance(doc, dict):
        return setups
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return setups
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if isinstance(step, dict):
                uses = step.get("uses")
                if isinstance(uses, str) and uses.startswith("actions/setup-"):
                    setups.append(uses)
                with_ = step.get("with")
                if isinstance(with_, dict):
                    for k, v in with_.items():
                        setups.append(f"with:{k}={v}")
    return setups


def parse_actions(repo_root: Path) -> Dict[str, Any]:
    root = Path(repo_root)
    wf_dir = root / ".github" / "workflows"
    files: List[str] = []
    runs: List[str] = []
    setups: List[str] = []
    errors: List[str] = []
    if wf_dir.exists():
        for p in wf_dir.rglob("*.yml"):
            if p.is_file():
                files.append(str(p.relative_to(root)))
                text = p.read_text(encoding="utf-8", errors="ignore")
                doc = _safe_yaml_load(text)
                if doc is None:
                    # fall back to naive regex to capture run lines
                    for m in re.finditer(r"run:\s*(.+)", text):
                        runs.append(m.group(1).strip())
                    errors.append(f"YAML parse failed for {p}")
                else:
                    runs.extend(_parse_runs_from_yaml(doc))
                    setups.extend(_parse_setups_from_yaml(doc))
        for p in wf_dir.rglob("*.yaml"):
            if p.is_file():
                files.append(str(p.relative_to(root)))
                text = p.read_text(encoding="utf-8", errors="ignore")
                doc = _safe_yaml_load(text)
                if doc is None:
                    for m in re.finditer(r"run:\s*(.+)", text):
                        runs.append(m.group(1).strip())
                    errors.append(f"YAML parse failed for {p}")
                else:
                    runs.extend(_parse_runs_from_yaml(doc))
                    setups.extend(_parse_setups_from_yaml(doc))

    # Minimal signals
    signals: Dict[str, Any] = {
        "workflow_files": sorted(set(files)),
        "run_commands": runs[:200],
        "setups": sorted(set(setups))[:50],
        "errors": errors,
    }
    return signals
