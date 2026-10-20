"""Complete, field-addressable validation for HR policy drafts."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
import re

from payroll_tool.config.policy_models import ValidationIssue
from payroll_tool.config.policy_normalization import normalize_policy


TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
PAYROLL_SCHEMES = {
    "full_time_monthly",
    "intern_daily_hourly",
    "conversion_split",
}
EMPLOYEE_EXCEPTION_TYPES = {
    "statutory_enabled", "statutory_tier", "statutory_base_mode", "statutory_fixed_base",
    "housing_fund_enabled", "housing_fund_tier", "housing_fund_base_mode",
    "housing_fund_fixed_base", "commercial_enabled", "commercial_amount",
    "commercial_base", "employment_type", "perfect_attendance_amount",
}


def validate_policy(snapshot: Mapping[str, object]) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    if not isinstance(snapshot, Mapping):
        return (_issue("type", "规则配置必须是对象", "policy"),)
    snapshot = normalize_policy(snapshot)
    assert isinstance(snapshot, Mapping)
    company = _mapping(snapshot.get("company"), "company", issues)
    employment_types = _validate_employment_types(snapshot.get("employment_types"), issues)
    _validate_worktime(company, issues)
    _validate_leaves(company, issues)
    _validate_overtime(company, issues)
    _validate_payroll(company, issues)
    _validate_income_items(company, issues)
    _validate_statutory(snapshot.get("statutory"), employment_types, issues)
    _validate_commercial(snapshot.get("commercial_insurance"), employment_types, issues)
    _validate_employee_exceptions(snapshot, employment_types, issues)
    return tuple(issues)


def _validate_employee_exceptions(
    snapshot: Mapping[str, object], employment_types: set[str], issues: list[ValidationIssue]
) -> None:
    values = snapshot.get("employee_exceptions", [])
    if not isinstance(values, list):
        issues.append(_issue("type", "员工例外必须是列表", "employee_exceptions"))
        return
    statutory = snapshot.get("statutory")
    insurance = statutory.get("insurance", []) if isinstance(statutory, Mapping) else []
    insurance_items = [item for item in insurance if isinstance(item, Mapping)]
    statutory_codes = {str(item.get("code")) for item in insurance_items}
    housing_codes = {
        str(item.get("code")) for item in insurance_items
        if item.get("item_group") == "housing_fund" or item.get("code") == "housing_fund"
    }
    social_codes = statutory_codes - housing_codes
    tiers = {
        (str(item.get("code")), str(item.get("tier_code"))) for item in insurance_items
        if item.get("tier_code") not in (None, "")
    }
    commercial = snapshot.get("commercial_insurance", [])
    commercial_codes = {str(item.get("code")) for item in commercial if isinstance(item, Mapping)}
    intervals: dict[tuple[str, str, str], list[tuple[date, date]]] = {}
    for index, raw in enumerate(values):
        path = f"employee_exceptions[{index}]"
        item = _mapping(raw, path, issues)
        employee_id = _required_text(item, "employee_id", f"{path}.employee_id", issues)
        override_type = _required_text(item, "override_type", f"{path}.override_type", issues)
        if override_type and override_type not in EMPLOYEE_EXCEPTION_TYPES:
            issues.append(_issue("enum", "请选择支持的员工例外类型", f"{path}.override_type"))
        target = _required_text(item, "target_code", f"{path}.target_code", issues)
        enabled = _required_bool(item, "enabled", f"{path}.enabled", issues)
        start_text = _required_date(item, "effective_from", f"{path}.effective_from", issues)
        end_text = _optional_date(item.get("effective_to"), f"{path}.effective_to", issues)
        _required_text(item, "reason", f"{path}.reason", issues)
        value = item.get("value")
        if override_type.startswith("statutory_"):
            if target and target not in social_codes:
                issues.append(_issue("reference", "目标法定项目不存在", f"{path}.target_code"))
        elif override_type.startswith("housing_fund_"):
            if target and target not in housing_codes:
                issues.append(_issue("reference", "目标公积金项目不存在", f"{path}.target_code"))
        elif override_type.startswith("commercial_"):
            if target and target not in commercial_codes:
                issues.append(_issue("reference", "目标商业险不存在", f"{path}.target_code"))
        elif override_type == "employment_type":
            if target not in ("", "employment_type"):
                issues.append(_issue("reference", "用工类型覆盖目标必须是 employment_type", f"{path}.target_code"))
            if value not in employment_types:
                issues.append(_issue("reference", "目标用工类型不存在或未启用", f"{path}.value"))
        elif override_type == "perfect_attendance_amount" and target not in ("", "perfect_attendance"):
            issues.append(_issue("reference", "全勤奖覆盖目标必须是 perfect_attendance", f"{path}.target_code"))
        if override_type.endswith("_enabled"):
            if not isinstance(value, bool):
                issues.append(_issue("type", "启用覆盖值必须选择是或否", f"{path}.value"))
        elif override_type.endswith("_base_mode"):
            if value not in {"fixed", "salary_full", "company_default"}:
                issues.append(_issue("enum", "请选择有效的基数模式", f"{path}.value"))
        elif override_type.endswith("_tier") or override_type == "employment_type":
            if not isinstance(value, str) or not value.strip():
                issues.append(_issue("required", "请填写覆盖值", f"{path}.value"))
            elif override_type.endswith("_tier") and (target, value) not in tiers:
                issues.append(_issue("reference", "目标项目不存在该档位", f"{path}.value"))
        elif override_type in EMPLOYEE_EXCEPTION_TYPES:
            _non_negative_decimal(value, f"{path}.value", issues)
        else:
            if value in (None, ""):
                issues.append(_issue("required", "请填写覆盖值", f"{path}.value"))
        if start_text and end_text and end_text < start_text:
            issues.append(_issue("range", "失效日不能早于生效日", f"{path}.effective_to"))
        if enabled is True and employee_id and override_type in EMPLOYEE_EXCEPTION_TYPES and target and start_text:
            start = date.fromisoformat(start_text)
            end = date.fromisoformat(end_text) if end_text else date.max
            key = (employee_id, override_type, target)
            if any(start <= previous_end and previous_start <= end for previous_start, previous_end in intervals.get(key, [])):
                issues.append(_issue("overlap", "同一员工和覆盖项目的生效区间不能重叠", f"{path}.effective_from"))
            intervals.setdefault(key, []).append((start, end))


def _validate_worktime(company: Mapping[str, object], issues: list[ValidationIssue]) -> None:
    worktime = _mapping(company.get("worktime"), "company.worktime", issues)
    mode = _required_text(worktime, "mode", "company.worktime.mode", issues)
    if mode and mode not in {"fixed", "flexible"}:
        issues.append(_issue("enum", "请选择固定工时或弹性工时", "company.worktime.mode"))
    daily = worktime.get("daily_minutes")
    if isinstance(daily, bool) or not isinstance(daily, int) or daily <= 0:
        issues.append(
            _issue("range", "每日标准工时必须是大于 0 的整数分钟", "company.worktime.daily_minutes")
        )
    lunch = _mapping(worktime.get("lunch"), "company.worktime.lunch", issues)
    lunch_enabled = _required_bool(
        lunch, "enabled", "company.worktime.lunch.enabled", issues
    )
    lunch_times: tuple[int, int] | None = None
    if lunch_enabled:
        lunch_times = _time_range(
            lunch,
            "start",
            "end",
            "company.worktime.lunch",
            issues,
            "午休",
        )
    working = _time_range(
        worktime,
        "standard_start",
        "standard_end",
        "company.worktime",
        issues,
        "名义上下班",
    )
    if working and lunch_times and not (
        working[0] <= lunch_times[0] < lunch_times[1] <= working[1]
    ):
        issues.append(
            _issue("range", "午休必须位于名义上下班区间内", "company.worktime.lunch.start")
        )
    if mode == "fixed":
        if working and isinstance(daily, int) and not isinstance(daily, bool):
            available = working[1] - working[0]
            if lunch_times:
                available -= lunch_times[1] - lunch_times[0]
            if daily > available:
                issues.append(
                    _issue(
                        "range",
                        "每日标准工时不能超过上下班区间扣除午休后的分钟数",
                        "company.worktime.daily_minutes",
                    )
                )
    elif mode == "flexible":
        strategy = _required_text(
            worktime, "strategy", "company.worktime.strategy", issues
        )
        if strategy and strategy not in {"work_hours", "latest_start", "core_hours"}:
            issues.append(_issue("enum", "请选择有效的弹性工时策略", "company.worktime.strategy"))
        if strategy == "latest_start":
            _required_time(worktime, "latest_start", "company.worktime.latest_start", issues)
        if strategy == "core_hours":
            _time_range(
                worktime,
                "core_start",
                "core_end",
                "company.worktime",
                issues,
                "核心时段",
            )


def _validate_leaves(company: Mapping[str, object], issues: list[ValidationIssue]) -> None:
    leaves = company.get("leaves")
    if not isinstance(leaves, list):
        issues.append(_issue("required", "请配置假勤类型", "company.leaves"))
        return
    seen: set[str] = set()
    seen_names: set[str] = set()
    for index, value in enumerate(leaves):
        path = f"company.leaves[{index}]"
        rule = _mapping(value, path, issues)
        code = _required_text(rule, "code", f"{path}.code", issues)
        if code and not CODE_RE.fullmatch(code):
            issues.append(_issue("format", "编码只能使用小写字母、数字和下划线", f"{path}.code"))
        if code in seen:
            issues.append(_issue("duplicate", "假勤编码不能重复", f"{path}.code"))
        if code:
            seen.add(code)
        name = _required_text(rule, "name", f"{path}.name", issues)
        if name in seen_names:
            issues.append(_issue("duplicate", "假勤名称不能重复", f"{path}.name"))
        if name:
            seen_names.add(name)
        enabled = _required_bool(rule, "enabled", f"{path}.enabled", issues)
        if enabled is False:
            continue
        category = _required_text(rule, "category", f"{path}.category", issues)
        if category and category not in {"leave", "attendance", "overtime", "other"}:
            issues.append(_issue("enum", "请选择有效的假勤分类", f"{path}.category"))
        pay_scheme = _required_text(rule, "pay_scheme", f"{path}.pay_scheme", issues)
        if pay_scheme == "ratio":
            _rate(rule.get("pay_ratio"), f"{path}.pay_ratio", issues)
        elif pay_scheme == "fixed_deduction":
            _non_negative_decimal(
                rule.get("fixed_deduction_amount"),
                f"{path}.fixed_deduction_amount",
                issues,
            )
        elif pay_scheme == "formula":
            formula = _required_text(rule, "formula_id", f"{path}.formula_id", issues)
            if formula and formula not in {"hourly_salary_ratio", "daily_salary_ratio"}:
                issues.append(_issue("enum", "请选择支持的假勤计薪公式", f"{path}.formula_id"))
            parameters = _mapping(
                rule.get("formula_parameters"), f"{path}.formula_parameters", issues
            )
            _non_negative_decimal(
                parameters.get("multiplier"),
                f"{path}.formula_parameters.multiplier",
                issues,
            )
        elif pay_scheme not in {"full_pay", "unpaid"} and pay_scheme:
            issues.append(_issue("enum", "请选择有效的计薪方案", f"{path}.pay_scheme"))
        for field in (
            "counts_as_attendance",
            "counts_as_absence",
            "affects_perfect_attendance",
            "skip_punch_requirement",
            "cross_day_allowed",
        ):
            _required_bool(rule, field, f"{path}.{field}", issues)
        proof_required = _required_bool(
            rule, "proof_required", f"{path}.proof_required", issues
        )
        if proof_required:
            proof_action = _required_text(
                rule, "missing_proof_action", f"{path}.missing_proof_action", issues
            )
            if proof_action and proof_action not in {"review", "unpaid", "reject"}:
                issues.append(_issue("enum", "请选择缺少证明时的处理方式", f"{path}.missing_proof_action"))
        deduction = _required_text(
            rule, "deduction_category", f"{path}.deduction_category", issues
        )
        if deduction and deduction not in {"none", "attendance", "sick", "other"}:
            issues.append(_issue("enum", "请选择有效的扣款归类", f"{path}.deduction_category"))


def _validate_overtime(company: Mapping[str, object], issues: list[ValidationIssue]) -> None:
    overtime = _mapping(company.get("overtime"), "company.overtime", issues)
    enabled = _required_bool(overtime, "enabled", "company.overtime.enabled", issues)
    cash = _required_bool(overtime, "cash_enabled", "company.overtime.cash_enabled", issues)
    comp = _required_bool(
        overtime, "comp_time_enabled", "company.overtime.comp_time_enabled", issues
    )
    if enabled is False:
        if cash is True:
            issues.append(_issue(
                "conflict", "关闭加班时不能开启现金加班费",
                "company.overtime.cash_enabled",
            ))
        if comp is True:
            issues.append(_issue(
                "conflict", "关闭加班时不能开启调休转换",
                "company.overtime.comp_time_enabled",
            ))
        return
    if enabled is not True:
        return
    _required_bool(overtime, "approval_required", "company.overtime.approval_required", issues)
    _required_bool(
        overtime,
        "cross_midnight_allowed",
        "company.overtime.cross_midnight_allowed",
        issues,
    )
    minimum = overtime.get("minimum_minutes")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0:
        issues.append(_issue("range", "最小加班分钟必须是不小于 0 的整数", "company.overtime.minimum_minutes"))
    rounding = _required_text(
        overtime, "rounding_mode", "company.overtime.rounding_mode", issues
    )
    if rounding and rounding not in {"actual_minutes", "down_30", "up_30"}:
        issues.append(_issue("enum", "请选择有效的加班取整方式", "company.overtime.rounding_mode"))
    start_mode = _required_text(
        overtime, "start_mode", "company.overtime.start_mode", issues
    )
    if start_mode and start_mode not in {
        "approval_start",
        "after_normal_end",
        "later_of_approval_and_normal_end",
    }:
        issues.append(_issue("enum", "请选择有效的加班起算方式", "company.overtime.start_mode"))
    if cash:
        formula = _required_text(
            overtime, "cash_formula", "company.overtime.cash_formula", issues
        )
        if formula and formula not in {"hourly_rate_multiplier", "fixed_hourly_rate"}:
            issues.append(_issue("enum", "请选择支持的加班费公式", "company.overtime.cash_formula"))
        _positive_decimal(overtime.get("cash_rate"), "company.overtime.cash_rate", issues)
        day_rates = _mapping(overtime.get("day_rates"), "company.overtime.day_rates", issues)
        required_day_types = {"workday", "rest_day", "holiday"}
        if set(day_rates) != required_day_types:
            issues.append(_issue(
                "keys",
                "加班工作日类型倍率只能包含工作日、休息日和法定节假日",
                "company.overtime.day_rates",
            ))
        for day_type in ("workday", "rest_day", "holiday"):
            _positive_decimal(
                day_rates.get(day_type), f"company.overtime.day_rates.{day_type}", issues
            )
    if comp:
        _positive_decimal(
            overtime.get("comp_time_ratio"), "company.overtime.comp_time_ratio", issues
        )


def _validate_payroll(company: Mapping[str, object], issues: list[ValidationIssue]) -> None:
    payroll = _mapping(company.get("payroll"), "company.payroll", issues)
    _positive_decimal(payroll.get("monthly_pay_days"), "company.payroll.monthly_pay_days", issues)
    _non_negative_decimal(
        payroll.get("perfect_attendance_award"),
        "company.payroll.perfect_attendance_award",
        issues,
    )
    places = payroll.get("rounding_places")
    if isinstance(places, bool) or not isinstance(places, int) or not 0 <= places <= 4:
        issues.append(_issue("range", "金额小数位必须是 0 到 4 的整数", "company.payroll.rounding_places"))
    rounding = _required_text(payroll, "rounding_mode", "company.payroll.rounding_mode", issues)
    if rounding and rounding not in {"half_up", "half_even", "down", "up"}:
        issues.append(_issue("enum", "请选择有效的金额舍入方式", "company.payroll.rounding_mode"))


def _validate_income_items(
    company: Mapping[str, object], issues: list[ValidationIssue]
) -> None:
    values = _mapping(company.get("income_items"), "company.income_items", issues)
    for code in ("allowance", "bonus"):
        path = f"company.income_items.{code}"
        item = _mapping(values.get(code), path, issues)
        for field in (
            "taxable",
            "included_in_social_base",
            "included_in_fund_base",
        ):
            _required_bool(item, field, f"{path}.{field}", issues)


def _validate_statutory(
    value: object, employment_types: set[str], issues: list[ValidationIssue]
) -> None:
    statutory = _mapping(value, "statutory", issues)
    tax = _mapping(statutory.get("tax"), "statutory.tax", issues)
    tax_enabled = _required_bool(tax, "enabled", "statutory.tax.enabled", issues)
    if tax_enabled:
        system = _required_text(tax, "system", "statutory.tax.system", issues)
        if system and system != "cn_cumulative_withholding":
            issues.append(_issue("enum", "请选择支持的计税制度", "statutory.tax.system"))
        _non_negative_decimal(tax.get("monthly_exemption"), "statutory.tax.monthly_exemption", issues)
        mode = _required_text(tax, "negative_tax_mode", "statutory.tax.negative_tax_mode", issues)
        if mode and mode not in {"zero", "carry_forward"}:
            issues.append(_issue("enum", "请选择负税额处理方式", "statutory.tax.negative_tax_mode"))
        _required_date(tax, "effective_from", "statutory.tax.effective_from", issues)
        brackets = tax.get("brackets")
        if not isinstance(brackets, list) or not brackets:
            issues.append(_issue("required", "请填写累计预扣税率表", "statutory.tax.brackets"))
        else:
            previous: Decimal | None = None
            for index, raw in enumerate(brackets):
                path = f"statutory.tax.brackets[{index}]"
                bracket = _mapping(raw, path, issues)
                threshold = _non_negative_decimal(bracket.get("threshold"), f"{path}.threshold", issues)
                _rate(bracket.get("rate"), f"{path}.rate", issues)
                _non_negative_decimal(
                    bracket.get("quick_deduction"), f"{path}.quick_deduction", issues
                )
                if threshold is not None and previous is not None and threshold <= previous:
                    issues.append(_issue("range", "税率档位起点必须递增", f"{path}.threshold"))
                if threshold is not None:
                    previous = threshold
                if index == 0 and threshold is not None and threshold != 0:
                    issues.append(_issue("range", "税率表首档起点必须为 0", f"{path}.threshold"))
    insurance = statutory.get("insurance")
    if not isinstance(insurance, list):
        issues.append(_issue("required", "请配置五险和公积金险种", "statutory.insurance"))
        return
    seen: set[tuple[str, str]] = set()
    for index, value in enumerate(insurance):
        path = f"statutory.insurance[{index}]"
        item = _mapping(value, path, issues)
        code = _required_text(item, "code", f"{path}.code", issues)
        _required_text(item, "name", f"{path}.name", issues)
        enabled = _required_bool(item, "enabled", f"{path}.enabled", issues)
        if not enabled:
            continue
        tier = _required_text(item, "tier_code", f"{path}.tier_code", issues)
        identity = (code, tier)
        if code and tier and identity in seen:
            issues.append(_issue("duplicate", "同一险种的档位编码不能重复", f"{path}.tier_code"))
        if code and tier:
            seen.add(identity)
        _required_text(item, "region", f"{path}.region", issues)
        effective_from = _required_date(
            item, "effective_from", f"{path}.effective_from", issues
        )
        effective_to = ""
        if item.get("effective_to") not in (None, ""):
            effective_to = _required_date(
                item, "effective_to", f"{path}.effective_to", issues
            )
        if effective_from and effective_to and effective_to < effective_from:
            issues.append(
                _issue("range", "失效日不能早于生效日", f"{path}.effective_to")
            )
        _required_text(item, "policy_source", f"{path}.policy_source", issues)
        applicable = _non_empty_string_list(
            item.get("employment_types"), f"{path}.employment_types", issues
        )
        _validate_references(applicable, employment_types, f"{path}.employment_types", issues)
        hire_rule = _required_text(item, "hire_month_rule", f"{path}.hire_month_rule", issues)
        termination_rule = _required_text(
            item, "termination_month_rule", f"{path}.termination_month_rule", issues
        )
        timing_modes = {"always", "never", "cutoff_day"}
        if hire_rule and hire_rule not in timing_modes:
            issues.append(_issue("enum", "请选择入职当月缴纳规则", f"{path}.hire_month_rule"))
        if termination_rule and termination_rule not in timing_modes:
            issues.append(_issue("enum", "请选择离职当月缴纳规则", f"{path}.termination_month_rule"))
        if hire_rule == "cutoff_day":
            _cutoff_day(item.get("hire_cutoff_day"), f"{path}.hire_cutoff_day", issues)
        if termination_rule == "cutoff_day":
            _cutoff_day(
                item.get("termination_cutoff_day"), f"{path}.termination_cutoff_day", issues
            )
        mode = _required_text(item, "base_mode", f"{path}.base_mode", issues)
        if mode and mode not in {"fixed", "salary_full"}:
            issues.append(_issue("enum", "请选择有效的缴费基数模式", f"{path}.base_mode"))
        lower = _non_negative_decimal(item.get("base_lower"), f"{path}.base_lower", issues)
        upper = _non_negative_decimal(item.get("base_upper"), f"{path}.base_upper", issues)
        if lower is not None and upper is not None and lower > upper:
            issues.append(_issue("range", "基数上限不能低于基数下限", f"{path}.base_upper"))
        _rate(item.get("employee_rate"), f"{path}.employee_rate", issues)
        _rate(item.get("employer_rate"), f"{path}.employer_rate", issues)
        if mode == "fixed":
            _non_negative_decimal(item.get("fixed_base"), f"{path}.fixed_base", issues)


def _validate_commercial(
    value: object, employment_types: set[str], issues: list[ValidationIssue]
) -> None:
    if not isinstance(value, list):
        issues.append(_issue("required", "商业保险配置必须是列表", "commercial_insurance"))
        return
    seen: set[str] = set()
    for index, raw in enumerate(value):
        path = f"commercial_insurance[{index}]"
        item = _mapping(raw, path, issues)
        code = _required_text(item, "code", f"{path}.code", issues)
        if code and not CODE_RE.fullmatch(code):
            issues.append(_issue("format", "编码只能使用小写字母、数字和下划线", f"{path}.code"))
        if code in seen:
            issues.append(_issue("duplicate", "商业险编码不能重复", f"{path}.code"))
        if code:
            seen.add(code)
        _required_text(item, "name", f"{path}.name", issues)
        enabled = _required_bool(item, "enabled", f"{path}.enabled", issues)
        if not enabled:
            continue
        _required_text(item, "region", f"{path}.region", issues)
        effective_from = _required_date(item, "effective_from", f"{path}.effective_from", issues)
        effective_to = _optional_date(item.get("effective_to"), f"{path}.effective_to", issues)
        if effective_from and effective_to and effective_to < effective_from:
            issues.append(_issue("range", "失效日不能早于生效日", f"{path}.effective_to"))
        employee_share = _rate(item.get("employee_share"), f"{path}.employee_share", issues)
        employer_share = _rate(item.get("employer_share"), f"{path}.employer_share", issues)
        if (
            employee_share is not None
            and employer_share is not None
            and employee_share + employer_share != Decimal("1")
        ):
            issues.append(
                _issue("range", "个人与单位承担比例合计必须为 1", f"{path}.employer_share")
            )
        _required_bool(item, "taxable", f"{path}.taxable", issues)
        _required_bool(item, "included_in_gross", f"{path}.included_in_gross", issues)
        deduction = _required_text(item, "deduction_mode", f"{path}.deduction_mode", issues)
        if deduction and deduction not in {"payroll_deduction", "company_paid", "reimbursement"}:
            issues.append(_issue("enum", "请选择商业险代扣方式", f"{path}.deduction_mode"))
        method = _required_text(item, "calculation", f"{path}.calculation", issues)
        if method == "fixed_amount":
            _non_negative_decimal(item.get("amount"), f"{path}.amount", issues)
        elif method == "base_rate":
            _rate(item.get("employee_rate"), f"{path}.employee_rate", issues)
            _rate(item.get("employer_rate"), f"{path}.employer_rate", issues)
        elif method:
            issues.append(_issue("enum", "请选择商业险计费方式", f"{path}.calculation"))
        applicable = _non_empty_string_list(
            item.get("employment_types"), f"{path}.employment_types", issues
        )
        _validate_references(applicable, employment_types, f"{path}.employment_types", issues)


def _validate_employment_types(value: object, issues: list[ValidationIssue]) -> set[str]:
    if not isinstance(value, list) or not value:
        issues.append(_issue("required", "请至少配置一种用工类型", "employment_types"))
        return set()
    seen_codes: set[str] = set()
    seen_names: set[str] = set()
    enabled_codes: set[str] = set()
    for index, raw in enumerate(value):
        path = f"employment_types[{index}]"
        item = _mapping(raw, path, issues)
        code = _required_text(item, "code", f"{path}.code", issues)
        if code and not CODE_RE.fullmatch(code):
            issues.append(_issue("format", "编码只能使用小写字母、数字和下划线", f"{path}.code"))
        if code in seen_codes:
            issues.append(_issue("duplicate", "用工类型编码不能重复", f"{path}.code"))
        if code:
            seen_codes.add(code)
        name = _required_text(item, "name", f"{path}.name", issues)
        if name in seen_names:
            issues.append(_issue("duplicate", "用工类型名称不能重复", f"{path}.name"))
        if name:
            seen_names.add(name)
        scheme = _required_text(item, "payroll_scheme", f"{path}.payroll_scheme", issues)
        if scheme and scheme not in PAYROLL_SCHEMES:
            issues.append(_issue("enum", "请选择支持的薪资方案", f"{path}.payroll_scheme"))
        for field in (
            "social_insurance_applicable",
            "housing_fund_applicable",
            "tax_applicable",
        ):
            _required_bool(item, field, f"{path}.{field}", issues)
        enabled = _required_bool(item, "enabled", f"{path}.enabled", issues)
        if item.get("migration_review_required") is True:
            issues.append(
                _issue(
                    "review_required",
                    "旧用工类型需要 HR 补全并确认后才能发布",
                    f"{path}.migration_review_required",
                )
            )
        if enabled is True and code and CODE_RE.fullmatch(code):
            enabled_codes.add(code)
    return enabled_codes


def _mapping(value: object, path: str, issues: list[ValidationIssue]) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    issues.append(_issue("required", "请填写此配置区域", path))
    return {}


def _required_text(
    data: Mapping[str, object], key: str, path: str, issues: list[ValidationIssue]
) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        issues.append(_issue("required", "此项为必填项", path))
        return ""
    return value.strip()


def _required_bool(
    data: Mapping[str, object], key: str, path: str, issues: list[ValidationIssue]
) -> bool | None:
    value = data.get(key)
    if not isinstance(value, bool):
        issues.append(_issue("required", "请明确选择是或否", path))
        return None
    return value


def _required_time(
    data: Mapping[str, object], key: str, path: str, issues: list[ValidationIssue]
) -> int | None:
    value = _required_text(data, key, path, issues)
    if not value:
        return None
    if not TIME_RE.fullmatch(value):
        issues.append(_issue("format", "时间必须使用 HH:MM", path))
        return None
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _time_range(
    data: Mapping[str, object],
    start_key: str,
    end_key: str,
    base_path: str,
    issues: list[ValidationIssue],
    label: str,
) -> tuple[int, int] | None:
    start = _required_time(data, start_key, f"{base_path}.{start_key}", issues)
    end = _required_time(data, end_key, f"{base_path}.{end_key}", issues)
    if start is None or end is None:
        return None
    if start >= end:
        issues.append(_issue("range", f"{label}结束时间必须晚于开始时间", f"{base_path}.{end_key}"))
        return None
    return start, end


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _positive_decimal(
    value: object, path: str, issues: list[ValidationIssue]
) -> Decimal | None:
    result = _decimal(value)
    if result is None or result <= 0:
        issues.append(_issue("range", "请输入大于 0 的数字", path))
        return None
    return result


def _non_negative_decimal(
    value: object, path: str, issues: list[ValidationIssue]
) -> Decimal | None:
    result = _decimal(value)
    if result is None or result < 0:
        issues.append(_issue("range", "请输入不小于 0 的数字", path))
        return None
    return result


def _rate(value: object, path: str, issues: list[ValidationIssue]) -> Decimal | None:
    result = _decimal(value)
    if result is None or not Decimal("0") <= result <= Decimal("1"):
        issues.append(_issue("range", "比例必须在 0 到 1 之间", path))
        return None
    return result


def _required_date(
    data: Mapping[str, object], key: str, path: str, issues: list[ValidationIssue]
) -> str:
    value = _required_text(data, key, path, issues)
    if not value:
        return ""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        issues.append(_issue("format", "日期必须使用 YYYY-MM-DD", path))
        return ""
    if parsed.isoformat() != value:
        issues.append(_issue("format", "日期必须使用 YYYY-MM-DD", path))
        return ""
    return value


def _optional_date(
    value: object, path: str, issues: list[ValidationIssue]
) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        issues.append(_issue("format", "日期必须使用 YYYY-MM-DD", path))
        return ""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        issues.append(_issue("format", "日期必须使用 YYYY-MM-DD", path))
        return ""
    if parsed.isoformat() != value:
        issues.append(_issue("format", "日期必须使用 YYYY-MM-DD", path))
        return ""
    return value


def _non_empty_string_list(
    value: object, path: str, issues: list[ValidationIssue]
) -> list[str]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        issues.append(_issue("required", "请至少选择一项", path))
        return []
    return value


def _validate_references(
    values: list[str], allowed: set[str], path: str, issues: list[ValidationIssue]
) -> None:
    unknown = sorted({value for value in values if value not in allowed})
    if unknown:
        issues.append(
            _issue("reference", f"包含未定义的用工类型：{'、'.join(unknown)}", path)
        )


def _cutoff_day(value: object, path: str, issues: list[ValidationIssue]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 31:
        issues.append(_issue("range", "截止日必须是 1 到 31 的整数", path))


def _issue(code: str, message: str, field: str) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, field=field)
