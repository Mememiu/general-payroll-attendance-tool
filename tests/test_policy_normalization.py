import unittest

from payroll_tool.config.policy_normalization import (
    normalize_employment_types,
    normalize_policy,
)


class PolicyNormalizationTests(unittest.TestCase):
    def test_legacy_employment_codes_become_review_required_objects(self):
        normalized = normalize_policy({"employment_types": ["full_time"]})

        self.assertEqual(normalized["employment_types"][0], {
            "code": "full_time",
            "name": "",
            "payroll_scheme": "",
            "social_insurance_applicable": None,
            "housing_fund_applicable": None,
            "tax_applicable": None,
            "enabled": True,
            "migration_review_required": True,
        })

    def test_normalization_does_not_invent_employment_rules(self):
        item = normalize_employment_types(["intern"])[0]

        self.assertIsNone(item["social_insurance_applicable"])
        self.assertIsNone(item["housing_fund_applicable"])
        self.assertIsNone(item["tax_applicable"])
        self.assertEqual(item["payroll_scheme"], "")

    def test_structured_items_are_json_copied_without_mutating_input(self):
        item = {
            "code": "contractor",
            "name": "外包",
            "payroll_scheme": "monthly",
            "social_insurance_applicable": False,
            "housing_fund_applicable": False,
            "tax_applicable": True,
            "enabled": True,
            "migration_review_required": False,
            "settings": {"formula_id": "monthly_prorated"},
        }

        normalized = normalize_policy({"employment_types": [item]})
        normalized["employment_types"][0]["settings"]["formula_id"] = "changed"

        self.assertEqual(item["settings"]["formula_id"], "monthly_prorated")

    def test_non_list_value_is_preserved_for_validation(self):
        normalized = normalize_policy({"employment_types": "full_time"})

        self.assertEqual(normalized["employment_types"], "full_time")


if __name__ == "__main__":
    unittest.main()
