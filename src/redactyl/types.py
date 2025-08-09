from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class PIIType(Enum):
    PERSON = auto()
    NAME_FIRST = auto()
    NAME_MIDDLE = auto()
    NAME_LAST = auto()
    NAME_TITLE = auto()
    EMAIL = auto()
    PHONE = auto()
    ADDRESS = auto()
    SSN = auto()
    CREDIT_CARD = auto()
    DATE = auto()
    IP_ADDRESS = auto()
    URL = auto()
    LOCATION = auto()
    ORGANIZATION = auto()
    CUSTOM = auto()


@dataclass(frozen=True)
class PIIEntity:
    type: PIIType
    value: str
    start: int
    end: int
    confidence: float

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError("Start position must be non-negative")
        if self.end <= self.start:
            raise ValueError("End position must be greater than start position")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0 and 1")
        if not self.value:
            raise ValueError("Value cannot be empty")


@dataclass(frozen=True)
class RedactionToken:
    original: str
    pii_type: PIIType
    token_index: int
    entity: PIIEntity

    @property
    def token(self) -> str:
        return f"[{self.pii_type.name}_{self.token_index}]"


@dataclass(frozen=True)
class RedactionState:
    tokens: dict[str, RedactionToken] = field(default_factory=lambda: {})
    metadata: dict[str, Any] = field(default_factory=lambda: {})
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokens": {
                token: {
                    "original": rt.original,
                    "pii_type": rt.pii_type.name,
                    "token_index": rt.token_index,
                    "entity": {
                        "type": rt.entity.type.name,
                        "value": rt.entity.value,
                        "start": rt.entity.start,
                        "end": rt.entity.end,
                        "confidence": rt.entity.confidence,
                    },
                }
                for token, rt in self.tokens.items()
            },
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RedactionState":
        tokens: dict[str, RedactionToken] = {}
        for token, rt_data in data.get("tokens", {}).items():
            entity = PIIEntity(
                type=PIIType[rt_data["entity"]["type"]],
                value=rt_data["entity"]["value"],
                start=rt_data["entity"]["start"],
                end=rt_data["entity"]["end"],
                confidence=rt_data["entity"]["confidence"],
            )
            tokens[token] = RedactionToken(
                original=rt_data["original"],
                pii_type=PIIType[rt_data["pii_type"]],
                token_index=rt_data["token_index"],
                entity=entity,
            )

        return cls(
            tokens=tokens,
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "RedactionState":
        import json

        return cls.from_dict(json.loads(json_str))

    def with_token(
        self, token: str, redaction_token: RedactionToken
    ) -> "RedactionState":
        new_tokens = {**self.tokens, token: redaction_token}
        return RedactionState(
            tokens=new_tokens,
            metadata=self.metadata,
            created_at=self.created_at,
        )

    def merge(self, other: "RedactionState") -> "RedactionState":
        merged_tokens = {**self.tokens, **other.tokens}
        merged_metadata = {**self.metadata, **other.metadata}
        return RedactionState(
            tokens=merged_tokens,
            metadata=merged_metadata,
            created_at=min(self.created_at, other.created_at),
        )


@dataclass(frozen=True)
class UnredactionIssue:
    token: str
    issue_type: str  # "hallucination", "fuzzy_match", "format_mismatch", etc.
    replacement: str | None = None
    confidence: float = 0.0
    details: str | None = None

    def __str__(self) -> str:
        if self.replacement:
            return (
                f"{self.issue_type}: {self.token} → {self.replacement} "
                f"(confidence: {self.confidence:.2f})"
            )
        return f"{self.issue_type}: {self.token} (no replacement found)"
