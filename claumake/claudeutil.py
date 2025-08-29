from __future__ import annotations

import asyncio
import json
import json as _json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Type, cast


def _load_sdk() -> Tuple[Type[Any], Type[Any]]:
    """Return (ClaudeSDKClient, ClaudeCodeOptions) or raise ImportError.

    Tries known module names for the Claude Code Python SDK.
    """
    last_err: Optional[Exception] = None
    for mod in ("claude_code_sdk", "claude_sdk"):
        try:
            m = __import__(mod, fromlist=["ClaudeSDKClient", "ClaudeCodeOptions"]) 
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


def _run_claude_sdk_json(prompt: str, cwd: Path, expect_file: Optional[Path] = None) -> Dict[str, Any]:
    # Run the Claude Code Python SDK with allowed tools and acceptEdits in repo cwd
    ClaudeSDKClient, ClaudeCodeOptions = _load_sdk()

    # Default to bypassPermissions so Bash/make/docker can run without prompts
    perm_mode = os.environ.get("CLAUMAKE_PERMISSION_MODE", "bypassPermissions")
    options = ClaudeCodeOptions(allowed_tools="Read,WebSearch,Write,Bash", permission_mode=perm_mode, cwd=str(cwd))

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
            # Try parsing accumulated text first
            if result_text.strip():
                return cast(Dict[str, Any], json.loads(result_text))
            # Fallback: if instructed to write a file, read it
            if expect_file and expect_file.exists():
                try:
                    return cast(Dict[str, Any], json.loads(expect_file.read_text(encoding="utf-8")))
                except Exception as e:
                    raise RuntimeError(f"Claude wrote file but JSON parse failed: {e}")
            raise RuntimeError("Claude SDK returned no text content and no expected file was found")

    return asyncio.run(_amain())


def stream_task(prompt: str, cwd: Path) -> None:
    """Run a Claude SDK task and stream assistant text blocks to the console.

    This function does not parse or expect JSON. It relies on Claude to write files
    (via Write tool) as necessary. All streaming output is printed immediately.
    """
    ClaudeSDKClient, ClaudeCodeOptions = _load_sdk()

    perm_mode = os.environ.get("CLAUMAKE_PERMISSION_MODE", "bypassPermissions")
    options = ClaudeCodeOptions(
        allowed_tools="Read,WebSearch,Write,Bash",
        permission_mode=perm_mode,
        cwd=str(cwd),
    )

    def _fmt_tool_use(name: str, data: Any) -> str:
        try:
            if isinstance(data, dict):
                if name.lower() == "read" and data.get("file_path"):
                    return f"[claude][read] {data.get('file_path')}"
                if name.lower() in ("ls", "list") and data.get("path"):
                    return f"[claude][ls] {data.get('path')}"
                if name.lower() == "glob" and data.get("pattern"):
                    return f"[claude][glob] {data.get('pattern')}"
                if name.lower() in ("bash", "run", "shell") and data.get("command"):
                    cmd = str(data.get("command"))[:160]
                    return f"[claude][bash] $ {cmd}"
                if name.lower() == "write" and data.get("path"):
                    return f"[claude][write] {data.get('path')}"
            # fallback generic
            s = str(data)
            if len(s) > 200:
                s = s[:200] + "…"
            return f"[claude][{name or 'tool'}] {s}"
        except Exception:
            return f"[claude][{name or 'tool'}] …"

    def _fmt_tool_result(data: Any) -> str:
        try:
            # If it's a JSON string, try parse
            if isinstance(data, str) and data.strip().startswith("{"):
                try:
                    obj = _json.loads(data)
                except Exception:
                    obj = {"content": data}
            elif isinstance(data, dict):
                obj = data
            else:
                obj = {"content": str(data)}
            is_err = obj.get("is_error") is True
            content = obj.get("content")
            if isinstance(content, str):
                line = content.strip().splitlines()[0] if content.strip() else ""
            else:
                line = str(content)[:160]
            prefix = "[claude][error]" if is_err else "[claude][done]"
            return f"{prefix} {line}" if line else prefix
        except Exception:
            return "[claude][done]"

    async def _amain() -> None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set in environment")
        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)
            last_tool_name: Optional[str] = None
            last_tool_input: Optional[Dict[str, Any]] = None
            async for msg in client.receive_response():
                # Best-effort streaming of any content blocks
                content = getattr(msg, "content", None)
                if not content:
                    continue
                for block in content:
                    # Assistant natural language
                    if hasattr(block, "text") and getattr(block, "text"):
                        for line in str(block.text).splitlines():
                            print(f"[claude] {line}")
                        sys.stdout.flush()
                        continue
                    # Tool invocations and results
                    btype = (getattr(block, "type", None) or type(block).__name__ or "").lower()
                    name = str(getattr(block, "name", getattr(block, "tool", "")) or "").lower()
                    if "tooluse" in btype or name:
                        data = getattr(block, "input", None) or getattr(block, "args", None) or {}
                        last_tool_name = name or None
                        last_tool_input = data if isinstance(data, dict) else None
                        print(_fmt_tool_use(name, data))
                        sys.stdout.flush()
                        continue
                    # Tool result
                    data = getattr(block, "result", None) or getattr(block, "output", None) or getattr(block, "content", None)
                    if data is not None:
                        # Parse for error/content
                        line = _fmt_tool_result(data)
                        # Filter and condense based on last tool
                        if line.startswith("[claude][error]"):
                            # Drop benign EISDIR noise
                            if "EISDIR" in line:
                                pass
                            else:
                                print(line)
                                sys.stdout.flush()
                        else:
                            # Non-error results: print only for write/bash; skip read/ls/glob noise
                            lname = (last_tool_name or "").lower()
                            if lname in ("write",):
                                # Show wrote path
                                path = None
                                if isinstance(last_tool_input, dict):
                                    path = last_tool_input.get("path") or last_tool_input.get("file_path") or last_tool_input.get("target")
                                if path:
                                    print(f"[claude][wrote] {path}")
                                    sys.stdout.flush()
                            elif lname in ("bash", "run", "shell"):
                                print(line.replace("[claude][done]", "[claude][bash ok]"))
                                sys.stdout.flush()
                            # else: suppress ls/read/glob results
                        # reset last tool after handling result
                        last_tool_name = None
                        last_tool_input = None

    return asyncio.run(_amain())


