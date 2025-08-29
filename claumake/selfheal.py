from __future__ import annotations

import json
import os
import shutil
import subprocess as sp
from pathlib import Path
from typing import Any, Dict, Tuple, Optional, Callable, cast

from .claudeutil import repair_files
from .verifier import verify_commands


def _claude_available() -> bool:
    return shutil.which("claude") is not None


def _load_json(path: Path) -> Dict[str, Any]:
    return cast(Dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _build_prompt(plan: Dict[str, Any], verify_report: Dict[str, Any]) -> str:
    # Base plan (exclude internal keys), but include some context/actions hints if available
    base_plan = {k: plan[k] for k in plan if not k.startswith("_")}
    context = plan.get("_context") or {}
    actions = plan.get("_actions") or {}
    hints = {
        "context": {
            "manifests": (context.get("manifests") or [])[:20],
            "readme_commands": (context.get("readme_commands") or [])[:20],
        },
        "actions": {
            "run_commands": (actions.get("run_commands") or [])[:30],
            "setups": (actions.get("setups") or [])[:15],
        },
    }
    # Extract failing entries with stderr tails for more signal
    def failing_entries(tag: str) -> list[dict[str, str | int | None]]:
        out: list[dict[str, str | int | None]] = []
        for e in (verify_report.get(tag) or [])[:5]:
            if not e.get("skipped") and (e.get("returncode") or 1) != 0:
                out.append({
                    "command": e.get("command"),
                    "returncode": e.get("returncode"),
                    "stderr_tail": e.get("stderr_tail"),
                })
        return out

    vr_summary = verify_report.get("summary", {})
    prompt_payload = {
        "plan": base_plan,
        "hints": hints,
        "verify_summary": vr_summary,
        "verify_fail_samples": {
            "build": failing_entries("build"),
            "test": failing_entries("test"),
            "start": failing_entries("start"),
        },
    }
    payload_str = json.dumps(prompt_payload, indent=2)
    return (
        "Du bist DevOps/Build-Engineer. Lies Plan/Hints/Verify und gib ausschliesslich "
        "ein valides BuildPlan-JSON (gleiches Schema) zurück.\n"
        "Ziel: Kommandos so wählen, dass build/test (und start wenn anwendbar) erfolgreich sind.\n"
        "Bevorzuge Docker Compose (compose.yaml). Falls nicht vorhanden, liefere minimalen Compose-Vorschlag.\n"
        "Kein Text ausser JSON.\n\n"
        f"INPUT:\n{payload_str}\n"
    )


def _run_claude(prompt: str, cwd: Path) -> Tuple[Dict[str, Any], Optional[str]]:
    # Expect the claude CLI to output a JSON object; if it wraps result, unwrap.
    # Ensure claude CLI can write config in sandbox by overriding HOME within repo
    env = os.environ.copy()
    home_dir = cwd / ".claude" / "home"
    home_dir.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home_dir)
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("'claude' CLI not found on PATH")
    proc = sp.run(
        [
            exe,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--allowedTools",
            "Read,WebSearch,Write,Bash",
            "--permission-mode",
            "acceptEdits",
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
        cwd=str(cwd),
    )
    out = proc.stdout.strip()
    try:
        data = json.loads(out)
        if isinstance(data, dict) and "result" in data:
            try:
                inner = data["result"]
                if isinstance(inner, str):
                    inner_obj = json.loads(inner)
                    if isinstance(inner_obj, dict) and "plan" in inner_obj:
                        return inner_obj["plan"], (inner_obj.get("explain") or None)
                    return inner_obj, None
                if isinstance(inner, dict):
                    if "plan" in inner:
                        return inner["plan"], (inner.get("explain") or None)
                    return inner, None
            except (ValueError, TypeError):
                pass
        if isinstance(data, dict):
            if "plan" in data:
                return data["plan"], (data.get("explain") or None)
            return data, None
    except (ValueError, TypeError):
        pass
    # If parsing fails, include stderr for debugging
    raise RuntimeError(f"claude output not parseable JSON. stderr={proc.stderr[:400]}\nout={out[:400]}")


def self_heal_until_green(
    repo_root: Path,
    plan_path: Optional[Path],
    max_iter: int = 20,
    on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    repo_root = Path(repo_root)
    plan_path = Path(plan_path) if plan_path else None
    # verify initial
    if on_event:
        on_event("verify_initial", {})
    last_report = verify_commands(repo_root)

    def passed(rep: Dict[str, Any]) -> bool:
        # Tight criteria: build and test must have at least one executed and passed, and zero failed.
        s = rep.get("summary", {})
        for key in ("build", "test"):
            ks = s.get(key, {})
            if ks.get("failed", 0) != 0:
                return False
            if ks.get("passed", 0) < 1:
                return False
            if ks.get("total", 0) < 1:
                return False
        # If docker available and a compose start command exists, require start success too.
        docker_ok = rep.get("env", {}).get("docker_available")
        has_compose_start = any("docker compose" in (e.get("command") or "") for e in (rep.get("start") or []))
        if docker_ok and has_compose_start:
            ks = s.get("start", {})
            if ks.get("failed", 0) != 0:
                return False
            if ks.get("passed", 0) < 1:
                return False
        return True

    it = 0
    while it < max_iter and not passed(last_report):
        it += 1
        if on_event:
            summ = last_report.get("summary", {})
            # Collect a couple failing samples with stderr tails for readability
            def first_fails(tag: str):
                out = []
                for e in (last_report.get(tag) or []):
                    if not e.get("skipped") and (e.get("returncode") or 1) != 0:
                        out.append({"command": e.get("command"), "stderr_tail": e.get("stderr_tail")})
                        if len(out) >= 2:
                            break
                return out
            reason = {
                "build": summ.get("build"),
                "test": summ.get("test"),
                "start": summ.get("start"),
                "failing": {
                    "build": first_fails("build"),
                    "test": first_fails("test"),
                    "start": first_fails("start"),
                },
            }
            on_event("heal_iteration_start", {"iteration": it, "reason": reason})
        # Ask Claude to repair files directly (streaming)
        try:
            repair_files(repo_root, last_report)
        except Exception as e:
            if on_event:
                on_event("heal_claude_error", {"error": str(e)[:200]})
            break
        # Re-verify after Claude's edits
        if on_event:
            on_event("heal_iteration_done", {"iteration": it})
        last_report = verify_commands(repo_root)

    return last_report
