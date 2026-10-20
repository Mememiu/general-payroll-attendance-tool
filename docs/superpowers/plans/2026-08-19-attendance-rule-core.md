# HR-Configured Attendance Rule Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove hidden company attendance behavior and make fixed hours, flexible modes, daily required hours, grace handling, and overtime start rules execute only from the uploaded HR workbook.

**Architecture:** Extend the typed `AttendancePolicy` and workbook importer with explicit strategy fields. Convert HR's numeric `daily_required_hours` input to an exact whole-minute target, then keep interval merging and comparisons in minutes; fixed and flexible policies become separate strategy branches. Overtime remains separate from normal attendance and reads its start strategy from the same policy.

**Tech Stack:** Python 3.11+, Flask, openpyxl, `dataclasses`, `Decimal`, `unittest`.

---

## Scope And Follow-Up Plans

This plan implements the attendance-rule foundation only. The approved design is intentionally split into later independent plans:

1. Dynamic unlimited leave types and approval timeline, including offsite return integration.
2. Configured payroll formulas using any HR-entered daily work duration, trial periods, and employment types.
3. Overtime pay, compensatory-time conversion, and full-attendance strategies.
4. Social/fund cutoff rules, commercial insurance, and cumulative tax inputs.

## File Responsibilities

- `payroll_tool/config/schema.py`: typed attendance strategy and validation-neutral data model.
- `payroll_tool/templates/hr_workbook.py`: HR-facing fields, dropdowns, conditional completeness checks, and template version.
- `payroll_tool/importers/hr_workbook.py`: strict conversion from workbook values to `AttendancePolicy`.
- `payroll_tool/attendance/engine.py`: real-minute fixed/flexible attendance coverage and absence classification.
- `payroll_tool/attendance/daily_pipeline.py`: overtime start strategy composition.
- `tests/test_hr_workbook.py`: template structure and conditional validation.
- `tests/test_hr_workbook_import.py`: typed strategy parsing.
- `tests/test_attendance_engine.py`: fixed and flexible behavior.
- `tests/test_daily_pipeline.py`: overtime behavior.
- `tests/test_app.py`: complete workbook fixture and upload regression.
- `docs/hr-workbook.md`, `README.md`, `CHANGELOG.md`: HR instructions and migration notice.

### Task 1: Define The Version 1.2 Attendance Strategy Fields

**Files:**
- Modify: `tests/test_hr_workbook.py`
- Modify: `payroll_tool/templates/hr_workbook.py`

- [ ] **Step 1: Write failing template and validation tests**

Add assertions that template `1.2.0` contains the strategy fields and that invalid conditional combinations are rejected:

```python
def test_template_contains_explicit_attendance_strategies(self):
    workbook = load_workbook(BytesIO(build_hr_workbook_template()))
    try:
        base = workbook["基础与考勤"]
        codes = {
            base.cell(row, 1).value
            for row in range(2, base.max_row + 1)
        }
        self.assertEqual(base["C2"].value, "1.2.0")
        self.assertIn("flexible_rule_mode", codes)
        self.assertIn("flexible_latest_start", codes)
        self.assertIn("core_start", codes)
        self.assertIn("core_end", codes)
        self.assertIn("overtime_start_mode", codes)
    finally:
        workbook.close()

def test_flexible_latest_arrival_requires_latest_start(self):
    workbook = load_workbook(BytesIO(_completed_policy_workbook()))
    _set_base(workbook, "work_mode", "弹性工时")
    _set_base(workbook, "flexible_rule_mode", "最晚到岗限制")
    _set_base(workbook, "flexible_latest_start", None)
    report = validate_hr_workbook(_save(workbook), require_complete=True)
    self.assertTrue(any("flexible_latest_start" in item for item in report.errors))
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_hr_workbook -v
```

Expected: FAIL because the template is `1.1.0` and strategy fields are absent.

- [ ] **Step 3: Add blank HR fields and dropdown validation**

Set the template version to `1.2.0`. Add these fields to `BASE_FIELDS` with no business value prefilled:

