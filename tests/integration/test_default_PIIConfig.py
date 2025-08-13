from redactyl.detectors.presidio import PresidioDetector
from redactyl.pydantic_integration import PIIConfig


def test_default_config():
    # Create a default PIIConfig
    pii = PIIConfig()

    # Verify detector is created and is a PresidioDetector
    assert pii.detector is not None
    assert isinstance(pii.detector, PresidioDetector)

    # Verify PresidioDetector settings
    assert pii.detector.use_gliner_for_names is False  # Changed default to nameparser
    assert pii.detector.language == "en"
    assert pii.detector.confidence_threshold == 0.7  # Default confidence

    # Verify PIIConfig settings
    assert pii.batch_detection is True
    assert pii.use_name_parsing is True
    assert pii.fuzzy_unredaction is False

    # Verify callbacks are set (should have defaults)
    assert pii.on_gliner_unavailable is not None  # Should have default warning
    assert pii.on_batch_error is not None  # Should have default warning
    assert pii.on_hallucination is None  # No default hallucination handler
    assert pii.on_detection is None  # No default detection callback
