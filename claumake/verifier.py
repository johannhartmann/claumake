from __future__ import annotations

import os
import shutil
import subprocess as sp
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RunResult:
    command: str
    returncode: Optional[int]
    stdout: str
    stderr: str
    skipped: bool = False
    reason: Optional[str] = None


def _ensure_str(val: Any) -> str:
    if isinstance(val, str):
        return val
    if isinstance(val, bytes):
        try:
            return val.decode()
        except Exception:
            return ""
    return ""


def _run(cmd: str, cwd: Path, timeout: int = 900) -> RunResult:
    try:
        # Running arbitrary plan/test commands requires a shell. Inputs are repository-local and
        # executed in a controlled environment. nosec B602
        p = sp.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)  # nosec B602
        return RunResult(command=cmd, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except sp.TimeoutExpired as e:
        return RunResult(command=cmd, returncode=None, stdout=_ensure_str(e.stdout), stderr=_ensure_str(e.stderr) + "\nTIMEOUT", skipped=False)


def _docker_available() -> bool:
    """Return True only if docker CLI exists AND daemon is reachable.

    Override with CLAUMAKE_ASSUME_DOCKER=1 to force True (e.g., in CI).
    """
    if os.environ.get("CLAUMAKE_ASSUME_DOCKER") == "1":
        return True
    if shutil.which("docker") is None:
        return False
    try:
        # Query docker daemon status; shell used for portability. nosec B602 B607
        p = sp.run("docker info --format {{.ServerVersion}}", shell=True, capture_output=True, text=True, timeout=10)  # nosec B602 B607
        return p.returncode == 0
    except Exception:
        return False


def verify_commands(repo_root: Path, plan_path: Optional[Path] = None) -> Dict[str, Any]:
    import json
    cmds: Dict[str, List[str]] = {}
    build_cmds: List[str] = []
    test_cmds: List[str] = []
    start_cmds: List[str] = []
    if plan_path and plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        cmds = plan.get("commands") or {}
        build_cmds = cmds.get("build") or []
        test_cmds = cmds.get("test") or []
        start_cmds = cmds.get("start") or []
    else:
        build_cmds = ["make -f Makefile.build build"]
        test_cmds = ["make -f Makefile.build test"]
        start_cmds = ["make -f Makefile.build start"]

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
    for c in start_cmds[:1]:
        if "docker compose" in c and "up -d" in c:
            if not results["env"]["docker_available"]:
                record("start", RunResult(c, None, "", "docker not available", skipped=True, reason="docker_missing"))
            else:
                up = _run(c, repo_root, timeout=300)
                record("start", up)
                # fetch ps output for context
                ps = _run("docker compose -f compose.claumake.yaml ps", repo_root, timeout=120)
                record("start", ps)
                # tear down
                _ = _run("docker compose -f compose.claumake.yaml down", repo_root, timeout=300)
        else:
            # We don't know how to verify arbitrary long-running start commands safely
            record("start", RunResult(c, None, "", "unsupported start verification", skipped=True, reason="unsupported"))

    # Summary
    def summarize(tag: str) -> Dict[str, Any]:
        entries = results[tag]
        def rc(e: Dict[str, Any]) -> Optional[int]:
            v = e.get("returncode")
            try:
                return int(v) if v is not None else None
            except Exception:
                return None
        ok = [e for e in entries if not e.get("skipped") and rc(e) == 0]
        fail = [e for e in entries if not e.get("skipped") and (rc(e) is not None and rc(e) != 0)]
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
