# 通用薪酬绩效工具 Implementation Plan

> **2026-08-14 更新：** 原计划中的 `configs/example-company/*.yaml` 示例配置已废弃并删除。HR 输入现统一为运行时生成的固定 Excel 工作簿；仓库不得包含可直接生效的公司考勤、薪酬或五险一金默认规则。以下 YAML 任务仅保留为早期实施记录，不代表当前产品输入方式。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent, offline-first payroll calculation application with configurable company rules and only synthetic test data.

**Architecture:** A typed Python core normalizes imported spreadsheet data before passing it into separated attendance, payroll, statutory, and export modules. Company policy is loaded from versioned YAML configuration and every calculation emits an audit manifest with input and result hashes. A local Flask desktop shell is added only after the calculation core is fully tested.

**Tech Stack:** Python 3.11+, Flask, openpyxl, pandas, PyYAML, PyInstaller, unittest, GitHub Actions.

---

## File Structure

- Create: `pyproject.toml` - project metadata, runtime dependencies, test commands.
- Create: `payroll_tool/config/schema.py` - configuration dataclasses and validation.
- Create: `configs/example-company/*.yaml` - synthetic example configuration package.
- Create: `payroll_tool/statutory/social_insurance.py` - opt-in social insurance and housing fund validation.
- Create: `payroll_tool/models.py` - normalized employee, time segment, daily result, payroll result types.
- Create: `payroll_tool/attendance/engine.py` - segment-based fixed-hours attendance calculation.
- Create: `payroll_tool/payroll/engine.py` - employee class and pay-plan calculation.
- Create: `payroll_tool/statutory/cn_tax.py` - China mainland annual cumulative withholding calculator.
- Create: `payroll_tool/importers/excel.py` - explicit Excel field mapping and validation report.
- Create: `payroll_tool/audit.py` - file/config/result hashing and safe audit manifest.
- Create: `payroll_tool/exporters/excel.py` - standardized export workbook and audit worksheet.
- Create: `app.py`, `desktop.py` - localhost-only HR application and desktop launcher.
- Create: `tests/fixtures/`, `tests/test_*.py` - purely synthetic data and regression coverage.
- Create: `.github/workflows/ci.yml`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md` - repository governance and CI.

### Task 1: Establish the Safe Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `payroll_tool/__init__.py`
- Create: `tests/test_repository_safety.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write a failing repository-safety test**

```python
from pathlib import Path
import unittest


class RepositorySafetyTests(unittest.TestCase):
    def test_repository_contains_no_spreadsheet_fixture(self):
        root = Path(__file__).parents[1]
        files = [path for path in root.rglob("*") if path.is_file()]
        self.assertFalse(any(path.suffix.lower() in {".xlsx", ".xls", ".csv"} for path in files))
```

- [ ] **Step 2: Run the test and verify it fails because the package is absent**

Run: `python -m unittest tests.test_repository_safety -v`
Expected: import/discovery failure before project files exist.

- [ ] **Step 3: Add the package marker and test configuration**

```toml
[project]
name = "general-payroll-tool"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["Flask>=3.1,<4", "openpyxl>=3.1,<4", "pandas>=2.2,<3", "PyYAML>=6,<7"]

[tool.unittest]
start-directory = "tests"
```

- [ ] **Step 4: Run the safety test and verify it passes**

Run: `python -m unittest tests.test_repository_safety -v`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml payroll_tool/__init__.py tests/test_repository_safety.py .gitignore
git commit -m "chore: add safe general payroll project skeleton"
```

### Task 2: Add Versioned Company Policy Validation

**Files:**
- Create: `payroll_tool/config/schema.py`
- Create: `configs/example-company/attendance_policy.yaml`
- Create: `configs/example-company/payroll_plan.yaml`
- Create: `tests/test_config_schema.py`

- [ ] **Step 1: Write a failing test for a valid policy package**

```python
from pathlib import Path
from payroll_tool.config.schema import load_company_policy


def test_example_policy_has_versioned_work_schedule():
    policy = load_company_policy(Path("configs/example-company"))
    assert policy.package_id == "example-cn-fixed-hours"
    assert policy.version == "1.0.0"
    assert policy.attendance.standard_start == "09:00"
