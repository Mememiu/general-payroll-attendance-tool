from decimal import Decimal
import unittest

from payroll_tool.attendance.daily_pipeline import calculate_day_from_text
from payroll_tool.config.policy_serialization import calculation_policy_from_snapshot
from tests.test_policy_validation import complete_policy


class OvertimeApprovalBehaviorTests(unittest.TestCase):
    def test_required_approval_rejects_coarse_overtime_period(self):
        policy = _policy(approval_required=True)

        result = calculate_day_from_text(
            "正常(09:30),正常(20:00);加班(全天)",
            policy.attendance,
            policy.leave_rules,
        )

        self.assertEqual(result.raw_overtime_minutes, Decimal("0"))
        self.assertEqual(result.overtime_minutes, Decimal("0"))
        self.assertTrue(any("明确起止时间" in reason for reason in result.review_reasons))

    def test_optional_approval_infers_overtime_from_complete_punches(self):
        policy = _policy(approval_required=False)

        result = calculate_day_from_text(
            "正常(09:30),正常(20:00)",
            policy.attendance,
            policy.leave_rules,
        )

        self.assertEqual(result.raw_overtime_minutes, Decimal("120"))
        self.assertEqual(result.overtime_minutes, Decimal("120"))
        self.assertEqual(result.review_reasons, ())

    def test_leave_overlap_keeps_raw_overtime_but_requires_review(self):
        policy = _policy(approval_required=True)

        result = calculate_day_from_text(
            "正常(09:30),正常(20:00);加班(18:00-20:00);事假(19:00-19:30)",
            policy.attendance,
            policy.leave_rules,
        )

        self.assertEqual(result.raw_overtime_minutes, Decimal("120"))
        self.assertEqual(result.overtime_minutes, Decimal("0"))
        self.assertTrue(any("与非加班审批重叠" in reason for reason in result.review_reasons))

    def test_overlap_before_normal_checkout_still_requires_review(self):
        policy = _policy(approval_required=True)

        result = calculate_day_from_text(
            "正常(09:30),正常(20:00);加班(17:00-20:00);事假(17:30-17:45)",
            policy.attendance,
            policy.leave_rules,
        )

        self.assertEqual(result.raw_overtime_minutes, Decimal("120"))
        self.assertEqual(result.overtime_minutes, Decimal("0"))
        self.assertTrue(any("与非加班审批重叠" in reason for reason in result.review_reasons))

    def test_overtime_is_recognized_without_counting_as_normal_attendance(self):
        policy = _policy(
            approval_required=True,
            overtime_counts_as_attendance=False,
        )

        result = calculate_day_from_text(
            "正常(09:30),正常(20:00);加班(18:00-20:00)",
            policy.attendance,
            policy.leave_rules,
        )

        self.assertEqual(result.attendance.effective_hours, 7.5)
        self.assertEqual(result.overtime_minutes, Decimal("120"))


def _policy(
    *, approval_required: bool, overtime_counts_as_attendance: bool = True
):
    snapshot = complete_policy()
    snapshot["company"]["leaves"] = [
        {
            "code": "overtime", "name": "加班", "category": "overtime",
            "pay_scheme": "full_pay",
            "counts_as_attendance": overtime_counts_as_attendance,
            "counts_as_absence": False, "affects_perfect_attendance": False,
            "skip_punch_requirement": False, "proof_required": False,
            "missing_proof_action": "review", "cross_day_allowed": True,
            "deduction_category": "none", "enabled": True,
        },
        {
            "code": "personal_leave", "name": "事假", "category": "leave",
            "pay_scheme": "unpaid", "counts_as_attendance": False,
            "counts_as_absence": True, "affects_perfect_attendance": True,
            "skip_punch_requirement": False, "proof_required": False,
            "missing_proof_action": "review", "cross_day_allowed": False,
            "deduction_category": "attendance", "enabled": True,
        },
    ]
    snapshot["company"]["overtime"] = {
        "enabled": True,
        "start_mode": "after_normal_end",
        "minimum_minutes": 0,
        "rounding_mode": "actual_minutes",
        "approval_required": approval_required,
        "cross_midnight_allowed": True,
        "cash_enabled": False,
        "comp_time_enabled": False,
    }
    return calculation_policy_from_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
