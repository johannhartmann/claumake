from __future__ import annotations

from pathlib import Path

from claumake.gen.compose import maybe_generate_compose


def test_maybe_generate_compose_skips_when_present(tmp_path: Path) -> None:
    # Simulate repo with an existing compose.yaml
    (tmp_path / "compose.yaml").write_text("services:{}\n", encoding="utf-8")
    plan = {
        "compose": {"present": True, "file": "compose.yaml"},
        "language": "unknown",
    }
    maybe_generate_compose(plan, tmp_path, force=False)
    # Non-invasive file should not be created
    assert not (tmp_path / "compose.claumake.yaml").exists()

