from __future__ import annotations

from pathlib import Path

from claumake.heuristics import derive_heuristics


def test_exposed_port_in_dockerfile_influences_compose(tmp_path: Path) -> None:
    # Write a Dockerfile with EXPOSE to be picked up by heuristics
    (tmp_path / "Dockerfile").write_text("FROM alpine\nEXPOSE 4567\n", encoding="utf-8")
    ctx = {"manifests": []}
    actions = {"run_commands": []}
    heur = derive_heuristics(tmp_path, ctx, actions)
    assert any("EXPOSE 4567" in n for n in heur.get("notes", []))
    ports = heur.get("compose", {}).get("services", [{}])[0].get("ports", [])
    assert "4567:4567" in ports

