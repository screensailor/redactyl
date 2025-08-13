from pydantic import BaseModel

from redactyl.pydantic_integration import PIIConfig


class Captured[I: BaseModel, O: BaseModel](BaseModel):
    input: I
    redacted_input: I
    redacted_output: O
    output: O


def capture_redacted_input[I: BaseModel, O: BaseModel](
    input: I,
    redacted_output: O,
    pii: PIIConfig | None = None,
) -> Captured[I, O]:
    if pii is None:
        pii = PIIConfig()

    _i: I = input

    @pii.protect
    def process(i: I) -> O:
        nonlocal _i
        _i = i
        return redacted_output

    _o = process(input)

    return Captured(
        input=input,
        redacted_input=_i,
        redacted_output=redacted_output,
        output=_o,
    )
