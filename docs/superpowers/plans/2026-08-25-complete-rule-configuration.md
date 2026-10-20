# Complete Rule Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete, self-explanatory HR rule configuration workspace with structured employment types, working commercial insurance and employee exception editors, separated statutory sections, and read-only calculation records.

**Architecture:** Keep published policy versions as immutable normalized JSON snapshots. Add focused policy-normalization helpers for backward compatibility, extend the existing SQLite repository for calculation records, and keep the Flask page as a thin API client. Split browser behavior by configuration responsibility so conditional requirements and list editors can be tested without coupling them to payroll calculation.

**Tech Stack:** Python 3.13, Flask, SQLite, `unittest`, vanilla HTML/CSS/JavaScript, existing policy repository and validation modules.

---

## File Structure

- `payroll_tool/config/policy_normalization.py`: Normalize legacy and current policy snapshots without inventing business values.
- `payroll_tool/config/policy_validation.py`: Validate structured employment types, commercial insurance and employee exceptions.
- `payroll_tool/config/policy_conversion.py`: Convert normalized HR configuration into calculation policy objects.
- `payroll_tool/config/policy_repository.py`: Persist and query immutable calculation records.
- `app.py`: Expose policy and calculation-record APIs.
- `templates/workspace.html`: Complete navigation, forms, tables and dialogs.
- `static/workspace.js`: Page orchestration and API calls only.
- `static/rule-editor.js`: Required-state display, completion progress and rule list editors.
- `static/workspace.css`: Shared desktop visual rules.
- `static/workspace-responsive.css`: Responsive constraints.
- `tests/test_policy_normalization.py`: Legacy migration and canonical shape.
- `tests/test_policy_validation.py`: Cross-field and reference validation.
- `tests/test_policy_conversion.py`: Calculation conversion compatibility.
- `tests/test_policy_repository.py`: Calculation-record persistence and immutability.
- `tests/test_policy_api.py`: API contracts.
- `tests/test_workspace_ui.py`: HTML and static UI contracts.
- `tests/test_workspace_browser.py`: Browser-independent state fixtures where feasible.
- `docs/USER_GUIDE.md`: HR-facing explanations and examples.

### Task 1: Required Fields, Conditional Help and Completion State

**Files:**
- Modify: `templates/workspace.html`
- Create: `static/rule-editor.js`
- Modify: `static/workspace.js`
- Modify: `static/workspace.css`
- Modify: `static/workspace-responsive.css`
- Modify: `tests/test_workspace_ui.py`

- [ ] **Step 1: Write failing UI contract tests**

Add tests asserting that the page contains the required legend, `data-required-path`, `data-required-when`, completion progress and field-addressable error targets:

```python
def test_rule_editor_marks_required_and_conditional_fields(self):
    html = self.client.get("/").get_data(as_text=True)
    self.assertIn('id="policy-completion"', html)
    self.assertIn('class="required-mark"', html)
    self.assertIn('data-required-path="company.worktime.mode"', html)
    self.assertIn('data-required-when="company.worktime.lunch.enabled:true"', html)
    self.assertIn('data-error-for="company.worktime.mode"', html)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_workspace_ui.WorkspaceUiTests.test_rule_editor_marks_required_and_conditional_fields -v`

Expected: FAIL because completion and required metadata are absent.

- [ ] **Step 3: Add semantic required metadata and progress UI**

Use labels shaped like:

```html
<label data-required-path="company.worktime.mode">
  工时模式 <span class="required-mark" aria-hidden="true">*</span>
  <select data-field="company.worktime.mode"></select>
  <small data-error-for="company.worktime.mode"></small>
</label>
```

Conditional fields use `data-required-when="path:value"`. Add `requiredState(snapshot, validationErrors)` in `static/rule-editor.js` that returns `{required, completed, percent}` and never supplies field values.

- [ ] **Step 4: Connect validation errors to tabs and controls**

Map each server error path to the nearest `[data-field]`, `[data-list-path]` or `[data-error-for]`; mark its parent tab and scroll the first error into view after “检查规则”. Preserve entered values when requests fail.