```python
("flexible_rule_mode", "弹性考勤模式", None, "否", "纯工时弹性、最晚到岗限制或核心时段覆盖"),
("flexible_latest_start", "弹性最晚到岗", None, "否", "最晚到岗限制模式必填，HH:MM"),
("core_start", "核心时段开始", None, "否", "核心时段覆盖模式必填，HH:MM"),
("core_end", "核心时段结束", None, "否", "核心时段覆盖模式必填，HH:MM"),
("overtime_start_mode", "加班起算方式", None, "是", "审批开始、正常下班后或两者取较晚"),
```

Add dropdowns:

```python
_list_validation(
    sheet,
    f"C{_row_for(sheet, 'flexible_rule_mode')}",
    '"纯工时弹性,最晚到岗限制,核心时段覆盖"',
)
_list_validation(
    sheet,
    f"C{_row_for(sheet, 'overtime_start_mode')}",
    '"审批开始时间,正常下班后,审批开始与正常下班取较晚"',
)
```

In `_completeness_errors()`, require no flexible strategy for fixed mode, require a recognized strategy for flexible mode, and conditionally require the matching time fields. Validate every supplied time as `HH:MM`. Keep blank `grace_checkout` valid; it means zero added grace, not `standard_end + 15`.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_hr_workbook -v
```

Expected: all `tests.test_hr_workbook` tests PASS.

- [ ] **Step 5: Commit**

```bash
git add payroll_tool/templates/hr_workbook.py tests/test_hr_workbook.py
git commit -m "Add explicit HR attendance strategy fields"
```

### Task 2: Parse Strategies Without Runtime Defaults

**Files:**
- Modify: `tests/test_hr_workbook_import.py`
- Modify: `tests/test_app.py`
- Modify: `payroll_tool/config/schema.py`
- Modify: `payroll_tool/importers/hr_workbook.py`

- [ ] **Step 1: Write failing importer tests**

```python
def test_parser_reads_explicit_attendance_strategies(self):
    workbook = load_workbook(BytesIO(_completed_workbook()))
    _set_base(workbook, "overtime_start_mode", "审批开始时间")
    policy = attendance_policy_from_hr(parse_hr_workbook(_save(workbook)))
    self.assertEqual(policy.overtime_start_mode, "审批开始时间")
    self.assertIsNone(policy.flexible_rule_mode)

def test_parser_reads_core_time_flexible_policy(self):
    workbook = load_workbook(BytesIO(_completed_workbook()))
    _set_base(workbook, "work_mode", "弹性工时")
    _set_base(workbook, "flexible_rule_mode", "核心时段覆盖")
    _set_base(workbook, "core_start", "10:30")
    _set_base(workbook, "core_end", "16:30")
    policy = attendance_policy_from_hr(parse_hr_workbook(_save(workbook)))
    self.assertEqual(policy.flexible_rule_mode, "核心时段覆盖")
    self.assertEqual(policy.core_start, "10:30")
    self.assertEqual(policy.core_end, "16:30")
```

Update completed workbook fixtures in `tests/test_hr_workbook_import.py` and `tests/test_app.py` with an explicit `overtime_start_mode`. Do not add company time defaults to production template cells.

- [ ] **Step 2: Run tests and verify RED**

```bash
.venv/bin/python -m unittest tests.test_hr_workbook_import tests.test_app -v
```

Expected: FAIL because `AttendancePolicy` has no strategy attributes.

- [ ] **Step 3: Extend the typed policy and importer**

Add required/optional policy fields:

```python
@dataclass(frozen=True)
class AttendancePolicy:
    standard_start: str
    standard_end: str
    lunch_start: str
    lunch_end: str
    latest_normal_start: str
    late_grace_end: str
    work_mode: str
    daily_required_hours: float
    leave_types: dict[str, "LeaveTypePolicy"]
    attendance_exemptions: dict[str, "AttendanceExemptionPolicy"]
    overtime_start_mode: str
    flexible_rule_mode: str | None = None
    flexible_latest_start: str | None = None
    core_start: str | None = None
    core_end: str | None = None
    earliest_valid_start: str | None = None
    grace_checkout: str | None = None
    late_makeup_allowed: bool = False
    full_day_absence_after_hours: float | None = None
    entry_day_full_attendance: bool = False
    termination_day_full_attendance: bool = False
