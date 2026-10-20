# Employee Payroll Template Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the employee payroll XLSX self-explanatory and make invalid employee values report their row, employee ID, and field without changing the import schema.

**Architecture:** Keep `EXPECTED_HEADERS["员工薪酬"]` as the single import contract. Add immutable field metadata beside the workbook generator, render it into a read-only guidance sheet and header comments, then wrap row conversion errors at the importer boundary where row and employee context are available.

**Tech Stack:** Python 3, openpyxl, unittest, Flask test client.

---

### Task 1: Complete Field Guidance In The Downloaded Workbook

**Files:**
- Modify: `payroll_tool/templates/employee_workbook.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing workbook-structure test**

Update `test_employee_payroll_template_is_blank_and_matches_import_columns` to require `['填写说明', '字段说明', '员工薪酬']`. Assert that the first column of `字段说明` exactly equals `EXPECTED_HEADERS['员工薪酬']`, every metadata row has six non-empty cells, required headers have comments containing `必填`, and row 2 in `员工薪酬` remains blank.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m unittest tests.test_app.PayrollAppTests.test_employee_payroll_template_is_blank_and_matches_import_columns -v`

Expected: FAIL because `字段说明` does not exist.

- [ ] **Step 3: Add explicit metadata for every standard field**

In `payroll_tool/templates/employee_workbook.py`, define one metadata record per item in `EXPECTED_HEADERS['员工薪酬']` with these keys: `field`, `label`, `requirement`, `condition`, `format`, and `description`. Add an import-time assertion that metadata field order exactly matches the standard headers so later schema changes cannot silently omit documentation.

- [ ] **Step 4: Render guidance and visible required markers**

Create `字段说明` between the guide and data sheets. Render the six metadata columns, freeze its header, enable filtering, apply existing restrained header styling, and size columns for Chinese text. Add openpyxl comments to each data header; use distinct fills for always-required, conditionally-required, and optional columns while retaining the exact cell values used by the parser.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python -m unittest tests.test_app.PayrollAppTests.test_employee_payroll_template_is_blank_and_matches_import_columns -v`

Expected: PASS.

- [ ] **Step 6: Commit the workbook guidance**

```bash
git add payroll_tool/templates/employee_workbook.py tests/test_app.py
git commit -m "Improve employee payroll template guidance"
```

### Task 2: Report Row, Employee, And Field For Invalid Values

**Files:**
- Modify: `payroll_tool/importers/employee_workbook.py`
- Modify: `tests/test_employee_workbook.py`

- [ ] **Step 1: Write failing importer-context tests**

Add tests that provide `tax_year='2026.5'` and `hire_date='08/01/2026'`. Assert messages include `第 2 行`, employee ID, and the relevant field code (`tax_year` or `hire_date`). Keep existing damaged-file, duplicate-ID, and employment-type tests unchanged.

- [ ] **Step 2: Run importer tests and verify RED**

Run: `python -m unittest tests.test_employee_workbook -v`

Expected: the new tests FAIL because conversion errors currently contain only the invalid value.

- [ ] **Step 3: Add field-aware conversion context**

At the `parse_employee_workbook` row boundary, catch `ValueError` from `employee_from_row` and raise a new `ValueError` formatted as `员工薪酬第 {row_number} 行（工号 {employee_id}）字段 {field}: {reason}`. Introduce a small field-conversion helper so date, year, and amount conversion failures preserve the field code; do not change successful conversion semantics.

- [ ] **Step 4: Run importer tests and verify GREEN**

Run: `python -m unittest tests.test_employee_workbook -v`

Expected: PASS.

- [ ] **Step 5: Commit importer diagnostics**

```bash
git add payroll_tool/importers/employee_workbook.py tests/test_employee_workbook.py
git commit -m "Clarify employee payroll import errors"
```

### Task 3: Regression And Release Readiness

**Files:**
- Verify: `payroll_tool/templates/employee_workbook.py`
- Verify: `payroll_tool/importers/employee_workbook.py`
- Verify: `tests/test_app.py`
- Verify: `tests/test_employee_workbook.py`

- [ ] **Step 1: Run template and importer suites**

Run: `python -m unittest tests.test_app tests.test_employee_workbook tests.test_workspace_ui -v`

Expected: PASS with no errors or warnings.

- [ ] **Step 2: Run the complete suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 3: Verify repository hygiene**

Run: `git diff --check` and `git status --short`.

Expected: no whitespace errors; pre-existing user-owned changes remain unstaged and untouched.

- [ ] **Step 4: Commit any test-only final adjustment**

Only when Task 3 required a scoped test correction:

```bash
git add tests/test_app.py tests/test_employee_workbook.py
git commit -m "Harden employee template regression coverage"
```

Do not create this commit when no additional change is needed.
