"""Conservative parser for common Chinese attendance result text."""

from dataclasses import dataclass
import re


TIME = r"(?:[01]\d|2[0-3]):[0-5]\d"
APPROVAL_RE = re.compile(
    rf"(?P<kind>[^;，,()（）]+?)[（(](?:(?P<start>{TIME})\s*[-~至]\s*(?P<end>{TIME})|(?P<coarse>上午|下午|全天))[）)]"
)
TIME_RE = re.compile(TIME)


@dataclass(frozen=True)
class ApprovalSegment:
    kind: str
    start: str | None
    end: str | None
    coarse_period: str | None


@dataclass(frozen=True)
class ParsedDailyAttendanceText:
    punch_times: tuple[str, ...]
    approvals: tuple[ApprovalSegment, ...]


def parse_daily_attendance_text(text: object) -> ParsedDailyAttendanceText:
    source = str(text or "")
    approvals = tuple(
        ApprovalSegment(
            kind=match.group("kind").strip(),
            start=match.group("start"),
            end=match.group("end"),
            coarse_period=match.group("coarse"),
        )
        for match in APPROVAL_RE.finditer(source)
    )
    approval_time_spans = [match.span() for match in APPROVAL_RE.finditer(source)]
    punches = tuple(
        match.group(0)
        for match in TIME_RE.finditer(source)
        if not any(start <= match.start() < end for start, end in approval_time_spans)
    )
    return ParsedDailyAttendanceText(punch_times=punches, approvals=approvals)
