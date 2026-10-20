"""Fixed-hours attendance calculation based on merged time coverage."""

from payroll_tool.config.schema import AttendancePolicy
from payroll_tool.models import DailyAttendance, OffsiteResolution, Segment


Interval = tuple[int, int]


def calculate_day(
    *,
    arrival: str | None,
    departure: str | None,
    policy: AttendancePolicy,
    paid_segments: list[Segment] | None = None,
    onsite_segments: list[Segment] | None = None,
) -> DailyAttendance:
    paid_segments = paid_segments or []
    onsite_segments = onsite_segments or []
    standard_start = _minutes(policy.standard_start)
    standard_end = _minutes(policy.standard_end)
    latest_normal_start = _minutes(policy.latest_normal_start)
    late_grace_end = _minutes(policy.late_grace_end)
    required = _subtract(
        [(standard_start, standard_end)],
        [(_minutes(policy.lunch_start), _minutes(policy.lunch_end))],
    )

    arrival_minutes = _minutes(arrival) if arrival else None
    departure_minutes = _minutes(departure) if departure else None
    if arrival_minutes is not None and policy.earliest_valid_start is not None:
        arrival_minutes = max(arrival_minutes, _minutes(policy.earliest_valid_start))
    paid_coverage = [_interval(segment) for segment in paid_segments]
    coverage = paid_coverage + [_interval(segment) for segment in onsite_segments]
    if policy.work_mode == "flexible":
        if policy.flexible_rule_mode not in {
            "纯工时弹性", "最晚到岗限制", "核心时段覆盖",
        }:
            raise ValueError("弹性工时策略必须由 HR 明确配置")
        if arrival_minutes is not None and departure_minutes is not None:
            if departure_minutes <= arrival_minutes:
                raise ValueError("下班时间必须晚于上班时间；跨午夜记录需单独解析")
            coverage.append((arrival_minutes, departure_minutes))
        merged_coverage = _merge(coverage)
        break_intervals = [
            (_minutes(policy.lunch_start), _minutes(policy.lunch_end)),
        ]
        covered_minutes = _duration_minutes(
            _subtract(
                merged_coverage,
                break_intervals,
            )
        )
        required_minutes = round(policy.daily_required_hours * 60)
        absence_minutes = max(0, required_minutes - covered_minutes)
        late_minutes = 0
        if policy.flexible_rule_mode == "最晚到岗限制":
            if policy.flexible_latest_start is None:
                raise ValueError("最晚到岗限制必须配置弹性最晚到岗时间")
            if arrival_minutes is not None:
                latest_start = _minutes(policy.flexible_latest_start)
                late_minutes = _duration_minutes(
                    _subtract(
                        [(latest_start, max(latest_start, arrival_minutes))],
                        _merge(paid_coverage + break_intervals),
                    )
                )
                late_minutes = min(required_minutes, late_minutes)
                absence_minutes = max(absence_minutes, late_minutes)
        elif policy.flexible_rule_mode == "核心时段覆盖":
            if policy.core_start is None or policy.core_end is None:
                raise ValueError("核心时段覆盖必须配置核心开始和结束时间")
            if _minutes(policy.core_end) <= _minutes(policy.core_start):
                raise ValueError("核心时段结束必须晚于核心时段开始")
            core_required = _subtract(
                [(_minutes(policy.core_start), _minutes(policy.core_end))],
                break_intervals,
            )
            covered_core_minutes = _duration_minutes(
                _intersection(core_required, merged_coverage)
            )
            missing_core_minutes = max(
                0,
                _duration_minutes(core_required) - covered_core_minutes,
            )
            absence_minutes = max(absence_minutes, missing_core_minutes)
        absence_minutes = min(required_minutes, absence_minutes)
        return DailyAttendance(
            effective_hours=(required_minutes - absence_minutes) / 60,
            absence_hours=absence_minutes / 60,
            late_hours=late_minutes / 60,
        )

    late_hours = 0.0
    if arrival_minutes is not None and arrival_minutes > late_grace_end:
        late_window = _subtract(
            [(standard_start, min(arrival_minutes, standard_end))],
            _merge(paid_coverage),
        )
        lunch_start, lunch_end = _minutes(policy.lunch_start), _minutes(policy.lunch_end)
        if not late_window or all(
            lunch_start <= start and end <= lunch_end for start, end in late_window
        ):
            late_hours = 0.0
        else:
            late_hours = _duration_hours(late_window)

    checkout_boundary = _minutes(
        infer_checkout_boundary(
            _time_text(arrival_minutes) if arrival_minutes is not None else None,
            policy,
        )
    )
    if arrival_minutes is not None and departure_minutes is not None:
        coverage_start = max(standard_start, arrival_minutes)
        coverage_end = min(departure_minutes, checkout_boundary)
        if coverage_start < coverage_end:
            coverage.append((coverage_start, coverage_end))

    fixed_coverage = _clip_intervals(
        coverage,
        standard_start,
        checkout_boundary,
    )
    covered_minutes = _duration_minutes(
        _subtract(
            _merge(fixed_coverage),
            [(_minutes(policy.lunch_start), _minutes(policy.lunch_end))],
        )
    )
    required_minutes = round(policy.daily_required_hours * 60)
    effective_minutes = min(required_minutes, covered_minutes)
    raw_absence_minutes = max(0, required_minutes - effective_minutes)
    absence_hours = min(
        required_minutes / 60,
        max(raw_absence_minutes / 60, late_hours),
    )
    if (
        policy.full_day_absence_after_hours is not None
        and late_hours > policy.full_day_absence_after_hours
    ):
        absence_hours = required_minutes / 60
    effective_hours = required_minutes / 60 - absence_hours
    return DailyAttendance(
        effective_hours=max(0.0, effective_hours),
        absence_hours=absence_hours,
        late_hours=late_hours,
    )


