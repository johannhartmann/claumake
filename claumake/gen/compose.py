from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def _compose_yaml(service_name: str, port_map: str) -> str:
    return (
        "# generated-by: claumake\n"
        "services:\n"
        f"  {service_name}:\n"
        "    build:\n"
        "      context: .\n"
        "      dockerfile: Dockerfile.claumake\n"
        "    ports:\n"
        f"      - \"{port_map}\"\n"
        "    environment: []\n"
    )


def _dockerfile(language: str, port: Optional[int]) -> str:
    # Minimal base; Claude is expected to synthesize a proper Dockerfile in the plan.
    # We generate a simple placeholder to keep Compose valid if the plan omitted it.
    return (
        "FROM alpine:3.19\n"
        "WORKDIR /app\n"
        "COPY . .\n"
        "CMD [\"sh\",\"-c\",\"echo 'Add a proper Dockerfile via claumake/Claude plan' && sleep 1\"]\n"
    )


def maybe_generate_compose(plan: Dict[str, Any], out_dir: Path, force: bool = False) -> None:
    compose = plan.get("compose") or {}
    present = compose.get("present")
    # Always generate to non-invasive filename to avoid clobbering existing files
    file_name = "compose.claumake.yaml"
    services = compose.get("services") or []

    compose_path = out_dir / file_name
    dockerfile_path = out_dir / "Dockerfile.claumake"

    if present and (out_dir / (compose.get("file") or "compose.yaml")).exists() and not force:
        return

    # Generate minimal compose if absent
    port_map = None
    if services:
        svc = services[0]
        ports = (svc.get("ports") or [":"])
        port_map = ports[0]
    if not port_map:
        port_map = "3000:3000"

    if force or not compose_path.exists():
        compose_path.write_text(_compose_yaml("app", port_map), encoding="utf-8")

    # Generate Dockerfile if missing
    lang = (plan.get("language") or "unknown").lower()
    if force or not dockerfile_path.exists():
        # try to infer container port from port_map
        try:
            container_port = int(str(port_map).split(":")[1])
        except Exception:
            container_port = None
        dockerfile_path.write_text(_dockerfile(lang, container_port), encoding="utf-8")
