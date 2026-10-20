"""Resolve explicit approval segments according to HR-defined leave rules."""

from dataclasses import dataclass
from decimal import Decimal

from payroll_tool.attendance.text_parser import ApprovalSegment
from payroll_tool.importers.hr_workbook import LeaveRuleInput
from payroll_tool.models import Segment


@dataclass(frozen=True)
class ResolvedApprovals:
    paid_segments: tuple[Segment, ...]
    absence_segments: tuple[Segment, ...]
    coarse_approvals: tuple[ApprovalSegment, ...]


def resolve_approvals(
    approvals: tuple[ApprovalSegment, ...],
    leave_rules: dict[str, LeaveRuleInput],
    coarse_periods: dict[str, tuple[Segment, ...]] | None = None,
) -> ResolvedApprovals:
    coarse_periods = coarse_periods or {}
    paid: list[Segment] = []
    absence: list[Segment] = []
    coarse: list[ApprovalSegment] = []
    for approval in approvals:
        rule = leave_rules.get(approval.kind)
        if rule is None:
            raise ValueError(f"HR 工作簿未定义审批规则：{approval.kind}")
        if approval.start is None or approval.end is None:
            mapped = coarse_periods.get(approval.coarse_period or "")
            if mapped is None:
                coarse.append(approval)
                continue
            segments = [Segment(approval.kind, item.start, item.end) for item in mapped]
        else:
            segments = [Segment(approval.kind, approval.start, approval.end)]
        if rule.counts_as_attendance and rule.paid_ratio == Decimal("1"):
            paid.extend(segments)
        if rule.counts_as_absence:
            absence.extend(segments)
    return ResolvedApprovals(tuple(paid), tuple(absence), tuple(coarse))
