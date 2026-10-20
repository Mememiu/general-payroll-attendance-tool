# HR Configured Overtime Settlement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply every published HR overtime decision to recognized minutes, cash overtime pay and current-period compensatory-time accrual.

**Architecture:** Add an immutable `OvertimePolicy` to the calculation snapshot, keep duration recognition in the attendance layer, and keep money calculation in the payroll layer. Pass explicit per-day overtime facts through `AttendanceDay`; do not derive workday type from weekday and do not let overtime alter normal attendance coverage.

**Tech Stack:** Python dataclasses, `Decimal`, Flask, openpyxl, unittest, existing policy snapshot and XLSX export pipeline.

---

## File Structure

- `payroll_tool/config/policy_serialization.py`: define and serialize the immutable HR overtime policy.
- `payroll_tool/config/schema.py`: extend attendance-only policy fields needed for recognition.
- `payroll_tool/attendance/daily_pipeline.py`: calculate raw and recognized overtime minutes.
- `payroll_tool/attendance/batch.py`: attach workday type and aggregate recognized time and comp-time accrual.
- `payroll_tool/payroll/engine.py`: calculate cash overtime by employee salary scheme and include it in taxable/gross/net/employer totals.
- `payroll_tool/importers/excel.py`: preserve an optional `workday_type` attendance column.
- `app.py`: map the optional column, pass overtime policy and summary facts, and export audit columns.
- `payroll_tool/export.py`: retain stable column ordering for new overtime fields if this module has an explicit header list.
- `tests/test_policy_serialization.py`: prove HR values survive conversion without defaults.
- `tests/test_overtime_start_modes.py`: prove minimum, rounding and cross-midnight recognition.
- `tests/test_attendance_batch.py`: prove workday facts and comp-time aggregation.
- `tests/test_payroll_engine.py`: prove cash formulas for monthly, intern and converted employees.
- `tests/test_app.py`: prove uploaded data reaches XLSX output end to end.
- `docs/USER_GUIDE.md`, `docs/hr-workbook.md`: document the completed behavior and input column.

### Task 1: Immutable Overtime Policy Contract

**Files:**
- Modify: `payroll_tool/config/policy_serialization.py`
- Modify: `payroll_tool/config/schema.py`
- Modify: `tests/test_policy_serialization.py`

- [ ] **Step 1: Write the failing serialization test**

Add a test that sets non-default values and asserts exact typed output:

```python
def test_overtime_settlement_values_are_preserved_without_defaults(self):
    snapshot = _calculation_policy()
    snapshot["company"]["overtime"].update({
        "enabled": True,
        "start_mode": "approval_start",
        "minimum_minutes": 47,
        "rounding_mode": "up_30",
        "approval_required": True,
        "cross_midnight_allowed": False,
        "cash_enabled": True,
        "cash_formula": "hourly_rate_multiplier",
        "cash_rate": "1.2",
        "day_rates": {"workday": "1.5", "rest_day": "2", "holiday": "3"},
        "comp_time_enabled": True,
        "comp_time_ratio": "1.25",
    })

    result = calculation_policy_from_snapshot(snapshot)

    self.assertEqual(result.overtime.minimum_minutes, 47)
    self.assertEqual(result.overtime.rounding_mode, "up_30")
    self.assertFalse(result.overtime.cross_midnight_allowed)
    self.assertEqual(result.overtime.cash_rate, Decimal("1.2"))
    self.assertEqual(result.overtime.day_rates["holiday"], Decimal("3"))
    self.assertEqual(result.overtime.comp_time_ratio, Decimal("1.25"))
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  tests.test_policy_serialization.PolicyCalculationSerializationTests.test_overtime_settlement_values_are_preserved_without_defaults -v
```

Expected: fail because `CalculationPolicy` has no `overtime` field.

- [ ] **Step 3: Add typed policy objects**

Define:

```python
@dataclass(frozen=True)
class OvertimePolicy:
    enabled: bool
    start_mode: str | None
    minimum_minutes: int | None
    rounding_mode: str | None
    approval_required: bool | None
    cross_midnight_allowed: bool | None
    cash_enabled: bool
    cash_formula: str | None
    cash_rate: Decimal | None
    day_rates: dict[str, Decimal]
    comp_time_enabled: bool
    comp_time_ratio: Decimal | None
```

Add `overtime: OvertimePolicy` to `CalculationPolicy`. Implement `_overtime_policy()` using existing `_required_*` helpers. When disabled, preserve explicit booleans but do not invent a start mode, rate, ratio, minimum or rounding mode. Extend `AttendancePolicy` with only these recognition fields:

```python
overtime_minimum_minutes: int | None = None
overtime_rounding_mode: str | None = None
overtime_approval_required: bool | None = None
overtime_cross_midnight_allowed: bool | None = None
```

