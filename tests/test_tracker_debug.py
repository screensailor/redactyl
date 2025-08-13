"""Debug the streaming issue."""

from pydantic import BaseModel

from redactyl.types import PIIEntity, PIIType


class User(BaseModel):
    """Test model."""
    name: str
    email: str


class DebugDetector:
    """Detector that prints what it detects."""
    
    def detect(self, text: str) -> list[PIIEntity]:
        """Detect and print."""
        import re
        res = []
        for match in re.finditer(r'\b[a-z]+@[a-z]+\.com\b', text):
            entity = PIIEntity(
                PIIType.EMAIL,
                match.group(),
                match.start(),
                match.end(),
                0.95
            )
            res.append(entity)
            print(f"Detected: {entity.value} at {entity.start}-{entity.end}")
        return res


def test_debug():
    """Debug test."""
    detector = DebugDetector()
    # Create protector directly
    from redactyl.pydantic_integration import PydanticPIIProtector
    
    protector = PydanticPIIProtector(
        detector=detector,
        batch_detection=False,
        use_name_parsing=False,
    )
    
    # Simulate streaming
    state_acc = None
    
    for i, (name, email) in enumerate([
        ("Alice", "alice@example.com"),
        ("Bob", "bob@example.com"),
        ("Charlie", "alice@example.com"),
    ]):
        user = User(name=name, email=email)
        print(f"\n--- Processing user {i+1}: {email} ---")
        protected, state = protector.protect_model(user)
        print(f"Protected: {protected.email}")
        print(f"State tokens: {list(state.tokens.keys())}")
        
        if state_acc is None:
            state_acc = state
        else:
            state_acc = state_acc.merge(state)


if __name__ == "__main__":
    test_debug()