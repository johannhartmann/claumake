from __future__ import annotations

from claumake.heuristics import _detect_language as detect  # type: ignore[attr-defined]


def test_detect_language_node() -> None:
    assert detect(["package.json"]) == "node"


def test_detect_language_python() -> None:
    assert detect(["pyproject.toml"]) == "python"
    assert detect(["requirements.txt"]) == "python"
    assert detect(["Pipfile"]) == "python"


def test_detect_language_java() -> None:
    assert detect(["pom.xml"]) == "java"
    assert detect(["build.gradle"]) == "java"
    assert detect(["build.gradle.kts"]) == "java"


def test_detect_language_go() -> None:
    assert detect(["go.mod"]) == "go"


def test_detect_language_rust() -> None:
    assert detect(["Cargo.toml"]) == "rust"


def test_detect_language_unknown() -> None:
    assert detect(["README.md"]) == "unknown"