- [ ] **Step 5: Run UI tests and verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_workspace_ui -v`

Expected: all workspace UI tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add templates/workspace.html static/rule-editor.js static/workspace.js static/workspace.css static/workspace-responsive.css tests/test_workspace_ui.py
git commit -m "Clarify required HR rule fields"
```

### Task 2: Structured Employment Types and Legacy Normalization

**Files:**
- Create: `payroll_tool/config/policy_normalization.py`
- Modify: `payroll_tool/config/policy_validation.py`
- Modify: `payroll_tool/config/policy_conversion.py`
- Create: `tests/test_policy_normalization.py`
- Modify: `tests/test_policy_validation.py`
- Modify: `tests/test_policy_conversion.py`

- [ ] **Step 1: Write failing normalization tests**

```python
def test_legacy_employment_codes_become_review_required_objects(self):
    normalized = normalize_policy({"employment_types": ["full_time"]})
    self.assertEqual(normalized["employment_types"][0], {
        "code": "full_time", "name": "", "payroll_scheme": "",
        "social_insurance_applicable": None,
        "housing_fund_applicable": None,
        "tax_applicable": None, "enabled": True,
        "migration_review_required": True,
    })

def test_normalization_does_not_invent_employment_rules(self):
    item = normalize_policy({"employment_types": ["intern"]})["employment_types"][0]
    self.assertIsNone(item["social_insurance_applicable"])
    self.assertEqual(item["payroll_scheme"], "")
```

- [ ] **Step 2: Run normalization tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_policy_normalization -v`

Expected: FAIL because `normalize_policy` does not exist.

- [ ] **Step 3: Implement canonical employment-type normalization**

Create pure functions `normalize_policy(snapshot)` and `normalize_employment_types(value)`. Preserve structured objects verbatim after JSON-safe copying; convert only legacy strings to review-required objects. Never infer names, formulas or statutory applicability.

- [ ] **Step 4: Write failing structured validation tests**

Test duplicate codes and names, code format, required booleans, unknown payroll schemes and insurance references to disabled types. Expected paths must identify `employment_types[index].field`.

- [ ] **Step 5: Update validation and conversion**

Change `_validate_employment_types` to return enabled codes from structured objects. Update conversion to key employment policies by `code`; reject `migration_review_required=True` at publish conversion.

- [ ] **Step 6: Run normalization, validation and conversion tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_policy_normalization tests.test_policy_validation tests.test_policy_conversion -v`

Expected: all tests pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add payroll_tool/config/policy_normalization.py payroll_tool/config/policy_validation.py payroll_tool/config/policy_conversion.py tests/test_policy_normalization.py tests/test_policy_validation.py tests/test_policy_conversion.py
git commit -m "Structure employment type policies"
```

### Task 3: Employment Type Editor

**Files:**
- Modify: `templates/workspace.html`
- Modify: `static/rule-editor.js`
- Modify: `static/workspace.css`
- Modify: `tests/test_workspace_ui.py`

- [ ] **Step 1: Write failing editor contract tests**

Assert `employment-type-table`, `add-employment-type`, `employment-type-dialog`, close controls, and fields for code, name, payroll scheme, three applicability choices and enabled status.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_workspace_ui.WorkspaceUiTests.test_structured_employment_type_editor -v`

Expected: FAIL because the current textarea is still present.

- [ ] **Step 3: Replace textarea with list and dialog**

Render a row per employment type. New entries permit editing `code`; previously saved or referenced entries render the code read-only. Cancel and close use `type="button" data-close-dialog` and never call `reportValidity()`.

- [ ] **Step 4: Add client-side duplicate and format feedback**

Before updating local draft state, reject duplicate normalized code/name and codes outside `^[a-z][a-z0-9_]*$`. Keep server validation authoritative at save and publish.

- [ ] **Step 5: Run UI and policy API tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_workspace_ui tests.test_policy_api -v`

Expected: all tests pass.

- [ ] **Step 6: Browser verification**

At desktop and mobile widths, create, edit, cancel and disable an employment type; verify no horizontal page overflow and no console errors.

- [ ] **Step 7: Commit Task 3**

```bash
git add templates/workspace.html static/rule-editor.js static/workspace.css tests/test_workspace_ui.py
git commit -m "Add employment type rule editor"
```

### Task 4: Commercial Insurance Editor

**Files:**
- Modify: `templates/workspace.html`
- Modify: `static/rule-editor.js`
- Modify: `tests/test_workspace_ui.py`
- Modify: `tests/test_policy_validation.py`

- [ ] **Step 1: Write failing commercial-insurance UI tests**

Assert the add button opens a dialog represented by `commercial-insurance-dialog`; require code, name, region, effective date, calculation mode, shares, deduction mode and employment types; assert close controls are non-submit buttons.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_workspace_ui.WorkspaceUiTests.test_commercial_insurance_editor -v`