- [ ] **Step 4: Run serialization and validation tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  tests.test_policy_serialization tests.test_policy_validation -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add payroll_tool/config/policy_serialization.py payroll_tool/config/schema.py tests/test_policy_serialization.py
git commit -m "Serialize configured overtime settlement"
```

### Task 2: Recognized Overtime Minutes

**Files:**
- Modify: `payroll_tool/attendance/daily_pipeline.py`
- Modify: `tests/test_overtime_start_modes.py`

- [ ] **Step 1: Write failing recognition tests**

Add focused tests for the agreed order:

```python
def test_minimum_is_checked_before_up_rounding(self):
    policy = replace(
        POLICY, overtime_start_mode="审批开始时间",
        overtime_minimum_minutes=45, overtime_rounding_mode="up_30",
        overtime_cross_midnight_allowed=True,
    )
    result = calculate_day_from_text(
        "正常(10:00),正常(20:14);加班(19:30-20:14)", policy, OVERTIME_RULES
    )
    self.assertEqual(result.raw_overtime_minutes, Decimal("44"))
    self.assertEqual(result.overtime_minutes, Decimal("0"))

def test_qualified_minutes_are_rounded_down_after_threshold(self):
    policy = replace(
        POLICY, overtime_start_mode="审批开始时间",
        overtime_minimum_minutes=45, overtime_rounding_mode="down_30",
        overtime_cross_midnight_allowed=True,
    )
    result = calculate_day_from_text(
        "正常(10:00),正常(20:16);加班(19:30-20:16)", policy, OVERTIME_RULES
    )
    self.assertEqual(result.raw_overtime_minutes, Decimal("46"))
    self.assertEqual(result.overtime_minutes, Decimal("30"))

def test_disallowed_cross_midnight_requires_review(self):
    policy = replace(
        POLICY, overtime_start_mode="审批开始时间",
        overtime_minimum_minutes=0, overtime_rounding_mode="actual_minutes",
        overtime_cross_midnight_allowed=False,
    )
    result = calculate_day_from_text(
        "正常(10:00),次日(00:30);加班(23:30-00:30)", policy, OVERTIME_RULES
    )
    self.assertEqual(result.overtime_minutes, Decimal("0"))
    self.assertTrue(any("跨午夜" in reason for reason in result.review_reasons))
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_overtime_start_modes -v
```

Expected: fail because raw/recognized minute fields and rounding do not exist.

- [ ] **Step 3: Implement minute recognition**

Change `DailyPipelineResult` to expose:

```python
raw_overtime_minutes: Decimal = Decimal("0")
overtime_minutes: Decimal = Decimal("0")

@property
def overtime_hours(self) -> Decimal:
    return self.overtime_minutes / Decimal("60")
```

Replace `_overtime_hours()` with `_overtime_minutes()` returning `(raw, recognized, reasons)`. After calculating the raw interval:

```python
if raw < Decimal(policy.overtime_minimum_minutes):
    recognized = Decimal("0")
elif policy.overtime_rounding_mode == "actual_minutes":
    recognized = raw
elif policy.overtime_rounding_mode == "down_30":
    recognized = raw // Decimal("30") * Decimal("30")
