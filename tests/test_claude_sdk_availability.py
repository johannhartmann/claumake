from __future__ import annotations

import importlib.util

import pytest

from claumake.claudeutil import claude_sdk_available


@pytest.mark.skipif(importlib.util.find_spec("claude_sdk") is not None or importlib.util.find_spec("claude_code_sdk") is not None, reason="SDK present in environment")
def test_claude_sdk_unavailable_returns_false() -> None:
    assert claude_sdk_available() is False

