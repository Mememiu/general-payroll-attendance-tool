"""One-time conversion of the legacy HR workbook into an editable policy draft."""

from decimal import Decimal

from payroll_tool.importers.hr_workbook import parse_hr_workbook


def migrate_hr_workbook(content: bytes) -> dict[str, object]:
    parsed = parse_hr_workbook(content)
    values = parsed.base_values
    worktime = {
        "mode": {"固定工时": "fixed", "弹性工时": "flexible"}.get(values.get("work_mode")),
        "daily_minutes": _hours_to_minutes(values.get("daily_required_hours")),
        "standard_start": _text(values.get("standard_start")),
        "standard_end": _text(values.get("standard_end")),
        "lunch": {
            "enabled": bool(values.get("lunch_start") and values.get("lunch_end")),
            "start": _text(values.get("lunch_start")),
            "end": _text(values.get("lunch_end")),
        },
    }
    leaves = [
        {
            "code": name,
            "name": name,
            "enabled": True,
            "pay_scheme": "ratio",
            "pay_ratio": str(rule.paid_ratio),
            "counts_as_attendance": rule.counts_as_attendance,
            "counts_as_absence": rule.counts_as_absence,
            "affects_perfect_attendance": rule.affects_perfect_attendance,
            "skip_punch_requirement": rule.punch_exempt,
        }
        for name, rule in parsed.leave_rules.items()
    ]
    snapshot = {
        "company": {
            "worktime": worktime,
            "leaves": leaves,
            "payroll": {
                "monthly_pay_days": _text(values.get("monthly_pay_days")),
                "perfect_attendance_award": _text(values.get("perfect_attendance_award")),
            },
        },
        "legacy_migration": {
            "source": "hr_workbook_xlsx",
            "requires_hr_review": True,
            "attendance_mapping": parsed.attendance_mapping,
        },
    }
    return {"status": "draft", "snapshot": snapshot, "requires_hr_review": True}


def _hours_to_minutes(value: object) -> int | None:
    if value is None or value == "":
        return None
    minutes = Decimal(str(value)) * Decimal("60")
    if minutes != minutes.to_integral_value() or minutes <= 0:
        raise ValueError("旧规则的每日标准工时必须大于 0 且精确到整分钟")
    return int(minutes)


def _text(value: object) -> str | None:
    if value is None or value == "":
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    return str(value).strip()
