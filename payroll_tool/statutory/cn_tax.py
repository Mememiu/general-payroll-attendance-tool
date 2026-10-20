"""Annual cumulative withholding for China mainland comprehensive income."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


CENTS = Decimal("0.01")
MONTHLY_BASIC_DEDUCTION = Decimal("5000")
TAX_BRACKETS = (
    (Decimal("36000"), Decimal("0.03"), Decimal("0")),
    (Decimal("144000"), Decimal("0.10"), Decimal("2520")),
    (Decimal("300000"), Decimal("0.20"), Decimal("16920")),
    (Decimal("420000"), Decimal("0.25"), Decimal("31920")),
    (Decimal("660000"), Decimal("0.30"), Decimal("52920")),
    (Decimal("960000"), Decimal("0.35"), Decimal("85920")),
    (None, Decimal("0.45"), Decimal("181920")),
)


@dataclass(frozen=True)
class CumulativeWithholdingResult:
    taxable_base: Decimal
    cumulative_tax: Decimal
    current_withholding: Decimal
    carry_forward_balance: Decimal = Decimal("0")


def calculate_cn_cumulative_withholding(
    *,
    current_taxable_income: Decimal,
    prior_taxable_income: Decimal,
    months_in_year: int,
    prior_withheld: Decimal,
    prior_special_deductions: Decimal = Decimal("0"),
    current_special_deductions: Decimal = Decimal("0"),
    monthly_exemption: Decimal = MONTHLY_BASIC_DEDUCTION,
    brackets: tuple[tuple[Decimal, Decimal, Decimal], ...] | None = None,
    negative_tax_mode: str = "zero",
) -> CumulativeWithholdingResult:
    if months_in_year < 1 or months_in_year > 12:
        raise ValueError("months_in_year must be between 1 and 12")
    values = (
        current_taxable_income,
        prior_taxable_income,
        prior_withheld,
        prior_special_deductions,
        current_special_deductions,
        monthly_exemption,
    )
    if any(value < 0 for value in values):
        raise ValueError("cumulative tax inputs cannot be negative")
    taxable_base = max(
        Decimal("0"),
        current_taxable_income
        + prior_taxable_income
        - monthly_exemption * months_in_year
        - prior_special_deductions
        - current_special_deductions,
    )
    cumulative_tax = _tax_for_configured(taxable_base, brackets) if brackets else _tax_for(taxable_base)
    if negative_tax_mode not in {"zero", "carry_forward"}:
        raise ValueError("negative_tax_mode is unsupported")
    withholding_difference = cumulative_tax - prior_withheld
    carry_forward = (
        max(Decimal("0"), -withholding_difference)
        if negative_tax_mode == "carry_forward" else Decimal("0")
    )
    return CumulativeWithholdingResult(
        taxable_base=_money(taxable_base),
        cumulative_tax=_money(cumulative_tax),
        current_withholding=_money(max(Decimal("0"), withholding_difference)),
        carry_forward_balance=_money(carry_forward),
    )


def _tax_for(taxable_base: Decimal) -> Decimal:
    for upper_limit, rate, quick_deduction in TAX_BRACKETS:
        if upper_limit is None or taxable_base <= upper_limit:
            return taxable_base * rate - quick_deduction
    raise AssertionError("tax brackets are incomplete")


def _tax_for_configured(
    taxable_base: Decimal,
    brackets: tuple[tuple[Decimal, Decimal, Decimal], ...],
) -> Decimal:
    if not brackets or brackets[0][0] != 0:
        raise ValueError("tax brackets must start at zero")
    previous: Decimal | None = None
    selected: tuple[Decimal, Decimal, Decimal] | None = None
    for threshold, rate, quick_deduction in brackets:
        if min(threshold, rate, quick_deduction) < 0:
            raise ValueError("tax bracket values cannot be negative")
        if previous is not None and threshold <= previous:
            raise ValueError("tax bracket thresholds must increase")
        previous = threshold
        if taxable_base >= threshold:
            selected = (threshold, rate, quick_deduction)
    if selected is None:
        raise AssertionError("tax brackets are incomplete")
    return taxable_base * selected[1] - selected[2]


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)
