from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    kind: str
    start: str
    end: str


@dataclass(frozen=True)
class DailyAttendance:
    effective_hours: float
    absence_hours: float
    late_hours: float


@dataclass(frozen=True)
class OffsiteResolution:
    offsite_segment: Segment
    onsite_segment: Segment | None
