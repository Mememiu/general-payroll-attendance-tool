from datetime import date
from decimal import Decimal
import unittest

from payroll_tool.statutory.social_insurance import (
    ContributionRule,
    EmployeeStatutoryProfile,
    LocalStatutoryPolicy,
    applicable_statutory_tiers,
    calculate_statutory_deductions,
    calculate_configured_statutory_deductions,
)
from payroll_tool.importers.hr_workbook import StatutoryRuleInput
from payroll_tool.payroll.engine import EmployeePayProfile


class SocialInsurancePolicyTests(unittest.TestCase):
    def test_generic_tier_override_supports_any_statutory_item(self):
        employee = EmployeePayProfile(
            employee_id="S1", employment_type="full_time",
            monthly_salary=Decimal("10000"), statutory_enabled=True,
            statutory_tier_overrides=(("unemployment", "city_b"),),
        )
        rules = (
            StatutoryRuleInput("unemployment", "city_a", "X", date(2026, 1, 1), None, "固定基数", Decimal("0"), Decimal("20000"), Decimal("5000"), Decimal("0.01"), Decimal("0.02")),
            StatutoryRuleInput("unemployment", "city_b", "X", date(2026, 1, 1), None, "固定基数", Decimal("0"), Decimal("20000"), Decimal("5000"), Decimal("0.02"), Decimal("0.03")),
        )

        result = calculate_configured_statutory_deductions(
            employee, rules, social_income=Decimal("10000"),
            fund_income=Decimal("10000"), period_date=date(2026, 8, 1),
        )

        self.assertEqual(result.employee_amounts["unemployment"], Decimal("100.00"))

    def test_housing_fund_can_be_disabled_without_disabling_social_insurance(self):
        employee = EmployeePayProfile(
            employee_id="S1", employment_type="full_time",
            monthly_salary=Decimal("10000"), statutory_enabled=True,
            social_insurance_enabled=True, housing_fund_enabled=False,
        )
        rules = (
            StatutoryRuleInput("pension", "standard", "X", date(2026, 1, 1), None, "固定基数", Decimal("0"), Decimal("20000"), Decimal("5000"), Decimal("0.08"), Decimal("0.16")),
            StatutoryRuleInput("housing_fund", "standard", "X", date(2026, 1, 1), None, "固定基数", Decimal("0"), Decimal("20000"), Decimal("5000"), Decimal("0.05"), Decimal("0.05")),
        )

        result = calculate_configured_statutory_deductions(
            employee, rules, social_income=Decimal("10000"),
            fund_income=Decimal("10000"), period_date=date(2026, 8, 1),
        )

        self.assertEqual(set(result.employee_amounts), {"pension"})

    def test_hire_and_termination_cutoff_rules_control_contribution_month(self):
        employee = EmployeePayProfile(
            employee_id="S1", employment_type="full_time",
            monthly_salary=Decimal("10000"), statutory_enabled=True,
            hire_date=date(2026, 8, 16), termination_date=None,
        )
        rule = StatutoryRuleInput(
            "pension", "standard", "X", date(2026, 1, 1), None,
            "固定基数", Decimal("0"), Decimal("20000"), Decimal("5000"),
            Decimal("0.08"), Decimal("0.16"), (), "cutoff_day", "cutoff_day", 15, 15,
        )

        result = calculate_configured_statutory_deductions(
            employee, (rule,), social_income=Decimal("10000"),
            fund_income=Decimal("10000"), period_date=date(2026, 8, 1),
        )

        self.assertEqual(result.employee_total, Decimal("0.00"))
        self.assertEqual(
            applicable_statutory_tiers(
                employee, (rule,), period_date=date(2026, 8, 1)
            ),
            {},
        )

    def test_same_month_hire_and_termination_must_both_allow_contribution(self):
        employee = EmployeePayProfile(
            employee_id="S1", employment_type="full_time",
            monthly_salary=Decimal("10000"), statutory_enabled=True,
            hire_date=date(2026, 8, 1), termination_date=date(2026, 8, 10),
        )
        rule = StatutoryRuleInput(
            "pension", "standard", "X", date(2026, 1, 1), None,
            "固定基数", Decimal("0"), Decimal("20000"), Decimal("5000"),
            Decimal("0.08"), Decimal("0.16"), (), "cutoff_day", "cutoff_day", 15, 15,
        )

        result = calculate_configured_statutory_deductions(
            employee, (rule,), social_income=Decimal("10000"),
            fund_income=Decimal("10000"), period_date=date(2026, 8, 1),
        )

        self.assertEqual(result.employee_total, Decimal("0.00"))

    def test_effective_date_is_distinct_from_contribution_month(self):
        employee = EmployeePayProfile(
            employee_id="S1", employment_type="full_time",
            monthly_salary=Decimal("10000"), statutory_enabled=True,
            hire_date=date(2026, 8, 16),
        )
        rule = StatutoryRuleInput(
            "pension", "standard", "X", date(2026, 7, 15), None,
            "固定基数", Decimal("0"), Decimal("20000"), Decimal("5000"),
            Decimal("0.08"), Decimal("0.16"), (), "cutoff_day", "always", 15, None,
        )

        result = calculate_configured_statutory_deductions(
            employee, (rule,), social_income=Decimal("10000"),
            fund_income=Decimal("10000"), period_date=date(2026, 8, 1),
            effective_date=date(2026, 7, 26),
        )

        self.assertEqual(result.employee_total, Decimal("0.00"))

    def test_configured_rules_apply_individual_bases_and_employee_opt_out(self):
        rules = (
            StatutoryRuleInput("pension", "standard", "Synthetic City", date(2026, 1, 1), None, "薪资全额", Decimal("5000"), Decimal("20000"), None, Decimal("0.08"), Decimal("0.16")),
            StatutoryRuleInput("housing_fund", "standard", "Synthetic City", date(2026, 1, 1), None, "固定基数", Decimal("0"), Decimal("20000"), Decimal("3000"), Decimal("0.05"), Decimal("0.05")),
        )
        employee = EmployeePayProfile("synthetic-001", "full_time", statutory_enabled=True)

        result = calculate_configured_statutory_deductions(
            employee, rules, social_income=Decimal("25000"), fund_income=Decimal("25000"), period_date=date(2026, 8, 1)
        )

        self.assertEqual(result.employee_total, Decimal("1750.00"))
        self.assertEqual(result.employer_total, Decimal("3350.00"))
        self.assertEqual(result.employee_amounts["pension"], Decimal("1600.00"))

    def test_enabled_employee_requires_configured_statutory_rules(self):
        employee = EmployeePayProfile("synthetic-001", "full_time", statutory_enabled=True)

        with self.assertRaisesRegex(ValueError, "not configured"):
            calculate_configured_statutory_deductions(
                employee, (), social_income=Decimal("10000"), fund_income=Decimal("10000"), period_date=date(2026, 8, 1)
            )

    def test_employee_tier_and_base_overrides_are_applied(self):
        rules = (
            StatutoryRuleInput("pension", "standard", "Synthetic City", date(2026, 1, 1), None, "薪资全额", Decimal("0"), Decimal("50000"), None, Decimal("0.08"), Decimal("0.16")),
            StatutoryRuleInput("pension", "special", "Synthetic City", date(2026, 1, 1), None, "薪资全额", Decimal("0"), Decimal("50000"), None, Decimal("0.10"), Decimal("0.20")),
            StatutoryRuleInput("housing_fund", "standard", "Synthetic City", date(2026, 1, 1), None, "薪资全额", Decimal("0"), Decimal("50000"), None, Decimal("0.05"), Decimal("0.05")),
        )
        employee = EmployeePayProfile(
            "synthetic-override", "full_time", statutory_enabled=True,
            pension_tier="special", social_base_mode="固定基数", social_fixed_base=Decimal("6000"),
            fund_base_mode="固定基数", fund_fixed_base=Decimal("3000"),
        )

        result = calculate_configured_statutory_deductions(
            employee, rules, social_income=Decimal("25000"), fund_income=Decimal("25000"),
            period_date=date(2026, 8, 1),
        )

        self.assertEqual(result.employee_amounts["pension"], Decimal("600.00"))
        self.assertEqual(result.employee_amounts["housing_fund"], Decimal("150.00"))
        self.assertEqual(result.employee_total, Decimal("750.00"))

    def test_company_default_base_override_inherits_policy(self):
        rules = (
            StatutoryRuleInput("pension", "standard", "Synthetic City", date(2026, 1, 1), None, "固定基数", Decimal("0"), Decimal("50000"), Decimal("5000"), Decimal("0.08"), Decimal("0.16")),
        )
        employee = EmployeePayProfile(
            "synthetic-default", "full_time", statutory_enabled=True,
            social_base_mode="公司默认", social_fixed_base=Decimal("9999"),
        )

        result = calculate_configured_statutory_deductions(
            employee, rules, social_income=Decimal("25000"), fund_income=Decimal("25000"),
            period_date=date(2026, 8, 1),
        )

        self.assertEqual(result.employee_amounts["pension"], Decimal("400.00"))
    def test_missing_policy_blocks_statutory_calculation(self):
        employee = EmployeeStatutoryProfile("synthetic-001")

        with self.assertRaisesRegex(ValueError, "not configured"):
            calculate_statutory_deductions(employee, Decimal("10000"), None, date(2026, 8, 1))

    def test_disabled_or_incomplete_policy_blocks_calculation(self):
        employee = EmployeeStatutoryProfile("synthetic-001")
        disabled = LocalStatutoryPolicy(
            enabled=False,
            region="",
            effective_from=None,
            effective_to=None,
            pension_tiers={},
            medical_tiers={},
            unemployment=None,
            work_injury_tiers={},
            maternity=None,
            housing_fund=None,
        )

        with self.assertRaisesRegex(ValueError, "not configured"):
            calculate_statutory_deductions(employee, Decimal("10000"), disabled, date(2026, 8, 1))

    def test_complete_policy_requires_selected_tiers_and_calculates_contributions(self):
        policy = LocalStatutoryPolicy(
            enabled=True,
            region="Synthetic City",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            pension_tiers={"standard": ContributionRule(Decimal("0.08"), Decimal("0.16"))},
            medical_tiers={"standard": ContributionRule(Decimal("0.02"), Decimal("0.05"))},
            unemployment=ContributionRule(Decimal("0.005"), Decimal("0.01")),
            work_injury_tiers={"low": ContributionRule(Decimal("0"), Decimal("0.002"))},
            maternity=ContributionRule(Decimal("0"), Decimal("0.008")),
            housing_fund=ContributionRule(Decimal("0.05"), Decimal("0.05")),
        )
        employee = EmployeeStatutoryProfile(
            "synthetic-001", pension_tier="standard", medical_tier="standard", work_injury_tier="low"
        )

        result = calculate_statutory_deductions(employee, Decimal("10000"), policy, date(2026, 8, 1))

        self.assertEqual(result.employee_total, Decimal("1550.00"))
        self.assertEqual(result.employer_total, Decimal("2800.00"))


if __name__ == "__main__":
    unittest.main()
