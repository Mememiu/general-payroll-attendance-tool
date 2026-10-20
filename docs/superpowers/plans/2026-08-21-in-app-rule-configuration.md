# In-App HR Rule Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace monthly HR rule-workbook uploads with validated, versioned in-app configuration while preserving historical payroll calculations and an advanced backup/migration path.

**Architecture:** Add a focused SQLite-backed policy repository, explicit validation service, and serializer that converts published JSON snapshots into the existing attendance/payroll input models. Keep employee payroll data as a fixed XLSX upload, make monthly tasks reference immutable published policy versions, and expose configuration through JSON APIs plus a multi-tab local UI.

**Tech Stack:** Python 3, Flask, SQLite (`sqlite3`), dataclasses, `Decimal`, JSON, existing OpenPyXL importers, HTML/CSS/vanilla JavaScript, `unittest`.

---

## File Map

- Create `payroll_tool/config/policy_models.py`: policy status, metadata, immutable snapshot and validation issue models.
- Create `payroll_tool/config/policy_repository.py`: SQLite schema and draft/version/task persistence.
- Create `payroll_tool/config/policy_validation.py`: field and cross-module validation with UI field paths.
- Create `payroll_tool/config/policy_serialization.py`: canonical JSON, hashes and conversion to existing calculation models.
- Create `payroll_tool/config/legacy_migration.py`: one-time XLSX rule-workbook to draft conversion.
- Create `payroll_tool/config/backup.py`: versioned local backup export/import and collision checks.
- Create `payroll_tool/importers/employee_workbook.py`: employee payroll data import separated from policy configuration.
- Create `payroll_tool/web/policy_api.py`: Flask blueprint for draft, validation, publish, clone and lookup.
- Create `payroll_tool/web/backup_api.py`: Flask blueprint for advanced backup and migration.
- Create `static/workspace.css`: responsive application layout and configuration controls.
- Create `static/workspace.js`: navigation, configuration forms, tables, modals and API calls.
- Modify `app.py`: register repositories/blueprints and make tasks reference `policy_version_id`.
- Modify `templates/workspace.html`: replace rule upload UI with configuration tabs and two monthly uploads.
- Modify existing specs that still describe HR rule uploads as the normal workflow.
- Add focused tests alongside each module and update `tests/test_app.py` for the new end-to-end contract.

Do not discard or rewrite the pre-existing uncommitted changes in `tests/test_daily_pipeline.py` or `docs/superpowers/plans/2026-08-18-statutory-deductions.md`.

### Task 1: Policy Domain Models and Canonical Snapshot

**Files:**
- Create: `payroll_tool/config/policy_models.py`
- Create: `payroll_tool/config/policy_serialization.py`
- Test: `tests/test_policy_models.py`

- [ ] **Step 1: Write failing tests for immutable version metadata and stable hashes**

```python
def test_snapshot_hash_is_independent_of_dictionary_order():
    left = canonical_snapshot({"worktime": {"daily_minutes": 450, "mode": "fixed"}})
    right = canonical_snapshot({"worktime": {"mode": "fixed", "daily_minutes": 450}})
    assert left.sha256 == right.sha256
    assert left.payload == right.payload

def test_validation_issue_exposes_ui_field_path():
    issue = ValidationIssue("required", "请输入每日标准工时", "company.worktime.daily_minutes")
    assert issue.as_dict()["field"] == "company.worktime.daily_minutes"
```

- [ ] **Step 2: Run the focused tests and verify missing imports fail**

Run: `python -m unittest tests.test_policy_models -v`
Expected: `ImportError` for `policy_models` or `policy_serialization`.

- [ ] **Step 3: Implement explicit models and canonical serialization**

```python
class PolicyStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"

@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    field: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

@dataclass(frozen=True)
class CanonicalSnapshot:
    payload: str
    sha256: str

def canonical_snapshot(value: Mapping[str, object]) -> CanonicalSnapshot:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return CanonicalSnapshot(payload, hashlib.sha256(payload.encode("utf-8")).hexdigest())
```

- [ ] **Step 4: Run tests and commit**

Run: `python -m unittest tests.test_policy_models -v`
Expected: all tests pass.

Commit: `git add payroll_tool/config/policy_models.py payroll_tool/config/policy_serialization.py tests/test_policy_models.py && git commit -m "Add policy snapshot domain models"`

### Task 2: SQLite Policy Repository

**Files:**
- Create: `payroll_tool/config/policy_repository.py`
- Test: `tests/test_policy_repository.py`

