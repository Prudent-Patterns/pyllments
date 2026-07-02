from __future__ import annotations

import asyncio

import pytest

from pyllments.payloads import ToolUsePayload
from pyllments.runtime.lifecycle_manager import LifecycleManager, manager as lifecycle_manager
from pyllments.runtime.loop_registry import LoopRegistry


@pytest.fixture(autouse=True)
def _reset_pyllments_runtime_after_test():
    """Reset bound loop and lifecycle state between tests."""
    ToolUsePayload.clear_executor_registry()
    yield
    ToolUsePayload.clear_executor_registry()
    LoopRegistry.reset()
    LifecycleManager.reset_for_tests()


@pytest.fixture
async def pyllments_runtime_cleanup():
    """Bind the pytest loop and tear down registered resources after async tests."""
    LoopRegistry.set(asyncio.get_running_loop())
    yield
    await lifecycle_manager.shutdown()
