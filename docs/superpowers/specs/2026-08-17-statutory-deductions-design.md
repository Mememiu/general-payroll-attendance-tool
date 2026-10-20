# HR-Configured Statutory Deductions Design

## Goal

Apply the current task's HR workbook statutory rules to each employee's payroll result without embedding regional defaults. The result must expose gross pay, employee deductions, employer cost, individual income tax, net pay, and total employer cost.

## Scope

This change implements statutory contribution input parsing, per-employee eligibility, base resolution, payroll integration, and export columns. Annual cumulative withholding is intentionally a separate follow-up; this change will expose the taxable amount after employee statutory deductions but will not calculate tax from the cumulative-tax sheet yet.

## Workbook Contract

`员工薪酬` adds `statutory_enabled` after `employee_id`. HR must enter `是` or `否` for every employee. This is the sole eligibility control: the software does not infer eligibility from employment type. A common use is setting interns to `否` and employees after conversion to `是`.

For an eligible employee, the existing pension, medical, and work-injury tiers must select an enabled tier row. The existing social and fund base mode/value columns remain the employee overrides. Disabled employees may leave tiers and statutory base override fields blank.

`五险一金` remains the source of enabled contribution rows, rates, effective period, bounds, fixed base, and source metadata. It must contain enough enabled rows to construct every contribution required for an employee marked `是`; otherwise upload validation blocks calculation.

## Calculation

1. Calculate `base_pay`, allowance, and bonus using existing attendance logic.
2. Resolve social and housing-fund bases using the employee override mode first, otherwise each contribution row's configured mode. Apply its lower and upper limits. Base selection is auditable per contribution row.
3. Sum employee contributions into `employee_statutory_deduction` and employer contributions into `employer_statutory_cost`.
4. Derive `taxable_income_after_statutory = taxable_income - employee_statutory_deduction`, floored at zero. This becomes the input for the later cumulative-tax step.
5. Until cumulative tax is integrated, `individual_income_tax` is zero. `net_pay = gross_pay - employee_statutory_deduction`. `total_employer_cost = gross_pay + employer_statutory_cost`.

All monetary values round to cents using existing half-up rounding. An ineligible employee gets zero statutory amounts and no missing-tier validation.

## Components

- `payroll_tool/importers/hr_workbook.py`: parse statutory eligibility and workbook contribution rules into typed models.
- `payroll_tool/statutory/social_insurance.py`: resolve bases per contribution row and calculate named employee/employer amounts plus totals.
- `payroll_tool/payroll/engine.py`: compose gross pay and statutory result into an expanded immutable payroll result.
- `app.py`: pass the uploaded workbook rules and payroll month into the pure payroll calculation.
- `payroll_tool/exporters/excel.py`: automatically exports the expanded typed result fields.
- `tests/`: cover employee opt-out, per-item bounds and bases, integration into net pay and cost, upload validation, and exported headers.

## Failure Handling

Calculation blocks with a specific HR-workbook error when an eligible employee has no required tier, an enabled contribution has incomplete base or rate data, a rule is outside its effective period, or the policy rows disagree on region/effective period. No default rate, base, or region is applied.

## Compatibility

The fixed HR workbook format advances to `1.1.0`; previous `1.0.0` templates are rejected with the existing redownload prompt because their header cannot represent per-employee eligibility.
