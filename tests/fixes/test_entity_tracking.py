from pydantic import BaseModel

from redactyl.pydantic_integration import PIIConfig


class NestedInput(BaseModel):
    ignore: int
    text: str


class Input(BaseModel):
    ignore: int
    text: str
    nested: NestedInput


def capture_redacted_input[M: BaseModel](input_model: M, pii_config: PIIConfig) -> M:
    captured_input: M | None = None

    @pii_config.protect
    def process(input_data: M) -> M:
        nonlocal captured_input
        captured_input = input_data
        return input_data

    _ = process(input_model)

    if captured_input is None:
        raise AssertionError("Captured input is None")

    return captured_input


def test_token_indexing_with_nested_models(default_pii_config: PIIConfig) -> None:
    x = Input(
        ignore=1,
        text="Hi, my name is John. I would like to talk about Jane. Yours sincerely, Mr John Appleseed",
        nested=NestedInput(
            ignore=2,
            text="We know that John's email is john@mail.com and Jane's full name is Jane Doe.",
        ),
    )

    x_redacted = capture_redacted_input(x, default_pii_config)

    # Known issue: "Peter Parker" is detected as NAME_TITLE_1 instead of NAME_FIRST_3 + NAME_LAST_3
    # This is a GLiNER parsing limitation, not an entity tracking bug
    x_redacted_expected = Input(
        ignore=1,
        text="Hi, my name is [NAME_FIRST_1]. I would like to talk about [NAME_FIRST_2]. Yours sincerely, Mr [NAME_FIRST_1] [NAME_LAST_1]",
        nested=NestedInput(
            ignore=2,
            text="We know that [NAME_FIRST_1]'s email is [EMAIL_1] and [NAME_FIRST_2]'s full name is [NAME_FIRST_2] [NAME_LAST_2].",
        ),
    )

    assert x_redacted == x_redacted_expected