```

The workbook importer must pass every field explicitly. Defaults exist only to keep low-level construction safe; a complete uploaded workbook is validated before import and cannot omit required decisions.

Validate the HR-entered work duration at import time without enumerating allowed hours:

```python
required_minutes = Decimal(str(values["daily_required_hours"])) * Decimal("60")
if required_minutes <= 0 or required_minutes != required_minutes.to_integral_value():
    raise ValueError("每日标准工时必须是大于0且精确到整分钟的数值")
daily_required_hours = float(required_minutes / Decimal("60"))
```

- [ ] **Step 4: Run tests and verify GREEN**

```bash
.venv/bin/python -m unittest tests.test_hr_workbook_import tests.test_app -v
```

Expected: all selected tests PASS.

- [ ] **Step 5: Commit**

```bash
git add payroll_tool/config/schema.py payroll_tool/importers/hr_workbook.py tests/test_hr_workbook_import.py tests/test_app.py
git commit -m "Parse HR attendance strategies"
```

### Task 3: Make Fixed Hours Use Real Minute Coverage

**Files:**
- Modify: `tests/test_attendance_engine.py`
- Modify: `payroll_tool/attendance/engine.py`

- [ ] **Step 1: Write failing fixed-hours tests**

Replace the uncommitted checkout-mode test with work-mode behavior and add a non-integer HR-entered target to prove the engine does not enumerate standard hours:

```python
def test_fixed_hours_do_not_apply_early_arrival_checkout(self):
    policy = replace(POLICY, daily_required_hours=8.0)
    day = calculate_day(arrival="09:00", departure="18:30", policy=policy)
    self.assertEqual(day.effective_hours, 7.0)
    self.assertEqual(day.absence_hours, 1.0)

def test_blank_grace_checkout_adds_zero_minutes(self):
    policy = replace(POLICY, grace_checkout=None, late_makeup_allowed=True)
    self.assertEqual(infer_checkout_boundary("10:28", policy), "19:30")

def test_fixed_policy_uses_exact_hr_daily_hours_as_target(self):
    policy = replace(
        POLICY,
        standard_start="09:12",
        standard_end="17:30",
        lunch_start="12:00",
        lunch_end="13:30",
        daily_required_hours=6.8,
    )
    day = calculate_day(arrival="09:12", departure="17:30", policy=policy)
    self.assertEqual(day.effective_minutes, 408)
    self.assertEqual(day.absence_hours, 0.0)
```

The first case counts only `10:00-18:30` in a fixed `10:00-19:30` schedule, less lunch: 7 hours. It does not infer an `18:30` valid checkout from the `09:00` arrival.

- [ ] **Step 2: Run tests and verify RED**

```bash
.venv/bin/python -m unittest tests.test_attendance_engine -v
```

Expected: FAIL because early arrival currently moves checkout and blank grace adds 15 minutes.

- [ ] **Step 3: Implement real fixed-hour coverage**

For fixed mode:

```python
fixed_start = max(arrival_minutes, standard_start)
fixed_end = policy_checkout_boundary(policy)
coverage.append((fixed_start, min(departure_minutes, fixed_end)))
covered_minutes = _duration_minutes(
    _subtract(_merge(coverage), break_intervals)
)
required_minutes = _required_minutes(policy.daily_required_hours)
effective_minutes = min(required_minutes, covered_minutes)
absence_minutes = max(0, required_minutes - effective_minutes)
```

`policy_checkout_boundary()` returns `standard_end` unless HR enabled makeup and supplied a later `grace_checkout`. A blank value returns `standard_end`; delete the `standard_end + 15` fallback. Early punches before `standard_start` do not count in fixed mode. Paid approval intervals remain merged and de-duplicated.

Preserve configured late classification and full-day absence threshold, but never fabricate coverage from `standard_start` when the employee arrived later.

- [ ] **Step 4: Run tests and verify GREEN**

```bash
.venv/bin/python -m unittest tests.test_attendance_engine -v
```

Expected: all attendance engine tests PASS.

- [ ] **Step 5: Commit**

```bash
git add payroll_tool/attendance/engine.py tests/test_attendance_engine.py
git commit -m "Use real minute coverage for fixed attendance"
```

### Task 4: Implement The Three Flexible Modes

**Files:**
- Modify: `tests/test_attendance_engine.py`
- Modify: `payroll_tool/attendance/engine.py`

- [ ] **Step 1: Write one failing test per flexible strategy**

```python
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
```

- [ ] **Step 2: Run tests and verify RED**

```bash
.venv/bin/python -m unittest tests.test_attendance_engine -v
```

Expected: latest-arrival and core-time tests FAIL because flexible mode currently ignores strategy.

- [ ] **Step 3: Add explicit flexible strategy branches**

Calculate merged punch and paid coverage once. Then:

```python
if policy.flexible_rule_mode == "纯工时弹性":
    late_hours = 0.0
    policy_gap = 0.0
