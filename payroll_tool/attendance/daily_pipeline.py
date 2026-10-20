"""Compose text parsing, HR approval rules, and daily attendance calculation."""

from dataclasses import dataclass
from decimal import Decimal

from payroll_tool.attendance.approvals import resolve_approvals
from payroll_tool.attendance.engine import calculate_day, infer_checkout_boundary
from payroll_tool.attendance.text_parser import parse_daily_attendance_text
from payroll_tool.config.schema import AttendancePolicy
from payroll_tool.importers.hr_workbook import LeaveRuleInput
from payroll_tool.models import DailyAttendance, Segment


@dataclass(frozen=True)
class DailyPipelineResult:
    attendance: DailyAttendance
    requires_review: bool
    review_reasons: tuple[str, ...]
    payroll_attendance: DailyAttendance | None = None
    leave_adjustments: tuple[tuple[str, Decimal, Decimal], ...] = ()
    has_leave: bool = False
    leave_hours: dict[str, Decimal] | None = None
    raw_overtime_minutes: Decimal = Decimal("0")
    overtime_minutes: Decimal = Decimal("0")
    legacy_overtime_reporting: bool = False

    @property
    def overtime_hours(self) -> Decimal:
        minutes = (
            self.raw_overtime_minutes
            if self.legacy_overtime_reporting
            else self.overtime_minutes
        )
        return minutes / Decimal("60")


