from dataclasses import dataclass
from pathlib import Path
import re

import yaml


TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
REQUIRED_INCOME_ITEMS = {"allowance", "bonus"}


@dataclass(frozen=True)
class AttendancePolicy:
    standard_start: str
    standard_end: str
    lunch_start: str
    lunch_end: str
    latest_normal_start: str
    late_grace_end: str
    work_mode: str
    daily_required_hours: float
    leave_types: dict[str, "LeaveTypePolicy"]
    attendance_exemptions: dict[str, "AttendanceExemptionPolicy"]
    earliest_valid_start: str | None = None
    grace_checkout: str | None = None
    late_makeup_allowed: bool = False
    full_day_absence_after_hours: float | None = None
    entry_day_full_attendance: bool = False
    termination_day_full_attendance: bool = False
    overtime_start_mode: str | None = None
    overtime_minimum_minutes: int | None = None
    overtime_rounding_mode: str | None = None
    overtime_approval_required: bool | None = None
    overtime_cross_midnight_allowed: bool | None = None
    flexible_rule_mode: str | None = None
    flexible_latest_start: str | None = None
    core_start: str | None = None
    core_end: str | None = None
    checkout_boundary_mode: str | None = None


@dataclass(frozen=True)
class LeaveTypePolicy:
    counts_as_attendance: bool
    affects_perfect_attendance: bool
    skip_punch_requirement: bool


@dataclass(frozen=True)
class AttendanceExemptionPolicy:
    counts_as_attendance: bool
    affects_perfect_attendance: bool
    skip_punch_requirement: bool


@dataclass(frozen=True)
class IncomeItemPolicy:
    taxable: bool
    included_in_social_base: bool
    included_in_fund_base: bool


@dataclass(frozen=True)
class CompanyPolicy:
    package_id: str
    version: str
    attendance: AttendancePolicy
    income_items: dict[str, IncomeItemPolicy]


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"missing configuration file: {path.name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"configuration file must contain an object: {path.name}")
    return data


def _required_text(data: dict, key: str) -> str:
    value = str(data.get(key, "")).strip()
    if not value:
        raise ValueError(f"configuration {key} is required")
    return value


def _required_time(data: dict, key: str) -> str:
    value = _required_text(data, key)
    if not TIME_RE.fullmatch(value):
        raise ValueError(f"configuration time is invalid: {key}")
    return value


def _income_policy(name: str, data: object) -> IncomeItemPolicy:
    if not isinstance(data, dict):
        raise ValueError(f"income item must be an object: {name}")
    required = {"taxable", "included_in_social_base", "included_in_fund_base"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"income item {name} missing fields: {', '.join(sorted(missing))}")
    if any(not isinstance(data[key], bool) for key in required):
        raise ValueError(f"income item {name} flags must be boolean")
    return IncomeItemPolicy(**{key: data[key] for key in required})


def _attendance_handling(kind: str, name: str, data: object) -> LeaveTypePolicy:
    if not isinstance(data, dict):
        raise ValueError(f"{kind} must be an object: {name}")
    required = {
        "counts_as_attendance",
        "affects_perfect_attendance",
        "skip_punch_requirement",
    }
    missing = required - set(data)
    if missing:
        raise ValueError(f"{kind} {name} missing fields: {', '.join(sorted(missing))}")
    if any(not isinstance(data[key], bool) for key in required):
        raise ValueError(f"{kind} {name} flags must be boolean")
    return LeaveTypePolicy(**{key: data[key] for key in required})


def _work_mode(data: dict) -> str:
    work_mode = _required_text(data, "work_mode")
    if work_mode not in {"fixed", "flexible"}:
        raise ValueError("configuration work_mode must be fixed or flexible")
    return work_mode


def _daily_required_hours(data: dict) -> float:
    value = data.get("daily_required_hours")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("configuration daily_required_hours must be a positive number")
    return float(value)


def load_company_policy(directory: Path) -> CompanyPolicy:
    attendance_data = _read_yaml(directory / "attendance_policy.yaml")
    payroll_data = _read_yaml(directory / "payroll_plan.yaml")
    return parse_company_policy(attendance_data, payroll_data)


def parse_company_policy(attendance_data: dict, payroll_data: dict) -> CompanyPolicy:
    package_id = _required_text(attendance_data, "package_id")
    version = _required_text(attendance_data, "version")
    attendance = AttendancePolicy(
        standard_start=_required_time(attendance_data, "standard_start"),
        standard_end=_required_time(attendance_data, "standard_end"),
        lunch_start=_required_time(attendance_data, "lunch_start"),
        lunch_end=_required_time(attendance_data, "lunch_end"),
        latest_normal_start=_required_time(attendance_data, "latest_normal_start"),
        late_grace_end=_required_time(attendance_data, "late_grace_end"),
        work_mode=_work_mode(attendance_data),
        daily_required_hours=_daily_required_hours(attendance_data),
        leave_types={
            name: _attendance_handling("leave type", name, rule)
            for name, rule in _required_mapping(attendance_data, "leave_types").items()
        },
        attendance_exemptions={
            name: AttendanceExemptionPolicy(
                **_attendance_handling("attendance exemption", name, rule).__dict__
            )
            for name, rule in _required_mapping(attendance_data, "attendance_exemptions").items()
        },
    )
    items = payroll_data.get("income_items")
    if not isinstance(items, dict):
        raise ValueError("configuration income_items is required")
    missing_items = REQUIRED_INCOME_ITEMS - set(items)
    if missing_items:
        raise ValueError(f"unsupported income items: missing {', '.join(sorted(missing_items))}")
    return CompanyPolicy(
        package_id=package_id,
        version=version,
        attendance=attendance,
        income_items={name: _income_policy(name, item) for name, item in items.items()},
    )


def _required_mapping(data: dict, key: str) -> dict:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"configuration {key} is required")
    return value
