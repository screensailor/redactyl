# Redactyl

Type-safe, reversible PII protection for LLM apps — now centered around the `@pii.protect` decorator.

Redactyl replaces sensitive values with stable tokens (for example: `[EMAIL_1]`, `[NAME_FIRST_1]`) before your code talks to an LLM, and restores originals when results come back. It works across Pydantic models, nested containers, sync/async functions, and streams — automatically.

**PII Membrane (“protect” bubble)**
- Inside decorated functions: arguments are redacted; your code and LLMs see tokens.
- Outside: return values and stream yields are unredacted; callers see originals.
- Two-way membrane: redacts on entry, unredacts on exit.
- Mapping source of truth: only incoming arguments build the redaction map; outputs are unredacted using that map.

Warning: You need a spaCy model installed (see Installation). Optional GLiNER improves name component detection.

## Why Redactyl?

- ✅ Zero trust to LLMs: Never expose real PII
- ✅ Type-safe: Full Pydantic integration and container traversal
- ✅ Reversible: Get original data back every time
- ✅ Streaming-ready: Works with sync/async generators
- ✅ Intelligent: Understands name relationships and components

### Quickstart (Plain String)

Use `@pii.protect` on ordinary functions too — no Pydantic required. Decorated functions are transparent to callers: from the outside you can’t tell PII protection is happening.

```python
from redactyl.pydantic_integration import PIIConfig

pii = PIIConfig()

@pii.protect
def summarize(text: str) -> str:
    # Inside: text is redacted (e.g., emails → [EMAIL_1])
    return f"Processed: {text}"

print(summarize("Email me at john@example.com"))
# → "Processed: Email me at john@example.com" (unredacted on return)
```

## The `@pii.protect` Moment

Drop a decorator and keep coding. Redactyl figures it out.

```python
from typing import Annotated
from pydantic import BaseModel
from redactyl.pydantic_integration import PIIConfig, pii_field
from redactyl.types import PIIType

# Zero-config to start; tuned via PIIConfig kwargs
pii = PIIConfig()

class Email(BaseModel):
    sender_name: Annotated[str, pii_field(PIIType.PERSON, parse_components=True)]
    sender_email: Annotated[str, pii_field(PIIType.EMAIL)]
    subject: str  # auto-detected
    body: str     # auto-detected

@pii.protect
async def draft_reply(email: Email) -> str:
    # Inside: email fields are redacted, e.g.
    #   "John Smith <john@example.com>" → "[NAME_FIRST_1] [NAME_LAST_1] <[EMAIL_1]>"
    # Call your LLM as usual — it will see tokens
    reply = await llm.generate({
        "subject": f"Re: {email.subject}",
        "body": f"Hi {email.sender_name}, …"
    })
    # Return values are automatically unredacted
    return reply

# What you get back has real PII restored
text = await draft_reply(Email(
    sender_name="John Smith",
    sender_email="john@example.com",
    subject="Project X",
    body="Ping me tomorrow"
))
print(text)  # → "Hi John, … I'll email john@example.com"
```

Why this feels essential:
- Minimal change: add a decorator; keep your LLM calls.
- Smart defaults: auto-detects sync/async/generator functions and Pydantic arguments.
- Transparent: callers see originals; tokens exist only inside the bubble.
- Reversible: tokens round-trip perfectly; originals are restored for outputs.

Name intelligence:
- Full names become the source of truth. Later mentions like "John", "Mr. Appleseed", or just "Appleseed" reuse the same token index.
- Example: "John Appleseed … Appleseed" → "[NAME_FIRST_1] [NAME_LAST_1] … [NAME_LAST_1]".

## Progressive Examples

### 1) Basics: Functions and Models

```python
from pydantic import BaseModel
from typing import Annotated
from redactyl.pydantic_integration import PIIConfig, pii_field
from redactyl.types import PIIType

pii = PIIConfig()

class Message(BaseModel):
    user: Annotated[str, pii_field(PIIType.PERSON, parse_components=True)]
    email: Annotated[str, pii_field(PIIType.EMAIL)]
    text: str  # auto-detected

@pii.protect
def handle(msg: Message) -> str:
    # msg is redacted here: "Jane <jane@x.com>" → tokens
    return llm.call(msg.model_dump())  # LLM works with tokens

result = handle(Message(user="Jane Roe", email="jane@x.com", text="Hello"))
print(result)  # Unredacted output
```

### 2) Streaming: Transparent Membrane

Decorated generators work like a two-way membrane: inputs are redacted on entry and every yielded item is unredacted on exit. Consumers of the stream never see tokens — only original values.

```python
from collections.abc import AsyncIterator
from pydantic import BaseModel

class In(BaseModel):
    content: str

class Out(BaseModel):
    content: str

# Optional: observe input-derived state after a stream completes (for persistence/debugging)
captured_state = None
pii = PIIConfig(on_stream_complete=lambda st: globals().__setitem__("captured_state", st))

@pii.protect
async def chat_stream(message: In) -> AsyncIterator[Out]:
    # Inside: message.content is redacted (e.g., john@example.com → [EMAIL_1])
    async for chunk in llm.stream(message.content):
        # The LLM sees tokens and may emit them in its text
        # On exit, the decorator unredacts using the input-based map
        yield Out(content=chunk)

# Consumers get unredacted values; tokens never leak outside the bubble
async for part in chat_stream(In(content="Email me at john@example.com")):
    print(part.content)  # e.g., "Thanks, I’ll email john@example.com"
```