- [ ] **Step 1: Write failing lifecycle and immutability tests**

```python
class PolicyRepositoryTests(unittest.TestCase):
    def test_publish_makes_version_immutable(self):
        with TemporaryDirectory() as directory:
            repository = PolicyRepository(Path(directory) / "policies.sqlite3")
            draft = repository.create_draft("公司制度", "2026.01", "2026-01-01")
            repository.save_draft(draft.id, {"company": {"monthly_pay_days": "21.5"}})
            version = repository.publish(draft.id)
            with self.assertRaises(PolicyConflictError):
                repository.save_draft(version.id, {"company": {"monthly_pay_days": "22"}})

    def test_clone_preserves_published_snapshot(self):
        with TemporaryDirectory() as directory:
            repository = PolicyRepository(Path(directory) / "policies.sqlite3")
            source = publish_policy(repository, version="2026.01")
            clone = repository.clone_version(source.id, "2026.07", "2026-07-01")
            repository.save_draft(clone.id, {"company": {"monthly_pay_days": "22"}})
            self.assertEqual(
                repository.get(source.id).snapshot["company"]["monthly_pay_days"], "21.5"
            )
```

- [ ] **Step 2: Run tests and verify repository is missing**

Run: `python -m unittest tests.test_policy_repository -v`
Expected: import failure.

- [ ] **Step 3: Implement schema and transactional repository methods**

Create tables `policies`, `policy_versions`, and `monthly_tasks`. Use `PRAGMA foreign_keys = ON`, parameterized statements, UTC timestamps, unique `(policy_id, version)`, and transactions for publish/clone. `save_draft` must reject non-draft rows; `publish` must store canonical JSON and its SHA-256 digest without mutating older versions.

Required public methods:

```python
create_draft(name: str, version: str, effective_from: str) -> PolicyVersion
save_draft(version_id: str, snapshot: Mapping[str, object]) -> PolicyVersion
get(version_id: str) -> PolicyVersion
list_versions() -> list[PolicyVersion]
publish(version_id: str) -> PolicyVersion
clone_version(source_id: str, version: str, effective_from: str) -> PolicyVersion
retire(version_id: str) -> PolicyVersion
```

- [ ] **Step 4: Run repository and safety tests**

Run: `python -m unittest tests.test_policy_repository tests.test_repository_safety -v`
Expected: all tests pass; existing repository safety checks remain green.

- [ ] **Step 5: Commit**

Commit: `git add payroll_tool/config/policy_repository.py tests/test_policy_repository.py && git commit -m "Add SQLite policy repository"`

### Task 3: Complete Policy Validation

**Files:**
- Create: `payroll_tool/config/policy_validation.py`
- Test: `tests/test_policy_validation.py`

- [ ] **Step 1: Write table-driven failing tests for conditional requirements**

Cover fixed/flexible worktime, lunch intervals, daily minutes, leave identifiers, payroll formulas, insurance bounds/rates, overtime conversion, tax values, effective dates and hidden inactive sections. Include these assertions:

```python
issues = validate_policy({"company": {"worktime": {"mode": "fixed"}}})
assert any(i.field == "company.worktime.daily_minutes" for i in issues)

issues = validate_policy({"statutory": {"pension": {"enabled": False}}})
assert not any(i.field.startswith("statutory.pension.rate") for i in issues)

issues = validate_policy(policy_with_duplicate_leave_codes())
assert any(i.code == "duplicate" and i.field == "company.leaves[1].code" for i in issues)
```

- [ ] **Step 2: Verify failures**

Run: `python -m unittest tests.test_policy_validation -v`
Expected: import failure.

- [ ] **Step 3: Implement validators as small section functions**

```python
def validate_policy(snapshot: Mapping[str, object]) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    _validate_identity(snapshot, issues)
    _validate_worktime(snapshot.get("company", {}), issues)
    _validate_leaves(snapshot.get("company", {}), issues)
    _validate_overtime(snapshot.get("company", {}), issues)
    _validate_payroll(snapshot.get("company", {}), issues)
    _validate_statutory(snapshot.get("statutory", {}), issues)
    _validate_commercial(snapshot.get("commercial_insurance", []), issues)
    return tuple(issues)
```

Use `Decimal` for all rates and monetary ranges. Return all errors in one pass with exact field paths; do not raise on normal user input errors.

- [ ] **Step 4: Run validation tests and commit**

Run: `python -m unittest tests.test_policy_validation tests.test_config_schema -v`
Expected: all tests pass.

