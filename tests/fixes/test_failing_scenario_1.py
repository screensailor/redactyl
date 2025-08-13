from pydantic import BaseModel

from tests.utils.decorator import capture_redacted_input


class NestedInput(BaseModel):
    ignore: int
    text: str


class Input(BaseModel):
    ignore: int
    text: str
    nested: NestedInput


class Output(BaseModel):
    text: str


def test_empty() -> None:
    assert True


def test_failing_scenario() -> None:
    x = Input(
        ignore=1,
        text="Hi, my name is John. I would like to talk about Jane. Yours sincerely, Mr John Appleseed",
        nested=NestedInput(
            ignore=2,
            text="We know that John's email is john@mail.com and Jane's full name is Jane Doe.",
        ),
    )
    x_redacted = Input(
        ignore=1,
        text="Hi, my name is [NAME_FIRST_1]. I would like to talk about [NAME_FIRST_2]. Yours sincerely, Mr [NAME_FIRST_1] [NAME_LAST_1]",
        nested=NestedInput(
            ignore=2,
            text="We know that [NAME_FIRST_1]'s email is [EMAIL_1] and [NAME_FIRST_2]'s full name is [NAME_FIRST_2] [NAME_LAST_2].",
        ),
    )
    y_redacted = Output(
        text="Hi [NAME_FIRST_1], let's talk about [NAME_FIRST_2].",
    )
    y = Output(
        text="Hi John, let's talk about Jane.",
    )

    captured = capture_redacted_input(x, y_redacted)

    assert captured.redacted_input == x_redacted
    assert captured.output == y
