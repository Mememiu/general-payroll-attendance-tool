# Desktop Release And Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce double-clickable, offline macOS and Windows release artifacts with persistent user data, guarded schema migration, release automation, real-data acceptance evidence, and complete user documentation.

**Architecture:** Keep Flask and the calculation engine unchanged behind a loopback-only server. Add a focused desktop runtime package for platform data paths, migration and lifecycle; package it with PyInstaller and a native WebView. Build each operating-system artifact on its native GitHub runner and publish only after tests and repository safety checks pass.

**Tech Stack:** Python 3.11, Flask, pywebview, platformdirs, PyInstaller, SQLite, unittest, GitHub Actions.

---

### Task 1: Production Data Directory

**Files:**
- Create: `payroll_tool/desktop/__init__.py`
- Create: `payroll_tool/desktop/storage.py`
- Modify: `app.py`
- Test: `tests/test_desktop_storage.py`

- [ ] Write tests proving macOS and Windows paths resolve to `GeneralPayrollTool`, production configuration maps policy, task and rule-pack roots below that directory, and injected test paths remain unchanged.
- [ ] Run `python -m unittest tests.test_desktop_storage -v` and confirm the new imports or behavior fail.
- [ ] Implement `user_data_root(system=None, environ=None, home=None)` with `platformdirs.user_data_path` and `production_config(root)` returning explicit `POLICY_DATABASE`, `TASK_ROOT`, and `RULE_PACK_ROOT` paths.
- [ ] Add `create_desktop_app(data_root=None)` in `app.py`; it calls `create_app(production_config(...))` without changing `create_app()` test behavior.
- [ ] Run the focused tests and `tests.test_app`; confirm all pass.
- [ ] Commit only Task 1 files with message `Add persistent desktop data storage`.

### Task 2: Versioned Migration And Automatic Backup

**Files:**
- Create: `payroll_tool/desktop/migrations.py`
- Test: `tests/test_desktop_migrations.py`

- [ ] Write tests for a new install, adoption of existing unversioned data, idempotent restart, pre-migration backup, failed migration preserving the old marker, and rejection of a newer unsupported schema.
- [ ] Run `python -m unittest tests.test_desktop_migrations -v` and confirm failure.
- [ ] Implement schema version `1`, atomic JSON marker writes, timestamped backup directories, and an ordered migration registry. Copy `policies.sqlite3` and an existing marker before adoption or forward migration.
- [ ] Ensure migration failures raise a typed `DataMigrationError` exposing the backup directory but never employee or salary data.
- [ ] Run focused tests and commit with message `Add guarded desktop data migrations`.

### Task 3: Native Desktop Lifecycle

**Files:**
- Modify: `desktop.py`
- Create: `payroll_tool/desktop/launcher.py`
- Test: `tests/test_desktop_launcher.py`
- Modify: `tests/test_app.py`

- [ ] Write tests proving the launcher runs migration before creating Flask, chooses a free loopback port, passes only the loopback URL to the WebView, and always stops the server when the window closes or creation fails.
- [ ] Run the focused tests and confirm failure.
- [ ] Retain `LocalAppServer` as the tested server boundary and implement `run_desktop()` with dependency-injected WebView creation for tests. Use `webview.create_window("通用薪酬绩效工具", url, min_size=(1024, 720))` and `webview.start()`.
- [ ] Add a guarded `main()` that shows a native error dialog or writes a concise stderr message when startup/migration fails, then exits nonzero.
- [ ] Run desktop tests and commit with message `Add native desktop application lifecycle`.

### Task 4: Reproducible Native Packaging

**Files:**
- Modify: `pyproject.toml`
- Create: `packaging/general-payroll-tool.spec`
- Create: `scripts/build_desktop.py`
- Create: `tests/test_packaging_config.py`
- Modify: `.gitignore`

