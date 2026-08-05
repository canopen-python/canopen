
import pytest

import canopen


@pytest.fixture(scope="session", autouse=True)
def enable_network_exceptions():
    """Fixture to enable exceptions in the reception threads.

    This makes sure exceptions are not swallowed in the reception threads,
    which is useful for debugging and testing.
    """
    canopen.Network.FILTER_ERRORS = False
    yield
