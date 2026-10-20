from dataclasses import replace
from datetime import date
from decimal import Decimal
import unittest

from payroll_tool.config.schema import IncomeItemPolicy
from payroll_tool.config.policy_serialization import OvertimePolicy
from payroll_tool.payroll.engine import (
    AttendanceDay,
    EmployeePayProfile,
    calculate_payroll,
)
from payroll_tool.payroll.commercial_insurance import CommercialInsurancePolicy
from payroll_tool.importers.hr_workbook import CumulativeTaxInput, StatutoryRuleInput


INCOME_ITEMS = {
    "allowance": IncomeItemPolicy(True, False, False),
    "bonus": IncomeItemPolicy(True, False, False),
}


def _overtime_policy(
    *, cash_formula: str = "hourly_rate_multiplier",
    cash_rate: Decimal = Decimal("1"),
) -> OvertimePolicy:
    return OvertimePolicy(
        enabled=True,
        start_mode="after_normal_end",
        minimum_minutes=0,
        rounding_mode="actual_minutes",
        approval_required=True,
        cross_midnight_allowed=True,
        cash_enabled=True,
        cash_formula=cash_formula,
        cash_rate=cash_rate,
        day_rates={
            "workday": Decimal("1.5"),
            "rest_day": Decimal("2"),
            "holiday": Decimal("3"),
        },
        comp_time_enabled=False,
        comp_time_ratio=None,
    )


