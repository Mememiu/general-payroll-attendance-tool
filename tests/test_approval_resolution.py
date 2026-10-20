from decimal import Decimal
import unittest

from payroll_tool.attendance.approvals import resolve_approvals
from payroll_tool.attendance.text_parser import parse_daily_attendance_text
from payroll_tool.importers.hr_workbook import LeaveRuleInput
from payroll_tool.models import Segment


class ApprovalResolutionTests(unittest.TestCase):
    def test_paid_leave_and_external_segments_become_attendance_coverage(self):
        parsed = parse_daily_attendance_text("调休假(10:00-12:00);外出(13:30-15:00)")
        rules = {
            "调休假": LeaveRuleInput(Decimal("1"), True, False, True, True),
            "外出": LeaveRuleInput(Decimal("1"), True, False, False, True),
        }

        resolved = resolve_approvals(parsed.approvals, rules)

        self.assertEqual([segment.kind for segment in resolved.paid_segments], ["调休假", "外出"])
        self.assertEqual(resolved.absence_segments, ())

    def test_undefined_approval_label_is_rejected(self):
        parsed = parse_daily_attendance_text("护理假(10:00-12:00)")

        with self.assertRaisesRegex(ValueError, "护理假"):
            resolve_approvals(parsed.approvals, {})

    def test_coarse_morning_approval_uses_hr_schedule_segments(self):
        parsed = parse_daily_attendance_text("出差(上午)")
        rules = {"出差": LeaveRuleInput(Decimal("1"), True, False, False, True)}

        resolved = resolve_approvals(
            parsed.approvals,
            rules,
            coarse_periods={"上午": (Segment("出差", "10:00", "12:00"),)},
        )

        self.assertEqual(resolved.paid_segments[0].start, "10:00")
        self.assertEqual(resolved.coarse_approvals, ())

    def test_coarse_afternoon_approval_uses_all_mapped_segments(self):
        parsed = parse_daily_attendance_text("出差(下午)")
        rules = {"出差": LeaveRuleInput(Decimal("1"), True, False, False, True)}

        resolved = resolve_approvals(
            parsed.approvals,
            rules,
            coarse_periods={"下午": (Segment("schedule", "13:30", "19:30"),)},
        )

        self.assertEqual(
            resolved.paid_segments,
            (Segment("出差", "13:30", "19:30"),),
        )


if __name__ == "__main__":
    unittest.main()
