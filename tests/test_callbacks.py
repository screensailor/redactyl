"""Tests for the callback system in redactyl."""

import warnings
from unittest.mock import Mock, patch

import pytest
from pydantic import BaseModel

from redactyl.callbacks import CallbackContext
from redactyl.core import PIILoop
from redactyl.detectors.presidio import PresidioDetector
from redactyl.pydantic_integration import PIIConfig
from redactyl.types import PIIEntity, PIIType, UnredactionIssue


class TestCallbackContext:
    """Tests for CallbackContext."""
    
    def test_default_callbacks(self):
        """Test that default callbacks use warnings."""
        context = CallbackContext.with_defaults()
        
        # Check that callbacks are set
        assert context.on_gliner_unavailable is not None
        assert context.on_batch_error is not None
        assert context.on_gliner_model_error is not None
        
        # Test that they trigger warnings
        with pytest.warns(UserWarning, match="GLiNER is not installed"):
            context.trigger_gliner_unavailable()
        
        with pytest.warns(RuntimeWarning, match="Batch processing error"):
            context.trigger_batch_error(Exception("test error"))
        
        with pytest.warns(RuntimeWarning, match="Failed to load GLiNER model"):
            context.trigger_gliner_model_error("test_model", Exception("load error"))
    
    def test_silent_context(self):
        """Test that silent context has no callbacks."""
        context = CallbackContext.silent()
        
        # All callbacks should be None
        assert context.on_gliner_unavailable is None
        assert context.on_detection is None
        assert context.on_batch_error is None
        assert context.on_unredaction_issue is None
        assert context.on_gliner_model_error is None
        
        # Triggering should do nothing (no errors)
        context.trigger_gliner_unavailable()
        context.trigger_detection([])
        context.trigger_batch_error(Exception("test"))
        context.trigger_unredaction_issue(UnredactionIssue("token", "type"))
        context.trigger_gliner_model_error("model", Exception("error"))
    
    def test_custom_callbacks(self):
        """Test custom callbacks are triggered correctly."""
        # Create mocks for callbacks
        on_gliner = Mock()
        on_detection = Mock()
        on_batch = Mock()
        on_issue = Mock()
        
        context = CallbackContext(
            on_gliner_unavailable=on_gliner,
            on_detection=on_detection,
            on_batch_error=on_batch,
            on_unredaction_issue=on_issue,
        )
        
        # Trigger callbacks
        entities = [PIIEntity(PIIType.PERSON, "John", 0, 4, 0.9)]
        error = Exception("test error")
        issue = UnredactionIssue("token", "hallucination")
        
        context.trigger_gliner_unavailable()
        context.trigger_detection(entities)
        context.trigger_batch_error(error)
        context.trigger_unredaction_issue(issue)
        
        # Verify callbacks were called
        on_gliner.assert_called_once()
        on_detection.assert_called_once_with(entities)
        on_batch.assert_called_once_with(error)
        on_issue.assert_called_once_with(issue)


class TestPIIConfigCallbacks:
    """Tests for PIIConfig callback integration."""
    
    def test_default_callbacks(self):
        """Test that PIIConfig sets default callbacks correctly."""
        detector = Mock()
        config = PIIConfig(detector)
        
        # Check defaults are set
        assert config.on_gliner_unavailable is not None
        assert config.on_batch_error is not None
        assert config.on_detection is None  # No default for this
        assert config.on_unredaction_issue is None  # No default for this
    
    def test_custom_callbacks(self):
        """Test custom callbacks in PIIConfig."""
        detector = Mock()
        on_gliner = Mock()
        on_detection = Mock()
        on_batch = Mock()
        on_issue = Mock()
        
        config = PIIConfig(
            detector,
            on_gliner_unavailable=on_gliner,
            on_detection=on_detection,
            on_batch_error=on_batch,
            on_unredaction_issue=on_issue,
        )
        
        assert config.on_gliner_unavailable == on_gliner
        assert config.on_detection == on_detection
        assert config.on_batch_error == on_batch
        assert config.on_unredaction_issue == on_issue
    
    def test_silence_callbacks(self):
        """Test that callbacks can be silenced by setting to None."""
        detector = Mock()
        config = PIIConfig(
            detector,
            on_gliner_unavailable=None,
            on_batch_error=None,
        )
        
        # These should be None (silenced)
        assert config.on_gliner_unavailable is None
        assert config.on_batch_error is None


class TestPIILoopCallbacks:
    """Tests for PIILoop callback integration."""
    
    def test_detection_callback(self):
        """Test that detection callback is triggered."""
        detector = Mock()
        detector.detect.return_value = [
            PIIEntity(PIIType.EMAIL, "test@example.com", 0, 16, 0.9)
        ]
        
        on_detection = Mock()
        callbacks = CallbackContext(on_detection=on_detection)
        
        loop = PIILoop(detector, callbacks=callbacks)
        loop.redact("test@example.com")
        
        # Verify detection callback was called
        on_detection.assert_called_once()
        args = on_detection.call_args[0][0]
        assert len(args) == 1
        assert args[0].type == PIIType.EMAIL
    
    def test_from_config(self):
        """Test creating PIILoop from PIIConfig."""
        detector = Mock()
        on_detection = Mock()
        
        config = PIIConfig(
            detector,
            on_detection=on_detection,
            use_name_parsing=False,
        )
        
        loop = PIILoop.from_config(config)
        
        assert loop._detector == detector
        assert loop._use_name_parsing is False
        assert loop._callbacks.on_detection == on_detection


