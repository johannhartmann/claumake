from __future__ import annotations

import json
import os
import shutil
import subprocess as sp
from pathlib import Path
from typing import Any, Dict

from .gen.makefile import generate_makefiles
from .gen.compose import maybe_generate_compose
from .verifier import verify_commands
from .claudeutil import refine_plan


def _claude_available() -> bool:
    return shutil.which("claude") is not None


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _run_claude(prompt: str, cwd: Path) -> tuple[Dict[str, Any], str | None]:
    # Expect the claude CLI to output a JSON object; if it wraps result, unwrap.
    # Ensure claude CLI can write config in sandbox by overriding HOME within repo
    env = os.environ.copy()
    home_dir = cwd / ".claude" / "home"
    home_dir.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home_dir)
    proc = sp.run(
        [
            "claude",
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
            except Exception:
                pass
        if isinstance(data, dict):
            if "plan" in data:
                return data["plan"], (data.get("explain") or None)
            return data, None
    except Exception:
        pass
    # If parsing fails, include stderr for debugging
    raise RuntimeError(f"claude output not parseable JSON. stderr={proc.stderr[:400]}\nout={out[:400]}")


def self_heal_until_green(
    repo_root: Path,
    plan_path: Path,
    max_iter: int = 3,
    on_event: callable | None = None,
) -> Dict[str, Any]:
    repo_root = Path(repo_root)
    plan_path = Path(plan_path)
    # verify initial
    if on_event:
        on_event("verify_initial", {})
    last_report = verify_commands(repo_root, plan_path)

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
        new_plan = None
        if _claude_available():
            # Load plan
            plan = _load_json(plan_path)
            # Build payload with current plan and verification report only; Claude will inspect repo as needed.
            payload = {
                "plan": {k: plan[k] for k in plan if not k.startswith("_")},
                "verify": last_report,
            }
            try:
                new_plan = refine_plan(repo_root, payload)
            except Exception as e:
                if on_event:
                    on_event("heal_claude_error", {"error": str(e)[:200]})
        else:
            if on_event:
                on_event("heal_no_claude", {})
        if new_plan is None:
            # Could not obtain a refined plan from Claude; abort healing
            break
        # Ensure minimal schema fields are present
        new_plan.setdefault("version", "1")
        new_plan.setdefault("commands", {"build": [], "start": [], "test": []})
        _save_json(plan_path, new_plan)
        # Regenerate artifacts and re-verify
        generate_makefiles(new_plan, repo_root)
        # Force regeneration to apply changes (ports, poetry, etc.)
        maybe_generate_compose(new_plan, repo_root, force=True)
        if on_event:
            on_event("heal_iteration_done", {"iteration": it})
        last_report = verify_commands(repo_root, plan_path)

    return last_report