Commit: `git add payroll_tool/config/policy_validation.py tests/test_policy_validation.py && git commit -m "Validate in-app HR policies"`

### Task 4: Policy HTTP API

**Files:**
- Create: `payroll_tool/web/__init__.py`
- Create: `payroll_tool/web/policy_api.py`
- Modify: `app.py`
- Test: `tests/test_policy_api.py`

- [ ] **Step 1: Write failing API contract tests**

Test `POST /api/policies`, `PUT /api/policies/<id>/draft`, `POST /api/policies/<id>/validate`, `POST /api/policies/<id>/publish`, `POST /api/policies/<id>/clone`, and `GET /api/policies`. Verify invalid publish returns HTTP 422 with `{errors: [{field, code, message}]}`, published updates return 409, and valid publish returns status `published` plus SHA-256.

- [ ] **Step 2: Run tests and confirm 404 responses**

Run: `python -m unittest tests.test_policy_api -v`
Expected: endpoint tests fail with HTTP 404.

- [ ] **Step 3: Implement and register the blueprint**

```python
policy_api = Blueprint("policy_api", __name__, url_prefix="/api/policies")

@policy_api.post("/<version_id>/publish")
def publish_policy(version_id: str):
    repository = current_app.extensions["policy_repository"]
    version = repository.get(version_id)
    errors = validate_policy(version.snapshot)
    if errors:
        return jsonify(ok=False, errors=[item.as_dict() for item in errors]), 422
    return jsonify(ok=True, item=repository.publish(version_id).as_dict())
```

Configure `POLICY_DATABASE` under `instance_path`, initialize one repository in `create_app`, and translate missing IDs to 404 and conflicts to 409.

- [ ] **Step 4: Run API tests and commit**

Run: `python -m unittest tests.test_policy_api tests.test_app -v`
Expected: policy API passes; existing app tests may still assert the old HTML and remain scheduled for Task 8.

Commit: `git add payroll_tool/web/__init__.py payroll_tool/web/policy_api.py app.py tests/test_policy_api.py && git commit -m "Expose policy configuration API"`

### Task 5: Legacy Migration and Advanced Backup

**Files:**
- Create: `payroll_tool/config/legacy_migration.py`
- Create: `payroll_tool/config/backup.py`
- Create: `payroll_tool/web/backup_api.py`
- Modify: `app.py`
- Test: `tests/test_policy_backup.py`

- [ ] **Step 1: Write failing migration, round-trip and collision tests**

```python
def test_legacy_workbook_import_creates_draft_not_published():
    draft = migrate_hr_workbook(completed_hr_workbook())
    assert draft["status"] == "draft"
    assert draft["snapshot"]["company"]["worktime"]["daily_minutes"] == 480

def test_import_rejects_same_version_with_different_digest(self):
    with TemporaryDirectory() as directory:
        repository = PolicyRepository(Path(directory) / "policies.sqlite3")
        payload = export_backup(repository)
        changed = mutate_snapshot_without_changing_version(payload)
        with self.assertRaises(BackupConflictError):
            import_backup(repository, changed)
```

- [ ] **Step 2: Verify failures**

Run: `python -m unittest tests.test_policy_backup -v`
Expected: import failure.

- [ ] **Step 3: Implement a versioned ZIP backup and legacy conversion**

Backup archive contents:

```text
manifest.json  # format_version, exported_at, version count and archive digest
policies.json  # policy/version metadata and canonical snapshots
```

Reject path traversal, unknown format versions, invalid hashes and `(policy, version)` collisions with different content. Legacy XLSX import must call existing `parse_hr_workbook`, map every explicit value into the new schema, create a draft, and never publish automatically.

- [ ] **Step 4: Add advanced endpoints and run tests**

Endpoints: `POST /api/advanced/migrate-workbook`, `GET /api/advanced/backup`, and `POST /api/advanced/restore`.

