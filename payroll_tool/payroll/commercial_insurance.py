"""Commercial insurance calculation kept separate from statutory contributions."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from payroll_tool.payroll.engine import EmployeePayProfile


CENTS = Decimal("0.01")


@dataclass(frozen=True)
class CommercialInsurancePolicy:
    code: str
    name: str
    effective_from: date
    effective_to: date | None
    calculation: str
    amount: Decimal | None
    employee_share: Decimal
    employer_share: Decimal
    employee_rate: Decimal | None
    employer_rate: Decimal | None
    taxable: bool
    included_in_gross: bool
    deduction_mode: str
    employment_types: tuple[str, ...]


@dataclass(frozen=True)
class CommercialInsuranceResult:
    employee_deduction: Decimal
    employer_cost: Decimal
    taxable_addition: Decimal
    gross_addition: Decimal


def calculate_commercial_insurance(
    employee: "EmployeePayProfile",
    policies: tuple[CommercialInsurancePolicy, ...],
    *,
    base_income: Decimal,
    effective_date: date,
    employment_type_code: str,
) -> CommercialInsuranceResult:
    if base_income < 0:
        raise ValueError("commercial insurance base income cannot be negative")
    enabled = dict(employee.commercial_enabled_overrides)
    amount_overrides = dict(employee.commercial_amount_overrides)
    base_overrides = dict(employee.commercial_base_overrides)
    employee_total = employer_total = taxable_total = gross_total = Decimal("0")
    for policy in policies:
        if not enabled.get(policy.code, True):
            continue
        if employment_type_code not in policy.employment_types:
            continue
        if effective_date < policy.effective_from or (
            policy.effective_to is not None and effective_date > policy.effective_to
        ):
            continue
        employee_amount, employer_amount = _premium_amounts(
            policy,
            amount_override=amount_overrides.get(policy.code),
            base=base_overrides.get(policy.code, base_income),
        )
        total = employee_amount + employer_amount
        if policy.deduction_mode == "payroll_deduction":
            employee_cost = employee_amount
            employer_cost = employer_amount
        elif policy.deduction_mode in {"company_paid", "reimbursement"}:
            employee_cost = Decimal("0")
            employer_cost = total
        else:
            raise ValueError(f"unsupported commercial deduction mode: {policy.deduction_mode}")
        employee_total += employee_cost
        employer_total += employer_cost
        if policy.taxable:
            taxable_total += employer_cost
        if policy.included_in_gross:
            gross_total += employer_cost
    return CommercialInsuranceResult(
        employee_deduction=_money(employee_total),
        employer_cost=_money(employer_total),
        taxable_addition=_money(taxable_total),
        gross_addition=_money(gross_total),
    )


def _premium_amounts(policy, *, amount_override: Decimal | None, base: Decimal):
    if base < 0:
        raise ValueError(f"commercial insurance base cannot be negative: {policy.code}")
    if policy.calculation == "fixed_amount":
        amount = amount_override if amount_override is not None else policy.amount
        if amount is None or amount < 0:
            raise ValueError(f"commercial insurance amount is invalid: {policy.code}")
        return amount * policy.employee_share, amount * policy.employer_share
    if policy.calculation == "base_rate":
        if policy.employee_rate is None or policy.employer_rate is None:
            raise ValueError(f"commercial insurance rate is missing: {policy.code}")
        total = base * (policy.employee_rate + policy.employer_rate)
        return total * policy.employee_share, total * policy.employer_share
    raise ValueError(f"unsupported commercial insurance calculation: {policy.calculation}")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)
