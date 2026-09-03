from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

_SEPARATOR = "\x1f"
_REQUIRED = ("position", "location", "detail", "source_url")


class PostKind(StrEnum):
    VACANCY = "vacancy"
    RESULT = "result"


def normalize(value: str) -> str:
    """Collapse whitespace and unicode variants for display."""
    return " ".join(unicodedata.normalize("NFKC", value).replace("\xa0", " ").split())


def squash(value: str) -> str:
    """Comparison form: letters and digits only.

    The careers site edits spacing, commas and capitalisation without changing
    the meaning, so those must never make an already sent post look new.
    """
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(c for c in normalized if c.isalnum())


def _digest(*parts: str) -> str:
    return hashlib.sha256(_SEPARATOR.join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class JobPost:
    kind: PostKind
    position: str
    location: str
    detail: str
    source_url: str
    source_key: str = ""
    attachment_url: str = ""
    extras: tuple[tuple[str, str], ...] = ()
    candidate_rows: tuple[tuple[str, ...], ...] = ()
    # Both keys are derived once. Hashing the same card on every lookup is waste.
    identity: str = field(init=False, repr=False, compare=False, default="")
    content_key: str = field(init=False, repr=False, compare=False, default="")

    def __post_init__(self) -> None:
        for name in _REQUIRED:
            if not normalize(getattr(self, name)):
                raise ValueError(f"Job post field '{name}' cannot be empty")
        identity = _digest(self.kind.value, squash(self.position), squash(self.location))
        object.__setattr__(self, "identity", identity)
        object.__setattr__(
            self,
            "content_key",
            _digest(
                identity,
                squash(self.detail),
                squash(self.source_key),
                squash(self.attachment_url),
            ),
        )

    @property
    def label(self) -> str:
        return f"{self.kind.value} '{self.position}'"