def calculate_day_from_text(
    text: object,
    policy: AttendancePolicy,
    leave_rules: dict[str, LeaveRuleInput],
) -> DailyPipelineResult:
    parsed = parse_daily_attendance_text(text)
    overtime_approvals = tuple(
        approval for approval in parsed.approvals if approval.kind == "加班"
    )
    if overtime_approvals and "加班" not in leave_rules:
        raise ValueError("HR 工作簿未定义审批规则：加班")
    coarse_overtime = tuple(
        approval for approval in overtime_approvals
        if approval.start is None or approval.end is None
    )
    resolvable_approvals = tuple(
        approval for approval in parsed.approvals
        if approval not in coarse_overtime
    )
    coarse_periods = {
        "上午": (Segment("schedule", policy.standard_start, policy.lunch_start),),
        "下午": (Segment("schedule", policy.lunch_end, policy.standard_end),),
        "全天": (
            Segment("schedule", policy.standard_start, policy.lunch_start),
            Segment("schedule", policy.lunch_end, policy.standard_end),
        ),
    }
    approvals = resolve_approvals(resolvable_approvals, leave_rules, coarse_periods)
    overtime_segments = tuple(
        Segment("加班", approval.start, approval.end)
        for approval in overtime_approvals
        if approval.start is not None and approval.end is not None
    )
    paid_segments = tuple(
        segment for segment in approvals.paid_segments if segment.kind != "加班"
    )
    absence_segments = tuple(
        segment for segment in approvals.absence_segments if segment.kind != "加班"
    )
    arrival = departure = None
    if len(parsed.punch_times) >= 2:
        arrival, departure = parsed.punch_times[0], parsed.punch_times[-1]
    attendance = calculate_day(
        arrival=arrival,
        departure=departure,
        paid_segments=list(paid_segments),
        policy=policy,
    )

    approval_segments = paid_segments + absence_segments
    approval_coverage = calculate_day(
        arrival=None,
        departure=None,
        paid_segments=list(approval_segments),
        policy=policy,
    )
    punches_are_exempt = bool(approval_segments) and all(
        leave_rules[segment.kind].punch_exempt for segment in approval_segments
    ) and approval_coverage.effective_hours >= policy.daily_required_hours
    payroll_attendance = calculate_day(
        arrival=arrival,
        departure=departure,
        paid_segments=list(approval_segments),
        policy=policy,
    )
    leave_adjustments = tuple(
        (segment.kind, Decimal(str(_segment_work_hours(segment, policy))), leave_rules[segment.kind].paid_ratio)
        for segment in absence_segments
        if _segment_work_hours(segment, policy) > 0
    )
    leave_hours: dict[str, Decimal] = {}
    for segment in approval_segments:
        hours = Decimal(str(_segment_work_hours(segment, policy)))
        if hours > 0:
            leave_hours[segment.kind] = leave_hours.get(segment.kind, Decimal("0")) + hours
    overtime_reasons: list[str] = []
    inferred_punch_interval = _punch_overtime_interval(
        policy, arrival, departure
    )
    if coarse_overtime and policy.overtime_approval_required is True:
        overtime_reasons.append("加班审批必须提供明确起止时间，需要 HR 复核")
    elif (
        policy.overtime_approval_required is True
        and not overtime_segments
        and inferred_punch_interval is not None
    ):
        overtime_reasons.append("存在正常下班后打卡但没有有效加班审批区间，需要 HR 复核")
    legacy_overtime_reporting = bool(overtime_segments) and _missing_overtime_config(policy)
    all_intervals: list[tuple[int, int]] = []
    eligible_intervals: list[tuple[int, int]] = []
    conflict_intervals: list[tuple[int, int]] = []
    for segment in overtime_segments:
        raw_approval_interval, _ = _raw_overtime_interval(
            segment, policy, arrival, departure
        )
        conflict_intervals.append(raw_approval_interval)
        interval, crosses_midnight = _overtime_interval(
            segment, policy, arrival, departure
        )
        if interval is None:
            continue
        all_intervals.append(interval)
        if crosses_midnight and policy.overtime_cross_midnight_allowed is False:
            overtime_reasons.append(
                f"跨午夜加班 {segment.start}-{segment.end} 未获允许，需要 HR 复核"
            )
        else:
            eligible_intervals.append(interval)
    if (
        policy.overtime_approval_required is False
        and not overtime_segments
        and inferred_punch_interval is not None
    ):
        interval, crosses_midnight = inferred_punch_interval
        all_intervals.append(interval)
        conflict_intervals.append(interval)
        if crosses_midnight and policy.overtime_cross_midnight_allowed is False:
            overtime_reasons.append("跨午夜打卡加班未获允许，需要 HR 复核")
        else:
            eligible_intervals.append(interval)
    non_overtime_segments = paid_segments + absence_segments
    if any(
        _interval_overlaps_segment(interval, segment)
        for interval in conflict_intervals
        for segment in non_overtime_segments
    ):
        overtime_reasons.append("加班与非加班审批重叠，暂不认可并需要 HR 复核")
        eligible_intervals = []
    raw_overtime_minutes = _merged_minutes(all_intervals)
    if legacy_overtime_reporting:
        overtime_minutes = Decimal("0")
        overtime_reasons.append("旧加班规则缺少分钟或跨午夜配置，需要 HR 复核")
    else:
        overtime_minutes = _recognize_overtime_minutes(
            _merged_minutes(eligible_intervals), policy
        )

    reasons: list[str] = []
    if len(parsed.punch_times) == 1 and not punches_are_exempt:
        reasons.append("单卡记录，无法判断上班卡或下班卡")
    elif not parsed.punch_times and not punches_are_exempt:
        reasons.append("无有效打卡记录")
    if approvals.coarse_approvals:
        labels = "、".join(
            f"{item.kind}({item.coarse_period})" for item in approvals.coarse_approvals
        )
        reasons.append(f"粗粒度审批需要 HR 映射：{labels}")
    reasons.extend(overtime_reasons)
    return DailyPipelineResult(
        attendance=attendance,
        requires_review=bool(reasons),
        review_reasons=tuple(reasons),
        payroll_attendance=payroll_attendance,
        leave_adjustments=leave_adjustments,
        has_leave=bool(approval_segments),
        leave_hours=leave_hours,
        raw_overtime_minutes=raw_overtime_minutes,
        overtime_minutes=overtime_minutes,
        legacy_overtime_reporting=legacy_overtime_reporting,
    )


def _segment_work_hours(segment: Segment, policy: AttendancePolicy) -> float:
    start = max(_minutes(segment.start), _minutes(policy.standard_start))
    end = min(_minutes(segment.end), _minutes(policy.standard_end))
    if end <= start:
        return 0.0
    lunch_start, lunch_end = _minutes(policy.lunch_start), _minutes(policy.lunch_end)
    lunch_overlap = max(0, min(end, lunch_end) - max(start, lunch_start))
    return (end - start - lunch_overlap) / 60


