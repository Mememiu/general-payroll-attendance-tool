from dataclasses import replace
from decimal import Decimal
import unittest

from payroll_tool.attendance.daily_pipeline import calculate_day_from_text
from payroll_tool.config.schema import AttendancePolicy
from payroll_tool.importers.hr_workbook import LeaveRuleInput


POLICY = AttendancePolicy(
    standard_start="10:00",
    standard_end="19:30",
    lunch_start="12:00",
    lunch_end="13:30",
    latest_normal_start="10:15",
    late_grace_end="10:30",
    work_mode="fixed",
    daily_required_hours=8,
    leave_types={},
    attendance_exemptions={},
    grace_checkout="19:50",
    late_makeup_allowed=True,
)
OVERTIME_RULES = {
    "加班": LeaveRuleInput(Decimal("1"), True, False, False, True)
}


class OvertimeStartModeTests(unittest.TestCase):
    def test_approval_start_mode_does_not_wait_for_normal_checkout(self):
        policy = replace(POLICY, overtime_start_mode="审批开始时间")

        result = calculate_day_from_text(
            "正常(10:28),正常(22:00);加班(19:30-22:00)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.overtime_hours, Decimal("2.5"))

    def test_normal_checkout_mode_ignores_earlier_approval_start(self):
        policy = replace(POLICY, overtime_start_mode="正常下班后")

        result = calculate_day_from_text(
            "正常(10:28),正常(22:00);加班(19:30-22:00)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(
            result.overtime_hours,
            Decimal("2.166666666666666666666666667"),
        )

    def test_later_mode_uses_later_of_approval_and_normal_checkout(self):
        policy = replace(POLICY, overtime_start_mode="审批与正常下班取较晚")

        result = calculate_day_from_text(
            "正常(10:28),正常(22:00);加班(20:00-22:00)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.overtime_hours, Decimal("2"))

    def test_later_mode_treats_after_midnight_approval_as_next_day(self):
        policy = replace(POLICY, overtime_start_mode="审批与正常下班取较晚")

        result = calculate_day_from_text(
            "正常(10:00),次日(02:00);加班(00:30-02:00)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.overtime_hours, Decimal("1.5"))

    def test_later_mode_does_not_move_pre_checkout_approval_to_next_day(self):
        policy = replace(POLICY, overtime_start_mode="审批与正常下班取较晚")

        result = calculate_day_from_text(
            "正常(10:28),正常(19:50);加班(18:00-19:00)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.overtime_hours, Decimal("0"))

    def test_normal_checkout_mode_returns_zero_when_approval_already_ended(self):
        policy = replace(POLICY, overtime_start_mode="正常下班后")

        result = calculate_day_from_text(
            "正常(10:28),正常(19:50);加班(18:00-19:00)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.overtime_hours, Decimal("0"))

    def test_missing_overtime_start_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "加班起算方式"):
            calculate_day_from_text(
                "正常(10:28),正常(22:00);加班(19:30-22:00)",
                POLICY,
                OVERTIME_RULES,
            )

    def test_minimum_is_checked_before_up_rounding(self):
        policy = replace(
            POLICY,
            overtime_start_mode="审批开始时间",
            overtime_minimum_minutes=45,
            overtime_rounding_mode="up_30",
            overtime_cross_midnight_allowed=True,
        )

        result = calculate_day_from_text(
            "正常(10:00),正常(20:14);加班(19:30-20:14)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.raw_overtime_minutes, Decimal("44"))
        self.assertEqual(result.overtime_minutes, Decimal("0"))

    def test_qualified_minutes_are_rounded_down_after_threshold(self):
        policy = replace(
            POLICY,
            overtime_start_mode="审批开始时间",
            overtime_minimum_minutes=45,
            overtime_rounding_mode="down_30",
            overtime_cross_midnight_allowed=True,
        )

        result = calculate_day_from_text(
            "正常(10:00),正常(20:16);加班(19:30-20:16)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.raw_overtime_minutes, Decimal("46"))
        self.assertEqual(result.overtime_minutes, Decimal("30"))

    def test_disallowed_cross_midnight_requires_review(self):
        policy = replace(
            POLICY,
            overtime_start_mode="审批开始时间",
            overtime_minimum_minutes=0,
            overtime_rounding_mode="actual_minutes",
            overtime_cross_midnight_allowed=False,
        )

        result = calculate_day_from_text(
            "正常(10:00),次日(00:30);加班(23:30-00:30)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.overtime_minutes, Decimal("0"))
        self.assertTrue(any("跨午夜" in reason for reason in result.review_reasons))

    def test_disallowed_after_midnight_continuation_requires_review(self):
        policy = replace(
            POLICY,
            overtime_start_mode="审批开始时间",
            overtime_minimum_minutes=0,
            overtime_rounding_mode="actual_minutes",
            overtime_cross_midnight_allowed=False,
        )

        result = calculate_day_from_text(
            "正常(10:00),次日(02:00);加班(00:30-02:00)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.overtime_minutes, Decimal("0"))
        self.assertTrue(any("跨午夜" in reason for reason in result.review_reasons))

    def test_legacy_missing_recognition_fields_is_explicitly_reviewable(self):
        policy = replace(POLICY, overtime_start_mode="审批开始时间")

        result = calculate_day_from_text(
            "正常(10:00),正常(20:30);加班(19:30-20:30)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.overtime_minutes, Decimal("0"))
        self.assertEqual(result.overtime_hours, Decimal("1"))
        self.assertTrue(any("旧加班规则" in reason for reason in result.review_reasons))

    def test_split_contiguous_approvals_use_daily_total_before_threshold(self):
        policy = replace(
            POLICY,
            overtime_start_mode="审批开始时间",
            overtime_minimum_minutes=30,
            overtime_rounding_mode="up_30",
            overtime_cross_midnight_allowed=True,
        )

        result = calculate_day_from_text(
            "正常(10:00),正常(20:10);加班(19:30-19:50);加班(19:50-20:10)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.raw_overtime_minutes, Decimal("40"))
        self.assertEqual(result.overtime_minutes, Decimal("60"))

    def test_overlapping_approvals_do_not_double_count_minutes(self):
        policy = replace(
            POLICY,
            overtime_start_mode="审批开始时间",
            overtime_minimum_minutes=0,
            overtime_rounding_mode="actual_minutes",
            overtime_cross_midnight_allowed=True,
        )

        result = calculate_day_from_text(
            "正常(10:00),正常(20:15);加班(19:30-20:00);加班(19:45-20:15)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.raw_overtime_minutes, Decimal("45"))
        self.assertEqual(result.overtime_minutes, Decimal("45"))

    def test_early_morning_same_day_overtime_is_not_cross_midnight(self):
        policy = replace(
            POLICY,
            overtime_start_mode="审批开始时间",
            overtime_minimum_minutes=0,
            overtime_rounding_mode="actual_minutes",
            overtime_cross_midnight_allowed=False,
        )

        result = calculate_day_from_text(
            "正常(10:00),正常(19:30);加班(08:00-09:00)",
            policy,
            OVERTIME_RULES,
        )

        self.assertEqual(result.overtime_minutes, Decimal("60"))
        self.assertFalse(any("跨午夜" in reason for reason in result.review_reasons))


if __name__ == "__main__":
    unittest.main()
