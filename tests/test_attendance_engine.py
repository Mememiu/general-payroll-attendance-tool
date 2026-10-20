import unittest
from dataclasses import replace

from payroll_tool.attendance.engine import (
    calculate_day,
    infer_checkout_boundary,
    resolve_offsite_segment,
)
from payroll_tool.config.schema import AttendancePolicy
from payroll_tool.models import Segment


POLICY = AttendancePolicy(
    standard_start="10:00",
    standard_end="19:30",
    lunch_start="12:00",
    lunch_end="13:30",
    latest_normal_start="10:15",
    late_grace_end="10:30",
    work_mode="fixed",
    daily_required_hours=8.0,
    leave_types={},
    attendance_exemptions={},
    grace_checkout="19:45",
)

FLEXIBLE_POLICY = AttendancePolicy(
    standard_start="09:00",
    standard_end="18:30",
    lunch_start="12:00",
    lunch_end="13:30",
    latest_normal_start="09:15",
    late_grace_end="09:30",
    work_mode="flexible",
    daily_required_hours=8.0,
    leave_types={},
    attendance_exemptions={},
)


class AttendanceEngineTests(unittest.TestCase):
    def test_external_work_and_onsite_work_are_not_double_counted(self):
        day = calculate_day(
            arrival="10:00",
            departure="19:30",
            paid_segments=[Segment("external", "10:00", "11:30")],
            onsite_segments=[Segment("onsite", "11:30", "19:30")],
            policy=POLICY,
        )

        self.assertEqual(day.effective_hours, 8.0)
        self.assertEqual(day.absence_hours, 0.0)

    def test_gap_after_external_work_is_absent_after_lunch_is_removed(self):
        day = calculate_day(
            arrival=None,
            departure="19:30",
            paid_segments=[Segment("external", "10:00", "11:30")],
            onsite_segments=[Segment("onsite", "14:30", "19:30")],
            policy=POLICY,
        )

        self.assertEqual(day.effective_hours, 6.5)
        self.assertEqual(day.absence_hours, 1.5)

    def test_arrival_in_grace_window_can_make_up_time_at_policy_boundary(self):
        policy = replace(
            POLICY,
            late_makeup_allowed=True,
            grace_checkout="19:58",
        )
        day = calculate_day(
            arrival="10:28",
            departure="19:58",
            policy=policy,
        )

        self.assertEqual(day.late_hours, 0.0)
        self.assertEqual(day.effective_hours, 8.0)
        self.assertEqual(day.absence_hours, 0.0)

    def test_arrival_after_grace_remains_late_even_when_leaving_late(self):
        day = calculate_day(
            arrival="10:37",
            departure="21:17",
            policy=POLICY,
        )

        self.assertAlmostEqual(day.late_hours, 37 / 60)
        self.assertAlmostEqual(day.effective_hours, 8 - 37 / 60)
        self.assertAlmostEqual(day.absence_hours, 37 / 60)

    def test_hr_configured_grace_checkout_boundary_is_used(self):
        policy = replace(POLICY, late_makeup_allowed=True, grace_checkout="20:00")

        day = calculate_day(arrival="10:28", departure="19:50", policy=policy)

        self.assertAlmostEqual(day.absence_hours, 8 / 60)

    def test_fixed_checkout_mode_does_not_apply_early_arrival_rule(self):
        policy = replace(POLICY, checkout_boundary_mode="固定标准下班")

        day = calculate_day(arrival="09:00", departure="18:30", policy=policy)

        self.assertEqual(day.absence_hours, 1.0)

    def test_fixed_hours_do_not_infer_early_checkout_without_explicit_strategy(self):
        policy = replace(POLICY, checkout_boundary_mode=None)

        day = calculate_day(arrival="09:00", departure="18:30", policy=policy)

        self.assertEqual(day.effective_hours, 7.0)
        self.assertEqual(day.absence_hours, 1.0)

    def test_fixed_hours_keep_standard_checkout_after_early_arrival(self):
        policy = replace(POLICY, checkout_boundary_mode="固定标准下班")

        day = calculate_day(arrival="09:00", departure="19:30", policy=policy)

        self.assertEqual(day.effective_hours, 8.0)
        self.assertEqual(day.absence_hours, 0.0)

    def test_blank_grace_checkout_adds_zero_minutes(self):
        policy = replace(
            POLICY,
            checkout_boundary_mode="按到岗推算",
            grace_checkout=None,
            late_makeup_allowed=True,
        )

        self.assertEqual(infer_checkout_boundary("10:28", policy), "19:30")

    def test_fixed_policy_uses_exact_hr_daily_hours_as_target(self):
        policy = replace(
            POLICY,
            standard_start="09:12",
            standard_end="17:30",
            lunch_start="12:00",
            lunch_end="13:30",
            daily_required_hours=6.8,
            checkout_boundary_mode="固定标准下班",
        )

        day = calculate_day(arrival="09:12", departure="17:30", policy=policy)

        self.assertEqual(day.effective_hours, 6.8)
        self.assertEqual(day.absence_hours, 0.0)

    def test_absence_is_capped_at_hr_daily_work_duration(self):
        policy = replace(
            POLICY,
            daily_required_hours=6.8,
            full_day_absence_after_hours=None,
        )

        day = calculate_day(arrival="19:30", departure="20:00", policy=policy)

        self.assertEqual(day.effective_hours, 0.0)
        self.assertEqual(day.absence_hours, 6.8)

    def test_grace_checkout_before_standard_checkout_is_ignored(self):
        policy = replace(
            POLICY,
            late_makeup_allowed=True,
            grace_checkout="18:00",
        )

        self.assertEqual(infer_checkout_boundary("10:28", policy), "19:30")

    def test_hr_configured_late_threshold_can_mark_a_full_day_absence(self):
        policy = replace(POLICY, full_day_absence_after_hours=2.0)

        day = calculate_day(arrival="12:31", departure="19:30", policy=policy)

        self.assertEqual(day.effective_hours, 0.0)
        self.assertEqual(day.absence_hours, 8.0)

    def test_paid_leave_is_attendance_coverage(self):
        day = calculate_day(
            arrival="13:30",
            departure="19:30",
            paid_segments=[Segment("compensatory_leave", "10:00", "12:00")],
            onsite_segments=[Segment("onsite", "13:30", "19:30")],
            policy=POLICY,
        )

        self.assertEqual(day.effective_hours, 8.0)
        self.assertEqual(day.absence_hours, 0.0)

    def test_flexible_policy_uses_required_hours_without_late_penalty(self):
        policy = replace(FLEXIBLE_POLICY, flexible_rule_mode="纯工时弹性")
        day = calculate_day(
            arrival="10:00",
            departure="19:30",
            policy=policy,
        )

        self.assertEqual(day.late_hours, 0.0)
        self.assertEqual(day.effective_hours, 8.0)
        self.assertEqual(day.absence_hours, 0.0)

    def test_flexible_policy_requires_an_explicit_strategy(self):
        with self.assertRaisesRegex(ValueError, "弹性工时策略"):
            calculate_day(
                arrival="09:00",
                departure="18:30",
                policy=FLEXIBLE_POLICY,
            )

    def test_pure_flexible_mode_uses_hours_without_late(self):
        policy = replace(FLEXIBLE_POLICY, flexible_rule_mode="纯工时弹性")

        day = calculate_day(arrival="11:00", departure="20:30", policy=policy)

        self.assertEqual(day.effective_hours, 8.0)
        self.assertEqual(day.late_hours, 0.0)

    def test_latest_arrival_flexible_mode_records_excess_late_minutes(self):
        policy = replace(
            FLEXIBLE_POLICY,
            flexible_rule_mode="最晚到岗限制",
            flexible_latest_start="10:30",
        )

        day = calculate_day(arrival="10:45", departure="20:15", policy=policy)

        self.assertEqual(day.late_hours, 0.25)

    def test_paid_approval_offsets_flexible_latest_arrival_lateness(self):
        policy = replace(
            FLEXIBLE_POLICY,
            flexible_rule_mode="最晚到岗限制",
            flexible_latest_start="10:30",
        )

        day = calculate_day(
            arrival="11:00",
            departure="19:30",
            paid_segments=[Segment("paid_leave", "09:00", "11:00")],
            policy=policy,
        )

        self.assertEqual(day.late_hours, 0.0)
        self.assertEqual(day.absence_hours, 0.0)

    def test_flexible_latest_arrival_lateness_excludes_paid_leave_and_lunch(self):
        policy = replace(
            FLEXIBLE_POLICY,
            flexible_rule_mode="最晚到岗限制",
            flexible_latest_start="10:30",
        )

        day = calculate_day(
            arrival="13:30",
            departure="19:30",
            paid_segments=[Segment("paid_leave", "09:00", "12:00")],
            policy=policy,
        )

        self.assertEqual(day.late_hours, 0.0)
        self.assertEqual(day.absence_hours, 0.0)

    def test_flexible_lateness_is_capped_at_hr_daily_work_duration(self):
        policy = replace(
            FLEXIBLE_POLICY,
            daily_required_hours=6.8,
            flexible_rule_mode="最晚到岗限制",
            flexible_latest_start="10:30",
        )

        day = calculate_day(arrival="19:30", departure="20:00", policy=policy)

        self.assertEqual(day.late_hours, 6.8)
        self.assertEqual(day.absence_hours, 6.8)

    def test_core_time_flexible_mode_counts_uncovered_core_minutes_as_absence(self):
        policy = replace(
            FLEXIBLE_POLICY,
            flexible_rule_mode="核心时段覆盖",
            core_start="10:30",
            core_end="16:30",
        )

        day = calculate_day(arrival="11:00", departure="20:30", policy=policy)

        self.assertEqual(day.effective_hours, 7.5)
        self.assertEqual(day.absence_hours, 0.5)

    def test_core_time_flexible_mode_rejects_reversed_core_interval(self):
        policy = replace(
            FLEXIBLE_POLICY,
            flexible_rule_mode="核心时段覆盖",
            core_start="16:30",
            core_end="10:30",
        )

        with self.assertRaisesRegex(ValueError, "核心时段结束"):
            calculate_day(arrival="09:00", departure="18:30", policy=policy)

    def test_flexible_mode_rejects_reversed_punch_interval(self):
        policy = replace(FLEXIBLE_POLICY, flexible_rule_mode="纯工时弹性")

        with self.assertRaisesRegex(ValueError, "下班时间必须晚于上班时间"):
            calculate_day(arrival="22:00", departure="06:00", policy=policy)

    def test_return_card_inside_external_segment_truncates_only_with_later_checkout(self):
        resolved = resolve_offsite_segment(
            Segment("external", "10:00", "16:30"),
            punch_times=["16:08", "20:23"],
            checkout_time="20:23",
        )

        self.assertEqual(resolved.offsite_segment.end, "16:08")
        self.assertEqual(resolved.onsite_segment, Segment("onsite", "16:08", "20:23"))

    def test_punches_inside_external_segment_do_not_prove_return_without_checkout_after_end(self):
        original = Segment("external", "10:00", "16:30")
        resolved = resolve_offsite_segment(
            original,
            punch_times=["11:56", "11:58"],
            checkout_time="11:58",
        )

        self.assertEqual(resolved.offsite_segment, original)
        self.assertIsNone(resolved.onsite_segment)


if __name__ == "__main__":
    unittest.main()
