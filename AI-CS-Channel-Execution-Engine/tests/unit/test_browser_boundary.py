from __future__ import annotations

import pytest

from channel_engine.browser import (
    BrowserCommand,
    BrowserExecutionDisabled,
    DisabledBrowserAdapter,
)


def test_browser_execution_is_disabled_in_foundation() -> None:
    adapter = DisabledBrowserAdapter()
    with pytest.raises(BrowserExecutionDisabled, match="Foundation V1"):
        adapter.execute(BrowserCommand(command_name="click", parameters={"target": "send"}))