Expected: FAIL because the button has no editor.

- [ ] **Step 3: Implement table rendering and dialog state**

Store items in `snapshot.commercial_insurance`. Toggle fixed amount versus base-rate fields from `calculation`; disabled items remain visible but do not require enabled-only fields.

- [ ] **Step 4: Complete validation coverage**

Add tests for optional empty list, duplicate code, reversed dates, fixed amount requirement, rate requirement, shares totaling exactly `1`, and references to enabled employment types.

- [ ] **Step 5: Run UI and policy validation tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_workspace_ui tests.test_policy_validation -v`

Expected: all tests pass.

- [ ] **Step 6: Browser verification and commit**

Verify add, edit, close, cancel, fixed amount and rate modes. Then:

```bash
git add templates/workspace.html static/rule-editor.js tests/test_workspace_ui.py tests/test_policy_validation.py
git commit -m "Complete commercial insurance configuration"
```

### Task 5: Employee Exception Model and Editor

**Files:**
- Modify: `payroll_tool/config/policy_validation.py`
- Modify: `payroll_tool/config/policy_conversion.py`
- Modify: `templates/workspace.html`
- Modify: `static/rule-editor.js`
- Modify: `tests/test_policy_validation.py`
- Modify: `tests/test_policy_conversion.py`
- Modify: `tests/test_workspace_ui.py`

- [ ] **Step 1: Write failing employee-exception validation tests**

Use the canonical item:

```python
{
    "employee_id": "SYNTHETIC-EMPLOYEE-001",
    "override_type": "housing_fund_fixed_base",
    "target_code": "housing_fund",
    "value": "8000",
    "effective_from": "2026-08-01",
    "effective_to": None,
    "reason": "HR approved special base",
    "enabled": True,
}
```

Test required fields, unknown target codes, decimal values, `0` perfect-attendance override, date reversal, and overlapping enabled intervals for the same employee/type/target.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_policy_validation.EmployeeExceptionValidationTests -v`

Expected: FAIL because employee exceptions are not validated.

- [ ] **Step 3: Implement allowed override types**

Validate only: statutory enabled, tier, base mode, fixed base, commercial enabled, commercial amount/base, employment type and perfect-attendance amount. Reject bonus, allowance, tax deduction and arbitrary field paths.

- [ ] **Step 4: Apply effective exceptions during conversion**

Add `employee_exceptions` to `CalculationPolicy` as immutable normalized records. Selection must use employee ID and calculation date; employee workbook monthly values remain separate and take no values from exception records outside the allowed set.

- [ ] **Step 5: Build the employee exception list and dialog**

Use dependent fields: choosing an override type constrains target and value controls. Require reason and effective start. Show `0 = cancel` and `blank = inherit` only for perfect-attendance amount.