class PayrollEngineTests(unittest.TestCase):
    def test_monthly_employee_receives_taxable_cash_overtime(self):
        employee = EmployeePayProfile(
            "S1", "full_time", monthly_salary=Decimal("21750")
        )
        day = AttendanceDay(
            date(2026, 8, 1), Decimal("8"), workday_type="rest_day",
            overtime_minutes=Decimal("120"),
        )

        result = calculate_payroll(
            employee, [day], income_items=INCOME_ITEMS,
            overtime_policy=_overtime_policy(),
        )

        self.assertEqual(result.overtime_pay, Decimal("500.00"))
        self.assertEqual(result.gross_pay, Decimal("1500.00"))
        self.assertEqual(result.taxable_income, Decimal("1500.00"))
        self.assertEqual(result.social_base_income, Decimal("1000.00"))
        self.assertEqual(result.net_pay, Decimal("1500.00"))
        self.assertEqual(result.total_employer_cost, Decimal("1500.00"))

    def test_intern_fixed_hourly_overtime_uses_configured_cash_rate(self):
        employee = EmployeePayProfile(
            "I1", "intern", intern_daily_rate=Decimal("300"),
            intern_hourly_rate=Decimal("30"),
        )
        overtime = _overtime_policy(
            cash_formula="fixed_hourly_rate", cash_rate=Decimal("50")
        )
        day = AttendanceDay(
            date(2026, 8, 1), Decimal("8"), workday_type="rest_day",
            overtime_minutes=Decimal("120"),
        )

        result = calculate_payroll(
            employee, [day], income_items=INCOME_ITEMS,
            overtime_policy=overtime,
        )

        self.assertEqual(result.base_pay, Decimal("300.00"))
        self.assertEqual(result.overtime_pay, Decimal("200.00"))

    def test_intern_multiplier_overtime_uses_intern_hourly_rate(self):
        employee = EmployeePayProfile(
            "I2", "intern", intern_daily_rate=Decimal("300"),
            intern_hourly_rate=Decimal("30"),
        )
        day = AttendanceDay(
            date(2026, 8, 1), Decimal("8"), workday_type="rest_day",
            overtime_minutes=Decimal("120"),
        )

        result = calculate_payroll(
            employee, [day], income_items=INCOME_ITEMS,
            overtime_policy=_overtime_policy(),
        )

        self.assertEqual(result.overtime_pay, Decimal("120.00"))

    def test_disabled_cash_ignores_overtime_without_workday_type(self):
        employee = EmployeePayProfile(
            "S2", "full_time", monthly_salary=Decimal("21750")
        )
        day = AttendanceDay(
            date(2026, 8, 1), Decimal("8"), overtime_minutes=Decimal("60")
        )
        overtime = replace(
            _overtime_policy(), cash_enabled=False, cash_formula=None,
            cash_rate=None, day_rates={},
        )

        result = calculate_payroll(
            employee, [day], income_items=INCOME_ITEMS,
            overtime_policy=overtime,
        )

        self.assertEqual(result.overtime_pay, Decimal("0.00"))
        self.assertEqual(result.gross_pay, Decimal("1000.00"))
        self.assertEqual(result.taxable_income, Decimal("1000.00"))
        self.assertEqual(result.total_employer_cost, Decimal("1000.00"))

    def test_overtime_component_and_gross_total_reconcile_to_cents(self):
        employee = EmployeePayProfile(
            "S3", "full_time", monthly_salary=Decimal("21.837")
        )
        day = AttendanceDay(
            date(2026, 8, 1), Decimal("8"), workday_type="workday",
            overtime_minutes=Decimal("1"),
        )

        result = calculate_payroll(
            employee, [day], income_items=INCOME_ITEMS,
            overtime_policy=_overtime_policy(),
        )

        self.assertEqual(
            result.gross_pay,
            result.base_pay + result.overtime_pay,
        )

    def test_negative_overtime_minutes_are_rejected_when_cash_is_disabled(self):
        employee = EmployeePayProfile(
            "S4", "full_time", monthly_salary=Decimal("21750")
        )
        day = AttendanceDay(
            date(2026, 8, 1), Decimal("8"), overtime_minutes=Decimal("-1")
        )
        overtime = replace(
            _overtime_policy(), cash_enabled=False, cash_formula=None,
            cash_rate=None, day_rates={},
        )

        with self.assertRaisesRegex(ValueError, "overtime minutes"):
            calculate_payroll(
                employee, [day], income_items=INCOME_ITEMS,
                overtime_policy=overtime,
            )

    def test_converted_employee_uses_rate_for_each_overtime_date(self):
        employee = EmployeePayProfile(
            "C1", "converted", monthly_salary=Decimal("21750"),
            intern_daily_rate=Decimal("300"), intern_hourly_rate=Decimal("30"),
            conversion_date=date(2026, 8, 16),
        )
        days = [
            AttendanceDay(
                date(2026, 8, 15), Decimal("8"), workday_type="workday",
                overtime_minutes=Decimal("60"),
            ),
            AttendanceDay(
                date(2026, 8, 16), Decimal("8"), workday_type="workday",
                overtime_minutes=Decimal("60"),
            ),
        ]

        result = calculate_payroll(
            employee, days, income_items=INCOME_ITEMS,
            overtime_policy=_overtime_policy(),
        )

        self.assertEqual(result.overtime_pay, Decimal("232.50"))

    def test_cash_overtime_requires_workday_type_for_recognized_minutes(self):
        employee = EmployeePayProfile(
            "S1", "full_time", monthly_salary=Decimal("21750")
        )
        day = AttendanceDay(
            date(2026, 8, 1), Decimal("8"), overtime_minutes=Decimal("60")
        )

        with self.assertRaisesRegex(ValueError, "workday type"):
            calculate_payroll(
                employee, [day], income_items=INCOME_ITEMS,
                overtime_policy=_overtime_policy(),
            )

    def test_commercial_insurance_is_separate_from_statutory_deductions(self):
        employee = EmployeePayProfile(
            "S1", "full_time", monthly_salary=Decimal("21750")
        )
        commercial = CommercialInsurancePolicy(
            code="accident", name="团体意外险",
            effective_from=date(2026, 1, 1), effective_to=None,
            calculation="fixed_amount", amount=Decimal("100"),
            employee_share=Decimal("0.2"), employer_share=Decimal("0.8"),
            employee_rate=None, employer_rate=None, taxable=False,
            included_in_gross=False, deduction_mode="payroll_deduction",
            employment_types=("full_time",),
        )

        result = calculate_payroll(
            employee, [AttendanceDay(date(2026, 8, 1), Decimal("8"))],
            income_items=INCOME_ITEMS, period_date=date(2026, 8, 1),
            commercial_insurance=(commercial,),
            commercial_employment_type="full_time",
        )

        self.assertEqual(result.employee_commercial_insurance_deduction, Decimal("20.00"))
        self.assertEqual(result.employer_commercial_insurance_cost, Decimal("80.00"))
        self.assertEqual(result.employee_statutory_deduction, Decimal("0.00"))
        self.assertEqual(result.net_pay, Decimal("980.00"))
        self.assertEqual(result.total_employer_cost, Decimal("1080.00"))

    def test_reimbursed_commercial_insurance_in_gross_is_not_counted_twice(self):
        employee = EmployeePayProfile(
            "S1", "full_time", monthly_salary=Decimal("21750")
        )
        commercial = CommercialInsurancePolicy(
            code="medical_claim", name="医疗报销",
            effective_from=date(2026, 1, 1), effective_to=None,
            calculation="fixed_amount", amount=Decimal("100"),
            employee_share=Decimal("0"), employer_share=Decimal("1"),
            employee_rate=None, employer_rate=None, taxable=False,
            included_in_gross=True, deduction_mode="reimbursement",
            employment_types=("full_time",),
        )

        result = calculate_payroll(
            employee, [AttendanceDay(date(2026, 8, 1), Decimal("8"))],
            income_items=INCOME_ITEMS, period_date=date(2026, 8, 1),
            commercial_insurance=(commercial,),
            commercial_employment_type="full_time",
        )

        self.assertEqual(result.gross_pay, Decimal("1100.00"))
        self.assertEqual(result.employer_commercial_insurance_cost, Decimal("100.00"))
        self.assertEqual(result.total_employer_cost, Decimal("1100.00"))
    def test_current_special_deductions_reduce_cumulative_tax(self):
        employee = EmployeePayProfile(
            "S1", "full_time", monthly_salary=Decimal("21750")
        )
        tax = CumulativeTaxInput(2026, Decimal("0"), Decimal("0"), Decimal("0"))

        result = calculate_payroll(
            employee,
            [AttendanceDay(date(2026, 1, 2), Decimal("8")) for _ in range(21)],
            income_items=INCOME_ITEMS,
            period_date=date(2026, 1, 1),
            cumulative_tax=tax,
            current_special_deductions=Decimal("1000"),
        )

        self.assertEqual(result.individual_income_tax, Decimal("450.00"))
    def test_cumulative_tax_is_deducted_from_net_pay(self):
        employee = EmployeePayProfile("synthetic-tax", "full_time", monthly_salary=Decimal("21750"))

        result = calculate_payroll(
            employee, [AttendanceDay(date(2026, 1, 3), Decimal("8")) for _ in range(21)],
            income_items=INCOME_ITEMS, period_date=date(2026, 1, 1),
            cumulative_tax=CumulativeTaxInput(2026, Decimal("0"), Decimal("0"), Decimal("0")),
        )

        self.assertEqual(result.individual_income_tax, Decimal("480.00"))
        self.assertEqual(result.net_pay, Decimal("20520.00"))

    def test_paid_ratio_leave_adjusts_the_daily_pay(self):
        employee = EmployeePayProfile("synthetic-sick", "full_time", monthly_salary=Decimal("21750"))

        result = calculate_payroll(
            employee,
            [AttendanceDay(date(2026, 1, 3), Decimal("8"), (("病假", Decimal("8"), Decimal("0.7")),))],
            income_items=INCOME_ITEMS,
        )

        self.assertEqual(result.base_pay, Decimal("700.00"))
        self.assertEqual(result.attendance_deduction, Decimal("0.00"))
        self.assertEqual(result.sick_leave_deduction, Decimal("300.00"))

    def test_perfect_attendance_award_is_added_when_employee_is_eligible(self):
        employee = EmployeePayProfile("synthetic-perfect", "full_time", monthly_salary=Decimal("21750"))

        result = calculate_payroll(
            employee,
            [AttendanceDay(date(2026, 1, 3), Decimal("8"))],
            income_items=INCOME_ITEMS,
            perfect_attendance_award=Decimal("200"),
            perfect_attendance_eligible=True,
        )

        self.assertEqual(result.perfect_attendance_award, Decimal("200.00"))
        self.assertEqual(result.gross_pay, Decimal("1200.00"))

    def test_employee_perfect_attendance_override_can_cancel_company_award(self):
        employee = EmployeePayProfile(
            "synthetic-no-perfect", "full_time", monthly_salary=Decimal("21750"),
            perfect_attendance_override=Decimal("0"),
        )

        result = calculate_payroll(
            employee,
            [AttendanceDay(date(2026, 1, 3), Decimal("8"))],
            income_items=INCOME_ITEMS,
            perfect_attendance_award=Decimal("200"),
            perfect_attendance_eligible=True,
        )

        self.assertEqual(result.perfect_attendance_award, Decimal("0.00"))
    def test_statutory_deductions_change_net_pay_and_employer_cost(self):
        employee = EmployeePayProfile(
            employee_id="synthetic-statutory", employment_type="full_time",
            monthly_salary=Decimal("21750"), statutory_enabled=True,
        )
        rules = (
            StatutoryRuleInput("pension", "standard", "Synthetic City", date(2026, 1, 1), None, "薪资全额", Decimal("0"), Decimal("50000"), None, Decimal("0.08"), Decimal("0.16")),
        )

        result = calculate_payroll(
            employee, [AttendanceDay(date(2026, 8, 3), Decimal("8")) for _ in range(21)],
            income_items=INCOME_ITEMS, statutory_rules=rules, period_date=date(2026, 8, 1),
        )

        self.assertEqual(result.gross_pay, Decimal("21000.00"))
        self.assertEqual(result.employee_statutory_deduction, Decimal("1680.00"))
        self.assertEqual(result.net_pay, Decimal("19320.00"))
        self.assertEqual(result.total_employer_cost, Decimal("24360.00"))
    def test_full_time_partial_period_is_prorated_by_effective_days(self):
        employee = EmployeePayProfile(
            employee_id="synthetic-001",
            employment_type="full_time",
            monthly_salary=Decimal("21750"),
        )

        result = calculate_payroll(
            employee,
            [AttendanceDay(date(2026, 8, 3), Decimal("8")) for _ in range(10)],
            income_items=INCOME_ITEMS,
        )

        self.assertEqual(result.base_pay, Decimal("10000.00"))

    def test_hr_daily_hours_and_monthly_pay_days_drive_full_day_pay(self):
        employee = EmployeePayProfile(
            employee_id="configured-hours",
            employment_type="full_time",
            monthly_salary=Decimal("20000"),
        )

        result = calculate_payroll(
            employee,
            [AttendanceDay(date(2026, 8, 3), Decimal("7.25"))],
            income_items=INCOME_ITEMS,
            daily_required_hours=Decimal("7.25"),
            monthly_pay_days=Decimal("20"),
        )

        self.assertEqual(result.base_pay, Decimal("1000.00"))
        self.assertEqual(result.attendance_deduction, Decimal("0.00"))

    def test_intern_uses_full_day_rate_and_partial_hour_rate(self):
        employee = EmployeePayProfile(
            employee_id="synthetic-002",
            employment_type="intern",
            intern_daily_rate=Decimal("300"),
            intern_hourly_rate=Decimal("30"),
        )

        result = calculate_payroll(
            employee,
            [
                AttendanceDay(date(2026, 8, 3), Decimal("8")),
                AttendanceDay(date(2026, 8, 4), Decimal("6.5")),
            ],
            income_items=INCOME_ITEMS,
        )

        self.assertEqual(result.base_pay, Decimal("495.00"))

    def test_conversion_month_uses_intern_rate_before_conversion_and_monthly_after(self):
        employee = EmployeePayProfile(
            employee_id="synthetic-003",
            employment_type="converted",
            monthly_salary=Decimal("21750"),
            intern_daily_rate=Decimal("300"),
            intern_hourly_rate=Decimal("30"),
            conversion_date=date(2026, 8, 16),
        )

        result = calculate_payroll(
            employee,
            [
                AttendanceDay(date(2026, 8, 15), Decimal("8")),
                AttendanceDay(date(2026, 8, 16), Decimal("8")),
            ],
            income_items=INCOME_ITEMS,
        )

        self.assertEqual(result.base_pay, Decimal("1300.00"))

    def test_taxable_allowance_and_bonus_are_in_gross_but_not_social_base(self):
        employee = EmployeePayProfile(
            employee_id="synthetic-004",
            employment_type="full_time",
            monthly_salary=Decimal("21750"),
            allowances=Decimal("2000"),
            bonuses=Decimal("3000"),
        )

        result = calculate_payroll(
            employee,
            [AttendanceDay(date(2026, 8, 3), Decimal("8")) for _ in range(21)],
            income_items=INCOME_ITEMS,
        )

        self.assertEqual(result.allowance, Decimal("2000.00"))
        self.assertEqual(result.bonus, Decimal("3000.00"))
        self.assertEqual(result.taxable_income, Decimal("26000.00"))
        self.assertEqual(result.social_base_income, Decimal("21000.00"))


if __name__ == "__main__":
    unittest.main()
