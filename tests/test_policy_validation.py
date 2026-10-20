from copy import deepcopy
import unittest

from payroll_tool.config.policy_validation import validate_policy


def complete_policy() -> dict[str, object]:
    return {
        "company": {
            "worktime": {
                "mode": "fixed",
                "daily_minutes": 450,
                "standard_start": "09:30",
                "standard_end": "18:00",
                "lunch": {"enabled": True, "start": "12:00", "end": "13:00"},
            },
            "leaves": [
                {
                    "code": "annual_paid",
                    "name": "带薪年假",
                    "category": "leave",
                    "pay_scheme": "ratio",
                    "pay_ratio": "1",
                    "counts_as_attendance": True,
                    "counts_as_absence": False,
                    "affects_perfect_attendance": True,
                    "skip_punch_requirement": True,
                    "proof_required": False,
                    "missing_proof_action": "review",
                    "cross_day_allowed": False,
                    "deduction_category": "none",
                    "enabled": True,
                }
            ],
            "overtime": {
                "enabled": False,
                "cash_enabled": False,
                "comp_time_enabled": False,
                "approval_required": True,
                "cross_midnight_allowed": False,
                "minimum_minutes": 0,
                "rounding_mode": "actual_minutes",
            },
            "payroll": {
                "monthly_pay_days": "20.83",
                "perfect_attendance_award": "0",
                "rounding_places": 2,
                "rounding_mode": "half_up",
            },
            "income_items": {
                "allowance": {
                    "taxable": True,
                    "included_in_social_base": False,
                    "included_in_fund_base": False,
                },
                "bonus": {
                    "taxable": True,
                    "included_in_social_base": False,
                    "included_in_fund_base": False,
                },
            },
        },
        "statutory": {
            "tax": {
                "enabled": True,
                "system": "cn_cumulative_withholding",
                "monthly_exemption": "5000",
                "negative_tax_mode": "zero",
                "effective_from": "2026-01-01",
                "brackets": [
                    {"threshold": "0", "rate": "0.03", "quick_deduction": "0"}
                ],
            },
            "insurance": [
                {"code": "pension", "name": "养老保险", "enabled": False}
            ],
        },
        "commercial_insurance": [],
        "employment_types": [{
            "code": "full_time",
            "name": "全职",
            "payroll_scheme": "full_time_monthly",
            "social_insurance_applicable": True,
            "housing_fund_applicable": True,
            "tax_applicable": True,
            "enabled": True,
            "migration_review_required": False,
        }],
    }


