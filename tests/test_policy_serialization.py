from copy import deepcopy
from datetime import date
from decimal import Decimal
import unittest

from payroll_tool.config.policy_serialization import calculation_policy_from_snapshot
from tests.test_policy_validation import complete_policy


class PolicyCalculationSerializationTests(unittest.TestCase):
    def test_overtime_settlement_values_are_preserved_without_defaults(self):
        snapshot = _calculation_policy()
        snapshot["company"]["overtime"].update({
            "enabled": True,
            "start_mode": "approval_start",
            "minimum_minutes": 47,
            "rounding_mode": "up_30",
            "approval_required": True,
            "cross_midnight_allowed": False,
            "cash_enabled": True,
            "cash_formula": "hourly_rate_multiplier",
            "cash_rate": "1.2",
            "day_rates": {
                "workday": "1.5",
                "rest_day": "2",
                "holiday": "3",
            },
            "comp_time_enabled": True,
            "comp_time_ratio": "1.25",
        })

        result = calculation_policy_from_snapshot(snapshot)

        self.assertEqual(result.overtime.minimum_minutes, 47)
        self.assertEqual(result.overtime.rounding_mode, "up_30")
        self.assertFalse(result.overtime.cross_midnight_allowed)
        self.assertEqual(result.overtime.cash_rate, Decimal("1.2"))
        self.assertEqual(
            result.overtime.day_rates["holiday"], Decimal("3")
        )
        self.assertEqual(result.overtime.comp_time_ratio, Decimal("1.25"))

    def test_disabled_overtime_does_not_invent_settlement_defaults(self):
        snapshot = _calculation_policy()
        snapshot["company"]["overtime"] = {
            "enabled": False,
            "approval_required": False,
            "cross_midnight_allowed": True,
            "cash_enabled": False,
            "comp_time_enabled": False,
        }

        result = calculation_policy_from_snapshot(snapshot)

        self.assertFalse(result.overtime.enabled)
        self.assertIsNone(result.overtime.approval_required)
        self.assertIsNone(result.overtime.cross_midnight_allowed)
        self.assertIsNone(result.overtime.start_mode)
        self.assertIsNone(result.overtime.minimum_minutes)
        self.assertIsNone(result.overtime.rounding_mode)
        self.assertIsNone(result.overtime.cash_formula)
        self.assertIsNone(result.overtime.cash_rate)
        self.assertEqual(result.overtime.day_rates, {})
        self.assertIsNone(result.overtime.comp_time_ratio)

    def test_disabled_overtime_allows_conditional_fields_to_be_absent(self):
        snapshot = _calculation_policy()
        snapshot["company"]["overtime"] = {
            "enabled": False,
            "cash_enabled": False,
            "comp_time_enabled": False,
        }

        result = calculation_policy_from_snapshot(snapshot)

        self.assertIsNone(result.overtime.approval_required)
        self.assertIsNone(result.overtime.cross_midnight_allowed)

    def test_enabled_cash_overtime_requires_every_day_rate(self):
        snapshot = _calculation_policy()
        snapshot["company"]["overtime"]["cash_enabled"] = True
        snapshot["company"]["overtime"]["cash_formula"] = "hourly_rate_multiplier"
        snapshot["company"]["overtime"]["cash_rate"] = "1"
        snapshot["company"]["overtime"]["day_rates"] = {
            "workday": "1.5", "rest_day": "2",
        }

        with self.assertRaisesRegex(
            ValueError, r"company\.overtime\.day_rates\.holiday"
        ):
            calculation_policy_from_snapshot(snapshot)

    def test_enabled_overtime_rejects_unsupported_settlement_enums(self):
        snapshot = _calculation_policy()
        snapshot["company"]["overtime"]["rounding_mode"] = "invented"

        with self.assertRaisesRegex(ValueError, "rounding_mode"):
            calculation_policy_from_snapshot(snapshot)

    def test_non_default_hr_values_are_preserved_exactly(self):
        snapshot = _calculation_policy()

        result = calculation_policy_from_snapshot(snapshot)

        self.assertEqual(result.daily_minutes, 435)
        self.assertEqual(result.attendance.daily_required_hours, 7.25)
        self.assertEqual(result.attendance.overtime_start_mode, "审批与正常下班取较晚")
        self.assertEqual(result.monthly_pay_days, Decimal("20.83"))
        self.assertEqual(result.perfect_attendance_award, Decimal("123.45"))
        self.assertIn("自定义照护假", result.leave_rules)
        self.assertEqual(result.leave_rules["自定义照护假"].paid_ratio, Decimal("0.6"))
        self.assertEqual(result.statutory_rules[0].tier_code, "standard")
        self.assertEqual(result.statutory_rules[0].employee_rate, Decimal("0.071"))
        self.assertEqual(result.statutory_rules[0].employment_types, ("full_time",))
        self.assertEqual(result.statutory_rules[0].hire_month_rule, "always")
        self.assertEqual(result.statutory_rules[0].termination_month_rule, "always")
        self.assertTrue(result.tax.enabled)
        self.assertEqual(result.tax.monthly_exemption, Decimal("5000"))
        self.assertEqual(result.tax.effective_from, date(2026, 1, 1))
        self.assertEqual(result.tax.brackets[0].threshold, Decimal("0"))
        self.assertEqual(result.tax.brackets[0].rate, Decimal("0.03"))

    def test_unknown_formula_is_rejected_before_calculation(self):
        snapshot = _calculation_policy()
        snapshot["company"]["leaves"][0]["pay_scheme"] = "formula"
        snapshot["company"]["leaves"][0]["formula_id"] = "python:danger()"
        snapshot["company"]["leaves"][0]["formula_parameters"] = {"multiplier": "1"}

        with self.assertRaisesRegex(ValueError, r"company\.leaves\[0\]\.formula_id"):
            calculation_policy_from_snapshot(snapshot)

    def test_missing_required_value_does_not_fall_back_to_company_defaults(self):
        snapshot = _calculation_policy()
        del snapshot["company"]["worktime"]["daily_minutes"]

        with self.assertRaisesRegex(ValueError, "company.worktime.daily_minutes"):
            calculation_policy_from_snapshot(snapshot)

    def test_employment_policies_are_keyed_by_code(self):
        result = calculation_policy_from_snapshot(_calculation_policy())

        policy = result.employment_types["full_time"]
        self.assertEqual(policy.name, "全职")
        self.assertEqual(policy.payroll_scheme, "full_time_monthly")
        self.assertTrue(policy.social_insurance_applicable)

    def test_commercial_insurance_is_preserved_for_calculation(self):
        snapshot = _calculation_policy()
        snapshot["commercial_insurance"] = [{
            "code": "accident", "name": "团体意外险", "enabled": True,
            "region": "测试地区", "effective_from": "2026-01-01",
            "effective_to": None, "calculation": "fixed_amount", "amount": "100",
            "employee_share": "0.2", "employer_share": "0.8",
            "taxable": False, "included_in_gross": False,
            "deduction_mode": "payroll_deduction",
            "employment_types": ["full_time"],
        }]

        result = calculation_policy_from_snapshot(snapshot)

        self.assertEqual(result.commercial_insurance[0].code, "accident")
        self.assertEqual(result.commercial_insurance[0].amount, Decimal("100"))

    def test_unreviewed_migrated_employment_type_cannot_reach_calculation(self):
        snapshot = _calculation_policy()
        snapshot["employment_types"][0]["migration_review_required"] = True

        with self.assertRaisesRegex(
            ValueError, r"employment_types\[0\]\.migration_review_required"
        ):
            calculation_policy_from_snapshot(snapshot)

    def test_legacy_string_employment_type_cannot_reach_calculation(self):
        snapshot = _calculation_policy()
        snapshot["employment_types"] = ["full_time"]

        with self.assertRaisesRegex(
            ValueError, r"employment_types\[0\]\.migration_review_required"
        ):
            calculation_policy_from_snapshot(snapshot)

    def test_employee_exceptions_are_immutable_and_selected_by_employee_and_date(self):
        snapshot = _calculation_policy()
        snapshot["employee_exceptions"] = [{
            "employee_id": "SYNTHETIC-EMPLOYEE-001", "override_type": "perfect_attendance_amount",
            "target_code": "perfect_attendance", "value": "0",
            "effective_from": "2026-08-01", "effective_to": "2026-08-31",
            "reason": "取消当月全勤奖", "enabled": True,
        }]
        result = calculation_policy_from_snapshot(snapshot)
        active = result.active_employee_exceptions("SYNTHETIC-EMPLOYEE-001", date(2026, 8, 15))
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].value, Decimal("0"))
        self.assertEqual(
            result.active_employee_exceptions("SYNTHETIC-EMPLOYEE-001", date(2026, 9, 1)), ()
        )
        self.assertEqual(
            len(result.employee_exceptions_for_period(
                "SYNTHETIC-EMPLOYEE-001", date(2026, 7, 15), date(2026, 8, 1)
            )),
            1,
        )

    def test_invalid_employee_exception_cannot_bypass_validation_during_conversion(self):
        snapshot = _calculation_policy()
        snapshot["employee_exceptions"] = [{
            "employee_id": "S1", "override_type": "bonus", "target_code": "bonus",
            "value": "999999", "effective_from": "2026-01-01",
            "reason": "not allowed", "enabled": True,
        }]
        with self.assertRaisesRegex(ValueError, r"employee_exceptions\[0\]\.override_type"):
            calculation_policy_from_snapshot(snapshot)


