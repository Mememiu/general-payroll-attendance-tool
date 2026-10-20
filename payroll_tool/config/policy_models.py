"""Domain values shared by in-app policy configuration components."""

from dataclasses import asdict, dataclass
from enum import StrEnum


class PolicyStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    field: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalSnapshot:
    payload: str
    sha256: str
