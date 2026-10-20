"""Opt-in local statutory contribution calculator with no embedded city rates."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from payroll_tool.payroll.engine import EmployeePayProfile

if TYPE_CHECKING:
    from payroll_tool.importers.hr_workbook import StatutoryRuleInput


CENTS = Decimal("0.01")


@dataclass(frozen=True)
class ContributionRule:
    employee_rate: Decimal
    employer_rate: Decimal


@dataclass(frozen=True)
class EmployeeStatutoryProfile:
    employee_id: str
    pension_tier: str | None = None
    medical_tier: str | None = None
    work_injury_tier: str | None = None


@dataclass(frozen=True)
class LocalStatutoryPolicy:
    enabled: bool
    region: str
    effective_from: date | None
    effective_to: date | None
    pension_tiers: dict[str, ContributionRule]
    medical_tiers: dict[str, ContributionRule]
    unemployment: ContributionRule | None
    work_injury_tiers: dict[str, ContributionRule]
    maternity: ContributionRule | None
    housing_fund: ContributionRule | None


@dataclass(frozen=True)
class StatutoryDeductionResult:
    employee_total: Decimal
    employer_total: Decimal


@dataclass(frozen=True)
class ConfiguredStatutoryDeductionResult:
    employee_amounts: dict[str, Decimal]
    employer_amounts: dict[str, Decimal]
    employee_total: Decimal
    employer_total: Decimal


def applicable_statutory_tiers(
    employee: EmployeePayProfile,
    rules: tuple["StatutoryRuleInput", ...],
    *,
    period_date: date,
    effective_date: date | None = None,
) -> dict[str, set[str]]:
    rule_date = effective_date or period_date
    result: dict[str, set[str]] = {}
    for rule in rules:
        if (
            rule_date >= rule.effective_from
            and (rule.effective_to is None or rule_date <= rule.effective_to)
            and _item_enabled(employee, rule.item_code)
            and _employment_month_allows(employee, rule, period_date)
        ):
            result.setdefault(rule.item_code, set()).add(rule.tier_code)
    return result


def calculate_configured_statutory_deductions(
    employee: EmployeePayProfile,
    rules: tuple["StatutoryRuleInput", ...],
    *,
    social_income: Decimal,
    fund_income: Decimal,
    period_date: date,
    effective_date: date | None = None,
) -> ConfiguredStatutoryDeductionResult:
    if social_income < 0 or fund_income < 0:
        raise ValueError("statutory contribution income cannot be negative")
    if not employee.statutory_enabled:
        return ConfiguredStatutoryDeductionResult({}, {}, Decimal("0.00"), Decimal("0.00"))
    if not rules:
        raise ValueError("statutory contribution policy is not configured")
    employee_amounts: dict[str, Decimal] = {}
    employer_amounts: dict[str, Decimal] = {}
    rule_date = effective_date or period_date
    active_rules = [
        rule for rule in rules
        if rule_date >= rule.effective_from
        and (rule.effective_to is None or rule_date <= rule.effective_to)
        and _item_enabled(employee, rule.item_code)
        and _employment_month_allows(employee, rule, period_date)
    ]
    selected_rules = _select_employee_rules(employee, active_rules)
    for rule in selected_rules:
        income = fund_income if rule.item_code == "housing_fund" else social_income
        base_mode, fixed_base = _employee_base_override(employee, rule.item_code)
        base = _configured_base(rule, income, base_mode=base_mode, fixed_base=fixed_base)
        employee_amounts[rule.item_code] = _money(base * rule.employee_rate)
        employer_amounts[rule.item_code] = _money(base * rule.employer_rate)
    return ConfiguredStatutoryDeductionResult(
        employee_amounts=employee_amounts,
        employer_amounts=employer_amounts,
        employee_total=_money(sum(employee_amounts.values(), Decimal("0"))),
        employer_total=_money(sum(employer_amounts.values(), Decimal("0"))),
    )


def _select_employee_rules(employee: EmployeePayProfile, rules: list["StatutoryRuleInput"]):
    grouped: dict[str, list["StatutoryRuleInput"]] = {}
    for rule in rules:
        grouped.setdefault(rule.item_code, []).append(rule)
    selected: list["StatutoryRuleInput"] = []
    tier_overrides = {
        "pension": employee.pension_tier,
        "medical": employee.medical_tier,
        "work_injury": employee.work_injury_tier,
    }
    tier_overrides.update(dict(employee.statutory_tier_overrides))
    for item_code, item_rules in grouped.items():
        tier = tier_overrides.get(item_code)
        if tier is not None:
            matches = [rule for rule in item_rules if rule.tier_code == tier]
            if len(matches) != 1:
                raise ValueError(f"employee {item_code} tier is not configured: {tier}")
            selected.append(matches[0])
        elif len(item_rules) == 1:
            selected.append(item_rules[0])
        else:
            raise ValueError(f"employee {item_code} tier is required")
    return selected


def _item_enabled(employee: EmployeePayProfile, item_code: str) -> bool:
    if item_code == "housing_fund":
        enabled = employee.housing_fund_enabled
    else:
        enabled = employee.social_insurance_enabled
    return employee.statutory_enabled if enabled is None else enabled


def _employment_month_allows(employee, rule, period_date: date) -> bool:
    month = (period_date.year, period_date.month)
    if employee.hire_date and (employee.hire_date.year, employee.hire_date.month) == month:
        if rule.hire_month_rule == "never":
            return False
        if (
            rule.hire_month_rule == "cutoff_day"
            and employee.hire_date.day > rule.hire_cutoff_day
        ):
            return False
    if (
        employee.termination_date
        and (employee.termination_date.year, employee.termination_date.month) == month
    ):
        if rule.termination_month_rule == "never":
            return False
        if (
            rule.termination_month_rule == "cutoff_day"
            and employee.termination_date.day <= rule.termination_cutoff_day
        ):
            return False
    return True


def _employee_base_override(employee: EmployeePayProfile, item_code: str):
    if item_code == "housing_fund":
        mode, fixed_base = employee.fund_base_mode, employee.fund_fixed_base
    else:
        mode, fixed_base = employee.social_base_mode, employee.social_fixed_base
    if mode in (None, "公司默认"):
        return None, None
    return mode, fixed_base


def _configured_base(
    rule: "StatutoryRuleInput",
    income: Decimal,
    *,
    base_mode: str | None = None,
    fixed_base: Decimal | None = None,
) -> Decimal:
    mode = base_mode or rule.base_mode
    if mode == "薪资全额":
        base = income
    elif mode == "固定基数":
        configured_fixed_base = fixed_base if base_mode else rule.fixed_base
        if configured_fixed_base is None:
            raise ValueError(f"{rule.item_code} requires a fixed contribution base")
        if configured_fixed_base < 0:
            raise ValueError(f"{rule.item_code} fixed contribution base cannot be negative")
        base = configured_fixed_base
    else:
        raise ValueError(f"unsupported statutory base mode: {mode}")
    return min(rule.base_upper, max(rule.base_lower, base))


def calculate_statutory_deductions(
    employee: EmployeeStatutoryProfile,
    contribution_base: Decimal,
    policy: LocalStatutoryPolicy | None,
    period_date: date,
) -> StatutoryDeductionResult:
    _validate_policy(policy, period_date)
    if contribution_base < 0:
        raise ValueError("contribution base cannot be negative")
    pension = _tier_rule(policy.pension_tiers, employee.pension_tier, "pension")
    medical = _tier_rule(policy.medical_tiers, employee.medical_tier, "medical")
    work_injury = _tier_rule(policy.work_injury_tiers, employee.work_injury_tier, "work injury")
    rules = (pension, medical, policy.unemployment, work_injury, policy.maternity, policy.housing_fund)
    employee_total = sum((contribution_base * rule.employee_rate for rule in rules), Decimal("0"))
    employer_total = sum((contribution_base * rule.employer_rate for rule in rules), Decimal("0"))
    return StatutoryDeductionResult(_money(employee_total), _money(employer_total))


def _validate_policy(policy: LocalStatutoryPolicy | None, period_date: date) -> None:
    if policy is None or not policy.enabled:
        raise ValueError("statutory contribution policy is not configured")
    if not policy.region.strip() or policy.effective_from is None:
        raise ValueError("statutory contribution policy is not configured")
    if period_date < policy.effective_from or (
        policy.effective_to is not None and period_date > policy.effective_to
    ):
        raise ValueError("statutory contribution policy is not effective for this period")
    if not policy.pension_tiers or not policy.medical_tiers or not policy.work_injury_tiers:
        raise ValueError("statutory contribution policy is not configured")
    if policy.unemployment is None or policy.maternity is None or policy.housing_fund is None:
        raise ValueError("statutory contribution policy is not configured")
    for rule in (
        *policy.pension_tiers.values(),
        *policy.medical_tiers.values(),
        policy.unemployment,
        *policy.work_injury_tiers.values(),
        policy.maternity,
        policy.housing_fund,
    ):
        if rule.employee_rate < 0 or rule.employer_rate < 0:
            raise ValueError("statutory contribution rates cannot be negative")


def _tier_rule(
    rules: dict[str, ContributionRule], tier: str | None, name: str
) -> ContributionRule:
    if not tier or tier not in rules:
        raise ValueError(f"employee {name} tier is required")
    return rules[tier]


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)
