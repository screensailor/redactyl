"""Shared pytest fixtures for Redactyl tests.

Usage in tests:
    def test_something(default_pii_config):
        # Use the default config - models loaded once per session
        pii = default_pii_config
        ...
    
    def test_needs_isolation(simple_pii_config):
        # Fresh config for each test when isolation is needed
        pii = simple_pii_config
        ...
    
    def test_no_gliner(pii_config_no_gliner):
        # Config without GLiNER for faster tests
        pii = pii_config_no_gliner
        ...
"""

import pytest

from redactyl.pydantic_integration import PIIConfig


@pytest.fixture(scope="session")
def default_pii_config():
    """Create a default PIIConfig instance that can be reused across tests.
    
    This fixture has session scope, so the models are only loaded once
    per test session, significantly speeding up tests that use the
    default configuration.
    """
    return PIIConfig()


@pytest.fixture(scope="session")
def pii_config_no_gliner():
    """Create a PIIConfig without GLiNER for faster tests that don't need name parsing.
    
    Useful for tests that want to avoid GLiNER model loading time.
    """
    from redactyl.detectors.presidio import PresidioDetector
    
    detector = PresidioDetector(
        use_gliner_for_names=False,
        language="en",
    )
    
    return PIIConfig(
        detector=detector,
        batch_detection=True,
        use_name_parsing=False,
    )


@pytest.fixture
def simple_pii_config():
    """Create a fresh PIIConfig for each test (function scope).
    
    Use this when tests need to modify the config or when isolation
    between tests is important.
    """
    return PIIConfig()