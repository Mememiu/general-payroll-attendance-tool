from datetime import date
from decimal import Decimal
import unittest

from payroll_tool.payroll.commercial_insurance import (
    CommercialInsurancePolicy,
    calculate_commercial_insurance,
)
from payroll_tool.payroll.engine import EmployeePayProfile


class CommercialInsuranceTests(unittest.TestCase):
    def test_fixed_premium_is_split_between_employee_and_employer(self):
        employee = EmployeePayProfile("S1", "full_time")
        policy = CommercialInsurancePolicy(
            code="accident", name="团体意外险",
            effective_from=date(2026, 1, 1), effective_to=None,
            calculation="fixed_amount", amount=Decimal("100"),
            employee_share=Decimal("0.2"), employer_share=Decimal("0.8"),
            employee_rate=None, employer_rate=None,
            taxable=False, included_in_gross=False,
            deduction_mode="payroll_deduction",
            employment_types=("full_time",),
        )

        result = calculate_commercial_insurance(
            employee, (policy,), base_income=Decimal("10000"),
            effective_date=date(2026, 8, 1), employment_type_code="full_time",
        )

        self.assertEqual(result.employee_deduction, Decimal("20.00"))
        self.assertEqual(result.employer_cost, Decimal("80.00"))

    def test_employee_amount_and_enabled_overrides_are_applied_by_code(self):
        employee = EmployeePayProfile(
            "S1", "full_time",
            commercial_enabled_overrides=(("accident", True), ("medical_plus", False)),
            commercial_amount_overrides=(("accident", Decimal("150")),),
        )
        policies = (
            CommercialInsurancePolicy(
                code="accident", name="团体意外险",
                effective_from=date(2026, 1, 1), effective_to=None,
                calculation="fixed_amount", amount=Decimal("100"),
                employee_share=Decimal("0"), employer_share=Decimal("1"),
                employee_rate=None, employer_rate=None, taxable=False,
                included_in_gross=False, deduction_mode="company_paid",
                employment_types=("full_time",),
            ),
            CommercialInsurancePolicy(
                code="medical_plus", name="补充医疗",
                effective_from=date(2026, 1, 1), effective_to=None,
                calculation="fixed_amount", amount=Decimal("200"),
                employee_share=Decimal("0"), employer_share=Decimal("1"),
                employee_rate=None, employer_rate=None, taxable=False,
                included_in_gross=False, deduction_mode="company_paid",
                employment_types=("full_time",),
            ),
        )

        result = calculate_commercial_insurance(
            employee, policies, base_income=Decimal("10000"),
            effective_date=date(2026, 8, 1), employment_type_code="full_time",
        )

        self.assertEqual(result.employer_cost, Decimal("150.00"))

    def test_base_rate_total_is_split_by_hr_shares(self):
        employee = EmployeePayProfile("S1", "full_time")
        policy = CommercialInsurancePolicy(
            code="medical_plus", name="补充医疗",
            effective_from=date(2026, 1, 1), effective_to=None,
            calculation="base_rate", amount=None,
            employee_share=Decimal("0.25"), employer_share=Decimal("0.75"),
            employee_rate=Decimal("0.01"), employer_rate=Decimal("0.02"),
            taxable=False, included_in_gross=False,
            deduction_mode="payroll_deduction", employment_types=("full_time",),
        )

        result = calculate_commercial_insurance(
            employee, (policy,), base_income=Decimal("10000"),
            effective_date=date(2026, 8, 1), employment_type_code="full_time",
        )

        self.assertEqual(result.employee_deduction, Decimal("75.00"))
        self.assertEqual(result.employer_cost, Decimal("225.00"))


if __name__ == "__main__":
    unittest.main()