- [ ] **Step 6: Run validation, conversion and UI tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_policy_validation tests.test_policy_conversion tests.test_workspace_ui -v`

Expected: all tests pass.

- [ ] **Step 7: Browser verification and commit**

Verify add, conflict feedback, edit, disable and cancel. Then:

```bash
git add payroll_tool/config/policy_validation.py payroll_tool/config/policy_conversion.py templates/workspace.html static/rule-editor.js tests/test_policy_validation.py tests/test_policy_conversion.py tests/test_workspace_ui.py
git commit -m "Add effective employee rule exceptions"
```

### Task 6: Calculation Record Repository and Page

**Files:**
- Modify: `payroll_tool/config/policy_repository.py`
- Modify: `app.py`
- Modify: `templates/workspace.html`
- Modify: `static/workspace.js`
- Modify: `tests/test_policy_repository.py`
- Modify: `tests/test_app.py`
- Modify: `tests/test_workspace_ui.py`

- [ ] **Step 1: Write failing repository tests**

Test a `CalculationRecord` containing task ID, policy version ID/digest, payroll month, period, input digests, employee count, exception count, status, error summary, result availability, created and completed timestamps. Verify insertion is append-only and later policy edits do not alter stored digest.

- [ ] **Step 2: Run repository tests and verify RED**

Run: `PYTHONDONTWRITEBYTECODE=1 python -m unittest tests.test_policy_repository.CalculationRecordTests -v`

Expected: FAIL because record APIs and columns do not exist.

- [ ] **Step 3: Add additive SQLite migration and repository methods**

Add missing columns with schema inspection and `ALTER TABLE`, preserving existing rows. Implement `create_calculation_record`, `complete_calculation_record`, `fail_calculation_record`, `list_calculation_records` and `get_calculation_record`. Updates may only transition task status and completion fields, never identity, period or policy digest.

- [ ] **Step 4: Write failing API tests**

Test `GET /api/calculation-records` ordering, sanitized input summaries, not-found behavior and result download availability. Ensure local paths and download tokens are absent from list payloads.

- [ ] **Step 5: Connect task lifecycle and API**

Create a record before preflight; update it on validation failure, calculation success or exception. Store normalized policy JSON digest and current upload digests. Existing download authorization remains unchanged.

- [ ] **Step 6: Move monthly tasks out of rule tabs**

Add left navigation “计算记录”, remove `tab-tasks`, render real API data and actions. An empty database displays a useful empty state.

- [ ] **Step 7: Run repository, app and UI tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest tests.test_policy_repository tests.test_app tests.test_workspace_ui -v`

Expected: all tests pass. Run the loopback-binding test with the previously approved local-port permission if sandboxing blocks it.

- [ ] **Step 8: Browser verification and commit**

Create one local calculation, verify the record appears with the correct rule version and status, and verify download still requires its token. Then:

```bash
git add payroll_tool/config/policy_repository.py app.py templates/workspace.html static/workspace.js tests/test_policy_repository.py tests/test_app.py tests/test_workspace_ui.py
git commit -m "Expose immutable calculation records"
```

### Task 7: Documentation, Migration and Full Verification

**Files:**
- Create: `docs/USER_GUIDE.md`
- Modify: `README.md`
- Modify: tests affected by final integration

- [ ] **Step 1: Update HR-facing guidance**

Document employment codes with examples, every conditional required rule, statutory versus commercial insurance, employee-exception boundaries, and calculation-record meaning. Explicitly state that monthly bonus, allowance and tax-deduction values belong in the employee payroll workbook.

- [ ] **Step 2: Add migration and recovery instructions**

Explain legacy employment-type review, published-version immutability, backup before upgrade, and how to recover from a failed draft without changing historical results.

- [ ] **Step 3: Run the complete automated suite**

Run: `PYTHONDONTWRITEBYTECODE=1 python -W error::ResourceWarning -m unittest discover -s tests -v`

Expected: all tests pass with no ResourceWarning. If the environment blocks loopback sockets, rerun only that test with local-port permission and require every other test to pass in the restricted run.

- [ ] **Step 4: Run final browser acceptance**

Verify desktop `1440x900` and mobile `390x844`: all seven rule tabs, conditional stars, each add/edit/cancel flow, five-insurance/housing-fund separation, employee exception conflict display, calculation records, no page overflow, no overlapping controls and no console errors.

- [ ] **Step 5: Verify no forbidden defaults**

Run:

```bash
rg -n '09:00|10:00|19:30|19:45|21\.75|daily_minutes[^\n]*480' templates static payroll_tool
```

Expected: no business default values in the generic UI or calculation configuration path; documentation examples must be clearly labeled and not loaded into runtime state.

- [ ] **Step 6: Commit Task 7**

```bash
git add docs/USER_GUIDE.md README.md tests
git commit -m "Document complete HR rule configuration"
```

## Final Integration Gate

- [ ] Confirm `git status --short` contains only previously known unrelated files.
- [ ] Review every commit against `docs/superpowers/specs/2026-08-25-complete-rule-configuration-design.md`.
- [ ] Keep the original company-specific tool untouched.
- [ ] Do not push GitHub until the user explicitly requests the final push.