class PolicyValidationTests(unittest.TestCase):
    def test_complete_policy_has_no_issues(self):
        self.assertEqual(validate_policy(complete_policy()), ())

    def test_missing_daily_minutes_has_exact_ui_path(self):
        policy = complete_policy()
        del policy["company"]["worktime"]["daily_minutes"]

        issues = validate_policy(policy)

        self.assertTrue(
            any(issue.field == "company.worktime.daily_minutes" for issue in issues)
        )

    def test_disabled_insurance_does_not_require_rates(self):
        policy = complete_policy()
        issues = validate_policy(policy)

        self.assertFalse(
            any(
                i.field in {
                    "statutory.insurance[0].employee_rate",
                    "statutory.insurance[0].employer_rate",
                }
                for i in issues
            )
        )

    def test_enabled_insurance_requires_policy_fields_and_valid_bounds(self):
        policy = complete_policy()
        policy["statutory"]["insurance"][0] = {
            "code": "pension",
            "name": "养老保险",
            "enabled": True,
            "base_mode": "fixed",
            "base_lower": "9000",
            "base_upper": "8000",
            "employee_rate": "1.2",
            "employer_rate": "0.16",
            "policy_source": "人社部门文件",
            "employment_types": ["full_time"],
            "hire_month_rule": "always",
            "termination_month_rule": "always",
        }

        issues = validate_policy(policy)
        fields = {issue.field for issue in issues}

        self.assertIn("statutory.insurance[0].region", fields)
        self.assertIn("statutory.insurance[0].effective_from", fields)
        self.assertIn("statutory.insurance[0].base_upper", fields)
        self.assertIn("statutory.insurance[0].employee_rate", fields)
        self.assertNotIn("statutory.insurance[0].policy_source", fields)

    def test_income_items_are_required_for_published_calculation(self):
        policy = complete_policy()
        del policy["company"]["income_items"]["bonus"]

        fields = {issue.field for issue in validate_policy(policy)}

        self.assertIn("company.income_items.bonus", fields)

    def test_insurance_tiers_are_unique_within_item_but_multiple_tiers_are_allowed(self):
        policy = complete_policy()
        base = {
            "code": "pension", "name": "养老保险", "enabled": True,
            "region": "自定义地区", "effective_from": "2026-01-01",
            "policy_source": "政策文件", "employment_types": ["full_time"],
            "hire_month_rule": "always", "termination_month_rule": "always",
            "base_mode": "salary_full", "base_lower": "0", "base_upper": "99999",
            "employee_rate": "0.08", "employer_rate": "0.16",
        }
        standard = {**base, "tier_code": "standard"}
        special = {**base, "tier_code": "special"}
        policy["statutory"]["insurance"] = [standard, special]
        self.assertFalse(
            any(issue.code == "duplicate" for issue in validate_policy(policy))
        )

        policy["statutory"]["insurance"] = [standard, dict(standard)]
        self.assertIn(
            "statutory.insurance[1].tier_code",
            {issue.field for issue in validate_policy(policy) if issue.code == "duplicate"},
        )

    def test_enabled_insurance_requires_source_employment_and_timing(self):
        policy = complete_policy()
        policy["statutory"]["insurance"][0] = {
            "code": "pension", "name": "养老保险", "enabled": True,
            "region": "自定义地区", "effective_from": "2026-01-01",
            "base_mode": "salary_full", "base_lower": "0", "base_upper": "99999",
            "employee_rate": "0.08", "employer_rate": "0.16",
        }
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertIn("statutory.insurance[0].policy_source", fields)
        self.assertIn("statutory.insurance[0].employment_types", fields)
        self.assertIn("statutory.insurance[0].hire_month_rule", fields)
        self.assertIn("statutory.insurance[0].termination_month_rule", fields)

    def test_flexible_strategy_requires_only_its_conditional_fields(self):
        policy = complete_policy()
        policy["company"]["worktime"] = {
            "mode": "flexible",
            "daily_minutes": 435,
            "strategy": "core_hours",
            "lunch": {"enabled": False},
        }

        fields = {issue.field for issue in validate_policy(policy)}

        self.assertIn("company.worktime.core_start", fields)
        self.assertIn("company.worktime.core_end", fields)
        self.assertIn("company.worktime.standard_start", fields)
        self.assertIn("company.worktime.standard_end", fields)

    def test_latest_start_strategy_and_fixed_mode_conditionals(self):
        policy = complete_policy()
        policy["company"]["worktime"] = {
            "mode": "flexible", "daily_minutes": 435, "strategy": "latest_start",
            "lunch": {"enabled": False},
        }
        self.assertIn(
            "company.worktime.latest_start",
            {issue.field for issue in validate_policy(policy)},
        )
        fixed = complete_policy()
        fixed["company"]["worktime"]["strategy"] = "invalid_unused_value"
        self.assertEqual(validate_policy(fixed), ())

    def test_work_hours_flexible_strategy_still_needs_approval_day_boundaries(self):
        policy = complete_policy()
        policy["company"]["worktime"] = {
            "mode": "flexible", "daily_minutes": 435, "strategy": "work_hours",
            "lunch": {"enabled": False},
        }
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertIn("company.worktime.standard_start", fields)
        self.assertIn("company.worktime.standard_end", fields)

    def test_duplicate_leave_display_names_are_rejected(self):
        policy = complete_policy()
        duplicate = deepcopy(policy["company"]["leaves"][0])
        duplicate["code"] = "another_code"
        policy["company"]["leaves"].append(duplicate)

        self.assertIn(
            "company.leaves[1].name",
            {issue.field for issue in validate_policy(policy) if issue.code == "duplicate"},
        )

    def test_insurance_effective_end_must_not_precede_start(self):
        policy = complete_policy()
        policy["statutory"]["insurance"] = [{
            "code": "pension", "tier_code": "standard", "name": "养老保险",
            "enabled": True, "region": "自定义地区",
            "effective_from": "2026-06-01", "effective_to": "2026-05-31",
            "policy_source": "政策文件", "employment_types": ["full_time"],
            "hire_month_rule": "always", "termination_month_rule": "always",
            "base_mode": "salary_full", "base_lower": "0", "base_upper": "99999",
            "employee_rate": "0.08", "employer_rate": "0.16",
        }]

        self.assertIn(
            "statutory.insurance[0].effective_to",
            {issue.field for issue in validate_policy(policy)},
        )

    def test_duplicate_leave_codes_report_second_row(self):
        policy = complete_policy()
        policy["company"]["leaves"].append(
            deepcopy(policy["company"]["leaves"][0])
        )

        issues = validate_policy(policy)

        self.assertTrue(
            any(i.code == "duplicate" and i.field == "company.leaves[1].code" for i in issues)
        )

    def test_disabled_leave_only_requires_identity_and_status(self):
        policy = complete_policy()
        policy["company"]["leaves"] = [
            {"code": "legacy_leave", "name": "历史假期", "enabled": False}
        ]
        self.assertEqual(validate_policy(policy), ())

    def test_missing_proof_action_is_ignored_when_proof_not_required(self):
        policy = complete_policy()
        del policy["company"]["leaves"][0]["missing_proof_action"]
        self.assertEqual(validate_policy(policy), ())

    def test_cash_overtime_requires_supported_formula_and_rate(self):
        policy = complete_policy()
        policy["company"]["overtime"] = {
            "enabled": True,
            "start_mode": "after_normal_end",
            "cash_enabled": True,
            "comp_time_enabled": False,
            "approval_required": True,
            "cross_midnight_allowed": False,
            "minimum_minutes": 0,
            "rounding_mode": "actual_minutes",
        }

        fields = {issue.field for issue in validate_policy(policy)}

        self.assertIn("company.overtime.cash_formula", fields)
        self.assertIn("company.overtime.cash_rate", fields)
        self.assertIn("company.overtime.day_rates", fields)

    def test_cash_overtime_rejects_unknown_day_rate_keys(self):
        policy = complete_policy()
        policy["company"]["overtime"] = {
            "enabled": True, "start_mode": "after_normal_end",
            "cash_enabled": True, "comp_time_enabled": False,
            "approval_required": True, "cross_midnight_allowed": False,
            "minimum_minutes": 0, "rounding_mode": "actual_minutes",
            "cash_formula": "hourly_rate_multiplier", "cash_rate": "1",
            "day_rates": {
                "workday": "1.5", "rest_day": "2", "holiday": "3",
                "weekend": "2",
            },
        }

        fields = {issue.field for issue in validate_policy(policy)}

        self.assertIn("company.overtime.day_rates", fields)

    def test_enabled_overtime_requires_operational_boundaries(self):
        policy = complete_policy()
        policy["company"]["overtime"] = {
            "enabled": True, "cash_enabled": False, "comp_time_enabled": False,
            "start_mode": "after_normal_end", "minimum_minutes": -1,
            "rounding_mode": "unknown",
        }
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertIn("company.overtime.approval_required", fields)
        self.assertIn("company.overtime.cross_midnight_allowed", fields)
        self.assertIn("company.overtime.minimum_minutes", fields)
        self.assertIn("company.overtime.rounding_mode", fields)

    def test_disabled_overtime_rejects_enabled_settlement_children(self):
        policy = complete_policy()
        policy["company"]["overtime"] = {
            "enabled": False,
            "cash_enabled": True,
            "comp_time_enabled": True,
        }

        fields = {issue.field for issue in validate_policy(policy)}

        self.assertIn("company.overtime.cash_enabled", fields)
        self.assertIn("company.overtime.comp_time_enabled", fields)

    def test_invalid_time_lunch_and_daily_minutes_are_reported_together(self):
        policy = complete_policy()
        worktime = policy["company"]["worktime"]
        worktime["standard_start"] = "9:30"
        worktime["lunch"] = {"enabled": True, "start": "19:00", "end": "18:00"}
        worktime["daily_minutes"] = 900

        fields = {issue.field for issue in validate_policy(policy)}

        self.assertIn("company.worktime.standard_start", fields)
        self.assertIn("company.worktime.lunch.end", fields)

        valid_times = complete_policy()
        valid_times["company"]["worktime"]["daily_minutes"] = 600
        self.assertIn(
            "company.worktime.daily_minutes",
            {issue.field for issue in validate_policy(valid_times)},
        )

    def test_strict_date_format_is_required(self):
        policy = complete_policy()
        policy["statutory"]["tax"]["effective_from"] = "2026-1-1"
        self.assertIn(
            "statutory.tax.effective_from",
            {issue.field for issue in validate_policy(policy)},
        )

    def test_leave_fixed_deduction_and_formula_require_parameters(self):
        for scheme, expected in (
            ("fixed_deduction", "company.leaves[0].fixed_deduction_amount"),
            ("formula", "company.leaves[0].formula_id"),
        ):
            policy = complete_policy()
            policy["company"]["leaves"][0]["pay_scheme"] = scheme
            self.assertIn(expected, {issue.field for issue in validate_policy(policy)})

    def test_tax_requires_system_and_valid_cumulative_brackets(self):
        policy = complete_policy()
        policy["statutory"]["tax"]["system"] = ""
        policy["statutory"]["tax"]["brackets"] = [
            {"threshold": "100", "rate": "1.5", "quick_deduction": "-1"}
        ]
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertIn("statutory.tax.system", fields)
        self.assertIn("statutory.tax.brackets[0].rate", fields)
        self.assertIn("statutory.tax.brackets[0].quick_deduction", fields)
        self.assertIn("statutory.tax.brackets[0].threshold", fields)

    def test_insurance_employment_types_must_reference_defined_type(self):
        policy = complete_policy()
        insurance = {
            "code": "pension", "name": "养老保险", "enabled": True,
            "region": "自定义地区", "effective_from": "2026-01-01",
            "policy_source": "政策文件", "employment_types": ["ghost"],
            "hire_month_rule": "always", "termination_month_rule": "always",
            "base_mode": "salary_full", "base_lower": "0", "base_upper": "99999",
            "employee_rate": "0.08", "employer_rate": "0.16",
        }
        policy["statutory"]["insurance"] = [insurance]
        self.assertIn(
            "statutory.insurance[0].employment_types",
            {issue.field for issue in validate_policy(policy)},
        )

    def test_employment_types_reject_duplicate_codes_and_names(self):
        policy = complete_policy()
        duplicate = deepcopy(policy["employment_types"][0])
        policy["employment_types"].append(duplicate)
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertIn("employment_types[1].code", fields)
        self.assertIn("employment_types[1].name", fields)

    def test_employment_type_requires_valid_code_scheme_and_booleans(self):
        policy = complete_policy()
        policy["employment_types"] = [{
            "code": "Bad Code", "name": "", "payroll_scheme": "arbitrary_python",
            "social_insurance_applicable": None,
            "housing_fund_applicable": None,
            "tax_applicable": None,
            "enabled": True,
        }]
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertIn("employment_types[0].code", fields)
        self.assertIn("employment_types[0].name", fields)
        self.assertIn("employment_types[0].payroll_scheme", fields)
        self.assertIn("employment_types[0].social_insurance_applicable", fields)
        self.assertIn("employment_types[0].housing_fund_applicable", fields)
        self.assertIn("employment_types[0].tax_applicable", fields)

    def test_disabled_employment_type_is_not_a_valid_insurance_reference(self):
        policy = complete_policy()
        policy["employment_types"][0]["enabled"] = False
        policy["statutory"]["insurance"] = [{
            "code": "pension", "name": "养老保险", "enabled": True,
            "region": "自定义地区", "effective_from": "2026-01-01",
            "policy_source": "政策文件", "employment_types": ["full_time"],
            "hire_month_rule": "always", "termination_month_rule": "always",
            "base_mode": "salary_full", "base_lower": "0", "base_upper": "99999",
            "employee_rate": "0.08", "employer_rate": "0.16",
        }]
        self.assertIn(
            "statutory.insurance[0].employment_types",
            {issue.field for issue in validate_policy(policy)},
        )

    def test_migrated_employment_type_must_be_reviewed_before_publish(self):
        policy = complete_policy()
        policy["employment_types"][0]["migration_review_required"] = True
        self.assertIn(
            "employment_types[0].migration_review_required",
            {issue.field for issue in validate_policy(policy)},
        )

    def test_legacy_string_employment_type_is_normalized_to_reviewable_paths(self):
        policy = complete_policy()
        policy["employment_types"] = ["full_time"]
        fields = {issue.field for issue in validate_policy(policy)}

        self.assertIn("employment_types[0].name", fields)
        self.assertIn("employment_types[0].payroll_scheme", fields)
        self.assertIn("employment_types[0].migration_review_required", fields)

    def test_enabled_commercial_insurance_requires_tax_and_deduction_fields(self):
        policy = complete_policy()
        policy["commercial_insurance"] = [{
            "code": "group_accident", "name": "团体意外险", "enabled": True,
            "effective_from": "2026-01-01", "calculation": "fixed_amount",
            "amount": "100", "employment_types": ["full_time"],
        }]
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertIn("commercial_insurance[0].region", fields)
        self.assertIn("commercial_insurance[0].taxable", fields)
        self.assertIn("commercial_insurance[0].included_in_gross", fields)
        self.assertIn("commercial_insurance[0].deduction_mode", fields)
        self.assertIn("commercial_insurance[0].employee_share", fields)
        self.assertIn("commercial_insurance[0].employer_share", fields)

    def test_commercial_insurance_shares_must_total_one(self):
        policy = complete_policy()
        policy["commercial_insurance"] = [{
            "code": "group_accident", "name": "团体意外险", "enabled": True,
            "region": "自定义地区", "effective_from": "2026-01-01",
            "calculation": "fixed_amount", "amount": "100",
            "employee_share": "1", "employer_share": "1", "taxable": False,
            "included_in_gross": False, "deduction_mode": "company_paid",
            "employment_types": ["full_time"],
        }]
        self.assertIn(
            "commercial_insurance[0].employer_share",
            {issue.field for issue in validate_policy(policy)},
        )

    def test_commercial_insurance_code_and_date_range_are_validated(self):
        policy = complete_policy()
        policy["commercial_insurance"] = [{
            "code": "Group-Accident", "name": "团体意外险", "enabled": True,
            "region": "自定义地区", "effective_from": "2026-06-01",
            "effective_to": "2026-05-31", "calculation": "fixed_amount",
            "amount": "100", "employee_share": "0", "employer_share": "1",
            "taxable": False, "included_in_gross": False,
            "deduction_mode": "company_paid", "employment_types": ["full_time"],
        }]
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertIn("commercial_insurance[0].code", fields)
        self.assertIn("commercial_insurance[0].effective_to", fields)

    def test_commercial_insurance_modes_require_their_own_values(self):
        policy = complete_policy()
        common = {
            "code": "group_accident", "name": "团体意外险", "enabled": True,
            "region": "自定义地区", "effective_from": "2026-01-01",
            "employee_share": "0", "employer_share": "1", "taxable": False,
            "included_in_gross": False, "deduction_mode": "company_paid",
            "employment_types": ["full_time"],
        }
        policy["commercial_insurance"] = [{**common, "calculation": "fixed_amount"}]
        self.assertIn(
            "commercial_insurance[0].amount",
            {issue.field for issue in validate_policy(policy)},
        )
        policy["commercial_insurance"] = [{**common, "calculation": "base_rate"}]
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertIn("commercial_insurance[0].employee_rate", fields)
        self.assertIn("commercial_insurance[0].employer_rate", fields)

    def test_validation_collects_errors_without_raising(self):
        issues = validate_policy({})
        self.assertGreater(len(issues), 3)
        self.assertTrue(all(issue.code and issue.message and issue.field for issue in issues))


