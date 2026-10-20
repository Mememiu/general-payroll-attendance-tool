import unittest

from payroll_tool.attendance.text_parser import parse_daily_attendance_text


class AttendanceTextParserTests(unittest.TestCase):
    def test_parser_extracts_ordered_punches_and_approved_segments(self):
        parsed = parse_daily_attendance_text(
            "正常(10:00),正常(19:30);外出(10:00-11:30);调休假(15:00-16:00)"
        )

        self.assertEqual(parsed.punch_times, ("10:00", "19:30"))
        self.assertEqual(parsed.approvals[0].kind, "外出")
        self.assertEqual(parsed.approvals[0].start, "10:00")
        self.assertEqual(parsed.approvals[1].kind, "调休假")

    def test_parser_does_not_turn_coarse_approval_into_false_exact_time(self):
        parsed = parse_daily_attendance_text("缺卡(-),正常(19:30);出差(上午)")

        self.assertEqual(parsed.punch_times, ("19:30",))
        self.assertEqual(parsed.approvals[0].kind, "出差")
        self.assertIsNone(parsed.approvals[0].start)
        self.assertEqual(parsed.approvals[0].coarse_period, "上午")


if __name__ == "__main__":
    unittest.main()
