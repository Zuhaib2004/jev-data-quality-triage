from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Decision(StrEnum):
    ACCEPT = "ACCEPT"
    REPAIR = "REPAIR"
    QUARANTINE = "QUARANTINE"


@dataclass
class Finding:
    code: str
    field: str
    severity: str
    reason: str


@dataclass
class Inspection:
    original: dict[str, Any]
    candidate: dict[str, Any]
    findings: list[Finding] = field(default_factory=list)
    changes: dict[str, dict[str, Any]] = field(default_factory=dict)

    def has(self, severity: str) -> bool:
        return any(f.severity == severity for f in self.findings)


@dataclass
class Verdict:
    decision: Decision
    confidence: float
    probabilities: dict[str, float]
    reason_code: str
    reason_confidence: float
    model: str


@dataclass
class Outcome:
    row: int
    decision: Decision
    source: str
    confidence: float | None
    reasons: list[str]
    original: dict[str, Any]
    record: dict[str, Any] | None
    findings: list[Finding]
    changes: dict[str, dict[str, Any]]
    model_verdict: Verdict | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
