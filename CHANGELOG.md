# Changelog

## 0.2.0-beta.3

### Added

- A blank, validated employee payroll workbook template downloadable from the calculation page.

## 0.2.0-beta.2

### Fixed

- Windows CI no longer treats POSIX mode bits as Windows ACL permissions.

## 0.2.0-beta.1

### Added

- Double-clickable macOS application packaging and native WebView lifecycle.
- Windows native build and GitHub Release automation.
- Persistent per-user application storage with version markers and pre-migration backups.
- Privacy-safe real-data acceptance evidence.
- Installation, first-launch and upgrade documentation for unsigned releases.

### Validation Status

- The macOS Apple Silicon artifact builds and launches successfully.
- Sanitized real attendance and employee payroll reconciliation is still required before the beta is promoted to a stable release.

## Unreleased

### Added

- Current-upload-only attendance and HR workbook validation.
- Fixed HR workbook template with attendance, leave, payroll, tax, and statutory fields.
- Configurable fixed/flexible attendance calculation and conservative approval parsing.
- HR-schedule-derived morning, afternoon, and full-day approval resolution.
- Employee attendance aggregation and full-time, intern, and conversion payroll calculation.
- Token-protected Excel result download with privacy-safe audit metadata.
- Annual cumulative individual-income-tax withholding from the HR workbook, including web task results.
- Employees without prior-year tax records automatically start cumulative withholding from zero.
- Employee statutory tiers and social/housing-fund base overrides now affect contribution calculation.
- HR-configured attendance boundaries and full-day lateness threshold now affect daily attendance calculation.
- Leave approval coverage and HR-configured leave pay ratios now affect payroll calculation.
- Payroll exports now separate attendance deductions from sick-leave deductions.
- Company and employee-level perfect-attendance awards now affect eligible payroll results.
- Payroll exports now include attendance, absence, lateness, leave-hour, and review-reason summaries.
- Payroll exports now include the employee name for human-readable review while retaining employee ID matching.
- Hire/termination dates now bound attendance records and support configured full-attendance entry/termination days.
- Entry/termination full-attendance days now ignore punch anomalies but preserve leave approvals.
- Overtime approvals are separated from normal attendance, support midnight crossing, and export zero cash overtime pay.
- Overtime now starts at the same inferred checkout boundary used by daily attendance.
- Repository safety checks and GitHub Actions tests.

### Distribution Note

- Packages are intentionally unsigned because this is a free open-source project; operating-system first-launch warnings are documented.
