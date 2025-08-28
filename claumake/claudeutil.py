from __future__ import annotations

import json
import os
import shutil
import subprocess as sp
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Type
import asyncio


def _load_sdk() -> Tuple[Type[Any], Type[Any]]:
    """Return (ClaudeSDKClient, ClaudeCodeOptions) or raise ImportError.

    Tries known module names for the Claude Code Python SDK.
    """
    last_err: Optional[Exception] = None
    for mod in ("claude_code_sdk", "claude_sdk"):
        try:
            m = __import__(mod, fromlist=["ClaudeSDKClient", "ClaudeCodeOptions"])  # type: ignore
            client = getattr(m, "ClaudeSDKClient")
            options = getattr(m, "ClaudeCodeOptions")
            return client, options
        except Exception as e:
            last_err = e
            continue
    raise ImportError(f"Could not import Claude Code SDK classes: {last_err}")


def claude_sdk_available() -> bool:
    try:
        _load_sdk()
        return True
    except Exception:
        return False


def _run_claude_sdk_json(prompt: str, cwd: Path) -> Dict[str, Any]:
    # Run the Claude Code Python SDK with allowed tools and acceptEdits in repo cwd
    ClaudeSDKClient, ClaudeCodeOptions = _load_sdk()

    options = ClaudeCodeOptions(
        allowed_tools="Read,WebSearch,Write,Bash",
        permission_mode="acceptEdits",
        cwd=str(cwd),
    )

    async def _amain() -> Dict[str, Any]:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set in environment")
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            result_text = ""
            async for msg in client.receive_response():
                if getattr(msg, "content", None):
                    for block in msg.content:
                        if hasattr(block, "text"):
                            result_text += block.text  # accumulate JSON text
            return json.loads(result_text)

    return asyncio.run(_amain())


def synthesize_plan(repo_root: Path) -> Dict[str, Any]:
    """Ask Claude (Python SDK) to produce a BuildPlan JSON by reading the repo itself.

    The SDK runs with allowed tools (Read,Bash,Write) and acceptEdits, so it can scan
    the repo and workflows directly without our programmatic parsing.
    """
    schema_hint = (
        '{"version":"1","language":"node|python|java|go|rust|mixed|unknown","compose":'
        '{"present":true|false,"file":"compose.yaml","services":[{"name":"app","build":"./","ports":["3000:3000"],"env":["..."]}]},'
        '"dockerfile":{"present":true|false,"path":"Dockerfile"},'
        '"commands":{"build":["…"],"start":["…"],"test":["…"]},"notes":["…"]}'
    )
    prompt = (
        "Du bist DevOps/Build-Engineer. Lies README/Docs und .github/workflows im aktuellen Projekt. "
        "Bevorzuge Docker Compose (Dateiname compose.yaml). Liefere ausschliesslich JSON im Schema BuildPlan. "
        "Keine Prosa. Nutze Read/Bash-Tools, um Inhalte zu inspizieren.\n\n"
        f"SCHEMA_HINT: {schema_hint}\n"
    )
    if not claude_sdk_available():
        raise RuntimeError("Claude Code Python SDK not available. Please install claude-code-sdk and set ANTHROPIC_API_KEY.")
    data = _run_claude_sdk_json(prompt, repo_root)
    if not isinstance(data, dict):
        raise RuntimeError("Claude did not return an object for plan")
    data.setdefault("version", "1")
    return data

def refine_plan(repo_root: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ask Claude to refine/repair the plan. Payload may include plan, verify summary, failing tails.

    Returns a dictionary. If the response contains a top-level 'plan', it is used; otherwise the response itself.
    """
    prompt = (
        "Du bist DevOps/Build-Engineer. Erhalte einen BuildPlan + Diagnose und gib ausschliesslich "
        "ein valides BuildPlan-JSON zurück (gleiches Schema). Bevorzuge Docker Compose. Keine Prosa.\n\n"
        f"INPUT:\n{json.dumps(payload, indent=2)}\n"
    )
    if not claude_sdk_available():
        raise RuntimeError("Claude Code Python SDK not available. Please install claude-code-sdk and set ANTHROPIC_API_KEY.")
    data = _run_claude_sdk_json(prompt, repo_root)
    if isinstance(data, dict) and "plan" in data and isinstance(data["plan"], dict):
        return data["plan"]
    if isinstance(data, dict):
        return data
    raise RuntimeError("Claude refine did not return an object")
