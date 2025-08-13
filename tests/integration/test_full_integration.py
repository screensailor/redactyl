import rich
from pydantic import BaseModel

from redactyl.pydantic_integration import PIIConfig


class NestedInput(BaseModel):
    ignore: int
    text: str


class Input(BaseModel):
    ignore: int
    text: str
    nested: NestedInput


class NestedOutput(BaseModel):
    ignore: int
    text: str


class Output(BaseModel):
    ignore: int
    text: str
    nested: NestedOutput


def test_redaction():
    pii = PIIConfig()

    x = Input(
        ignore=1,
        text="Hi, my name is John. I would like to talk about Jane. Yours sincerely, Mr John Appleseed",
        nested=NestedInput(
            ignore=2,
            text="We know that John's email is john@mail.com and Jane's full name is Jane Doe. The agent's name is Peter Parker.",
        ),
    )

    x_redacted: Input | None = None

    @pii.protect
    def f(input: Input) -> Input:
        nonlocal x_redacted
        x_redacted = input
        return input

    y = f(x)

    rich.print("✅ x_redacted:", x_redacted)
    rich.print("✅ y:", y)