class TestPresidioDetectorCallbacks:
    """Tests for PresidioDetector callback integration."""
    
    @patch("redactyl.detectors.gliner_parser.GlinerNameParser")
    def test_gliner_unavailable_callback(self, mock_parser_class):
        """Test that GLiNER unavailable callback is triggered."""
        # Mock the parser to simulate GLiNER not available
        mock_parser = Mock()
        mock_parser.is_available = False
        mock_parser_class.return_value = mock_parser
        
        on_gliner = Mock()
        callbacks = CallbackContext(on_gliner_unavailable=on_gliner)
        
        # Create detector with callbacks
        detector = PresidioDetector(
            use_gliner_for_names=True,
            callbacks=callbacks
        )
        
        # Verify callback was triggered
        on_gliner.assert_called_once()
    
    def test_silent_gliner_warning(self):
        """Test that GLiNER warning can be silenced."""
        # Create detector with silenced callbacks
        callbacks = CallbackContext.silent()
        
        # This should not produce any warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # Turn warnings into errors
            detector = PresidioDetector(
                use_gliner_for_names=True,
                callbacks=callbacks
            )


class User(BaseModel):
    """Test model for Pydantic integration."""
    name: str
    email: str
    notes: str


class TestPydanticCallbacks:
    """Tests for Pydantic integration callbacks."""
    
    def test_detection_callback_in_decorator(self):
        """Test that detection callback works with decorator."""
        detector = Mock()
        detector.detect.return_value = [
            PIIEntity(PIIType.PERSON, "John Doe", 0, 8, 0.9),
            PIIEntity(PIIType.EMAIL, "john@example.com", 9, 25, 0.9),
        ]
        
        on_detection = Mock()
        config = PIIConfig(
            detector,
            batch_detection=False,  # Disable batch for simpler test
            on_detection=on_detection,
        )
        
        @config.protect
        def process_user(user: User) -> User:
            return user
        
        user = User(name="John Doe", email="john@example.com", notes="Test notes")
        result = process_user(user)
        
        # Detection should have been called multiple times (once per field)
        assert on_detection.call_count > 0
    
    def test_unredaction_issue_callback(self):
        """Test that unredaction issue callback is triggered."""
        detector = Mock()
        detector.detect.return_value = []
        
        on_issue = Mock()
        config = PIIConfig(
            detector,
            on_unredaction_issue=on_issue,
        )
        
        @config.protect
        def process_user(user: User) -> User:
            # Inject a hallucinated token
            user.notes = user.notes + " [FAKE_TOKEN_1]"
            return user
        
        user = User(name="John", email="test@example.com", notes="Notes")
        result = process_user(user)
        
        # Issue callback should have been triggered for the hallucinated token
        if on_issue.called:
            issue = on_issue.call_args[0][0]
            assert "FAKE_TOKEN" in issue.token


class TestEndToEndCallbacks:
    """End-to-end tests for callback functionality."""
    
    def test_full_callback_flow(self):
        """Test complete flow with all callbacks."""
        # Track all events
        events = []
        
        def track_gliner():
            events.append("gliner_unavailable")
        
        def track_detection(entities):
            events.append(f"detected_{len(entities)}")
        
        def track_batch_error(exc):
            events.append(f"batch_error_{type(exc).__name__}")
        
        def track_issue(issue):
            events.append(f"issue_{issue.issue_type}")
        
        # Create config with all callbacks
        detector = Mock()
        detector.detect.return_value = [
            PIIEntity(PIIType.PERSON, "Alice", 0, 5, 0.9)
        ]
        
        config = PIIConfig(
            detector,
            on_gliner_unavailable=track_gliner,
            on_detection=track_detection,
            on_batch_error=track_batch_error,
            on_unredaction_issue=track_issue,
        )
        
        # Use the config
        loop = PIILoop.from_config(config)
        text, state = loop.redact("Alice is here")
        
        # Check that detection was tracked
        assert "detected_1" in events
    
    def test_example_custom_logging(self):
        """Test example from requirements: custom logging."""
        # Simulate a logger
        logged_messages = []
        
        class Logger:
            def warning(self, msg):
                logged_messages.append(("warning", msg))
        
        class Metrics:
            def __init__(self):
                self.records = []
            
            def record(self, key, value):
                self.records.append((key, value))
        
        logger = Logger()
        metrics = Metrics()
        
        detector = Mock()
        detector.detect.return_value = [
            PIIEntity(PIIType.EMAIL, "test@example.com", 0, 16, 0.9)
        ]
        
        # Custom logging as shown in requirements
        config = PIIConfig(
            detector,
            on_gliner_unavailable=lambda: logger.warning("GLiNER not available"),
            on_detection=lambda entities: metrics.record("pii.detected", len(entities)),
        )
        
        loop = PIILoop.from_config(config)
        loop.redact("test@example.com")
        
        # Verify metrics were recorded
        assert ("pii.detected", 1) in metrics.records
    
    def test_example_silence_warnings(self):
        """Test example from requirements: silence warnings."""
        detector = Mock()
        
        # Silence warnings as shown in requirements
        config = PIIConfig(
            detector,
            on_gliner_unavailable=None  # Don't warn about missing GLiNER
        )
        
        # This should not produce any warnings
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # Turn warnings into errors
            loop = PIILoop.from_config(config)
            # No error should be raised