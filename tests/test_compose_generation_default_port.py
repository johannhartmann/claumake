from __future__ import annotations

from pathlib import Path

from claumake.gen.compose import maybe_generate_compose


def test_compose_generation_defaults_to_3000_port(tmp_path: Path) -> None:
    plan = {"language": "unknown", "compose": {"present": False, "services": []}}
    maybe_generate_compose(plan, tmp_path, force=True)
    content = (tmp_path / "compose.claumake.yaml").read_text(encoding="utf-8")
    assert "3000:3000" in content

