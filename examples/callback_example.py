"""Example demonstrating the callback pattern in redactyl.

This example shows how to use callbacks instead of logging/printing
for event handling in PII detection and redaction.
"""

import logging
from dataclasses import dataclass

from pydantic import BaseModel

from redactyl.core import PIILoop
from redactyl.detectors.presidio import PresidioDetector
from redactyl.pydantic_integration import PIIConfig
from redactyl.types import PIIEntity

# Setup custom logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Example 1: Custom logging with callbacks
def example_custom_logging():
    """Demonstrate using callbacks for custom logging."""
    print("\n=== Example 1: Custom Logging ===")
    
    # Track metrics
    @dataclass
    class Metrics:
        detections: int = 0
        entities: list[str] = None
        
        def __post_init__(self):
            self.entities = []
    
    metrics = Metrics()
    
    # Create detector with custom callbacks
    detector = PresidioDetector(confidence_threshold=0.7)
    
    def log_gliner_unavailable():
        logger.warning("GLiNER is not available - using fallback")
    
    def track_detection(entities: list[PIIEntity]):
        metrics.detections += 1
        metrics.entities.extend([e.type.name for e in entities])
        logger.info(f"Detected {len(entities)} PII entities")
    
    config = PIIConfig(
        detector,
        on_gliner_unavailable=log_gliner_unavailable,
        on_detection=track_detection,
    )
    
    # Use the config
    loop = PIILoop.from_config(config)
    
    # Process some text
    text = "John Doe's email is john@example.com and his phone is 555-1234."
    redacted, state = loop.redact(text)
    
    print(f"Original: {text}")
    print(f"Redacted: {redacted}")
    print(f"Metrics: {metrics.detections} detection calls, entities: {metrics.entities}")


# Example 2: Silencing warnings
def example_silence_warnings():
    """Demonstrate how to silence specific warnings."""
    print("\n=== Example 2: Silencing Warnings ===")
    
    # Create detector that silences GLiNER warnings
    detector = PresidioDetector(confidence_threshold=0.7)
    
    config = PIIConfig(
        detector,
        on_gliner_unavailable=None,  # Silence GLiNER warnings
        on_batch_error=None,  # Silence batch errors
    )
    
    loop = PIILoop.from_config(config)
    
    # Process text (no warnings will be shown)
    text = "Contact Alice at alice@example.com"
    redacted, state = loop.redact(text)
    
    print(f"Original: {text}")
    print(f"Redacted: {redacted}")
    print("(No warnings were displayed)")


# Example 3: Using with Pydantic models
class User(BaseModel):
    name: str
    email: str
    notes: str


def example_pydantic_callbacks():
    """Demonstrate callbacks with Pydantic integration."""
    print("\n=== Example 3: Pydantic Integration ===")
    
    detector = PresidioDetector(confidence_threshold=0.7)
    
    # Track all events
    events = []
    
    def track_event(event_type: str):
        def handler(*args):
            events.append(event_type)
            if event_type == "detection" and args:
                entities = args[0]
                logger.info(f"Detected: {[e.type.name for e in entities]}")
        return handler
    
    config = PIIConfig(
        detector,
        batch_detection=False,  # Process fields individually for demo
        on_detection=track_event("detection"),
        on_unredaction_issue=track_event("unredaction_issue"),
    )
    
    @config.protect
    def process_user(user: User) -> User:
        # Simulate processing
        user.notes = f"Processed: {user.notes}"
        return user
    
    # Test the function
    user = User(
        name="Bob Smith",
        email="bob@example.com",
        notes="Call him at 555-9876"
    )
    
    print(f"Original user: {user}")
    result = process_user(user)
    print(f"Result user: {result}")
    print(f"Events tracked: {events}")


# Example 4: Error handling callbacks
def example_error_handling():
    """Demonstrate error handling with callbacks."""
    print("\n=== Example 4: Error Handling ===")
    
    detector = PresidioDetector(confidence_threshold=0.7)
    
    errors_caught = []
    
    def handle_batch_error(exc: Exception):
        errors_caught.append(str(exc))
        logger.error(f"Batch processing failed: {exc}")
    
    config = PIIConfig(
        detector,
        on_batch_error=handle_batch_error,
    )
    
    # This would normally process without errors
    loop = PIILoop.from_config(config)
    text = "Email: test@example.com"
    redacted, state = loop.redact(text)
    
    print(f"Processed: {redacted}")
    print(f"Errors caught: {errors_caught if errors_caught else 'None'}")


# Example 5: Complete callback configuration
def example_complete_configuration():
    """Demonstrate a complete callback configuration."""
    print("\n=== Example 5: Complete Configuration ===")
    
    class EventTracker:
        def __init__(self):
            self.events = []
        
        def gliner_unavailable(self):
            self.events.append("gliner_unavailable")
            logger.info("GLiNER not available, using fallback")
        
        def detection(self, entities: list[PIIEntity]):
            self.events.append(f"detected_{len(entities)}")
            for entity in entities:
                logger.debug(f"  {entity.type.name}: {entity.value}")
        
        def batch_error(self, exc: Exception):
            self.events.append(f"error_{type(exc).__name__}")
            logger.error(f"Batch error: {exc}")
        
        def unredaction_issue(self, issue):
            self.events.append(f"issue_{issue.issue_type}")
            logger.warning(f"Unredaction issue: {issue}")
    
    tracker = EventTracker()
    detector = PresidioDetector(confidence_threshold=0.7)
    
    config = PIIConfig(
        detector,
        on_gliner_unavailable=tracker.gliner_unavailable,
        on_detection=tracker.detection,
        on_batch_error=tracker.batch_error,
        on_unredaction_issue=tracker.unredaction_issue,
    )
    
    loop = PIILoop.from_config(config)
    
    # Process multiple texts
    texts = [
        "John's email is john@example.com",
        "Call Sarah at 555-1234",
        "Meeting with Dr. Smith tomorrow",
    ]
    
    for text in texts:
        redacted, state = loop.redact(text)
        print(f"  {text} -> {redacted}")
    
    print(f"\nAll events: {tracker.events}")


if __name__ == "__main__":
    example_custom_logging()
    example_silence_warnings()
    example_pydantic_callbacks()
    example_error_handling()
    example_complete_configuration()