import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict

from .claudeutil import synthesize_plan
from .gen.makefile import generate_makefiles
from .gen.compose import maybe_generate_compose
from .validator import validate_repo
from .verifier import verify_commands
from .selfheal import self_heal_until_green


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def cmd_plan(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    print("[claumake] Synthesizing plan with Claude (Python SDK)…")
    try:
        plan = synthesize_plan(repo)
    except Exception as e:
        raise SystemExit(
            "Claude plan synthesis failed and fallback is disabled. "
            "Ensure the Claude Code Python SDK is installed and ANTHROPIC_API_KEY is set.\n"
            f"Error: {e}"
        )

    out = Path(args.out or repo)
    write_json(out / ".claude" / "plan.json", plan)
    print(f"[claumake] Plan created: {out / '.claude' / 'plan.json'}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    plan_path = Path(args.plan or (repo / ".claude" / "plan.json"))
    if not plan_path.exists():
        raise SystemExit(f"Plan not found: {plan_path}")
    with plan_path.open("r", encoding="utf-8") as f:
        plan = json.load(f)

    out_dir = Path(args.out or repo)
    generate_makefiles(plan, out_dir)

    # Optional compose/dockerfile generation when missing
    maybe_generate_compose(plan, out_dir)

    print(f"[claumake] Makefiles generated in {out_dir}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    report = validate_repo(repo)
    if report.get("errors"):
        print("[claumake] Validation errors:")
        for e in report["errors"]:
            print(f"  - {e}")
    if report.get("warnings"):
        print("[claumake] Validation warnings:")
        for w in report["warnings"]:
            print(f"  - {w}")
    if report.get("info"):
        for i in report["info"]:
            print(f"[claumake] {i}")
    if report.get("errors"):
        return 2
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    # Convenience: plan -> generate -> validate
    args_plan = argparse.Namespace(repo=args.repo, out=args.out)
    print("[claumake] Planning…")
    cmd_plan(args_plan)
    args_gen = argparse.Namespace(repo=args.repo, plan=None, out=args.out)
    print("[claumake] Generating Makefiles…")
    cmd_generate(args_gen)
    args_val = argparse.Namespace(repo=args.repo)
    print("[claumake] Validating…")
    rc = cmd_validate(args_val)
    # Show plan insights
    repo = Path(args.repo).resolve()
    plan_path = repo / ".claude" / "plan.json"
    if plan_path.exists():
        try:
            with plan_path.open("r", encoding="utf-8") as f:
                plan = json.load(f)
            lang = plan.get("language", "unknown")
            cmds = plan.get("commands", {}) or {}
            print(f"[claumake] Detected language: {lang}")
            print(f"[claumake] Planned commands:")
            for k in ("build", "start", "test"):
                vals = cmds.get(k) or []
                if vals:
                    print(f"  - {k}: {vals[0]}")
        except Exception:
            pass
    # Always verify and self-heal until green, then print final report
    repo = Path(args.repo).resolve()
    plan_path = repo / ".claude" / "plan.json"
    if plan_path.exists():
        max_iter = int(os.environ.get("CLAUMAKE_MAX_HEAL", "3"))
        print("[claumake] Verifying build/test…")
        def _on_event(kind: str, payload: dict):
            if kind == "verify_initial":
                print("[claumake] Running initial verification…")
            elif kind == "heal_iteration_start":
                it = payload.get("iteration")
                reason = payload.get("reason", {})
                def _fmt(d):
                    return f"passed={d.get('passed',0)} failed={d.get('failed',0)} total={d.get('total',0)}" if d else "-"
                print(f"[claumake] Self-heal iteration {it} (build {_fmt(reason.get('build'))}, test {_fmt(reason.get('test'))}, start {_fmt(reason.get('start'))})…")
                failing = reason.get("failing", {})
                for tag in ("build", "test", "start"):
                    samples = failing.get(tag) or []
                    for sample in samples:
                        cmd = sample.get("command")
                        tail = (sample.get("stderr_tail") or "").strip().splitlines()[-1:] or [""]
                        print(f"    • {tag} failed: {cmd} — {tail[0]}")
            elif kind == "heal_no_claude":
                print("[claumake] Claude CLI not available; applying local fixes…")
            elif kind == "heal_claude_error":
                print(f"[claumake] Claude refinement failed; falling back to local fixes ({payload.get('error')})…")
            elif kind == "heal_claude_explain":
                explain = (payload.get("explain") or "").strip()
                if explain:
                    print(f"[claumake] Claude suggestion: {explain}")
            elif kind == "heal_iteration_done":
                it = payload.get("iteration")
                print(f"[claumake] Iteration {it} complete; re-verifying…")
        try:
            final_report = self_heal_until_green(repo, plan_path, max_iter=max_iter, on_event=_on_event)
            # Human-readable summary
            summ = final_report.get("summary", {})
            print("[claumake] Verification summary:")
            for k in ("build", "test", "start"):
                d = summ.get(k, {})
                print(f"  - {k}: passed={d.get('passed',0)} failed={d.get('failed',0)} skipped={d.get('skipped',0)} total={d.get('total',0)}")
            if any((summ.get(k, {}).get("failed", 0) for k in ("build", "test"))):
                print("[claumake] Some steps are still failing. Check .claude/verify logs.")
            else:
                print("[claumake] All critical steps passed.")
        except Exception as e:
            print(f"[claumake] Self-heal failed: {e}")
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="claumake", description="Generate build artifacts from repos")
    sub = p.add_subparsers(dest="cmd", required=True)

    # plan
    sp = sub.add_parser("plan", help="Scan repo and write .claude/plan.json")
    sp.add_argument("--repo", default=os.getcwd(), help="Path to repo root")
    sp.add_argument("--out", default=None, help="Output root (defaults to repo)")
    sp.set_defaults(func=cmd_plan)

    # generate
    sg = sub.add_parser("generate", help="Generate Makefiles (and optional compose)")
    sg.add_argument("--repo", default=os.getcwd(), help="Path to repo root")
    sg.add_argument("--plan", default=None, help="Path to plan.json (defaults to .claude/plan.json)")
    sg.add_argument("--out", default=None, help="Output directory (defaults to repo)")
    sg.set_defaults(func=cmd_generate)

    # validate
    sv = sub.add_parser("validate", help="Run static validations")
    sv.add_argument("--repo", default=os.getcwd(), help="Path to repo root")
    sv.set_defaults(func=cmd_validate)

    # all
    sa = sub.add_parser("all", help="Plan, generate, validate")
    sa.add_argument("--repo", default=os.getcwd(), help="Path to repo root")
    sa.add_argument("--out", default=None, help="Output directory (defaults to repo)")
    sa.set_defaults(func=cmd_all)

    # init: one-shot end-to-end with self-healing (preferred entrypoint)
    si = sub.add_parser("init", help="One-shot: plan, generate, self-heal to a working Makefile/setup")
    si.add_argument("--repo", default=os.getcwd(), help="Path to repo root")
    si.add_argument("--out", default=None, help="Output directory (defaults to repo)")
    si.set_defaults(func=cmd_all)

    # verify
    svf = sub.add_parser("verify", help="Execute plan commands for build/test and report results")
    svf.add_argument("--repo", default=os.getcwd(), help="Path to repo root")
    svf.add_argument("--plan", default=None, help="Path to plan.json (defaults to .claude/plan.json)")
    def _verify_cmd(a: argparse.Namespace) -> int:
        repo = Path(a.repo).resolve()
        plan = Path(a.plan or repo / ".claude" / "plan.json")
        rep = verify_commands(repo, plan)
        summ = rep.get("summary", {})
        print("[claumake] Verification summary:")
        for k in ("build", "test", "start"):
            d = summ.get(k, {})
            print(f"  - {k}: passed={d.get('passed',0)} failed={d.get('failed',0)} skipped={d.get('skipped',0)} total={d.get('total',0)}")
        return 0
    svf.set_defaults(func=_verify_cmd)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    raise SystemExit(args.func(args))
