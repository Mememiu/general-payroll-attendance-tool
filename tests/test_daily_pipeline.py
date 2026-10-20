from decimal import Decimal
import unittest

from payroll_tool.attendance.daily_pipeline import calculate_day_from_text
from payroll_tool.config.schema import AttendancePolicy
from payroll_tool.importers.hr_workbook import LeaveRuleInput


POLICY = AttendancePolicy(
    standard_start="10:00", standard_end="19:30", lunch_start="12:00", lunch_end="13:30",
    latest_normal_start="10:15", late_grace_end="10:30", work_mode="fixed",
    daily_required_hours=8, leave_types={}, attendance_exemptions={},
    grace_checkout="19:50", late_makeup_allowed=True,
    checkout_boundary_mode="按到岗推算",
    overtime_start_mode="审批与正常下班取较晚",
)


class DailyPipelineTests(unittest.TestCase):
    def test_text_punches_and_paid_leave_produce_daily_attendance(self):
        rules = {"调休假": LeaveRuleInput(Decimal("1"), True, False, True, True)}

        result = calculate_day_from_text(
            "请假(13:30),正常(19:30);调休假(10:00-12:00)", POLICY, rules
        )

        self.assertEqual(result.attendance.effective_hours, 8)
        self.assertEqual(result.attendance.absence_hours, 0)

    def test_single_punch_is_flagged_for_review_instead_of_guessed(self):
        result = calculate_day_from_text("缺卡(-),正常(19:30)", POLICY, {})

        self.assertTrue(result.requires_review)
        self.assertIn("单卡", result.review_reasons[0])

    def test_full_day_coarse_business_trip_uses_hr_schedule_without_review(self):
        rules = {"出差": LeaveRuleInput(Decimal("1"), True, False, False, True)}

        result = calculate_day_from_text("出差(全天)", POLICY, rules)

        self.assertEqual(result.attendance.effective_hours, 8)
        self.assertEqual(result.attendance.absence_hours, 0)
        self.assertFalse(result.requires_review)

    def test_cross_midnight_overtime_is_separate_from_normal_attendance(self):
        rules = {"加班": LeaveRuleInput(Decimal("1"), True, False, False, True)}

        result = calculate_day_from_text(
            "正常(10:00),正常(19:30);加班(19:30-00:30)", POLICY, rules
        )

        self.assertEqual(result.attendance.effective_hours, 8)
        self.assertEqual(result.overtime_hours, Decimal("5"))
        self.assertNotIn("加班", result.leave_hours)

    def test_overtime_starts_after_checkout_inferred_from_early_arrival(self):
        rules = {"加班": LeaveRuleInput(Decimal("1"), True, False, False, True)}

        result = calculate_day_from_text(
            "正常(09:00),正常(21:00);加班(18:30-21:00)", POLICY, rules
        )

        self.assertEqual(result.overtime_hours, Decimal("2.5"))

    def test_overtime_uses_configured_grace_checkout_boundary(self):
        from dataclasses import replace

        rules = {"加班": LeaveRuleInput(Decimal("1"), True, False, False, True)}
        policy = replace(POLICY, grace_checkout="19:50")

        result = calculate_day_from_text(
            "正常(10:28),正常(22:00);加班(19:30-22:00)", policy, rules
        )

        self.assertEqual(result.overtime_hours, Decimal("2.166666666666666666666666667"))


if __name__ == "__main__":
    unittest.main()
