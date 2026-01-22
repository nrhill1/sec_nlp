"""Pytest configuration for TUI tests.

Textual widget tests require socket access for their async event loop.
This conftest enables socket access for all tests in this directory.
"""

import pytest


@pytest.fixture(autouse=True)
def _allow_socket(socket_enabled: None) -> None:
    """Enable socket access for all TUI tests.

    Textual's async test harness uses socketpair() internally for its
    event loop, so we need to allow socket access for these tests.
    """
