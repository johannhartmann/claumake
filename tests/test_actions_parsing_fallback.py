from __future__ import annotations

from pathlib import Path

from claumake.scan.actions import parse_actions


def test_parse_actions_fallback_on_invalid_yaml(tmp_path: Path) -> None:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    bad = wf / "broken.yml"
    # Intentionally malformed YAML but with a run line we want to recover
    bad.write_text(
        """
        name: CI
        jobs:
          build:
            steps:
              - name: Broken
                run: echo hello-from-broken-yaml
                uses: actions/setup-node@v4: this is invalid
        """.strip(),
        encoding="utf-8",
    )
    sig = parse_actions(tmp_path)
    assert any("broken.yml" in f for f in sig.get("workflow_files", []))
    # Regex fallback should capture the run command
    assert any("echo hello-from-broken-yaml" in r for r in sig.get("run_commands", []))
    # And an error should be recorded
    assert sig.get("errors")