Run: `python -m unittest tests.test_policy_backup tests.test_hr_workbook_import -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

Commit: `git add payroll_tool/config/legacy_migration.py payroll_tool/config/backup.py payroll_tool/web/backup_api.py app.py tests/test_policy_backup.py && git commit -m "Add policy backup and legacy migration"`

### Task 6: Separate Employee Payroll Workbook Import

**Files:**
- Create: `payroll_tool/importers/employee_workbook.py`
- Modify: `payroll_tool/importers/hr_workbook.py`
- Test: `tests/test_employee_workbook.py`

- [ ] **Step 1: Write failing tests for employee-only imports**

Verify employee ID remains a string with leading zeroes, duplicate IDs fail, bonuses and allowances default to zero, policy sheets are not required, and employment-type codes must exist in the selected policy snapshot.

```python
employees = parse_employee_workbook(content, allowed_employment_types={"intern"})
assert employees[0].employee_id == "0012"
assert employees[0].bonus == Decimal("0")
```

- [ ] **Step 2: Verify failures**

Run: `python -m unittest tests.test_employee_workbook -v`
Expected: import failure.

- [ ] **Step 3: Extract employee parsing without duplicating cell conversion**

Move reusable row parsing helpers from `hr_workbook.py` into `employee_workbook.py`; keep compatibility wrappers so legacy migration tests continue to pass. Return the existing employee model consumed by `calculate_payroll`.

- [ ] **Step 4: Run importer regression and commit**

Run: `python -m unittest tests.test_employee_workbook tests.test_hr_workbook_import tests.test_uploaded_inputs -v`
Expected: all tests pass.

Commit: `git add payroll_tool/importers/employee_workbook.py payroll_tool/importers/hr_workbook.py tests/test_employee_workbook.py && git commit -m "Separate employee payroll workbook import"`

### Task 7: Convert Published Snapshots into Calculation Inputs

**Files:**
- Modify: `payroll_tool/config/policy_serialization.py`
- Test: `tests/test_policy_serialization.py`

- [ ] **Step 1: Write failing conversion tests with non-default HR values**

Use daily standard time `435` minutes, monthly pay days `20.83`, a custom leave code, flexible mode and custom insurance rates. Assert the resulting attendance and payroll policies preserve those exact values and contain no fallback to old company values.

- [ ] **Step 2: Verify failures**

Run: `python -m unittest tests.test_policy_serialization -v`
Expected: conversion functions are missing.

- [ ] **Step 3: Implement typed conversion functions**

```python
def calculation_policy_from_snapshot(snapshot: Mapping[str, object]) -> CalculationPolicy:
    return CalculationPolicy(
        attendance=attendance_policy_from_snapshot(snapshot),
        leave_rules=leave_rules_from_snapshot(snapshot),
        income_items=income_items_from_snapshot(snapshot),
        statutory=statutory_rules_from_snapshot(snapshot),
        perfect_attendance_award=Decimal(str(snapshot["company"]["payroll"]["award"])),
    )
```

Do not execute arbitrary formulas. Map only supported formula identifiers and reject unknown identifiers with a field-specific `ValueError` before calculation.

- [ ] **Step 4: Run cross-engine tests and commit**

Run: `python -m unittest tests.test_policy_serialization tests.test_attendance_engine tests.test_payroll_engine tests.test_social_insurance_policy -v`
Expected: all tests pass.

Commit: `git add payroll_tool/config/policy_serialization.py tests/test_policy_serialization.py && git commit -m "Convert policy snapshots for calculation"`

### Task 8: Replace the Workspace with an In-App Configuration UI

**Files:**
- Create: `static/workspace.css`
- Create: `static/workspace.js`
- Modify: `templates/workspace.html`
- Modify: `tests/test_app.py`
- Test: `tests/test_workspace_ui.py`

- [ ] **Step 1: Replace old HTML assertions with the new user contract**

Assert the first screen contains payroll month, attendance upload and employee payroll upload; does not contain `name="payroll_rules"`; and exposes navigation for 薪酬计算、规则配置、使用说明 and 高级设置. Assert rule tabs for 公司制度、法定政策、商业保险、员工例外 and 月度任务.

- [ ] **Step 2: Run UI contract tests and verify old markup fails**

Run: `python -m unittest tests.test_workspace_ui tests.test_app.AppTests.test_workspace_is_the_first_screen -v`
Expected: assertions fail against the current workspace.

- [ ] **Step 3: Implement the layout and configuration controls**

Use a restrained left navigation, top rule-version bar, segmented rule tabs, unframed page sections, compact tables and modal forms. Use switches for enable/disable, selects for finite strategies, numeric/date/time inputs for values, and icon buttons with accessible names for edit/delete. Do not render sample rates, 8 hours, 21.75 days or sample regions as saved values.

Required UI actions:

```javascript
saveDraft()       // PUT current visible and retained configuration
validateDraft()   // POST and map field errors to controls
publishDraft()    // confirm then publish only after successful validation
cloneVersion()    // create editable successor
editLeave(id)     // modal CRUD with conditional payroll fields
editInsurance(id) // modal CRUD with conditional base/rate fields
```

- [ ] **Step 4: Implement responsive behavior and accessibility checks**

At widths below 820px, collapse navigation, stack forms, allow tables to scroll horizontally, and size modals to the viewport. Preserve visible focus outlines, associated labels, button names and error summaries.

- [ ] **Step 5: Run UI tests and commit**

Run: `python -m unittest tests.test_workspace_ui tests.test_app -v`
Expected: updated UI contract passes.

Commit: `git add static/workspace.css static/workspace.js templates/workspace.html tests/test_workspace_ui.py tests/test_app.py && git commit -m "Build in-app HR configuration workspace"`

### Task 9: Make Monthly Tasks Reference Published Policies

**Files:**
- Modify: `app.py`
- Modify: `payroll_tool/config/policy_repository.py`
- Test: `tests/test_monthly_task_api.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing end-to-end task tests**