- [ ] Write static packaging tests proving the desktop dependencies, entry point, templates/static data, application name, windowed mode, and supported platform artifact names are present.
- [ ] Run `python -m unittest tests.test_packaging_config -v` and confirm failure.
- [ ] Add `pywebview`, `platformdirs`, and a `general-payroll-tool` project script; define `desktop` and `build` optional dependency groups containing PyInstaller only where needed.
- [ ] Create the PyInstaller spec with `app.py`, `desktop.py`, `payroll_tool`, `templates`, and `static` collected without any `instance` data.
- [ ] Implement `scripts/build_desktop.py` to clean only generated `build/` and `dist/`, invoke PyInstaller, and write a SHA-256 checksum for the artifact.
- [ ] Run tests, build the macOS artifact locally, launch it against a temporary data directory, verify HTTP 200 and clean shutdown, then commit with message `Package native desktop applications`.

### Task 5: Cross-Platform CI And GitHub Release

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Test: `tests/test_release_workflow.py`

- [ ] Write tests parsing both workflow files and asserting Linux/macOS/Windows tests, native package builds, safety scan, artifact upload, tag-only release, and SHA-256 files.
- [ ] Run `python -m unittest tests.test_release_workflow -v` and confirm failure.
- [ ] Expand CI to a three-OS matrix and add a release workflow triggered by `v*` tags. Each native runner installs `.[build]`, runs tests and safety checks, builds, archives, and uploads its artifact; the release job downloads artifacts and publishes them using GitHub's standard token.
- [ ] Validate workflow YAML locally, run repository safety checks, and commit with message `Automate cross-platform desktop releases`.

### Task 6: Real-Data Acceptance Harness

**Files:**
- Create: `scripts/acceptance_real_data.py`
- Create: `tests/test_real_data_acceptance.py`
- Create: `docs/acceptance/README.md`

- [ ] Write tests that generate sanitized representative XLSX inputs, run the same application task endpoint, download the result, reopen every sheet, and reconcile employee count, employee IDs, payroll totals, review count, and audit hashes.
- [ ] Run the focused test and confirm failure.
- [ ] Implement a command that accepts attendance, payroll, policy/version, period and an expected-results JSON path. It must write only digests and aggregate reconciliation evidence, never raw payroll rows.
- [ ] Run the synthetic harness. Then run it against user-supplied sanitized real files and record a privacy-safe acceptance report locally under ignored `instance/acceptance/`.
- [ ] Commit the harness, tests and instructions, but never the real workbooks or local report, with message `Add real-data release acceptance harness`.

### Task 7: User Guide, Upgrade Guide And Release Metadata

**Files:**
- Modify: `README.md`
- Modify: `docs/USER_GUIDE.md`
- Create: `docs/INSTALL.md`
- Create: `docs/UPGRADING.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`

- [ ] Add documentation tests or repository assertions for macOS Gatekeeper, Windows SmartScreen, offline storage paths, backup/restore, upgrade behavior, employee-ID matching, rule publication, monthly workflow and troubleshooting.
- [ ] Update the documents with exact artifact names and first-launch instructions; mark version `0.2.0` as the first desktop beta until real-data acceptance passes.
- [ ] Run documentation tests and safety scan; commit with message `Document desktop installation and upgrades`.

### Task 8: Release Verification And Publication

**Files:**
- No production source changes unless verification exposes a tested defect.

- [ ] Run `python scripts/check_repository_safety.py` and confirm no forbidden or sensitive tracked files.
- [ ] Run `PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -q` with loopback permission and record the exact count.
- [ ] Build and smoke-test the macOS `.app` from a clean environment; verify first run, calculation, restart persistence, upgrade simulation, export and clean shutdown.
- [ ] Review `git status` and stage no user-owned files (`tests/test_daily_pipeline.py`, `.superpowers/`, the existing statutory plan, or `instance/`).
- [ ] Fast-forward the reviewed feature branch to local `main`, run the full suite again, and push `main` to GitHub.
- [ ] After sanitized real-data acceptance passes, create and push tag `v0.2.0`; wait for both release artifacts and verify their checksums and GitHub download links.
