from typing import Annotated

import rich
from pydantic import BaseModel

from redactyl.pydantic_integration import PIIType, pii_field
from tests.utils.decorator import capture_redacted_input


class Input(BaseModel):
    session_id: Annotated[str, pii_field(pii_type=None)]
    case_id: Annotated[str, pii_field(pii_type=None)]
    user: Annotated[str, pii_field(pii_type=PIIType.EMAIL)]
    query: str
    context: str


class Output(BaseModel):
    text: str


def test_failing_scenario() -> None:
    x = Input(
        session_id="session_123",
        case_id="case_456",
        user="help@me.com",
        query="Hi, my name is John. I'd like to talk to you about Jane. I would like to order some ice cream for her. Cheers, John Appleseed",
        context="Jane's full name is Jane Porter and her email is jane.porter@me.com",
    )
    x_redacted = Input(
        session_id="session_123",
        case_id="case_456",
        user="[EMAIL_1]",
        query="Hi, my name is [NAME_FIRST_1]. I'd like to talk to you about [NAME_FIRST_2]. I would like to order some ice cream for her. Cheers, [NAME_FIRST_1] [NAME_LAST_1]",
        context="[NAME_FIRST_2]'s full name is [NAME_FIRST_2] [NAME_LAST_2] and her email is [EMAIL_2]",
    )

    y_redacted = Output(
        text="Hi [NAME_FIRST_1], let's talk about [NAME_FIRST_2]. I will order some ice cream for her.",
    )
    y = Output(
        text="Hi John, let's talk about Jane. I will order some ice cream for her.",
    )

    captured = capture_redacted_input(x, y_redacted)

    rich.print("✅ captured", captured)

    assert captured.redacted_input == x_redacted
    assert captured.output == y
