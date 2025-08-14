from typing import Annotated, AsyncGenerator, Generator

import pytest
from pydantic import BaseModel

from redactyl.pydantic_integration import PIIConfig, pii
from redactyl.detectors.smart_mock import SmartMockDetector
from redactyl.types import PIIType


class UserIn(BaseModel):
    name: str
    email: str
    notes: str = ""


class SelectiveOut(BaseModel):
    expose_email: Annotated[str, pii(PIIType.EMAIL)]  # default unredact=True
    audit_email: Annotated[str, pii(unredact=False)]
    message: str


def make_config() -> PIIConfig:
    detector = SmartMockDetector(
        [
            ("John Doe", PIIType.PERSON),
            ("john@example.com", PIIType.EMAIL),
            ("John", PIIType.NAME_FIRST),
            ("Doe", PIIType.NAME_LAST),
        ]
    )
    return PIIConfig(detector=detector, use_name_parsing=False)


def test_unredact_flag_simple_fields():
    config = make_config()

    @config.protect
    def transform(user: UserIn) -> SelectiveOut:
        # Inside, inputs are redacted; construct output from protected values
        return SelectiveOut(
            expose_email=user.email,
            audit_email=user.email,  # this should remain token on exit
            message=f"Hello {user.name}",
        )

    result = transform(UserIn(name="John Doe", email="john@example.com"))
    # expose_email unredacts back to original
    assert result.expose_email == "john@example.com"
    # audit_email remains token
    assert result.audit_email.startswith("[EMAIL_") and result.audit_email.endswith("]")
    # name in message unredacts
    assert "John Doe" in result.message


class Payload(BaseModel):
    user_name: str
    user_email: str
    note: str = ""


class AuditLog(BaseModel):
    event_id: str
    payload: Annotated[Payload, pii(unredact=False)]  # entire subtree remains tokens
    summary: str


def test_unredact_flag_nested_models():
    config = make_config()

    @config.protect
    def create_audit(user: UserIn) -> AuditLog:
        return AuditLog(
            event_id="EVT-1",
            payload=Payload(user_name=user.name, user_email=user.email, note=f"User {user.name}"),
            summary=f"Processed {user.name} <{user.email}>",
        )

    out = create_audit(UserIn(name="John Doe", email="john@example.com"))
    # Subtree stays redacted
    assert out.payload.user_name.startswith("[") and out.payload.user_name.endswith("]")
    assert out.payload.user_email.startswith("[EMAIL_")
    assert "[NAME_" in out.payload.note or "[PERSON_" in out.payload.note
    # Summary unredacts
    assert "John Doe <john@example.com>" in out.summary


def test_unredact_flag_streaming_sync():
    config = make_config()

    @config.protect
    def stream(user: UserIn) -> Generator[SelectiveOut, None, None]:
        yield SelectiveOut(
            expose_email=user.email,
            audit_email=user.email,
            message=f"Hi {user.name}",
        )
        yield SelectiveOut(
            expose_email=user.email,
            audit_email=user.email,
            message=f"Bye {user.name}",
        )

    items = list(stream(UserIn(name="John Doe", email="john@example.com")))
    assert len(items) == 2
    for it in items:
        assert it.expose_email == "john@example.com"
        assert it.audit_email.startswith("[EMAIL_") and it.audit_email.endswith("]")
        assert "John Doe" in it.message


@pytest.mark.asyncio
async def test_unredact_flag_streaming_async():
    config = make_config()

    @config.protect
    async def astream(user: UserIn) -> AsyncGenerator[SelectiveOut, None]:
        yield SelectiveOut(
            expose_email=user.email,
            audit_email=user.email,
            message=f"Hello {user.name}",
        )

    results = []
    async for item in astream(UserIn(name="John Doe", email="john@example.com")):
        results.append(item)
    assert len(results) == 1
    item = results[0]
    assert item.expose_email == "john@example.com"
    assert item.audit_email.startswith("[EMAIL_") and item.audit_email.endswith("]")
    assert "John Doe" in item.message