```

- [ ] **Step 2: Run the test and verify it fails because `load_company_policy` is missing**

Run: `python -m unittest tests.test_config_schema -v`
Expected: import error for `payroll_tool.config.schema`.

- [ ] **Step 3: Implement strict configuration loading**

```python
@dataclass(frozen=True)
class AttendancePolicy:
    standard_start: str
    standard_end: str
    lunch_start: str
    lunch_end: str
    late_grace_end: str


def load_company_policy(directory: Path) -> CompanyPolicy:
    attendance = yaml.safe_load((directory / "attendance_policy.yaml").read_text(encoding="utf-8"))
    if attendance["package_id"] != "example-cn-fixed-hours":
        raise ValueError("configuration package_id is required")
    if attendance["version"] != "1.0.0":
        raise ValueError("configuration version is required")
    return CompanyPolicy(...)
```

- [ ] **Step 4: Add tests for missing version, invalid time format, and unsupported income items**

```python
with self.assertRaisesRegex(ValueError, "version"):
    load_company_policy(temp_policy_without_version)
```

- [ ] **Step 5: Run config tests and commit**

Run: `python -m unittest tests.test_config_schema -v`
Expected: `OK`.

```bash
git add payroll_tool/config configs/example-company tests/test_config_schema.py
git commit -m "feat: add versioned company policy validation"
```

### Task 3: Build the Normalized Attendance Engine

**Files:**
- Create: `payroll_tool/models.py`
- Create: `payroll_tool/attendance/engine.py`
- Create: `tests/test_attendance_engine.py`

- [ ] **Step 1: Write failing tests with synthetic time segments**

```python
def test_external_work_and_onsite_work_are_not_double_counted():
    day = calculate_day(
        start="10:00", end="19:30",
        paid_segments=[Segment("external", "10:00", "11:30")],
        onsite_segments=[Segment("onsite", "11:30", "19:30")],
        policy=policy,
    )
    self.assertEqual(day.effective_hours, 8.0)
    self.assertEqual(day.absence_hours, 0.0)
```

- [ ] **Step 2: Run the test and verify it fails because `calculate_day` is missing**

Run: `python -m unittest tests.test_attendance_engine -v`
Expected: import error.

- [ ] **Step 3: Implement interval merge/subtract primitives and daily calculation**

```python
def calculate_day(...):
    standard = subtract_lunch(policy.standard_segments, policy.lunch_segment)
    coverage = merge_intervals(onsite_segments + paid_segments)
    absence = subtract_intervals(standard, coverage + unpaid_leave_segments)
    return DailyAttendance(effective_hours=..., absence_hours=...)
```

- [ ] **Step 4: Add tests for full sick leave, personal leave, travel, overtime and dynamic checkout**

```python
def test_arrival_in_grace_window_uses_policy_checkout_boundary(self):
    day = calculate_day(start="10:28", end="19:45", policy=policy)
    self.assertEqual(day.absence_hours, 0.0)
```

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_attendance_engine -v`
Expected: `OK`.

```bash
git add payroll_tool/models.py payroll_tool/attendance tests/test_attendance_engine.py
git commit -m "feat: add normalized attendance engine"
```

### Task 4: Add Payroll and Statutory Modules

**Files:**
- Create: `payroll_tool/payroll/engine.py`
- Create: `payroll_tool/statutory/cn_tax.py`
- Create: `tests/test_payroll_engine.py`
- Create: `tests/test_cn_tax.py`

- [ ] **Step 1: Write failing tests for full-time, intern, conversion, bonus, and allowance scenarios**

```python
def test_taxable_allowance_does_not_change_social_base():
    result = calculate_payroll(employee_with_allowance, attendance, policy)
    self.assertEqual(result.allowance, 2000)
    self.assertGreater(result.tax, result_without_allowance.tax)
    self.assertEqual(result.social_base, result_without_allowance.social_base)
```

- [ ] **Step 2: Run tests and verify the payroll module is missing**

Run: `python -m unittest tests.test_payroll_engine tests.test_cn_tax -v`
Expected: import errors.

- [ ] **Step 3: Implement payroll calculation with explicit income-item flags**

```python
@dataclass(frozen=True)
class IncomeItem:
    amount: Decimal
    taxable: bool
    included_in_social_base: bool
    included_in_fund_base: bool
```

