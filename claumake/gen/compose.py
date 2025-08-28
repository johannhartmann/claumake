from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def _compose_yaml(service_name: str, port_map: str) -> str:
    return f"""# generated-by: claumake
services:
  {service_name}:
    build: .
    ports:
      - "{port_map}"
    environment: []
"""


def _dockerfile(language: str, port: int | None) -> str:
    if language == "node":
        base = "node:20-alpine"
        expose = f"\nEXPOSE {port}" if port else ""
        return f"""FROM {base}
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev || npm install --omit=dev
COPY . .
{f'EXPOSE {port}' if port else ''}
CMD ["npm","start"]
"""
    if language == "python":
        return f"""FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt* ./
RUN pip install -r requirements.txt || true
COPY . .
{f'EXPOSE {port}' if port else ''}
CMD ["python","-m","http.server","{port or 8000}"]
"""
    # generic
    return """FROM alpine:3.19
WORKDIR /app
COPY . .
CMD ["sh","-c","echo 'Add a proper Dockerfile' && sleep 1"]
"""


def maybe_generate_compose(plan: Dict[str, Any], out_dir: Path, force: bool = False) -> None:
    compose = plan.get("compose") or {}
    present = compose.get("present")
    file_name = compose.get("file", "compose.yaml")
    services = compose.get("services") or []

    compose_path = out_dir / file_name
    dockerfile_path = out_dir / "Dockerfile"

    if present and compose_path.exists() and not force:
        return

    # Generate minimal compose if absent
    port_map = None
    if services:
        svc = services[0]
        ports = (svc.get("ports") or [":"])  # type: ignore
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