elif policy.overtime_rounding_mode == "up_30":
    recognized = ((raw + Decimal("29")) // Decimal("30")) * Decimal("30")
else:
    raise ValueError("HR 加班分钟取整方式无效或未配置")
```

Reject missing recognition configuration whenever an overtime segment exists. Preserve existing start-mode results under `actual_minutes` and a zero minimum.

- [ ] **Step 4: Run daily attendance tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  tests.test_overtime_start_modes tests.test_daily_pipeline -v
```

Expected: all tests pass, including existing cross-midnight boundaries.

- [ ] **Step 5: Commit Task 2**

```bash
git add payroll_tool/attendance/daily_pipeline.py tests/test_overtime_start_modes.py
git commit -m "Apply overtime minimum and rounding rules"
```

### Task 3: Workday Facts and Comp-Time Aggregation

**Files:**
- Modify: `payroll_tool/importers/excel.py`
- Modify: `payroll_tool/attendance/batch.py`
- Modify: `payroll_tool/payroll/engine.py`
- Modify: `tests/test_excel_import.py`
- Modify: `tests/test_attendance_batch.py`

- [ ] **Step 1: Write failing importer and aggregation tests**

Map an optional `workday_type` source column and assert the imported row preserves `rest_day`. Add an aggregation test:

```python
def test_recognized_overtime_accrues_configured_comp_time(self):
    policy = replace(
        POLICY, overtime_minimum_minutes=0,
        overtime_rounding_mode="actual_minutes",
        overtime_cross_midnight_allowed=True,
    )
    rows = ({
        "employee_id": "SYN001", "work_date": "2026-08-01",
        "attendance_text": "正常(10:00),正常(21:30);加班(19:30-21:30)",
        "workday_type": "workday",
    },)
    result = calculate_attendance_rows(
        rows, {"SYN001"}, date(2026, 8, 1), date(2026, 8, 31),
        policy, OVERTIME_RULES, comp_time_ratio=Decimal("1.5"),
    )["SYN001"]
    self.assertEqual(result.overtime_minutes, Decimal("120"))
    self.assertEqual(result.comp_time_accrual_minutes, Decimal("180"))
    self.assertEqual(result.attendance_days[0].workday_type, "workday")
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  tests.test_excel_import tests.test_attendance_batch -v
```

Expected: fail because summaries and `AttendanceDay` do not carry these facts.

- [ ] **Step 3: Extend immutable result facts**

Extend `AttendanceDay`:

```python
workday_type: str | None = None
overtime_minutes: Decimal = Decimal("0")
```

Extend `EmployeeAttendanceSummary` with `raw_overtime_minutes`, `overtime_minutes`, and `comp_time_accrual_minutes`. Validate nonblank workday types against `{"workday", "rest_day", "holiday"}`. Calculate comp time only from recognized minutes:

```python
comp_time = (
    recognized_minutes * comp_time_ratio
    if comp_time_ratio is not None else Decimal("0")
)
```

Keep `overtime_hours` as a compatibility property derived from recognized minutes.

- [ ] **Step 4: Run importer, batch and payroll regression tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  tests.test_excel_import tests.test_attendance_batch tests.test_payroll_engine -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add payroll_tool/importers/excel.py payroll_tool/attendance/batch.py \
  payroll_tool/payroll/engine.py tests/test_excel_import.py tests/test_attendance_batch.py
git commit -m "Aggregate overtime and comp time facts"
```

### Task 4: Cash Overtime Pay

**Files:**
- Modify: `payroll_tool/payroll/engine.py`
- Modify: `tests/test_payroll_engine.py`

- [ ] **Step 1: Write failing formula tests**

Cover monthly, intern and converted salary sources. A monthly employee example:

```python
def test_monthly_employee_receives_taxable_cash_overtime(self):
    overtime = OvertimePolicy(
        enabled=True, start_mode="after_normal_end", minimum_minutes=0,
        rounding_mode="actual_minutes", approval_required=True,
        cross_midnight_allowed=True, cash_enabled=True,
        cash_formula="hourly_rate_multiplier", cash_rate=Decimal("1"),
        day_rates={"workday": Decimal("1.5"), "rest_day": Decimal("2"),
                   "holiday": Decimal("3")},
        comp_time_enabled=False, comp_time_ratio=None,
    )
    employee = EmployeePayProfile(
        employee_id="S1", employment_type="full_time",
        monthly_salary=Decimal("21750"),
    )
    day = AttendanceDay(
        date(2026, 8, 1), Decimal("8"), workday_type="rest_day",
        overtime_minutes=Decimal("120"),
    )
    result = calculate_payroll(
        employee, [day], income_items=INCOME_ITEMS,
        overtime_policy=overtime,
        daily_required_hours=Decimal("8"), monthly_pay_days=Decimal("21.75"),
    )
    self.assertEqual(result.overtime_pay, Decimal("500.00"))
    self.assertEqual(result.gross_pay, result.base_pay + Decimal("500.00"))
    self.assertEqual(result.taxable_income, result.base_pay + Decimal("500.00"))
```

Use policy values `cash_formula="hourly_rate_multiplier"`, `cash_rate=1`, and `rest_day=2`; hourly pay is `21750 / 21.75 / 8 = 125`, so two hours produce 500. Add tests proving intern overtime uses `intern_hourly_rate`, converted employees select the rate by work date, disabled cash produces zero, and missing workday type raises an explicit review error.

- [ ] **Step 2: Run payroll tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_payroll_engine -v
```

Expected: fail because overtime pay is fixed at zero.

- [ ] **Step 3: Implement cash formulas**

Add `overtime_policy: OvertimePolicy | None = None` to `calculate_payroll()`. Sum per-day pay only when cash is enabled:

```python
hours = day.overtime_minutes / Decimal("60")
day_rate = overtime_policy.day_rates[day.workday_type]
if overtime_policy.cash_formula == "hourly_rate_multiplier":
    amount = hours * _hourly_pay(...) * overtime_policy.cash_rate * day_rate
elif overtime_policy.cash_formula == "fixed_hourly_rate":
    amount = hours * overtime_policy.cash_rate * day_rate
else:
    raise ValueError("unsupported overtime cash formula")
```

Add overtime pay to `taxable_income`, `gross_pay`, `net_pay`, and `total_employer_cost`. Do not add it to social or housing-fund base income. Apply `_money()` only to final result fields.

- [ ] **Step 4: Run payroll and tax tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  tests.test_payroll_engine tests.test_cumulative_tax tests.test_commercial_insurance -v
```

Expected: all tests pass and cash overtime changes only intended totals.

- [ ] **Step 5: Commit Task 4**

```bash
git add payroll_tool/payroll/engine.py tests/test_payroll_engine.py
git commit -m "Calculate configured cash overtime pay"
```

### Task 5: Application Wiring and XLSX Audit Output

**Files:**
- Modify: `app.py`
- Modify: `payroll_tool/export.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing end-to-end test**

Create a published rule with a 45-minute minimum, actual-minute rounding, cash enabled and comp-time ratio 1.5. Upload attendance containing `工作日类型=休息日` and a two-hour approved segment. Assert the output contains:

```python
for name in (
    "raw_overtime_hours", "overtime_hours", "overtime_pay",
    "comp_time_accrual_minutes",
):
    self.assertIn(name, headers)
self.assertEqual(row[headers.index("overtime_hours")], 2)
self.assertEqual(row[headers.index("comp_time_accrual_minutes")], 180)
self.assertGreater(row[headers.index("overtime_pay")], 0)
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  tests.test_app.AppTests.test_task_exports_configured_overtime_settlement -v
```

Expected: fail because policy, workday type and settlement facts are not wired.

- [ ] **Step 3: Wire the published policy path**

For App-configured policies, add the optional mapping when the uploaded workbook contains the column, or include it in the fixed map when cash is enabled:

```python
attendance_mapping = {
    "employee_id": "工号",
    "work_date": "日期",
    "attendance_text": "每日考勤结果",
    "workday_type": "工作日类型",
}
```

Accept Chinese values `工作日`, `休息日`, `法定节假日` at the App boundary and normalize them to canonical codes. Pass `calculation_policy.overtime` to batch and payroll calculations. For cash-enabled policies, a day with recognized overtime but no valid type becomes a review item and produces no automatic cash amount; it must not silently use a multiplier.

Add export values:

```python
"raw_overtime_hours": summary.raw_overtime_minutes / Decimal("60"),
"overtime_hours": summary.overtime_minutes / Decimal("60"),
"comp_time_accrual_minutes": summary.comp_time_accrual_minutes,
```

- [ ] **Step 4: Run application and export tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest \
  tests.test_app tests.test_export tests.test_policy_serialization -v
```

Expected: all tests pass and downloaded XLSX contains consistent values.

- [ ] **Step 5: Commit Task 5**

```bash
git add app.py payroll_tool/export.py tests/test_app.py
git commit -m "Export configured overtime settlements"
```

### Task 6: HR Guidance and Final Verification

**Files:**
- Modify: `docs/USER_GUIDE.md`
- Modify: `docs/hr-workbook.md`

- [ ] **Step 1: Update HR-facing documentation**

Document these exact points:

- Minimum minutes are checked before rounding.
- `工作日类型` accepts only `工作日`、`休息日`、`法定节假日`.
- Cash-disabled policies keep `overtime_pay=0`.
- Cash and comp time can run together.
- `comp_time_accrual_minutes` is a current-period accrual, not a cross-month balance.
- Overtime does not supplement normal attendance or enter statutory bases.

- [ ] **Step 2: Scan for obsolete limitations and forbidden defaults**

Run:

```bash
rg -n "加班费固定为|调休余额也不会|minimum_minutes.?=.?30|comp_time_ratio.?=.?1" \
  docs app.py payroll_tool templates static
```

Expected: no obsolete limitation and no invented business default.

- [ ] **Step 3: Run the complete suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning \
  -m unittest discover -s tests -q
```

Expected: all tests pass. Run outside the sandbox only for the existing loopback-port test.

- [ ] **Step 4: Verify the UI and output at both viewports**

Use the local App at `1440x900` and `390x844`. Confirm overtime rule fields remain usable, an end-to-end calculation downloads successfully, output columns fit the workbook, no horizontal page overflow exists, and no new console error is emitted.

- [ ] **Step 5: Commit Task 6**

```bash
git add docs/USER_GUIDE.md docs/hr-workbook.md
git commit -m "Document configured overtime settlement"
```

## Completion Checklist

- [ ] Every enabled overtime field configured by HR reaches calculation or produces a precise validation error.
- [ ] Minimum eligibility is evaluated before rounding.
- [ ] Normal attendance and overtime remain separate.
- [ ] Cash overtime is taxable, enters gross/net/employer totals, and does not alter statutory bases.
- [ ] Comp time is exported as current-period accrual only.
- [ ] Original company-specific tool remains untouched.
- [ ] Known unrelated worktree files remain uncommitted.
- [ ] GitHub is not pushed until the user explicitly requests it.
