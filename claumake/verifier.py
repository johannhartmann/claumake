from __future__ import annotations

import os
import shutil
import subprocess as sp
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class RunResult:
    command: str
    returncode: int | None
    stdout: str
    stderr: str
    skipped: bool = False
    reason: str | None = None


def _run(cmd: str, cwd: Path, timeout: int = 900) -> RunResult:
    try:
        p = sp.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
        return RunResult(command=cmd, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except sp.TimeoutExpired as e:
        return RunResult(command=cmd, returncode=None, stdout=e.stdout or "", stderr=(e.stderr or "") + "\nTIMEOUT", skipped=False)


def _docker_available() -> bool:
    """Return True only if docker CLI exists AND daemon is reachable.

    Override with CLAUMAKE_ASSUME_DOCKER=1 to force True (e.g., in CI).
    """
    if os.environ.get("CLAUMAKE_ASSUME_DOCKER") == "1":
        return True
    if shutil.which("docker") is None:
        return False
    try:
        p = sp.run("docker info --format {{.ServerVersion}}", shell=True, capture_output=True, text=True, timeout=10)
        return p.returncode == 0
    except Exception:
        return False


def verify_commands(repo_root: Path, plan_path: Path) -> Dict[str, Any]:
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan not found: {plan_path}")

    import json

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    cmds: Dict[str, List[str]] = plan.get("commands") or {}
    build_cmds = cmds.get("build") or []
    test_cmds = cmds.get("test") or []

    logs_dir = repo_root / ".claude" / "verify"
    logs_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[str, Any] = {"build": [], "test": [], "start": [], "env": {}}
    results["env"]["docker_available"] = _docker_available()

    def record(tag: str, res: RunResult) -> None:
        results[tag].append({
            "command": res.command,
            "returncode": res.returncode,
            "skipped": res.skipped,
            "reason": res.reason,
            "stdout_tail": (res.stdout or "")[-200:],
            "stderr_tail": (res.stderr or "")[-400:],
        })
        # store detailed logs
        safe = tag + "_" + (res.command.replace("/", "_").replace(" ", "_")[:60])
        (logs_dir / f"{safe}.out.log").write_text(res.stdout, encoding="utf-8")
        (logs_dir / f"{safe}.err.log").write_text(res.stderr, encoding="utf-8")

    # Build
    for c in build_cmds[:1]:  # run first candidate only
        if "docker compose" in c and not results["env"]["docker_available"]:
            record("build", RunResult(c, None, "", "docker not available", skipped=True, reason="docker_missing"))
        else:
            record("build", _run(c, repo_root))

    # Test
    for c in test_cmds[:1]:
        if "docker compose" in c and not results["env"]["docker_available"]:
            record("test", RunResult(c, None, "", "docker not available", skipped=True, reason="docker_missing"))
        else:
            record("test", _run(c, repo_root))

    # Start (best-effort): only handle compose up/down pattern
    start_cmds = cmds.get("start") or []
    for c in start_cmds[:1]:
        if "docker compose" in c and "up -d" in c:
            if not results["env"]["docker_available"]:
                record("start", RunResult(c, None, "", "docker not available", skipped=True, reason="docker_missing"))
            else:
                up = _run(c, repo_root, timeout=300)
                record("start", up)
                # fetch ps output for context
                ps = _run("docker compose ps", repo_root, timeout=120)
                record("start", ps)
                # tear down
                _ = _run("docker compose down", repo_root, timeout=300)
        else:
            # We don't know how to verify arbitrary long-running start commands safely
            record("start", RunResult(c, None, "", "unsupported start verification", skipped=True, reason="unsupported"))

    # Summary
    def summarize(tag: str) -> Dict[str, Any]:
        entries = results[tag]
        ok = [e for e in entries if not e.get("skipped") and e.get("returncode") == 0]
        fail = [e for e in entries if not e.get("skipped") and (e.get("returncode") or 1) != 0]
        skip = [e for e in entries if e.get("skipped")]
        return {"passed": len(ok), "failed": len(fail), "skipped": len(skip), "total": len(entries)}

    results["summary"] = {
        "build": summarize("build"),
        "test": summarize("test"),
        "start": summarize("start"),
    }

    # Persist report
    (logs_dir / "verify_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    return results