Notes:
- Works with async and sync generators alike.
- `on_stream_complete(state)` exposes the final input-based `RedactionState` for persistence or auditing; it isn’t needed to consume the stream.

### Streaming State Tracking

- Source of truth: only function arguments build the redaction map.
- Unredaction on exit: every yielded or returned value is unredacted using that map.
- Persistence hook: capture the final input-derived `RedactionState` with `on_stream_complete` if you need to store state for later unredaction.

### 3) Containers: Lists, Dicts, Sets, Tuples, Frozensets

No special casing required — Redactyl traverses common containers in both inputs and return values.

```python
from typing import Any
from pydantic import BaseModel

class Profile(BaseModel):
    name: str
    email: str

pii = PIIConfig()  # traverse_containers=True by default

@pii.protect
def analyze(batch: list[Profile] | dict[str, Any] | set[str]) -> dict[str, Any]:
    # All nested strings/models are protected here
    # You can safely pass "batch" to your LLM/tooling
    summary = llm.summarize(batch)
    # Return values (including containers) are unredacted on the way out
    return {"summary": summary}

out = analyze([
    Profile(name="Ada Lovelace", email="ada@example.com"),
    Profile(name="Alan Turing", email="alan@example.com"),
])
print(out["summary"])  # contains real names/emails again
```

## Install

```bash
pip install redactyl

# Optional: better name component detection
pip install "redactyl[gliner]"

# Required spaCy model
python -m spacy download en_core_web_sm
```

## Why Tokens (Not Fake Data)?

- LLMs preserve structured placeholders like `[EMAIL_1]` exactly.
- We track name components intelligently so short mentions like "John" map back to the same person as "John Smith".
- Every token is perfectly reversible — outputs come back with originals.

## Pydantic-Friendly API Surface

- `@pii.protect`: Auto-protects Pydantic `BaseModel` args, traverses containers, and unprotects returns and yields (membrane behavior).
- Function modes: Detects sync, async, generator, and async-generator transparently.
- `pii(...)`: Annotate fields for explicit types or to disable detection per-field.
- Callbacks: `on_detection`, `on_hallucination`, `on_gliner_unavailable`, `on_batch_error`, `on_unredaction_issue`, `on_gliner_model_error`.
- Streaming: yields are unredacted to callers; `on_stream_complete(state)` exposes the final `RedactionState` for persistence.

## Known Limitations

- **Text Length**: The underlying spaCy models have a maximum text length of 1 million characters. Texts exceeding this limit will raise an error. For longer documents, consider processing them in chunks.

## v0.2.0 Highlights

- Containers: Deep traversal for `list`, `dict`, `set`, `tuple`, and `frozenset` (both inputs and returns).
- Streaming membrane: generators now unredact yields; callers see original PII.
- Streaming persistence: `on_stream_complete` surfaces the final `RedactionState` after generator completion.
- Name components: Full-name phrases establish the source of truth; partials reuse the same index.
- Smarter decorator: Auto-detects async/sync, generator/async-generator; protects models; unprotects returns.
- Quality: 100% test pass rate (206/206 tests).

## Configuration Cheatsheet

```python
from redactyl.pydantic_integration import HallucinationResponse

pii = PIIConfig(
    batch_detection=True,        # speed + consistent numbering across fields
    use_name_parsing=True,       # parse title/first/middle/last when available
    fuzzy_unredaction=False,     # allow fuzzy matches on restore
    traverse_containers=True,    # enable container traversal
    on_detection=lambda es: log.info("%d entities", len(es)),
    on_hallucination=lambda issues: [
        # replace hallucinated emails; preserve others
        HallucinationResponse.replace("[REDACTED]") if "EMAIL" in i.token else HallucinationResponse.preserve()
        for i in issues
    ],
)
```

### Common customizations

```python
# Custom detector
pii = PIIConfig(detector=MyCustomDetector())

# Batch processing for consistency and speed
pii = PIIConfig(batch_detection=True)

# Handle hallucinations
from redactyl.pydantic_integration import HallucinationResponse
def handle_llm_mistakes(issues):
    return [
        HallucinationResponse.replace("[REDACTED]") if "EMAIL" in i.token else HallucinationResponse.preserve()
        for i in issues
    ]
pii = PIIConfig(on_hallucination=handle_llm_mistakes)
```

Field-level control with `pii_field`:

```python
class User(BaseModel):
    # force detection as a PERSON and parse components
    name: Annotated[str, pii_field(PIIType.PERSON, parse_components=True)]
    # mark as email explicitly
    email: Annotated[str, pii_field(PIIType.EMAIL)]
    # or disable detection for a field
    notes: Annotated[str, pii_field(detect=False)]
```

## Development

```bash
uv python pin 3.12
uv pip install -e .[dev]
uv run python -m spacy download en_core_web_sm

uv run ruff check --fix && uv run ruff format
uv run pyright src/
uv run pytest -q
```

## License

MIT — see LICENSE.

See CHANGELOG.md for release notes.
