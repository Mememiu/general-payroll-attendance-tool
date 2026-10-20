"""Pure payroll calculation without statutory deductions."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from payroll_tool.config.schema import IncomeItemPolicy

if TYPE_CHECKING:
    from payroll_tool.config.policy_serialization import OvertimePolicy
    from payroll_tool.importers.hr_workbook import CumulativeTaxInput, StatutoryRuleInput
    from payroll_tool.payroll.commercial_insurance import CommercialInsurancePolicy


AVERAGE_MONTHLY_PAY_DAYS = Decimal("21.75")
FULL_DAY_HOURS = Decimal("8")
CENTS = Decimal("0.01")


@dataclass(frozen=True)
class AttendanceDay:
    work_date: date
    effective_hours: Decimal
    leave_adjustments: tuple[tuple[str, Decimal, Decimal], ...] = ()
    workday_type: str | None = None
    overtime_minutes: Decimal = Decimal("0")


@dataclass(frozen=True)
class EmployeePayProfile:
    employee_id: str
    employment_type: str
    monthly_salary: Decimal | None = None
    intern_daily_rate: Decimal | None = None
    intern_hourly_rate: Decimal | None = None
    conversion_date: date | None = None
    allowances: Decimal = Decimal("0")
    bonuses: Decimal = Decimal("0")
    perfect_attendance_override: Decimal | None = None
    employee_name: str = ""
    hire_date: date | None = None
    termination_date: date | None = None
    statutory_enabled: bool = False
    social_insurance_enabled: bool | None = None
    housing_fund_enabled: bool | None = None
    statutory_tier_overrides: tuple[tuple[str, str], ...] = ()
    tax_year: int | None = None
    prior_taxable_income: Decimal = Decimal("0")
    prior_special_deductions: Decimal = Decimal("0")
    current_special_deductions: Decimal = Decimal("0")
    prior_withheld_tax: Decimal = Decimal("0")
    commercial_enabled_overrides: tuple[tuple[str, bool], ...] = ()
    commercial_amount_overrides: tuple[tuple[str, Decimal], ...] = ()
    commercial_base_overrides: tuple[tuple[str, Decimal], ...] = ()
    pension_tier: str | None = None
    medical_tier: str | None = None
    work_injury_tier: str | None = None
    social_base_mode: str | None = None
    social_fixed_base: Decimal | None = None
    fund_base_mode: str | None = None
    fund_fixed_base: Decimal | None = None


@dataclass(frozen=True)
class PayrollResult:
    base_pay: Decimal
    allowance: Decimal
    bonus: Decimal
    perfect_attendance_award: Decimal
    attendance_deduction: Decimal
    sick_leave_deduction: Decimal
    overtime_pay: Decimal
    taxable_income: Decimal
    social_base_income: Decimal
    housing_fund_base_income: Decimal
    gross_pay: Decimal
    employee_statutory_deduction: Decimal
    employer_statutory_cost: Decimal
    employee_commercial_insurance_deduction: Decimal
    employer_commercial_insurance_cost: Decimal
    taxable_income_after_statutory: Decimal
    individual_income_tax: Decimal
    tax_carry_forward_balance: Decimal
    net_pay: Decimal
    total_employer_cost: Decimal


def calculate_payroll(
    employee: EmployeePayProfile,
    attendance_days: list[AttendanceDay],
    *,
    income_items: dict[str, IncomeItemPolicy],
    statutory_rules: tuple["StatutoryRuleInput", ...] = (),
    period_date: date | None = None,
    cumulative_tax: "CumulativeTaxInput | None" = None,
    perfect_attendance_award: Decimal = Decimal("0"),
    perfect_attendance_eligible: bool = False,
    daily_required_hours: Decimal = FULL_DAY_HOURS,
    monthly_pay_days: Decimal = AVERAGE_MONTHLY_PAY_DAYS,
    tax_monthly_exemption: Decimal = Decimal("5000"),
    tax_brackets: tuple[tuple[Decimal, Decimal, Decimal], ...] | None = None,
    negative_tax_mode: str = "zero",
    statutory_effective_date: date | None = None,
    current_special_deductions: Decimal = Decimal("0"),
    commercial_insurance: tuple["CommercialInsurancePolicy", ...] = (),
    commercial_employment_type: str | None = None,
    overtime_policy: "OvertimePolicy | None" = None,
) -> PayrollResult:
    _validate_employee(employee)
    if daily_required_hours <= 0 or monthly_pay_days <= 0:
        raise ValueError("configured work hours and monthly pay days must be positive")
    base_pay = Decimal("0")
    attendance_deduction = Decimal("0")
    sick_leave_deduction = Decimal("0")
    for day in attendance_days:
        base_pay += _daily_pay(employee, day, daily_required_hours, monthly_pay_days)
        hourly_rate = _hourly_pay(employee, day.work_date, daily_required_hours, monthly_pay_days)
        attendance_deduction += hourly_rate * max(Decimal("0"), daily_required_hours - day.effective_hours)
        for kind, hours, paid_ratio in day.leave_adjustments:
            reduction = hourly_rate * hours * (Decimal("1") - paid_ratio)
            if kind == "病假":
                sick_leave_deduction += reduction
            else:
                attendance_deduction += reduction
    applied_perfect_award = (
        employee.perfect_attendance_override
        if employee.perfect_attendance_override is not None
        else perfect_attendance_award
    ) if perfect_attendance_eligible else Decimal("0")
    overtime_pay = _money(_overtime_pay(
        employee, attendance_days, overtime_policy,
        daily_required_hours, monthly_pay_days,
    ))
    income_amounts = {
        "allowance": employee.allowances,
        "bonus": employee.bonuses,
    }
    taxable_income = base_pay + applied_perfect_award + overtime_pay
    social_base_income = base_pay
    housing_fund_base_income = base_pay
    for name, amount in income_amounts.items():
        policy = income_items[name]
        if policy.taxable:
            taxable_income += amount
        if policy.included_in_social_base:
            social_base_income += amount
        if policy.included_in_fund_base:
            housing_fund_base_income += amount
    from payroll_tool.payroll.commercial_insurance import calculate_commercial_insurance

    commercial_date = statutory_effective_date or period_date
    if commercial_insurance and commercial_date is None:
        raise ValueError("commercial insurance calculation requires period_date")
    commercial = calculate_commercial_insurance(
        employee,
        commercial_insurance,
        base_income=base_pay,
        effective_date=commercial_date or date.min,
        employment_type_code=commercial_employment_type or employee.employment_type,
    )
    taxable_income += commercial.taxable_addition
    gross_pay = (
        base_pay + employee.allowances + employee.bonuses
        + applied_perfect_award + overtime_pay + commercial.gross_addition
    )
    if employee.statutory_enabled:
        if period_date is None:
            raise ValueError("statutory calculation requires period_date")
        from payroll_tool.statutory.social_insurance import calculate_configured_statutory_deductions

        statutory = calculate_configured_statutory_deductions(
            employee,
            statutory_rules,
            social_income=social_base_income,
            fund_income=housing_fund_base_income,
            period_date=period_date,
            effective_date=statutory_effective_date,
        )
    else:
        statutory_employee = statutory_employer = Decimal("0")
        statutory = None
    employee_deduction = statutory.employee_total if statutory else statutory_employee
    employer_cost = statutory.employer_total if statutory else statutory_employer
    taxable_after_statutory = max(Decimal("0"), taxable_income - employee_deduction)
    individual_income_tax = Decimal("0")
    tax_carry_forward_balance = Decimal("0")
    if cumulative_tax is not None:
        if period_date is None or cumulative_tax.tax_year != period_date.year:
            raise ValueError("cumulative tax year does not match payroll period")
        from payroll_tool.statutory.cn_tax import calculate_cn_cumulative_withholding

        tax_result = calculate_cn_cumulative_withholding(
            current_taxable_income=taxable_after_statutory,
            prior_taxable_income=cumulative_tax.prior_taxable_income,
            months_in_year=period_date.month,
            prior_withheld=cumulative_tax.prior_withheld_tax,
            prior_special_deductions=cumulative_tax.prior_special_deductions,
            current_special_deductions=current_special_deductions,
            monthly_exemption=tax_monthly_exemption,
            brackets=tax_brackets,
            negative_tax_mode=negative_tax_mode,
        )
        individual_income_tax = tax_result.current_withholding
        tax_carry_forward_balance = tax_result.carry_forward_balance
    net_pay = (
        gross_pay - employee_deduction
        - commercial.employee_deduction - individual_income_tax
    )
    return PayrollResult(
        base_pay=_money(base_pay),
        allowance=_money(employee.allowances),
        bonus=_money(employee.bonuses),
        perfect_attendance_award=_money(applied_perfect_award),
        attendance_deduction=_money(attendance_deduction),
        sick_leave_deduction=_money(sick_leave_deduction),
        overtime_pay=overtime_pay,
        taxable_income=_money(taxable_income),
        social_base_income=_money(social_base_income),
        housing_fund_base_income=_money(housing_fund_base_income),
        gross_pay=_money(gross_pay),
        employee_statutory_deduction=_money(employee_deduction),
        employer_statutory_cost=_money(employer_cost),
        employee_commercial_insurance_deduction=_money(commercial.employee_deduction),
        employer_commercial_insurance_cost=_money(commercial.employer_cost),
        taxable_income_after_statutory=_money(taxable_after_statutory),
        individual_income_tax=_money(individual_income_tax),
        tax_carry_forward_balance=_money(tax_carry_forward_balance),
        net_pay=_money(net_pay),
        total_employer_cost=_money(
            gross_pay + employer_cost
            + max(Decimal("0"), commercial.employer_cost - commercial.gross_addition)
        ),
    )


def _daily_pay(employee: EmployeePayProfile, day: AttendanceDay, daily_hours: Decimal, monthly_days: Decimal) -> Decimal:
    if day.effective_hours < 0 or day.effective_hours > daily_hours:
        raise ValueError("effective attendance hours exceed configured daily hours")
    if employee.employment_type == "intern":
        pay = _intern_pay(employee, day.effective_hours, daily_hours)
    elif employee.employment_type == "full_time":
        pay = _monthly_pay(employee, day.effective_hours, daily_hours, monthly_days)
    elif employee.employment_type == "converted":
        if employee.conversion_date is None:
            raise ValueError("converted employee requires conversion_date")
        if day.work_date < employee.conversion_date:
            pay = _intern_pay(employee, day.effective_hours, daily_hours)
        else:
            pay = _monthly_pay(employee, day.effective_hours, daily_hours, monthly_days)
    else:
        raise ValueError("employment_type must be full_time, intern, or converted")
    return max(Decimal("0"), pay - _leave_pay_reduction(employee, day, daily_hours, monthly_days))


def _overtime_pay(
    employee: EmployeePayProfile,
    attendance_days: list[AttendanceDay],
    policy: "OvertimePolicy | None",
    daily_hours: Decimal,
    monthly_days: Decimal,
) -> Decimal:
    if any(day.overtime_minutes < 0 for day in attendance_days):
        raise ValueError("overtime minutes cannot be negative")
    if policy is None or not policy.enabled or not policy.cash_enabled:
        return Decimal("0")
    if policy.cash_formula not in {"hourly_rate_multiplier", "fixed_hourly_rate"}:
        raise ValueError("unsupported overtime cash formula")
    if policy.cash_rate is None or policy.cash_rate <= 0:
        raise ValueError("overtime cash rate must be positive")
    total = Decimal("0")
    for day in attendance_days:
        if not day.overtime_minutes:
            continue
        if day.workday_type not in policy.day_rates:
            raise ValueError("recognized cash overtime requires a valid workday type")
        hours = day.overtime_minutes / Decimal("60")
        day_rate = policy.day_rates[day.workday_type]
        if policy.cash_formula == "hourly_rate_multiplier":
            hourly_rate = _hourly_pay(
                employee, day.work_date, daily_hours, monthly_days
            )
            total += hours * hourly_rate * policy.cash_rate * day_rate
        else:
            total += hours * policy.cash_rate * day_rate
    return total


def _leave_pay_reduction(employee: EmployeePayProfile, day: AttendanceDay, daily_hours: Decimal, monthly_days: Decimal) -> Decimal:
    if not day.leave_adjustments:
        return Decimal("0")
    hourly_rate = _hourly_pay(employee, day.work_date, daily_hours, monthly_days)
    reduction = Decimal("0")
    for _, hours, paid_ratio in day.leave_adjustments:
        if hours < 0 or paid_ratio < 0 or paid_ratio > 1:
            raise ValueError("leave adjustment must contain non-negative hours and a ratio from 0 to 1")
        reduction += hourly_rate * hours * (Decimal("1") - paid_ratio)
    return reduction


def _hourly_pay(employee: EmployeePayProfile, work_date: date, daily_hours: Decimal, monthly_days: Decimal) -> Decimal:
    if employee.employment_type == "intern":
        _require_amount(employee.intern_hourly_rate, "intern_hourly_rate")
        return employee.intern_hourly_rate
    if employee.employment_type == "converted" and employee.conversion_date is not None and work_date < employee.conversion_date:
        _require_amount(employee.intern_hourly_rate, "intern_hourly_rate")
        return employee.intern_hourly_rate
    _require_amount(employee.monthly_salary, "monthly_salary")
    return employee.monthly_salary / monthly_days / daily_hours


def _intern_pay(employee: EmployeePayProfile, hours: Decimal, daily_hours: Decimal) -> Decimal:
    _require_amount(employee.intern_daily_rate, "intern_daily_rate")
    _require_amount(employee.intern_hourly_rate, "intern_hourly_rate")
    if hours == daily_hours:
        return employee.intern_daily_rate
    return employee.intern_hourly_rate * hours


def _monthly_pay(employee: EmployeePayProfile, hours: Decimal, daily_hours: Decimal, monthly_days: Decimal) -> Decimal:
    _require_amount(employee.monthly_salary, "monthly_salary")
    return employee.monthly_salary / monthly_days * hours / daily_hours


def _validate_employee(employee: EmployeePayProfile) -> None:
    if not employee.employee_id.strip():
        raise ValueError("employee_id is required")
    if employee.allowances < 0 or employee.bonuses < 0:
        raise ValueError("allowances and bonuses cannot be negative")


def _require_amount(value: Decimal | None, name: str) -> None:
    if value is None or value < 0:
        raise ValueError(f"{name} must be a non-negative amount")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)