- [ ] **Step 4: Implement annual cumulative tax with prior income and withholding**

```python
def calculate_cn_cumulative_tax(current_taxable, prior_taxable, prior_withheld):
    annual_tax = bracket_tax(current_taxable + prior_taxable)
    return max(Decimal("0"), annual_tax - prior_withheld)
```

- [ ] **Step 5: Run payroll tests and commit**

Run: `python -m unittest tests.test_payroll_engine tests.test_cn_tax -v`
Expected: `OK`.

```bash
git add payroll_tool/payroll payroll_tool/statutory tests/test_payroll_engine.py tests/test_cn_tax.py
git commit -m "feat: add configurable payroll and tax modules"
```

### Task 5: Add Opt-In Social Insurance and Housing Fund Policies

**Files:**
- Create: `payroll_tool/statutory/social_insurance.py`
- Create: `configs/example-company/social_insurance.yaml`
- Create: `tests/test_social_insurance_policy.py`

- [ ] **Step 1: Write a failing test proving statutory deductions are disabled until a complete policy is supplied**

```python
def test_missing_social_policy_blocks_statutory_calculation():
    with self.assertRaisesRegex(ValueError, "not configured"):
        calculate_statutory_deductions(employee, payroll, policy=None)
```

- [ ] **Step 2: Write a failing test for an incomplete local policy**

```python
def test_policy_without_pension_or_housing_fund_is_not_calculable():
    incomplete = LocalStatutoryPolicy(region="Shenzhen", effective_from="2026-01-01")
    with self.assertRaisesRegex(ValueError, "pension"):
        validate_statutory_policy(incomplete)
```

- [ ] **Step 3: Implement an explicit local policy model**

```python
@dataclass(frozen=True)
class LocalStatutoryPolicy:
    region: str
    effective_from: date
    effective_to: date
    pension_tiers: dict[str, ContributionRule]
    medical_tiers: dict[str, ContributionRule]
    maternity: ContributionRule
    unemployment: ContributionRule
    work_injury_tiers: dict[str, ContributionRule]
    housing_fund: ContributionRule
```

- [ ] **Step 4: Reject unselected medical tiers and work-injury tiers**

```python
with self.assertRaisesRegex(ValueError, "medical tier"):
    calculate_statutory_deductions(employee_without_medical_tier, payroll, complete_policy)
```

- [ ] **Step 5: Require an explicit employee category for tiered pension rules**

```python
with self.assertRaisesRegex(ValueError, "pension tier"):
    calculate_statutory_deductions(employee_without_pension_tier, payroll, complete_policy)
```

Store a Shenzhen reference policy only after its effective year and official source URL are supplied. Its pension tiers must distinguish `shenzhen_household` (employee 8%, employer 17%) and `non_shenzhen_household` (employee 8%, employer 16%), with the 1% local supplementary pension recorded as a named employer component.

- [ ] **Step 6: Add only a disabled template, not a real city default**

```yaml
enabled: false
region: ""
effective_from: ""
effective_to: ""
# HR must fill every required contribution rule before enabling this policy.
```

- [ ] **Step 7: Run tests and commit**

Run: `python -m unittest tests.test_social_insurance_policy -v`
Expected: `OK`.

```bash
git add payroll_tool/statutory/social_insurance.py configs/example-company/social_insurance.yaml tests/test_social_insurance_policy.py
git commit -m "feat: require explicit statutory contribution policies"
```

### Task 6: Add Explicit Excel Import Validation and Safe Audit Reports

**Files:**
- Create: `payroll_tool/importers/excel.py`
- Create: `payroll_tool/audit.py`
- Create: `tests/test_excel_import.py`
- Create: `tests/test_audit.py`

- [ ] **Step 1: Write a failing test for an unknown required column**

```python
def test_import_rejects_unknown_required_mapping():
    report = validate_mapping(headers=["employee_name"], mapping={"employee_id": "staff_code"})
    self.assertFalse(report.ok)
    self.assertIn("staff_code", report.errors[0])
```

- [ ] **Step 2: Run tests and verify imports are missing**

Run: `python -m unittest tests.test_excel_import tests.test_audit -v`
Expected: import errors.

