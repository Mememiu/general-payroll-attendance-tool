# Desktop Release And Upgrade Design

## Objective

Deliver the general payroll tool as free, open-source, unsigned macOS and Windows desktop packages. A user must be able to install or extract the package, launch the application without Python, calculate payroll offline, close it cleanly, and upgrade without losing local rules, calculation records, or exported results.

## Release Boundary

- Source and release metadata are published through GitHub.
- GitHub Actions builds macOS and Windows artifacts on their native runners.
- The first release is unsigned and not notarized. Documentation must describe macOS Gatekeeper and Windows SmartScreen first-launch steps.
- No employee data, company policy database, uploaded workbook, calculation result, or local log is included in source control or release artifacts.
- Signing and automatic online updates are outside the first free release. Upgrades are performed by installing a newer package over the application while retaining the user data directory.

## Desktop Architecture

`desktop.py` becomes the platform-neutral launcher. It resolves the per-user application data directory, initializes storage, starts Flask on `127.0.0.1` using an available port, opens the application in a native WebView, and stops the server when the window closes. The HTTP service never listens on a LAN address.

PyInstaller builds a windowed executable containing Python, application packages, templates, static assets, and required runtime dependencies. The source-run Flask entry point remains available for development but is not the end-user launch path.

## Local Data Layout

The application uses a stable platform-specific directory:

- macOS: `~/Library/Application Support/GeneralPayrollTool/`
- Windows: `%LOCALAPPDATA%/GeneralPayrollTool/`

The directory contains:

- `policies/policies.sqlite3`: rule versions and calculation records.
- `tasks/<task-id>/`: uploaded workbooks, results, and privacy-safe task metadata.
- `rule-packs/`: legacy/imported rule-pack data retained for compatibility.
- `backups/`: timestamped pre-migration backups.
- `logs/app.log`: operational errors and version information, without salary rows or workbook contents.
- `data-version.json`: application data schema version and last successful migration.

Development and test configurations may continue to inject temporary storage roots. Production desktop startup must never write into the installed application bundle or source tree.

## Upgrade And Migration

Every desktop startup compares the stored data schema version with the version supported by the executable.

1. A new installation creates the directory and current version marker.
2. Before any forward migration, the application copies the SQLite database and version marker into a timestamped backup directory.
3. Migrations run in ordered, idempotent steps inside database transactions where applicable.
4. The version marker is updated only after all steps succeed.
5. On failure, startup stops with a user-facing error containing the backup location. It must not continue with partially migrated data.
6. A newer data schema cannot be opened by an older executable; the user is told to reinstall the newer version.

The first release establishes schema version `1`. Existing development data without a marker is adopted as version `1` after a backup because the current repository initializes its SQLite tables idempotently.

## Packaging And Releases

- `pyproject.toml` declares desktop and build dependencies and the application version.
- A checked-in PyInstaller specification defines hidden imports and bundles `templates/` and `static/`.
- A local build script produces the native artifact for developer verification.
- GitHub Actions runs repository safety checks and all tests, then builds on `macos-latest` and `windows-latest`.
- Tag pushes matching `v*` create a GitHub Release and attach both platform artifacts plus SHA-256 checksums.
- The Windows artifact is a portable ZIP containing the executable for the first release; the macOS artifact is a ZIP containing the `.app`. This avoids unreliable unsigned installer wrappers while still providing double-click launchable applications.

## End-To-End Acceptance

Acceptance uses user-supplied, sanitized real attendance and employee payroll workbooks. The test must cover:

- a published HR rule version;
- employee-ID matching;
- fixed and configured work duration behavior represented in the supplied data;
- leave, offsite work, business trip, overtime, absence, late arrival, and review cases present in the data;
- full-time, intern, and conversion employees present in the data;
- statutory contributions, housing fund, commercial insurance, cumulative tax, bonus, allowance, and perfect-attendance output where configured;
- Excel export opening successfully and audit totals reconciling to employee detail;
- a second run after application restart;
- an upgrade simulation proving rules, records, and prior results remain available.

No release is called validated against real data unless the exact input files and expected reconciliation totals are available locally. Automated synthetic tests remain necessary but are not a substitute for this acceptance pass.

## User Documentation

The release includes:

- installation and first-launch steps for macOS and Windows;
- the rule configuration workflow and required fields;
- input workbook preparation and employee-ID matching rules;
- monthly calculation, review, and export workflow;
- backup, restore, and upgrade instructions;
- privacy, offline operation, troubleshooting, and unsigned-package warnings;
- version number and changelog.

## Completion Criteria

- Automated tests pass on macOS, Windows, and Linux CI.
- Repository safety scan passes.
- macOS and Windows artifacts are produced by native runners without Python installed on the target machine.
- Desktop storage is outside the application bundle and survives upgrade simulation.
- The app binds only to loopback and closes its server with the desktop window.
- Sanitized real-data acceptance passes with recorded reconciliation evidence.
- Documentation matches the downloadable artifacts.
- The release commit and tag are pushed to GitHub and both artifacts are attached to the release.
