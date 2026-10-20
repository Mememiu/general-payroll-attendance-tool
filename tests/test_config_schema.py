from pathlib import Path
import tempfile
import unittest

from payroll_tool.config.schema import AttendancePolicy, load_company_policy


class CompanyPolicyTests(unittest.TestCase):
    def test_attendance_behavior_flags_default_to_disabled(self):
        policy = AttendancePolicy(
            "09:00", "18:00", "12:00", "13:00", "09:00", "09:00",
            "fixed", 8, {}, {},
        )

        self.assertFalse(policy.late_makeup_allowed)
        self.assertFalse(policy.entry_day_full_attendance)
        self.assertFalse(policy.termination_day_full_attendance)

    def test_new_strategy_fields_do_not_shift_existing_positional_arguments(self):
        policy = AttendancePolicy(
            "09:00", "18:00", "12:00", "13:00", "09:00", "09:00",
            "fixed", 8, {}, {}, "08:00",
        )

        self.assertEqual(policy.earliest_valid_start, "08:00")
        self.assertIsNone(policy.overtime_start_mode)

    def test_synthetic_policy_has_versioned_work_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            _write_synthetic_policy(path)
            policy = load_company_policy(path)

        self.assertEqual(policy.package_id, "synthetic-policy")
        self.assertEqual(policy.version, "1.0.0")
        self.assertEqual(policy.attendance.standard_start, "09:00")
        self.assertEqual(policy.attendance.late_grace_end, "10:30")
        self.assertEqual(policy.attendance.work_mode, "fixed")
        self.assertTrue(policy.attendance.leave_types["compensatory_leave"].counts_as_attendance)
        self.assertFalse(policy.attendance.leave_types["personal_leave"].counts_as_attendance)
        self.assertTrue(policy.attendance.attendance_exemptions["business_trip"].skip_punch_requirement)
        self.assertTrue(policy.income_items["allowance"].taxable)
        self.assertFalse(policy.income_items["allowance"].included_in_social_base)

    def test_policy_rejects_missing_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "attendance_policy.yaml").write_text(
                "package_id: example-cn-fixed-hours\nstandard_start: '09:00'\n",
                encoding="utf-8",
            )
            (path / "payroll_plan.yaml").write_text("income_items: {}\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "version"):
                load_company_policy(path)

    def test_policy_rejects_invalid_time_and_income_item(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "attendance_policy.yaml").write_text(
                "package_id: example-cn-fixed-hours\nversion: 1.0.0\nstandard_start: '9am'\n",
                encoding="utf-8",
            )
            (path / "payroll_plan.yaml").write_text(
                "income_items:\n  custom: {taxable: true}\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "time"):
                load_company_policy(path)

    def test_policy_rejects_leave_type_without_hr_defined_handling(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "attendance_policy.yaml").write_text(
                """package_id: test\nversion: 1\nwork_mode: fixed\ndaily_required_hours: 8\nstandard_start: '09:00'\nstandard_end: '18:30'\nlunch_start: '12:00'\nlunch_end: '13:30'\nlatest_normal_start: '09:15'\nlate_grace_end: '09:30'\nleave_types:\n  annual_leave: {counts_as_attendance: true}\nattendance_exemptions: {}\n""",
                encoding="utf-8",
            )
            (path / "payroll_plan.yaml").write_text(
                "income_items: {allowance: {taxable: true, included_in_social_base: false, included_in_fund_base: false}, bonus: {taxable: true, included_in_social_base: false, included_in_fund_base: false}}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "leave type"):
                load_company_policy(path)


def _write_synthetic_policy(path: Path) -> None:
    path.joinpath("attendance_policy.yaml").write_text(
        """package_id: synthetic-policy
version: 1.0.0
work_mode: fixed
daily_required_hours: 8
standard_start: '09:00'
standard_end: '18:30'
lunch_start: '12:00'
lunch_end: '13:30'
latest_normal_start: '10:15'
late_grace_end: '10:30'
leave_types:
  compensatory_leave:
    counts_as_attendance: true
    affects_perfect_attendance: true
    skip_punch_requirement: true
  personal_leave:
    counts_as_attendance: false
    affects_perfect_attendance: true
    skip_punch_requirement: true
attendance_exemptions:
  business_trip:
    counts_as_attendance: true
    affects_perfect_attendance: false
    skip_punch_requirement: true
""",
        encoding="utf-8",
    )
    path.joinpath("payroll_plan.yaml").write_text(
        """income_items:
  allowance: {taxable: true, included_in_social_base: false, included_in_fund_base: false}
  bonus: {taxable: true, included_in_social_base: false, included_in_fund_base: false}
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