- [ ] **Step 3: Implement mapping validation and audit manifest**

```python
def build_audit_manifest(input_bytes, config_bytes, result_bytes, timestamp):
    return {
        "timestamp": timestamp.isoformat(),
        "input_sha256": sha256(input_bytes).hexdigest(),
        "config_sha256": sha256(config_bytes).hexdigest(),
        "result_sha256": sha256(result_bytes).hexdigest(),
    }
```

The application workflow must pass only the two current upload byte streams into this function and into the importer. Add an integration test that uploads two different synthetic workbooks in separate requests and asserts that their input hashes and result task IDs differ.

- [ ] **Step 4: Add a test proving the audit manifest does not contain employee IDs, names, or amounts**

```python
self.assertNotIn("E001", json.dumps(manifest))
self.assertNotIn("12000", json.dumps(manifest))
```

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_excel_import tests.test_audit -v`
Expected: `OK`.

```bash
git add payroll_tool/importers payroll_tool/audit.py tests/test_excel_import.py tests/test_audit.py
git commit -m "feat: validate imports and add privacy-safe audit manifests"
```

### Task 7: Add Offline HR Interface and Export

**Files:**
- Create: `app.py`
- Create: `desktop.py`
- Create: `payroll_tool/exporters/excel.py`
- Create: `tests/test_app.py`
- Create: `tests/test_export.py`

- [ ] **Step 1: Write a failing test for a local-only application server**

```python
def test_desktop_server_binds_only_loopback():
    server = LocalAppServer()
    self.assertEqual(server.host, "127.0.0.1")
    server.stop()
```

- [ ] **Step 2: Implement isolated task storage and explicit download tokens**

```python
task_id = uuid.uuid4().hex
task_dir = tempfile.mkdtemp(prefix=f"payroll-{task_id}-")
```

- [ ] **Step 3: Implement export with audit worksheet and rule version fields**

```python
audit_sheet.append(["rule_package", result.audit.rule_package_id])
audit_sheet.append(["rule_version", result.audit.rule_version])
audit_sheet.append(["input_sha256", result.audit.input_sha256])
```

- [ ] **Step 4: Run interface/export tests and commit**

Run: `python -m unittest tests.test_app tests.test_export -v`
Expected: `OK`.

```bash
git add app.py desktop.py payroll_tool/exporters tests/test_app.py tests/test_export.py
git commit -m "feat: add offline HR workflow and audited export"
```

### Task 8: Add GitHub Governance, CI, and Release Readiness

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `SECURITY.md`
- Create: `CONTRIBUTING.md`
- Create: `CHANGELOG.md`
- Create: `scripts/check_repository_safety.py`

- [ ] **Step 1: Add a repository-safety script that rejects spreadsheets and private keys**

```python
FORBIDDEN_SUFFIXES = {".xlsx", ".xls", ".csv", ".pem", ".p12", ".key"}
for path in Path(".").rglob("*"):
    if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
        raise SystemExit(f"forbidden repository file: {path}")
```

- [ ] **Step 2: Add GitHub Actions checks**

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.11'}
      - run: pip install -e .
      - run: python scripts/check_repository_safety.py
      - run: python -m unittest discover -s tests -q
```

- [ ] **Step 3: Document vulnerability reporting, contribution rules, and private-release policy**

```markdown
## Security
Do not open public issues containing payroll files, employee identifiers, or credentials.
Report vulnerabilities privately to the repository maintainers.
```

- [ ] **Step 4: Run all checks and commit**

Run: `python scripts/check_repository_safety.py && python -m unittest discover -s tests -q`
Expected: `OK`.

```bash
git add .github SECURITY.md CONTRIBUTING.md CHANGELOG.md scripts/check_repository_safety.py
git commit -m "ci: add repository safety and release governance"
```

## Plan Review

- Spec coverage: Tasks 1-7 cover independent repository setup, configurable policy, normalized attendance, payroll/tax, import validation, auditability, offline application, CI, and distribution governance.
- Sensitive data: Tasks explicitly prohibit spreadsheet fixtures and include only synthetic in-memory test data.
- Scope: Public cloud access, employee self-service, non-China tax engines, and Apple notarization are intentionally excluded from the first implementation milestone.