elif policy.flexible_rule_mode == "最晚到岗限制":
    late_hours = max(0, arrival_minutes - _minutes(policy.flexible_latest_start)) / 60
    policy_gap = late_hours
elif policy.flexible_rule_mode == "核心时段覆盖":
    late_hours = 0.0
    policy_gap = _uncovered_hours(
        [(_minutes(policy.core_start), _minutes(policy.core_end))],
        merged_coverage,
    )
else:
    raise ValueError("HR 工作簿弹性考勤模式无效")

required_minutes = _required_minutes(policy.daily_required_hours)
duration_gap_minutes = max(0, required_minutes - covered_minutes)
absence_minutes = max(duration_gap_minutes, policy_gap_minutes)
effective_minutes = max(0, required_minutes - absence_minutes)
```

Paid approvals can cover late or core-time gaps. Missing conditional fields raise a clear error even if an invalid policy bypasses workbook validation.

- [ ] **Step 4: Run tests and verify GREEN**

```bash
.venv/bin/python -m unittest tests.test_attendance_engine -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add payroll_tool/attendance/engine.py tests/test_attendance_engine.py
git commit -m "Add configured flexible attendance modes"
```

### Task 5: Make Overtime Start Follow HR Selection

**Files:**
- Modify: `tests/test_daily_pipeline.py`
- Modify: `payroll_tool/attendance/daily_pipeline.py`

- [ ] **Step 1: Write failing tests for all overtime start modes**

```python
def test_overtime_can_start_at_approval_start(self):
    policy = replace(POLICY, overtime_start_mode="审批开始时间")
    result = calculate_day_from_text(
        "正常(10:00),正常(22:00);加班(19:00-22:00)", policy, OVERTIME_RULES
    )
    self.assertEqual(result.overtime_hours, Decimal("3"))

def test_overtime_can_start_after_normal_checkout(self):
    policy = replace(POLICY, overtime_start_mode="正常下班后")
    result = calculate_day_from_text(
        "正常(10:00),正常(22:00);加班(19:00-22:00)", policy, OVERTIME_RULES
    )
    self.assertEqual(result.overtime_hours, Decimal("2.5"))

def test_overtime_can_use_later_of_approval_and_checkout(self):
    policy = replace(POLICY, overtime_start_mode="审批开始与正常下班取较晚")
    result = calculate_day_from_text(
        "正常(10:00),正常(22:00);加班(20:00-22:00)", policy, OVERTIME_RULES
    )
    self.assertEqual(result.overtime_hours, Decimal("2"))
```

- [ ] **Step 2: Run tests and verify RED**

```bash
.venv/bin/python -m unittest tests.test_daily_pipeline -v
```

Expected: approval-start mode FAILS because `_overtime_hours()` always takes the later boundary.

- [ ] **Step 3: Implement the explicit start strategy**

```python
approval_start = _minutes(segment.start)
normal_checkout = _minutes(infer_checkout_boundary(arrival, policy))
if policy.overtime_start_mode == "审批开始时间":
    start = approval_start
