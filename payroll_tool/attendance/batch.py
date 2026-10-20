"""Aggregate normalized uploaded attendance rows by employee and pay period."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from payroll_tool.attendance.daily_pipeline import calculate_day_from_text
from payroll_tool.attendance.text_parser import parse_daily_attendance_text
from payroll_tool.config.schema import AttendancePolicy
from payroll_tool.importers.hr_workbook import LeaveRuleInput
from payroll_tool.payroll.engine import AttendanceDay


@dataclass(frozen=True)
class EmployeeAttendanceSummary:
    effective_hours: Decimal
    absence_hours: Decimal
    late_hours: Decimal
    processed_days: int
    review_reasons: tuple[str, ...]
    attendance_days: tuple[AttendanceDay, ...]
    has_leave: bool
    leave_hours: dict[str, Decimal]
    raw_overtime_minutes: Decimal
    overtime_minutes: Decimal
    comp_time_accrual_minutes: Decimal

    @property
    def overtime_hours(self) -> Decimal:
        return self.overtime_minutes / Decimal("60")


def calculate_attendance_rows(
    rows: tuple[dict[str, object], ...],
    employee_ids: set[str],
    period_start: date,
    period_end: date,
    policy: AttendancePolicy,
    leave_rules: dict[str, LeaveRuleInput],
    employee_periods: dict[str, tuple[date | None, date | None]] | None = None,
    comp_time_ratio: Decimal | None = None,
) -> dict[str, EmployeeAttendanceSummary]:
    if comp_time_ratio is not None and comp_time_ratio <= 0:
        raise ValueError("comp_time_ratio must be positive")
    employee_periods = employee_periods or {}
    totals: dict[str, dict[str, object]] = {}
    seen: set[tuple[str, date]] = set()
    for row in rows:
        work_date = _date(row.get("work_date"))
        if work_date < period_start or work_date > period_end:
            continue
        employee_id = str(row.get("employee_id") or "").strip()
        if employee_id not in employee_ids:
            raise ValueError(f"考勤工号未在薪酬工作簿中定义：{employee_id or '(空)'}")
        hire_date, termination_date = employee_periods.get(employee_id, (None, None))
        if (hire_date is not None and work_date < hire_date) or (
            termination_date is not None and work_date > termination_date
        ):
            continue
        key = employee_id, work_date
        if key in seen:
            raise ValueError(f"考勤存在重复员工日期：{employee_id} {work_date.isoformat()}")
        seen.add(key)
        workday_type = _workday_type(row.get("workday_type"))
        is_entry_full_day = policy.entry_day_full_attendance and work_date == hire_date
        is_termination_full_day = (
            policy.termination_day_full_attendance and work_date == termination_date
        )
        parsed_text = parse_daily_attendance_text(row.get("attendance_text"))
        if (is_entry_full_day or is_termination_full_day) and not parsed_text.approvals:
            total = totals.setdefault(
                employee_id,
                _new_total(),
            )
            full_day_hours = Decimal(str(policy.daily_required_hours))
            total["effective"] += full_day_hours
            total["days"] += 1
            total["attendance_days"].append(
                AttendanceDay(
                    work_date, full_day_hours, workday_type=workday_type
                )
            )
            continue
        day = calculate_day_from_text(row.get("attendance_text"), policy, leave_rules)
        total = totals.setdefault(
            employee_id,
            _new_total(),
        )
        total["effective"] += Decimal(str(day.attendance.effective_hours))
        total["absence"] += Decimal(str(day.attendance.absence_hours))
        total["late"] += Decimal(str(day.attendance.late_hours))
        total["days"] += 1
        total["has_leave"] = total["has_leave"] or day.has_leave
        total["raw_overtime"] += day.raw_overtime_minutes
        total["overtime"] += day.overtime_minutes
        if comp_time_ratio is not None:
            total["comp_time"] += day.overtime_minutes * comp_time_ratio
        for kind, hours in (day.leave_hours or {}).items():
            total["leave_hours"][kind] = total["leave_hours"].get(kind, Decimal("0")) + hours
        total["attendance_days"].append(
            AttendanceDay(
                work_date,
                Decimal(str((day.payroll_attendance or day.attendance).effective_hours)),
                day.leave_adjustments,
                workday_type,
                day.overtime_minutes,
            )
        )
        total["reasons"].extend(
            f"{work_date.isoformat()} {reason}" for reason in day.review_reasons
        )
    for employee_id, (hire_date, termination_date) in employee_periods.items():
        special_dates = []
        if policy.entry_day_full_attendance and hire_date is not None:
            special_dates.append(hire_date)
        if policy.termination_day_full_attendance and termination_date is not None:
            special_dates.append(termination_date)
        for special_date in special_dates:
            if not (period_start <= special_date <= period_end):
                continue
            if (employee_id, special_date) in seen:
                continue
            total = totals.setdefault(
                employee_id,
                _new_total(),
            )
            seen.add((employee_id, special_date))
            full_day_hours = Decimal(str(policy.daily_required_hours))
            total["effective"] += full_day_hours
            total["days"] += 1
            total["attendance_days"].append(AttendanceDay(special_date, full_day_hours))
    return {
        employee_id: EmployeeAttendanceSummary(
            effective_hours=total["effective"],
            absence_hours=total["absence"],
            late_hours=total["late"],
            processed_days=total["days"],
            review_reasons=tuple(total["reasons"]),
            attendance_days=tuple(total["attendance_days"]),
            has_leave=total["has_leave"],
            leave_hours=total["leave_hours"],
            raw_overtime_minutes=total["raw_overtime"],
            overtime_minutes=total["overtime"],
            comp_time_accrual_minutes=total["comp_time"],
        )
        for employee_id, total in totals.items()
    }


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"考勤日期无效：{value}") from exc


def _workday_type(value: object) -> str | None:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip()
    if normalized not in {"workday", "rest_day", "holiday"}:
        raise ValueError(f"workday_type 无效：{normalized}")
    return normalized


def _new_total() -> dict[str, object]:
    return {
        "effective": Decimal("0"),
        "absence": Decimal("0"),
        "late": Decimal("0"),
        "days": 0,
        "reasons": [],
        "attendance_days": [],
        "has_leave": False,
        "leave_hours": {},
        "raw_overtime": Decimal("0"),
        "overtime": Decimal("0"),
        "comp_time": Decimal("0"),
    }
