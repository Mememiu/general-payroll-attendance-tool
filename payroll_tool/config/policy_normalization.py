"""Backward-compatible normalization for persisted HR policy snapshots."""

from copy import deepcopy
from collections.abc import Mapping


def normalize_policy(snapshot: object) -> object:
    """Return a detached canonical draft without inventing business rules."""
    if not isinstance(snapshot, Mapping):
        return deepcopy(snapshot)
    result = deepcopy(dict(snapshot))
    if "employment_types" in result:
        result["employment_types"] = normalize_employment_types(
            result["employment_types"]
        )
    return result


def normalize_employment_types(value: object) -> object:
    if not isinstance(value, list):
        return deepcopy(value)
    result: list[object] = []
    for item in value:
        if isinstance(item, str):
            result.append({
                "code": item,
                "name": "",
                "payroll_scheme": "",
                "social_insurance_applicable": None,
                "housing_fund_applicable": None,
                "tax_applicable": None,
                "enabled": True,
                "migration_review_required": True,
            })
        else:
            result.append(deepcopy(item))
    return result
