"""Deterministic serialization for immutable policy snapshots."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
from types import MappingProxyType
from typing import Any
import unicodedata

from payroll_tool.config.policy_models import CanonicalSnapshot
from payroll_tool.config.policy_normalization import normalize_policy
from payroll_tool.config.schema import AttendancePolicy, IncomeItemPolicy
from payroll_tool.importers.hr_workbook import LeaveRuleInput, StatutoryRuleInput
from payroll_tool.payroll.commercial_insurance import CommercialInsurancePolicy


SUPPORTED_LEAVE_FORMULAS = {"hourly_salary_ratio", "daily_salary_ratio"}
SUPPORTED_PAYROLL_SCHEMES = {
    "full_time_monthly",
    "intern_daily_hourly",
    "conversion_split",
}


@dataclass(frozen=True)
class EmploymentTypePolicy:
    code: str
    name: str
    payroll_scheme: str
    social_insurance_applicable: bool
    housing_fund_applicable: bool
    tax_applicable: bool


@dataclass(frozen=True)
class EmployeeException:
    employee_id: str
    override_type: str
    target_code: str
    value: bool | Decimal | str
    effective_from: date
    effective_to: date | None
    reason: str


@dataclass(frozen=True)
class TaxBracketPolicy:
    threshold: Decimal
    rate: Decimal
    quick_deduction: Decimal


@dataclass(frozen=True)
class TaxPolicy:
    enabled: bool
    system: str | None
    monthly_exemption: Decimal
    negative_tax_mode: str
    brackets: tuple[TaxBracketPolicy, ...]
    effective_from: date | None


@dataclass(frozen=True)
class OvertimePolicy:
    enabled: bool
    start_mode: str | None
    minimum_minutes: int | None
    rounding_mode: str | None
    approval_required: bool | None
    cross_midnight_allowed: bool | None
    cash_enabled: bool
    cash_formula: str | None
    cash_rate: Decimal | None
    day_rates: Mapping[str, Decimal]
    comp_time_enabled: bool
    comp_time_ratio: Decimal | None


@dataclass(frozen=True)
class CalculationPolicy:
    attendance: AttendancePolicy
    overtime: OvertimePolicy
    leave_rules: dict[str, LeaveRuleInput]
    income_items: dict[str, IncomeItemPolicy]
    statutory_rules: tuple[StatutoryRuleInput, ...]
    daily_minutes: int
    monthly_pay_days: Decimal
    perfect_attendance_award: Decimal
    employment_types: dict[str, EmploymentTypePolicy]
    employee_exceptions: tuple[EmployeeException, ...]
    tax: TaxPolicy
    commercial_insurance: tuple[CommercialInsurancePolicy, ...]

    def active_employee_exceptions(
        self, employee_id: str, calculation_date: date
    ) -> tuple[EmployeeException, ...]:
        return tuple(item for item in self.employee_exceptions if item.employee_id == employee_id and item.effective_from <= calculation_date and (item.effective_to is None or calculation_date <= item.effective_to))

    def employee_exceptions_for_period(
        self, employee_id: str, period_start: date, period_end: date
    ) -> tuple[EmployeeException, ...]:
        if period_start > period_end:
            raise ValueError("period_start cannot be after period_end")
        return tuple(
            item for item in self.employee_exceptions
            if item.employee_id == employee_id
            and item.effective_from <= period_end
            and (item.effective_to is None or item.effective_to >= period_start)
        )


def calculation_policy_from_snapshot(
    snapshot: Mapping[str, object],
) -> CalculationPolicy:
    normalized = normalize_policy(snapshot)
    if not isinstance(normalized, Mapping):
        raise ValueError("policy must be an object")
    snapshot = normalized
    company = _required_mapping(snapshot, "company", "company")
    worktime = _required_mapping(company, "worktime", "company.worktime")
    payroll = _required_mapping(company, "payroll", "company.payroll")
    overtime = _required_mapping(company, "overtime", "company.overtime")
    daily_minutes = _required_int(
        worktime, "daily_minutes", "company.worktime.daily_minutes", minimum=1
    )
    monthly_pay_days = _required_decimal(
        payroll, "monthly_pay_days", "company.payroll.monthly_pay_days", positive=True
    )
    award = _required_decimal(
        payroll,
        "perfect_attendance_award",
        "company.payroll.perfect_attendance_award",
    )
    overtime_policy = _overtime_policy(overtime)
    return CalculationPolicy(
        attendance=_attendance_policy(worktime, overtime_policy, daily_minutes),
        overtime=overtime_policy,
        leave_rules=_leave_rules(company),
        income_items=_income_items(company),
        statutory_rules=_statutory_rules(snapshot),
        daily_minutes=daily_minutes,
        monthly_pay_days=monthly_pay_days,
        perfect_attendance_award=award,
        employment_types=_employment_types(snapshot),
        employee_exceptions=_employee_exceptions(snapshot),
        tax=_tax_policy(snapshot),
        commercial_insurance=_commercial_insurance(snapshot),
    )


def _commercial_insurance(
    snapshot: Mapping[str, object],
) -> tuple[CommercialInsurancePolicy, ...]:
    values = snapshot.get("commercial_insurance")
    if not isinstance(values, list):
        raise ValueError("commercial_insurance must be a list")
    result: list[CommercialInsurancePolicy] = []
    for index, raw in enumerate(values):
        path = f"commercial_insurance[{index}]"
        if not isinstance(raw, Mapping):
            raise ValueError(f"{path} must be an object")
        if raw.get("enabled") is not True:
            continue
        calculation = _required_text(raw, "calculation", f"{path}.calculation")
        result.append(CommercialInsurancePolicy(
            code=_required_text(raw, "code", f"{path}.code"),
            name=_required_text(raw, "name", f"{path}.name"),
            effective_from=_required_date(raw, "effective_from", f"{path}.effective_from"),
            effective_to=(
                _date_value(raw.get("effective_to"), f"{path}.effective_to")
                if raw.get("effective_to") not in (None, "") else None
            ),
            calculation=calculation,
            amount=(
                _required_decimal(raw, "amount", f"{path}.amount")
                if calculation == "fixed_amount" else None
            ),
            employee_share=_required_decimal(
                raw, "employee_share", f"{path}.employee_share"
            ),
            employer_share=_required_decimal(
                raw, "employer_share", f"{path}.employer_share"
            ),
            employee_rate=(
                _required_decimal(raw, "employee_rate", f"{path}.employee_rate")
                if calculation == "base_rate" else None
            ),
            employer_rate=(
                _required_decimal(raw, "employer_rate", f"{path}.employer_rate")
                if calculation == "base_rate" else None
            ),
            taxable=_required_bool(raw, "taxable", f"{path}.taxable"),
            included_in_gross=_required_bool(
                raw, "included_in_gross", f"{path}.included_in_gross"
            ),
            deduction_mode=_required_text(
                raw, "deduction_mode", f"{path}.deduction_mode"
            ),
            employment_types=tuple(str(value) for value in raw.get("employment_types", [])),
        ))
    return tuple(result)


def _tax_policy(snapshot: Mapping[str, object]) -> TaxPolicy:
    statutory = _required_mapping(snapshot, "statutory", "statutory")
    raw = _required_mapping(statutory, "tax", "statutory.tax")
    enabled = _required_bool(raw, "enabled", "statutory.tax.enabled")
    if not enabled:
        return TaxPolicy(False, None, Decimal("0"), "zero", (), None)
    system = _required_text(raw, "system", "statutory.tax.system")
    if system != "cn_cumulative_withholding":
        raise ValueError("statutory.tax.system is unsupported")
    values = raw.get("brackets")
    if not isinstance(values, list) or not values:
        raise ValueError("statutory.tax.brackets must be a non-empty list")
    brackets: list[TaxBracketPolicy] = []
    for index, value in enumerate(values):
        path = f"statutory.tax.brackets[{index}]"
        if not isinstance(value, Mapping):
            raise ValueError(f"{path} must be an object")
        brackets.append(TaxBracketPolicy(
            threshold=_required_decimal(value, "threshold", f"{path}.threshold"),
            rate=_required_decimal(value, "rate", f"{path}.rate"),
            quick_deduction=_required_decimal(
                value, "quick_deduction", f"{path}.quick_deduction"
            ),
        ))
    mode = _required_text(raw, "negative_tax_mode", "statutory.tax.negative_tax_mode")
    if mode not in {"zero", "carry_forward"}:
        raise ValueError("statutory.tax.negative_tax_mode is unsupported")
    return TaxPolicy(
        enabled=True,
        system=system,
        monthly_exemption=_required_decimal(
            raw, "monthly_exemption", "statutory.tax.monthly_exemption"
        ),
        negative_tax_mode=mode,
        brackets=tuple(brackets),
        effective_from=_required_date(
            raw, "effective_from", "statutory.tax.effective_from"
        ),
    )


def _employee_exceptions(snapshot: Mapping[str, object]) -> tuple[EmployeeException, ...]:
    from payroll_tool.config.policy_validation import validate_policy

    exception_issues = [
        issue for issue in validate_policy(snapshot)
        if issue.field == "employee_exceptions" or issue.field.startswith("employee_exceptions[")
    ]
    if exception_issues:
        issue = exception_issues[0]
        raise ValueError(f"{issue.field}: {issue.message}")
    values = snapshot.get("employee_exceptions", [])
    if not isinstance(values, list):
        raise ValueError("employee_exceptions must be a list")
    decimal_types = {
        "statutory_fixed_base", "housing_fund_fixed_base", "commercial_amount",
        "commercial_base", "perfect_attendance_amount",
    }
    result: list[EmployeeException] = []
    for index, raw in enumerate(values):
        path = f"employee_exceptions[{index}]"
        if not isinstance(raw, Mapping):
            raise ValueError(f"{path} must be an object")
        if raw.get("enabled") is not True:
            continue
        override_type = _required_text(raw, "override_type", f"{path}.override_type")
        raw_value = raw.get("value")
        value = _required_decimal(raw, "value", f"{path}.value") if override_type in decimal_types else raw_value
        if not isinstance(value, (bool, Decimal, str)):
            raise ValueError(f"{path}.value is invalid")
        effective_to = raw.get("effective_to")
        result.append(EmployeeException(
            employee_id=_required_text(raw, "employee_id", f"{path}.employee_id"),
            override_type=override_type,
            target_code=_required_text(raw, "target_code", f"{path}.target_code"),
            value=value,
            effective_from=_required_date(raw, "effective_from", f"{path}.effective_from"),
            effective_to=_date_value(effective_to, f"{path}.effective_to") if effective_to not in (None, "") else None,
            reason=_required_text(raw, "reason", f"{path}.reason"),
        ))
    return tuple(result)


def _employment_types(
    snapshot: Mapping[str, object],
) -> dict[str, EmploymentTypePolicy]:
    values = snapshot.get("employment_types")
    if not isinstance(values, list) or not values:
        raise ValueError("employment_types must be a non-empty list")
    result: dict[str, EmploymentTypePolicy] = {}
    for index, raw in enumerate(values):
        path = f"employment_types[{index}]"
        if not isinstance(raw, Mapping):
            raise ValueError(f"{path} must be an object")
        if raw.get("migration_review_required") is True:
            raise ValueError(f"{path}.migration_review_required must be false")
        code = _required_text(raw, "code", f"{path}.code")
        if code in result:
            raise ValueError(f"{path}.code must be unique")
        scheme = _required_text(raw, "payroll_scheme", f"{path}.payroll_scheme")
        if scheme not in SUPPORTED_PAYROLL_SCHEMES:
            raise ValueError(f"{path}.payroll_scheme is unsupported")
        if raw.get("enabled") is not True:
            continue
        result[code] = EmploymentTypePolicy(
            code=code,
            name=_required_text(raw, "name", f"{path}.name"),
            payroll_scheme=scheme,
            social_insurance_applicable=_required_bool(
                raw, "social_insurance_applicable", f"{path}.social_insurance_applicable"
            ),
            housing_fund_applicable=_required_bool(
                raw, "housing_fund_applicable", f"{path}.housing_fund_applicable"
            ),
            tax_applicable=_required_bool(raw, "tax_applicable", f"{path}.tax_applicable"),
        )
    return result


def _attendance_policy(
    worktime: Mapping[str, object],
    overtime: OvertimePolicy,
    daily_minutes: int,
) -> AttendancePolicy:
    mode = _required_text(worktime, "mode", "company.worktime.mode")
    if mode not in {"fixed", "flexible"}:
        raise ValueError("company.worktime.mode is unsupported")
    lunch = _required_mapping(worktime, "lunch", "company.worktime.lunch")
    lunch_enabled = _required_bool(lunch, "enabled", "company.worktime.lunch.enabled")
    standard_start = _required_text(
        worktime, "standard_start", "company.worktime.standard_start"
    )
    standard_end = _required_text(
        worktime, "standard_end", "company.worktime.standard_end"
    )
    if lunch_enabled:
        lunch_start = _required_text(lunch, "start", "company.worktime.lunch.start")
        lunch_end = _required_text(lunch, "end", "company.worktime.lunch.end")
    else:
        lunch_start = lunch_end = standard_start
    flexible_modes = {
        "work_hours": "纯工时弹性",
        "latest_start": "最晚到岗限制",
        "core_hours": "核心时段覆盖",
    }
    strategy = worktime.get("strategy")
    if mode == "flexible" and strategy not in flexible_modes:
        raise ValueError("company.worktime.strategy is unsupported")
    latest_normal = _optional_text(worktime.get("latest_normal_start")) or standard_start
    late_grace = _optional_text(worktime.get("late_grace_end")) or latest_normal
    overtime_modes = {
        "approval_start": "审批开始时间",
        "after_normal_end": "正常下班后",
        "later_of_approval_and_normal_end": "审批与正常下班取较晚",
    }
    overtime_start_mode = None
    if overtime.enabled:
        configured_mode = overtime.start_mode
        if configured_mode not in overtime_modes:
            raise ValueError("company.overtime.start_mode is unsupported")
        overtime_start_mode = overtime_modes[configured_mode]
    return AttendancePolicy(
        standard_start=standard_start,
        standard_end=standard_end,
        lunch_start=lunch_start,
        lunch_end=lunch_end,
        latest_normal_start=latest_normal,
        late_grace_end=late_grace,
        work_mode=mode,
        daily_required_hours=daily_minutes / 60,
        leave_types={},
        attendance_exemptions={},
        earliest_valid_start=_optional_text(worktime.get("earliest_valid_start")),
        grace_checkout=_optional_text(worktime.get("grace_checkout")),
        late_makeup_allowed=worktime.get("late_makeup_allowed") is True,
        full_day_absence_after_hours=_optional_decimal_float(
            worktime.get("full_day_absence_after_hours"),
            "company.worktime.full_day_absence_after_hours",
        ),
        entry_day_full_attendance=worktime.get("entry_day_full_attendance") is True,
        termination_day_full_attendance=worktime.get("termination_day_full_attendance") is True,
        overtime_start_mode=overtime_start_mode,
        overtime_minimum_minutes=overtime.minimum_minutes,
        overtime_rounding_mode=overtime.rounding_mode,
        overtime_approval_required=overtime.approval_required,
        overtime_cross_midnight_allowed=overtime.cross_midnight_allowed,
        flexible_rule_mode=flexible_modes.get(strategy),
        flexible_latest_start=_optional_text(worktime.get("latest_start")),
        core_start=_optional_text(worktime.get("core_start")),
        core_end=_optional_text(worktime.get("core_end")),
        checkout_boundary_mode=_optional_text(worktime.get("checkout_boundary_mode")),
    )


def _overtime_policy(overtime: Mapping[str, object]) -> OvertimePolicy:
    enabled = _required_bool(overtime, "enabled", "company.overtime.enabled")
    cash_enabled = _required_bool(
        overtime, "cash_enabled", "company.overtime.cash_enabled"
    )
    comp_time_enabled = _required_bool(
        overtime, "comp_time_enabled", "company.overtime.comp_time_enabled"
    )
    if not enabled:
        if cash_enabled or comp_time_enabled:
            raise ValueError(
                "company.overtime disabled policy cannot enable cash or comp time"
            )
        return OvertimePolicy(
            enabled=False,
            start_mode=None,
            minimum_minutes=None,
            rounding_mode=None,
            approval_required=None,
            cross_midnight_allowed=None,
            cash_enabled=cash_enabled,
            cash_formula=None,
            cash_rate=None,
            day_rates=MappingProxyType({}),
            comp_time_enabled=comp_time_enabled,
            comp_time_ratio=None,
        )

    approval_required = _required_bool(
        overtime, "approval_required", "company.overtime.approval_required"
    )
    cross_midnight_allowed = _required_bool(
        overtime,
        "cross_midnight_allowed",
        "company.overtime.cross_midnight_allowed",
    )
    rounding_mode = _required_text(
        overtime, "rounding_mode", "company.overtime.rounding_mode"
    )
    if rounding_mode not in {"actual_minutes", "down_30", "up_30"}:
        raise ValueError("company.overtime.rounding_mode is unsupported")
    day_rates: Mapping[str, Decimal] = MappingProxyType({})
    cash_formula = cash_rate = None
    if cash_enabled:
        cash_formula = _required_text(
            overtime, "cash_formula", "company.overtime.cash_formula"
        )
        if cash_formula not in {"hourly_rate_multiplier", "fixed_hourly_rate"}:
            raise ValueError("company.overtime.cash_formula is unsupported")
        cash_rate = _required_decimal(
            overtime, "cash_rate", "company.overtime.cash_rate", positive=True
        )
        configured_day_rates = _required_mapping(
            overtime, "day_rates", "company.overtime.day_rates"
        )
        required_day_types = {"workday", "rest_day", "holiday"}
        day_rates = MappingProxyType({
            key: _required_decimal(
                configured_day_rates, key, f"company.overtime.day_rates.{key}",
                positive=True,
            )
            for key in ("workday", "rest_day", "holiday")
        })
        if set(configured_day_rates) != required_day_types:
            raise ValueError(
                "company.overtime.day_rates must contain exactly "
                "workday, rest_day and holiday"
            )

    return OvertimePolicy(
        enabled=True,
        start_mode=_required_text(
            overtime, "start_mode", "company.overtime.start_mode"
        ),
        minimum_minutes=_required_int(
            overtime,
            "minimum_minutes",
            "company.overtime.minimum_minutes",
            minimum=0,
        ),
        rounding_mode=rounding_mode,
        approval_required=approval_required,
        cross_midnight_allowed=cross_midnight_allowed,
        cash_enabled=cash_enabled,
        cash_formula=cash_formula,
        cash_rate=cash_rate,
        day_rates=day_rates,
        comp_time_enabled=comp_time_enabled,
        comp_time_ratio=(
            _required_decimal(
                overtime, "comp_time_ratio", "company.overtime.comp_time_ratio",
                positive=True,
            )
            if comp_time_enabled
            else None
        ),
    )


def _leave_rules(company: Mapping[str, object]) -> dict[str, LeaveRuleInput]:
    values = company.get("leaves")
    if not isinstance(values, list):
        raise ValueError("company.leaves must be a list")
    result: dict[str, LeaveRuleInput] = {}
    for index, raw in enumerate(values):
        path = f"company.leaves[{index}]"
        if not isinstance(raw, Mapping):
            raise ValueError(f"{path} must be an object")
        if raw.get("enabled") is False:
            continue
        name = _required_text(raw, "name", f"{path}.name")
        code = _required_text(raw, "code", f"{path}.code")
        scheme = _required_text(raw, "pay_scheme", f"{path}.pay_scheme")
        fixed = formula_id = multiplier = None
        if scheme == "ratio":
            paid_ratio = _required_decimal(raw, "pay_ratio", f"{path}.pay_ratio")
        elif scheme == "full_pay":
            paid_ratio = Decimal("1")
        elif scheme == "unpaid":
            paid_ratio = Decimal("0")
        elif scheme == "fixed_deduction":
            paid_ratio = Decimal("1")
            fixed = _required_decimal(
                raw, "fixed_deduction_amount", f"{path}.fixed_deduction_amount"
            )
        elif scheme == "formula":
            paid_ratio = Decimal("1")
            formula_id = _required_text(raw, "formula_id", f"{path}.formula_id")
            if formula_id not in SUPPORTED_LEAVE_FORMULAS:
                raise ValueError(f"{path}.formula_id is unsupported")
            parameters = _required_mapping(raw, "formula_parameters", f"{path}.formula_parameters")
            multiplier = _required_decimal(
                parameters, "multiplier", f"{path}.formula_parameters.multiplier"
            )
        else:
            raise ValueError(f"{path}.pay_scheme is unsupported")
        result[name] = LeaveRuleInput(
            paid_ratio=paid_ratio,
            counts_as_attendance=_required_bool(
                raw, "counts_as_attendance", f"{path}.counts_as_attendance"
            ),
            counts_as_absence=_required_bool(
                raw, "counts_as_absence", f"{path}.counts_as_absence"
            ),
            affects_perfect_attendance=_required_bool(
                raw, "affects_perfect_attendance", f"{path}.affects_perfect_attendance"
            ),
            punch_exempt=_required_bool(
                raw, "skip_punch_requirement", f"{path}.skip_punch_requirement"
            ),
            code=code,
            pay_scheme=scheme,
            fixed_deduction_amount=fixed,
            formula_id=formula_id,
            formula_multiplier=multiplier,
            deduction_category=_required_text(
                raw, "deduction_category", f"{path}.deduction_category"
            ),
        )
    return result


def _income_items(company: Mapping[str, object]) -> dict[str, IncomeItemPolicy]:
    values = _required_mapping(company, "income_items", "company.income_items")
    result: dict[str, IncomeItemPolicy] = {}
    for code in ("allowance", "bonus"):
        path = f"company.income_items.{code}"
        item = _required_mapping(values, code, path)
        result[code] = IncomeItemPolicy(
            taxable=_required_bool(item, "taxable", f"{path}.taxable"),
            included_in_social_base=_required_bool(
                item, "included_in_social_base", f"{path}.included_in_social_base"
            ),
            included_in_fund_base=_required_bool(
                item, "included_in_fund_base", f"{path}.included_in_fund_base"
            ),
        )
    return result


def _statutory_rules(snapshot: Mapping[str, object]) -> tuple[StatutoryRuleInput, ...]:
    statutory = _required_mapping(snapshot, "statutory", "statutory")
    values = statutory.get("insurance")
    if not isinstance(values, list):
        raise ValueError("statutory.insurance must be a list")
    rules: list[StatutoryRuleInput] = []
    modes = {"fixed": "固定基数", "salary_full": "薪资全额"}
    for index, raw in enumerate(values):
        path = f"statutory.insurance[{index}]"
        if not isinstance(raw, Mapping):
            raise ValueError(f"{path} must be an object")
        if raw.get("enabled") is not True:
            continue
        mode = _required_text(raw, "base_mode", f"{path}.base_mode")
        if mode not in modes:
            raise ValueError(f"{path}.base_mode is unsupported for calculation")
        effective_to = raw.get("effective_to")
        rules.append(StatutoryRuleInput(
            item_code=_required_text(raw, "code", f"{path}.code"),
            tier_code=_required_text(raw, "tier_code", f"{path}.tier_code"),
            region=_required_text(raw, "region", f"{path}.region"),
            effective_from=_required_date(raw, "effective_from", f"{path}.effective_from"),
            effective_to=(
                _date_value(effective_to, f"{path}.effective_to")
                if effective_to not in (None, "") else None
            ),
            base_mode=modes[mode],
            base_lower=_required_decimal(raw, "base_lower", f"{path}.base_lower"),
            base_upper=_required_decimal(raw, "base_upper", f"{path}.base_upper"),
            fixed_base=(
                _required_decimal(raw, "fixed_base", f"{path}.fixed_base")
                if mode == "fixed" else None
            ),
            employee_rate=_required_decimal(raw, "employee_rate", f"{path}.employee_rate"),
            employer_rate=_required_decimal(raw, "employer_rate", f"{path}.employer_rate"),
            employment_types=tuple(
                _required_text({"value": value}, "value", f"{path}.employment_types")
                for value in raw.get("employment_types", [])
            ),
            hire_month_rule=_required_text(
                raw, "hire_month_rule", f"{path}.hire_month_rule"
            ),
            termination_month_rule=_required_text(
                raw, "termination_month_rule", f"{path}.termination_month_rule"
            ),
            hire_cutoff_day=(
                int(raw["hire_cutoff_day"])
                if raw.get("hire_month_rule") == "cutoff_day" else None
            ),
            termination_cutoff_day=(
                int(raw["termination_cutoff_day"])
                if raw.get("termination_month_rule") == "cutoff_day" else None
            ),
        ))
    return tuple(rules)


def _required_mapping(data: Mapping[str, object], key: str, path: str) -> Mapping[str, object]:
    value = data.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    return value


def _required_text(data: Mapping[str, object], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} is required")
    return value.strip()


def _required_bool(data: Mapping[str, object], key: str, path: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be boolean")
    return value


def _required_int(
    data: Mapping[str, object], key: str, path: str, *, minimum: int
) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{path} must be an integer of at least {minimum}")
    return value


def _required_decimal(
    data: Mapping[str, object], key: str, path: str, *, positive: bool = False
) -> Decimal:
    try:
        value = Decimal(str(data[key]))
    except (KeyError, InvalidOperation, ValueError) as exc:
        raise ValueError(f"{path} must be a decimal") from exc
    if not value.is_finite() or value < 0 or (positive and value <= 0):
        raise ValueError(f"{path} is outside the supported range")
    return value


def _required_date(data: Mapping[str, object], key: str, path: str) -> date:
    if key not in data:
        raise ValueError(f"{path} is required")
    return _date_value(data[key], path)


def _date_value(value: object, path: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{path} must use YYYY-MM-DD") from exc


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _optional_decimal_float(value: object, path: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{path} must be a decimal") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{path} is outside the supported range")
    return float(result)


def canonical_snapshot(value: Mapping[str, object]) -> CanonicalSnapshot:
    if not isinstance(value, Mapping):
        raise TypeError("Policy snapshot must be a mapping")
    normalized = _normalize(value, "")
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return CanonicalSnapshot(payload=payload, sha256=digest)


def _normalize(value: Any, path: str) -> Any:
    if value is None:
        return ["null"]
    if isinstance(value, str):
        return ["string", unicodedata.normalize("NFC", value)]
    if isinstance(value, bool):
        return ["boolean", value]
    if isinstance(value, int):
        return ["integer", str(value)]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"Unsupported non-finite float at {path}")
        return ["float", "0x0.0p+0" if value == 0.0 else value.hex()]
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise TypeError(f"Unsupported non-finite Decimal at {path}")
        return ["decimal", _canonical_decimal(value)]
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise TypeError(f"Expected timezone-aware datetime at {path}")
        utc_value = value.astimezone(timezone.utc)
        return ["datetime", utc_value.isoformat().replace("+00:00", "Z")]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    if isinstance(value, Mapping):
        normalized: list[list[Any]] = []
        seen_keys: set[str] = set()
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"Unsupported mapping key type at {path}: {type(key).__name__}"
                )
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in seen_keys:
                raise TypeError(f"Mapping keys collide after Unicode normalization at {path}")
            seen_keys.add(normalized_key)
            item_path = f"{path}/{_escape_pointer(normalized_key)}"
            normalized.append([normalized_key, _normalize(item, item_path)])
        normalized.sort(key=lambda pair: pair[0])
        return ["mapping", normalized]
    if isinstance(value, list):
        return [
            "list",
            [_normalize(item, f"{path}/{index}") for index, item in enumerate(value)],
        ]
    if isinstance(value, tuple):
        return [
            "tuple",
            [_normalize(item, f"{path}/{index}") for index, item in enumerate(value)],
        ]
    raise TypeError(f"Unsupported value type at {path}: {type(value).__name__}")


def _canonical_decimal(value: Decimal) -> str:
    if value.is_zero():
        return "0"
    sign, digits, exponent = value.as_tuple()
    digits = list(digits)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    coefficient = "".join(str(digit) for digit in digits)
    if exponent >= 0:
        rendered = coefficient + ("0" * exponent)
    else:
        point = len(coefficient) + exponent
        if point > 0:
            rendered = f"{coefficient[:point]}.{coefficient[point:]}"
        else:
            rendered = f"0.{('0' * -point)}{coefficient}"
    return f"-{rendered}" if sign else rendered


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")