Create a published policy through the repository, upload `attendance.xlsx` and `employee_payroll.xlsx`, and post `policy_version_id`. Assert missing/draft/retired versions fail, successful results record the policy hash, and changing a newer policy does not alter an older task download.

- [ ] **Step 2: Verify old task contract fails**

Run: `python -m unittest tests.test_monthly_task_api -v`
Expected: request fails because `policy_version_id` is not consumed and employee upload is unsupported.

- [ ] **Step 3: Replace rule workbook handling in `/tasks`**

Set required uploads to attendance and employee payroll only. Resolve the published version from `policy_version_id`, validate its effective date against the task period, convert its snapshot with `calculation_policy_from_snapshot`, and parse employee data separately. Store `policy_version_id`, canonical snapshot bytes and snapshot hash in the task record for audit/download.

- [ ] **Step 4: Update audit generation**

Use the immutable canonical JSON bytes as `config_bytes`; use policy ID/version from repository metadata. Never reread the current draft or latest policy during download.

- [ ] **Step 5: Run app, engine and export regression**

Run: `python -m unittest tests.test_monthly_task_api tests.test_app tests.test_export tests.test_audit -v`
Expected: all tests pass and no task endpoint accepts `payroll_rules` as a normal monthly input.

- [ ] **Step 6: Commit**

Commit: `git add app.py payroll_tool/config/policy_repository.py tests/test_monthly_task_api.py tests/test_app.py && git commit -m "Use published policies for monthly payroll"`

### Task 10: Browser Verification and Documentation Migration

**Files:**
- Modify: `docs/superpowers/specs/2026-08-19-general-payroll-product-requirements.md`
- Modify: `docs/superpowers/specs/2026-08-19-hr-configurable-rules-design.md`
- Modify: `docs/superpowers/specs/2026-08-19-input-template-and-data-quality-design.md`
- Modify: `docs/superpowers/specs/2026-08-19-local-app-and-data-security-design.md`
- Modify: `README.md`

- [ ] **Step 1: Update terminology and operating instructions**

Replace “HR uploads a rule pack each month” with “HR configures and publishes a local policy version.” Document employee payroll XLSX, attendance XLSX, advanced backup and one-time legacy migration. Preserve “rule snapshot/version” where it describes audit internals.

- [ ] **Step 2: Run placeholder and hidden-default scans**

Run: `rg -n "TBD|TODO|09:00|10:00|19:30|19:45|默认.*8|默认.*21\.75|上传规则包" templates static payroll_tool docs README.md`
Expected: no product defaults or normal-flow rule-upload instructions; test fixtures and migration documentation may contain clearly labelled examples.

- [ ] **Step 3: Run the full test suite**

Run: `python -m unittest discover -s tests -v`
Expected: all tests pass.

- [ ] **Step 4: Start the local server and verify desktop/mobile views**

Run: `PORT=5074 ./start.sh`
Expected: server starts on `http://127.0.0.1:5074/` without changing the existing `5073` process.

Use the in-app browser to verify at 1440x900 and 390x844: initial empty state, draft save/restore, validation error navigation, leave modal, insurance modal, published read-only state, clone flow, monthly two-file upload and advanced backup. Capture screenshots and verify no text overlap or horizontal page overflow; table-only horizontal scrolling is allowed on mobile.

- [ ] **Step 5: Commit documentation and verification adjustments**

Commit: `git add docs/superpowers/specs README.md && git commit -m "Document in-app policy configuration"`

- [ ] **Step 6: Request final code review before integration**

Use `superpowers:requesting-code-review` against the complete branch diff. Resolve every correctness, data-integrity and missing-test finding, rerun the full suite, then use `superpowers:verification-before-completion` before claiming completion or pushing to GitHub.
