from __future__ import annotations

from pathlib import Path

from claumake.scan.context import scan_context


def test_context_extracts_fenced_and_inline_commands(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        """
        # Sample

        ```bash
        npm run build
        ```

        Some text
        $ pytest -q
        """.strip(),
        encoding="utf-8",
    )
    ctx = scan_context(tmp_path)
    cmds = ctx.get("readme_commands", [])
    assert any("npm run build" in c for c in cmds)
    assert any("pytest -q" in c for c in cmds)

