from datetime import date
from decimal import Decimal
import unittest

from payroll_tool.attendance.batch import calculate_attendance_rows
from payroll_tool.config.schema import AttendancePolicy
from payroll_tool.importers.hr_workbook import LeaveRuleInput


POLICY = AttendancePolicy(
    standard_start="10:00", standard_end="19:30", lunch_start="12:00", lunch_end="13:30",
    latest_normal_start="10:15", late_grace_end="10:30", work_mode="fixed",
    daily_required_hours=8, leave_types={}, attendance_exemptions={},
    entry_day_full_attendance=True,
    overtime_start_mode="审批与正常下班取较晚",
    overtime_minimum_minutes=0,
    overtime_rounding_mode="actual_minutes",
    overtime_cross_midnight_allowed=True,
)


class AttendanceBatchTests(unittest.TestCase):
    def test_rows_are_filtered_by_period_and_aggregated_by_employee(self):
        rows = (
            {"employee_id": "SYN001", "work_date": "2026-08-01", "attendance_text": "正常(10:00),正常(19:30)"},
            {"employee_id": "SYN001", "work_date": "2026-07-31", "attendance_text": "正常(10:00),正常(19:30)"},
        )

        results = calculate_attendance_rows(
            rows, {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31), POLICY, {}
        )

        self.assertEqual(results["SYN001"].effective_hours, Decimal("8"))
        self.assertEqual(results["SYN001"].processed_days, 1)
        self.assertEqual(len(results["SYN001"].attendance_days), 1)
        self.assertFalse(results["SYN001"].has_leave)
        self.assertEqual(results["SYN001"].leave_hours, {})

    def test_unknown_employee_is_rejected(self):
        rows = ({"employee_id": "UNKNOWN", "work_date": "2026-08-01", "attendance_text": ""},)

        with self.assertRaisesRegex(ValueError, "UNKNOWN"):
            calculate_attendance_rows(
                rows, {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31), POLICY, {}
            )

    def test_entry_day_without_attendance_is_added_as_full_day(self):
        results = calculate_attendance_rows(
            (), {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31), POLICY, {},
            employee_periods={"SYN001": (date(2026, 8, 5), None)},
        )

        self.assertEqual(results["SYN001"].processed_days, 1)
        self.assertEqual(results["SYN001"].effective_hours, Decimal("8"))

    def test_attendance_outside_employment_period_is_ignored(self):
        rows = (
            {"employee_id": "SYN001", "work_date": "2026-08-04", "attendance_text": "正常(10:00),正常(19:30)"},
            {"employee_id": "SYN001", "work_date": "2026-08-05", "attendance_text": "正常(10:00),正常(19:30)"},
            {"employee_id": "SYN001", "work_date": "2026-08-06", "attendance_text": "正常(10:00),正常(19:30)"},
        )

        results = calculate_attendance_rows(
            rows, {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31), POLICY, {},
            employee_periods={"SYN001": (date(2026, 8, 5), date(2026, 8, 5))},
        )

        self.assertEqual(results["SYN001"].processed_days, 1)

    def test_entry_day_punch_anomaly_is_full_day_when_there_is_no_leave(self):
        rows = (
            {"employee_id": "SYN001", "work_date": "2026-08-05", "attendance_text": "缺卡(-),正常(16:00)", "workday_type": "holiday"},
        )

        results = calculate_attendance_rows(
            rows, {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31), POLICY, {},
            employee_periods={"SYN001": (date(2026, 8, 5), None)},
        )

        summary = results["SYN001"]
        self.assertEqual(summary.effective_hours, Decimal("8"))
        self.assertEqual(summary.absence_hours, Decimal("0"))
        self.assertEqual(summary.review_reasons, ())
        self.assertEqual(summary.attendance_days[0].workday_type, "holiday")

    def test_entry_day_leave_is_calculated_instead_of_forced_full_day(self):
        rows = (
            {"employee_id": "SYN001", "work_date": "2026-08-05", "attendance_text": "病假(全天)"},
        )
        rules = {"病假": LeaveRuleInput(Decimal("0.7"), False, True, True, True)}

        results = calculate_attendance_rows(
            rows, {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31), POLICY, rules,
            employee_periods={"SYN001": (date(2026, 8, 5), None)},
        )

        summary = results["SYN001"]
        self.assertEqual(summary.absence_hours, Decimal("8"))
        self.assertEqual(summary.leave_hours["病假"], Decimal("8"))

    def test_overtime_hours_are_aggregated_separately(self):
        rows = (
            {"employee_id": "SYN001", "work_date": "2026-08-01", "attendance_text": "正常(10:00),正常(19:30);加班(19:30-00:30)"},
        )
        rules = {"加班": LeaveRuleInput(Decimal("1"), True, False, False, True)}

        results = calculate_attendance_rows(
            rows, {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31), POLICY, rules
        )

        self.assertEqual(results["SYN001"].overtime_hours, Decimal("5"))

    def test_recognized_overtime_accrues_configured_comp_time(self):
        rows = ({
            "employee_id": "SYN001",
            "work_date": "2026-08-01",
            "attendance_text": "正常(10:00),正常(21:30);加班(19:30-21:30)",
            "workday_type": "workday",
        },)
        rules = {"加班": LeaveRuleInput(Decimal("1"), True, False, False, True)}

        summary = calculate_attendance_rows(
            rows, {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31),
            POLICY, rules, comp_time_ratio=Decimal("1.5"),
        )["SYN001"]

        self.assertEqual(summary.raw_overtime_minutes, Decimal("120"))
        self.assertEqual(summary.overtime_minutes, Decimal("120"))
        self.assertEqual(summary.comp_time_accrual_minutes, Decimal("180"))
        self.assertEqual(summary.overtime_hours, Decimal("2"))
        self.assertEqual(summary.attendance_days[0].workday_type, "workday")
        self.assertEqual(summary.attendance_days[0].overtime_minutes, Decimal("120"))

    def test_comp_time_uses_only_recognized_overtime_minutes(self):
        policy = AttendancePolicy(
            **{
                **POLICY.__dict__,
                "overtime_minimum_minutes": 45,
                "overtime_rounding_mode": "up_30",
            }
        )
        rows = ({
            "employee_id": "SYN001",
            "work_date": "2026-08-01",
            "attendance_text": "正常(10:00),正常(20:14);加班(19:30-20:14)",
            "workday_type": "rest_day",
        },)
        rules = {"加班": LeaveRuleInput(Decimal("1"), True, False, False, True)}

        summary = calculate_attendance_rows(
            rows, {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31),
            policy, rules, comp_time_ratio=Decimal("1.5"),
        )["SYN001"]

        self.assertEqual(summary.raw_overtime_minutes, Decimal("44"))
        self.assertEqual(summary.overtime_minutes, Decimal("0"))
        self.assertEqual(summary.comp_time_accrual_minutes, Decimal("0.0"))

    def test_noncanonical_workday_type_is_rejected(self):
        rows = ({
            "employee_id": "SYN001", "work_date": "2026-08-01",
            "attendance_text": "正常(10:00),正常(19:30)",
            "workday_type": "休息日",
        },)

        with self.assertRaisesRegex(ValueError, "workday_type"):
            calculate_attendance_rows(
                rows, {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31), POLICY, {}
            )

    def test_absence_leave_becomes_payroll_coverage_with_paid_ratio(self):
        rows = ({"employee_id": "SYN001", "work_date": "2026-08-01", "attendance_text": "病假(全天)"},)
        rules = {"病假": LeaveRuleInput(Decimal("0.7"), False, True, True, True)}

        results = calculate_attendance_rows(
            rows, {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31), POLICY, rules
        )

        summary = results["SYN001"]
        self.assertEqual(summary.absence_hours, Decimal("8"))
        self.assertEqual(summary.attendance_days[0].effective_hours, Decimal("8"))
        self.assertEqual(
            summary.attendance_days[0].leave_adjustments,
            (("病假", Decimal("2.0"), Decimal("0.7")), ("病假", Decimal("6.0"), Decimal("0.7"))),
        )
        self.assertTrue(summary.has_leave)
        self.assertEqual(summary.leave_hours["病假"], Decimal("8"))


if __name__ == "__main__":
    unittest.main()
