from decimal import Decimal
import unittest

from payroll_tool.statutory.cn_tax import calculate_cn_cumulative_withholding


class CnTaxTests(unittest.TestCase):
    def test_cumulative_withholding_deducts_current_month_from_total_tax(self):
        result = calculate_cn_cumulative_withholding(
            current_taxable_income=Decimal("10000"),
            prior_taxable_income=Decimal("10000"),
            months_in_year=2,
            prior_withheld=Decimal("90"),
        )

        self.assertEqual(result.taxable_base, Decimal("10000.00"))
        self.assertEqual(result.current_withholding, Decimal("210.00"))

    def test_withholding_does_not_go_negative_after_prior_over_withholding(self):
        result = calculate_cn_cumulative_withholding(
            current_taxable_income=Decimal("6000"),
            prior_taxable_income=Decimal("0"),
            months_in_year=1,
            prior_withheld=Decimal("100"),
        )

        self.assertEqual(result.current_withholding, Decimal("0.00"))

    def test_hr_exemption_and_brackets_control_withholding(self):
        result = calculate_cn_cumulative_withholding(
            current_taxable_income=Decimal("10000"),
            prior_taxable_income=Decimal("0"),
            months_in_year=1,
            prior_withheld=Decimal("0"),
            monthly_exemption=Decimal("2000"),
            brackets=((Decimal("0"), Decimal("0.10"), Decimal("0")),),
        )

        self.assertEqual(result.taxable_base, Decimal("8000.00"))
        self.assertEqual(result.current_withholding, Decimal("800.00"))

    def test_carry_forward_mode_exposes_prior_over_withholding_balance(self):
        result = calculate_cn_cumulative_withholding(
            current_taxable_income=Decimal("6000"),
            prior_taxable_income=Decimal("0"),
            months_in_year=1,
            prior_withheld=Decimal("100"),
            negative_tax_mode="carry_forward",
        )

        self.assertEqual(result.current_withholding, Decimal("0.00"))
        self.assertEqual(result.carry_forward_balance, Decimal("70.00"))


if __name__ == "__main__":
    unittest.main()