def _minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _overtime_interval(
    segment: Segment,
    policy: AttendancePolicy,
    arrival: str | None,
    departure: str | None,
) -> tuple[tuple[int, int] | None, bool]:
    (approval_start, approval_end), crosses_midnight = _raw_overtime_interval(
        segment, policy, arrival, departure
    )
    normal_checkout = _minutes(infer_checkout_boundary(arrival, policy))
    if policy.overtime_start_mode == "审批开始时间":
        start = approval_start
    elif policy.overtime_start_mode == "正常下班后":
        start = normal_checkout
    elif policy.overtime_start_mode in {
        "审批与正常下班取较晚",
        "审批开始与正常下班取较晚",
    }:
        start = max(approval_start, normal_checkout)
    else:
        raise ValueError("HR 加班起算方式无效或未配置")
    if approval_end <= start:
        return None, crosses_midnight
    return (start, approval_end), crosses_midnight


def _raw_overtime_interval(
    segment: Segment,
    policy: AttendancePolicy,
    arrival: str | None,
    departure: str | None,
) -> tuple[tuple[int, int], bool]:
    approval_start = _minutes(segment.start)
    approval_end = _minutes(segment.end)
    standard_start = _minutes(policy.standard_start)
    crosses_midnight = approval_end <= approval_start
    punches_cross_midnight = (
        arrival is not None
        and departure is not None
        and _minutes(departure) < _minutes(arrival)
    )
    if (
        punches_cross_midnight
        and approval_start < standard_start
        and approval_end <= standard_start
    ):
        crosses_midnight = True
        approval_start += 24 * 60
        approval_end += 24 * 60
    elif approval_end <= approval_start:
        approval_end += 24 * 60
    return (approval_start, approval_end), crosses_midnight


def _punch_overtime_interval(
    policy: AttendancePolicy,
    arrival: str | None,
    departure: str | None,
) -> tuple[tuple[int, int], bool] | None:
    if arrival is None or departure is None:
        return None
    start = _minutes(infer_checkout_boundary(arrival, policy))
    end = _minutes(departure)
    crosses_midnight = end < _minutes(arrival)
    if crosses_midnight:
        end += 24 * 60
    if end <= start:
        return None
    return (start, end), crosses_midnight


def _interval_overlaps_segment(
    interval: tuple[int, int], segment: Segment
) -> bool:
    segment_start = _minutes(segment.start)
    segment_end = _minutes(segment.end)
    if segment_end <= segment_start:
        segment_end += 24 * 60
    candidates = (
        (segment_start, segment_end),
        (segment_start + 24 * 60, segment_end + 24 * 60),
    )
    return any(
        max(interval[0], start) < min(interval[1], end)
        for start, end in candidates
    )


def _merged_minutes(intervals: list[tuple[int, int]]) -> Decimal:
    if not intervals:
        return Decimal("0")
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return Decimal(sum(end - start for start, end in merged))


def _recognize_overtime_minutes(
    raw: Decimal, policy: AttendancePolicy
) -> Decimal:
    if not raw:
        return Decimal("0")

    minimum = policy.overtime_minimum_minutes
    rounding_mode = policy.overtime_rounding_mode
    if raw < Decimal(minimum):
        recognized = Decimal("0")
    elif rounding_mode in {"actual", "actual_minutes"}:
        recognized = raw
    elif rounding_mode == "down_30":
        recognized = raw // Decimal("30") * Decimal("30")
    elif rounding_mode == "up_30":
        recognized = ((raw + Decimal("29")) // Decimal("30")) * Decimal("30")
    else:
        raise ValueError("HR 加班分钟取整方式无效或未配置")
    return recognized


def _missing_overtime_config(policy: AttendancePolicy) -> bool:
    return (
        policy.overtime_minimum_minutes is None
        or policy.overtime_rounding_mode is None
        or policy.overtime_cross_midnight_allowed is None
    )
