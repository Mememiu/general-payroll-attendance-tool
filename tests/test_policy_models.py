from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
import unittest

from payroll_tool.config.policy_models import PolicyStatus, ValidationIssue
from payroll_tool.config.policy_serialization import canonical_snapshot


class PolicyModelsTests(unittest.TestCase):
    def test_canonical_snapshot_is_independent_of_mapping_key_order(self):
        first = canonical_snapshot({"company": {"name": "示例公司", "active": True}, "version": 1})
        second = canonical_snapshot({"version": 1, "company": {"active": True, "name": "示例公司"}})

        self.assertEqual(first.payload, second.payload)
        self.assertEqual(first.sha256, second.sha256)

    def test_validation_issue_preserves_complete_field_path(self):
        issue = ValidationIssue(
            "required",
            "请输入每日标准工时",
            "company.worktime.daily_minutes",
        )

        self.assertEqual(issue.as_dict()["field"], "company.worktime.daily_minutes")

    def test_policy_status_values_are_stable_strings(self):
        self.assertEqual(
            [status.value for status in PolicyStatus],
            ["draft", "published", "retired"],
        )
        self.assertEqual(str(PolicyStatus.PUBLISHED), "published")

    def test_domain_values_are_frozen(self):
        issue = ValidationIssue("required", "message", "field")
        snapshot = canonical_snapshot({"version": 1})

        with self.assertRaises(FrozenInstanceError):
            issue.field = "other"
        with self.assertRaises(FrozenInstanceError):
            snapshot.payload = "{}"

    def test_canonical_snapshot_serializes_unicode_and_policy_scalar_types_deterministically(self):
        value = {
            "amount": Decimal("1234.50"),
            "effective_date": date(2026, 8, 21),
            "published_at": datetime(2026, 8, 21, 9, 30, tzinfo=timezone.utc),
            "label": "工资政策",
        }

        first = canonical_snapshot(value)
        second = canonical_snapshot(dict(reversed(list(value.items()))))

        self.assertEqual(first, second)
        self.assertIn('"decimal","1234.5"', first.payload)
        self.assertIn('"date","2026-08-21"', first.payload)
        self.assertIn('"datetime","2026-08-21T09:30:00Z"', first.payload)

    def test_distinct_python_types_cannot_share_a_snapshot_digest(self):
        pairs = (
            (Decimal("1.00"), "1.00"),
            (date(2026, 8, 21), "2026-08-21"),
            ((1, 2), [1, 2]),
        )
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                self.assertNotEqual(
                    canonical_snapshot({"value": left}).sha256,
                    canonical_snapshot({"value": right}).sha256,
                )

    def test_semantically_equal_values_have_the_same_digest(self):
        utc = datetime(2026, 8, 21, 1, 30, tzinfo=timezone.utc)
        china = datetime.fromisoformat("2026-08-21T09:30:00+08:00")
        pairs = (
            (Decimal("1.0"), Decimal("1.00")),
            (utc, china),
            ("é", "e\u0301"),
            (0.0, -0.0),
        )
        for left, right in pairs:
            with self.subTest(left=left, right=right):
                self.assertEqual(
                    canonical_snapshot({"value": left}).sha256,
                    canonical_snapshot({"value": right}).sha256,
                )

    def test_decimal_digest_is_independent_of_decimal_context_precision(self):
        value = {"amount": Decimal("1.234567890123456789")}
        with localcontext() as context:
            context.prec = 3
            low_precision = canonical_snapshot(value)
        with localcontext() as context:
            context.prec = 28
            high_precision = canonical_snapshot(value)

        self.assertEqual(low_precision, high_precision)

    def test_naive_datetime_is_rejected(self):
        with self.assertRaisesRegex(TypeError, "timezone-aware datetime"):
            canonical_snapshot({"published_at": datetime(2026, 8, 21, 9, 30)})

    def test_canonical_snapshot_rejects_unsupported_values_clearly(self):
        with self.assertRaisesRegex(TypeError, r"Unsupported value type at /codes: set"):
            canonical_snapshot({"codes": {"A", "B"}})

    def test_error_path_escapes_special_mapping_keys(self):
        with self.assertRaisesRegex(TypeError, r"at /a~1b~0c: set"):
            canonical_snapshot({"a/b~c": {"A"}})

    def test_canonical_snapshot_rejects_non_mapping_root(self):
        with self.assertRaisesRegex(TypeError, "must be a mapping"):
            canonical_snapshot([{"version": 1}])


if __name__ == "__main__":
    unittest.main()
