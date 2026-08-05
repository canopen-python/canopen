import asyncio
import unittest
from typing import Optional

from canopen.async_guard import enable_async_guard


class DualSyncAsyncTestCase(unittest.IsolatedAsyncioTestCase):
    """Base class for async test cases."""

    __test__ = False  # This is a base class, tests should not be run directly.

    async_test: bool
    """Flag to indicate the test mode. If True, the test will run in async
    mode, otherwise it will run in sync mode."""

    loop: Optional[asyncio.AbstractEventLoop]
    """The event loop to use for async tests. This will be set in the setUp
    method if async_test is True, otherwise it will be None."""

    def setUp(self):
        """Set up an object for async testing."""
        enable_async_guard(self.async_test)
        loop = None
        if self.async_test:
            loop = asyncio.get_event_loop()
        self.loop = loop

        # Add a cleanup to disable the async guard after the test
        self.addCleanup(enable_async_guard, False)