elif policy.overtime_start_mode == "正常下班后":
    start = normal_checkout
elif policy.overtime_start_mode == "审批开始与正常下班取较晚":
    start = max(approval_start, normal_checkout)
else:
    raise ValueError("HR 工作簿加班起算方式无效")
```

Retain cross-midnight handling. Do not calculate overtime pay or compensatory time in this phase.

- [ ] **Step 4: Run tests and verify GREEN**

```bash
.venv/bin/python -m unittest tests.test_daily_pipeline -v
```

Expected: all daily pipeline tests PASS.

- [ ] **Step 5: Commit**

```bash
git add payroll_tool/attendance/daily_pipeline.py tests/test_daily_pipeline.py
git commit -m "Apply HR overtime start strategy"
```

### Task 6: Add Cross-Layer Regression And Documentation

**Files:**
- Modify: `tests/test_app.py`
- Modify: `docs/hr-workbook.md`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add a failing application-level arbitrary-duration test**

Create a complete synthetic rule workbook with an irregular `408`-minute daily target and upload a matching row. The irregular value proves the application does not select from, round to, or fall back to predefined hour levels:

```python
def test_task_uses_exact_uploaded_daily_work_duration(self):
    response = client.post(
        "/tasks",
        data=_task_upload(
            daily_required_hours=6.8,
            standard_start="09:12",
            standard_end="17:30",
            lunch_start="12:00",
            lunch_end="13:30",
            attendance_text="正常(09:12),正常(17:30)",
        ),
        content_type="multipart/form-data",
    )
    self.assertEqual(response.status_code, 201)
    task = app.extensions["task_store"].tasks[response.get_json()["task_id"]]
    self.assertEqual(task["attendance_summaries"]["SYN001"].effective_minutes, 408)
```

- [ ] **Step 2: Run the focused integration test and verify RED if any layer substitutes a predefined work duration**

```bash
.venv/bin/python -m unittest tests.test_app -v
```

Expected: the new test PASS only when workbook, importer, and attendance engine all use HR's value.

- [ ] **Step 3: Update HR instructions and migration notes**

Document:

- no product default times or 15-minute fallback;
- fixed mode uses actual punch minutes inside the HR schedule;
- three flexible modes and their required fields;
- daily required hours are the attendance target;
- overtime start modes;
- old `1.1.0` workbooks must migrate to `1.2.0`.

State explicitly that all times, work durations, and monthly pay days appearing in tests are synthetic fixtures, not runtime defaults or supported-value lists.

- [ ] **Step 4: Run full verification**

```bash
.venv/bin/python -W error::ResourceWarning -m unittest -q
git diff --check
```

Expected: all tests PASS, no warnings, and `git diff --check` has no output.

- [ ] **Step 5: Commit**

```bash
git add tests/test_app.py docs/hr-workbook.md README.md CHANGELOG.md
git commit -m "Document configured attendance rules"
```

### Task 7: Review The Phase Before Starting Payroll Changes

**Files:** No production changes.

- [ ] **Step 1: Confirm no company policy values entered production code**

```bash
rg -n '09:00|10:00|19:30|19:45|standard_end \+ 15|FULL_DAY_HOURS' payroll_tool app.py templates
```

Expected: no company attendance times and no 15-minute fallback in production. `FULL_DAY_HOURS` may remain in the payroll engine until the configured-payroll phase, and must be listed as the next known limitation.

- [ ] **Step 2: Confirm workbook values are the runtime source**

```bash
.venv/bin/python -m unittest \
  tests.test_hr_workbook \
  tests.test_hr_workbook_import \
  tests.test_attendance_engine \
  tests.test_daily_pipeline \
  tests.test_app -v
```

Expected: all selected tests PASS.

- [ ] **Step 3: Request code review**

Review for hidden fallbacks, conditional validation gaps, invalid strategy handling, double-counted intervals, and compatibility errors. Resolve all correctness findings before starting dynamic leave types.