def _calculation_policy() -> dict[str, object]:
    policy = deepcopy(complete_policy())
    policy["company"]["worktime"] = {
        "mode": "flexible",
        "strategy": "work_hours",
        "daily_minutes": 435,
        "standard_start": "09:20",
        "standard_end": "18:05",
        "lunch": {"enabled": True, "start": "12:10", "end": "13:00"},
    }
    policy["company"]["payroll"]["perfect_attendance_award"] = "123.45"
    policy["company"]["overtime"] = {
        "enabled": True, "cash_enabled": False, "comp_time_enabled": True,
        "approval_required": True, "cross_midnight_allowed": True,
        "minimum_minutes": 0, "rounding_mode": "actual_minutes",
        "start_mode": "later_of_approval_and_normal_end", "comp_time_ratio": "1",
    }
    policy["company"]["leaves"] = [{
        "code": "care_leave", "name": "自定义照护假", "category": "leave",
        "pay_scheme": "ratio", "pay_ratio": "0.6",
        "counts_as_attendance": False, "counts_as_absence": True,
        "affects_perfect_attendance": True, "skip_punch_requirement": True,
        "proof_required": False, "missing_proof_action": "review",
        "cross_day_allowed": False, "deduction_category": "attendance", "enabled": True,
    }]
    policy["company"]["income_items"] = {
        "allowance": {
            "taxable": True, "included_in_social_base": False,
            "included_in_fund_base": False,
        },
        "bonus": {
            "taxable": True, "included_in_social_base": False,
            "included_in_fund_base": False,
        },
    }
    policy["statutory"]["insurance"] = [{
        "code": "pension", "name": "养老保险", "tier_code": "standard",
        "enabled": True, "region": "测试地区", "effective_from": "2026-01-01",
        "effective_to": None, "policy_source": "HR 手工录入",
        "employment_types": ["full_time"], "hire_month_rule": "always",
        "termination_month_rule": "always", "base_mode": "salary_full",
        "base_lower": "4000", "base_upper": "30000", "employee_rate": "0.071",
        "employer_rate": "0.16",
    }]
    return policy


if __name__ == "__main__":
    unittest.main()
