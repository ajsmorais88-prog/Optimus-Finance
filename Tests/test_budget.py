# BLOCO — Cenários de teste para validação das regras de budget.
import unittest
from decimal import Decimal
from app import validate_budget


class BudgetTests(unittest.TestCase):
    def test_valid_decimal_percentages(self):
        self.assertEqual(
            validate_budget(
                {
                    "monthly_income": "5000",
                    "fixed_percent": "50",
                    "credit_percent": "35.5",
                    "investment_percent": "14.5",
                }
            ),
            (Decimal("5000"), Decimal("50"), Decimal("35.5"), Decimal("14.5")),
        )

    def test_invalid_totals_values_and_precision(self):
        valid = {
            "monthly_income": "5000",
            "fixed_percent": "50",
            "credit_percent": "40",
            "investment_percent": "10",
        }
        for change in [
            {"investment_percent": "11"},
            {"fixed_percent": "-1"},
            {"credit_percent": "NaN"},
            {"monthly_income": "0"},
            {"investment_percent": "10.001"},
        ]:
            with self.assertRaises(ValueError):
                validate_budget({**valid, **change})


if __name__ == "__main__":
    unittest.main()