def resolve_offsite_segment(
    segment: Segment, *, punch_times: list[str], checkout_time: str | None
) -> OffsiteResolution:
    """Split an approved offsite period only when a verified return is evidenced."""
    start, end = _interval(segment)
    punch_minutes = [_minutes(value) for value in punch_times]
    has_return_card = any(start <= value < end for value in punch_minutes)
    if checkout_time is None or not has_return_card or _minutes(checkout_time) <= end:
        return OffsiteResolution(offsite_segment=segment, onsite_segment=None)

    return_time = min(value for value in punch_minutes if start <= value < end)
    return_time_text = f"{return_time // 60:02d}:{return_time % 60:02d}"
    return OffsiteResolution(
        offsite_segment=Segment(segment.kind, segment.start, return_time_text),
        onsite_segment=Segment("onsite", return_time_text, checkout_time),
    )


def _checkout_boundary(
    arrival: int,
    standard_start: int,
    standard_end: int,
    latest_normal_start: int,
    late_grace_end: int,
    grace_checkout: str | None,
    late_makeup_allowed: bool,
) -> int:
    if arrival <= latest_normal_start:
        return arrival + (standard_end - standard_start)
    if arrival <= late_grace_end:
        if not late_makeup_allowed:
            return standard_end
        grace_boundary = _minutes(grace_checkout) if grace_checkout else standard_end
        return max(standard_end, grace_boundary)
    return standard_end


def infer_checkout_boundary(arrival: str | None, policy: AttendancePolicy) -> str:
    if arrival is None:
        return policy.standard_end
    arrival_minutes = _minutes(arrival)
    if policy.earliest_valid_start is not None:
        arrival_minutes = max(arrival_minutes, _minutes(policy.earliest_valid_start))
    if policy.checkout_boundary_mode != "按到岗推算":
        if (
            policy.late_makeup_allowed
            and _minutes(policy.latest_normal_start) < arrival_minutes
            and arrival_minutes <= _minutes(policy.late_grace_end)
        ):
            if (
                policy.grace_checkout
                and _minutes(policy.grace_checkout) > _minutes(policy.standard_end)
            ):
                return policy.grace_checkout
            return policy.standard_end
        return policy.standard_end
    boundary = _checkout_boundary(
        arrival_minutes,
        _minutes(policy.standard_start),
        _minutes(policy.standard_end),
        _minutes(policy.latest_normal_start),
        _minutes(policy.late_grace_end),
        policy.grace_checkout,
        policy.late_makeup_allowed,
    )
    return _time_text(boundary)


def _time_text(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _interval(segment: Segment) -> Interval:
    start, end = _minutes(segment.start), _minutes(segment.end)
    if end <= start:
        raise ValueError(f"segment end must be after start: {segment.kind}")
    return start, end


def _merge(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _subtract(base: list[Interval], exclusions: list[Interval]) -> list[Interval]:
    result = base
    for exclusion_start, exclusion_end in exclusions:
        next_result: list[Interval] = []
        for start, end in result:
            if exclusion_end <= start or exclusion_start >= end:
                next_result.append((start, end))
                continue
            if start < exclusion_start:
                next_result.append((start, exclusion_start))
            if exclusion_end < end:
                next_result.append((exclusion_end, end))
        result = next_result
    return result


def _intersection_hours(required: list[Interval], coverage: list[Interval]) -> float:
    return _duration_hours(_intersection(required, coverage))


def _intersection(first: list[Interval], second: list[Interval]) -> list[Interval]:
    intersections: list[Interval] = []
    for first_start, first_end in first:
        for second_start, second_end in second:
            start, end = max(first_start, second_start), min(first_end, second_end)
            if start < end:
                intersections.append((start, end))
    return _merge(intersections)


def _duration_hours(intervals: list[Interval]) -> float:
    return _duration_minutes(intervals) / 60


def _duration_minutes(intervals: list[Interval]) -> int:
    return sum(end - start for start, end in intervals)


def _clip_intervals(
    intervals: list[Interval], lower: int, upper: int
) -> list[Interval]:
    clipped: list[Interval] = []
    for start, end in intervals:
        clipped_start = max(start, lower)
        clipped_end = min(end, upper)
        if clipped_start < clipped_end:
            clipped.append((clipped_start, clipped_end))
    return clipped