class EmployeeExceptionValidationTests(unittest.TestCase):
    def exception_policy(self):
        policy = complete_policy()
        policy["statutory"]["insurance"].append({
            "code": "housing_fund", "name": "住房公积金", "enabled": False,
            "item_group": "housing_fund",
        })
        policy["employee_exceptions"] = [{
            "employee_id": "SYNTHETIC-EMPLOYEE-001", "override_type": "housing_fund_fixed_base",
            "target_code": "housing_fund", "value": "8000",
            "effective_from": "2026-08-01", "effective_to": None,
            "reason": "HR approved special base", "enabled": True,
        }]
        return policy

    def test_canonical_employee_exception_is_valid(self):
        self.assertEqual(validate_policy(self.exception_policy()), ())

    def test_employee_exception_requires_identity_reason_and_dates(self):
        policy = self.exception_policy()
        policy["employee_exceptions"][0] = {"enabled": True}
        fields = {issue.field for issue in validate_policy(policy)}
        for field in ("employee_id", "override_type", "target_code", "value", "effective_from", "reason"):
            self.assertIn(f"employee_exceptions[0].{field}", fields)

    def test_employee_exception_rejects_unknown_type_target_and_bad_decimal(self):
        policy = self.exception_policy()
        policy["employee_exceptions"][0].update(
            override_type="bonus", target_code="unknown", value="not-money"
        )
        self.assertIn(
            "employee_exceptions[0].override_type",
            {issue.field for issue in validate_policy(policy)},
        )
        policy = self.exception_policy()
        policy["employee_exceptions"][0].update(target_code="unknown", value="not-money")
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertIn("employee_exceptions[0].target_code", fields)
        self.assertIn("employee_exceptions[0].value", fields)

    def test_zero_perfect_attendance_override_is_valid_and_reverse_date_is_not(self):
        policy = self.exception_policy()
        policy["employee_exceptions"][0].update(
            override_type="perfect_attendance_amount", target_code="perfect_attendance",
            value="0", effective_to="2026-07-31",
        )
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertNotIn("employee_exceptions[0].value", fields)
        self.assertIn("employee_exceptions[0].effective_to", fields)

    def test_overlapping_enabled_employee_exception_intervals_are_rejected(self):
        policy = self.exception_policy()
        second = deepcopy(policy["employee_exceptions"][0])
        second.update(effective_from="2026-08-15", effective_to="2026-09-01")
        policy["employee_exceptions"].append(second)
        self.assertIn(
            "employee_exceptions[1].effective_from",
            {issue.field for issue in validate_policy(policy)},
        )

    def test_exception_target_category_tier_and_employment_target_are_constrained(self):
        policy = self.exception_policy()
        item = policy["employee_exceptions"][0]
        item.update(override_type="housing_fund_tier", target_code="pension", value="missing")
        fields = {issue.field for issue in validate_policy(policy)}
        self.assertIn("employee_exceptions[0].target_code", fields)
        self.assertIn("employee_exceptions[0].value", fields)
        policy = self.exception_policy()
        policy["employee_exceptions"][0].update(
            override_type="employment_type", target_code="arbitrary", value="full_time"
        )
        self.assertIn(
            "employee_exceptions[0].target_code",
            {issue.field for issue in validate_policy(policy)},
        )


if __name__ == "__main__":
    unittest.main()