def bootstrap_files(repo_root: Path) -> None:
    """Ask Claude (SDK) to generate Makefile.build, Makefile.claude, and, if needed, compose.yaml and Dockerfile.

    Streaming is enabled and no JSON is expected. Claude writes files directly.
    Policy: Always containerize with Docker Compose; no host installations; all commands run in containers.
    """
    prompt = (
        "Du bist DevOps/Build-Engineer. Lies das aktuelle Projekt. Strikte Richtlinie: Immer Docker Compose verwenden; "
        "keine Host-Installationen. Erzeuge/aktualisiere folgende Dateien im Repo-Root, ohne existierende Compose/Dockerfiles zu überschreiben: \n"
        "- Makefile.build (Targets: help build start stop logs test lint fmt clean compose-up compose-down; alle Kommandos via 'docker compose'). "
        "  Verwende standardmäßig 'COMPOSE ?= docker compose -f compose.claumake.yaml'.\n"
        "- Makefile.claude (Targets: plan refine regenerate update-compose explain; headless Automationen)\n"
        "- compose.claumake.yaml (Service: app; build.context: .; build.dockerfile: Dockerfile.claumake)\n"
        "- Dockerfile.claumake (enthält alle nötigen Tools/Deps)\n\n"
        "Schreibe die Dateien direkt (Write-Tool). Nutze Bash/Read, um die Repo-Struktur zu verstehen. Keine Erklärtexte."
    )
    if not claude_sdk_available():
        raise RuntimeError("Claude Code Python SDK not available. Please install claude-code-sdk and set ANTHROPIC_API_KEY.")
    stream_task(prompt, repo_root)

def repair_files(repo_root: Path, verify_payload: Dict[str, Any]) -> None:
    """Ask Claude (SDK) to repair the generated files based on verification output.

    Streaming only; Claude edits files directly. No JSON expected or parsed.
    """
    prompt = (
        "Du bist DevOps/Build-Engineer. Die Verifikation ist fehlgeschlagen. Strikte Richtlinie: Docker Compose only; "
        "keine Host-Installationen. Passe ausschließlich folgende Dateien an (ohne bestehende Compose/Dockerfile zu überschreiben): \n"
        "- Makefile.build (nutzt 'docker compose -f compose.claumake.yaml')\n"
        "- compose.claumake.yaml\n"
        "- Dockerfile.claumake\n\n"
        f"VERIFY_SUMMARY:\n{json.dumps(verify_payload, indent=2)}\n\n"
        "Iteriere in dieser Sitzung: Führe zuerst 'make -f Makefile.build build' und 'make -f Makefile.build test' aus. "
        "Wenn ein Schritt fehlschlägt, editiere die oben genannten Dateien, dann führe die Kommandos erneut aus, bis build und test erfolgreich sind. "
        "Alle Änderungen mit dem Write-Tool schreiben. Keine Prosa, nur Aktionen und Dateiänderungen."
    )
    if not claude_sdk_available():
        raise RuntimeError("Claude Code Python SDK not available. Please install claude-code-sdk and set ANTHROPIC_API_KEY.")
    stream_task(prompt, repo_root)
