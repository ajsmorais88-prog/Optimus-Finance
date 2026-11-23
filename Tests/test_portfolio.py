# BLOCO — Cenários de teste para registro das posições observadas para o histórico de patrimônio.
import unittest
from decimal import Decimal
from portfolio import position_total


class PortfolioTests(unittest.TestCase):
    def test_current_positions_not_historical_purchases(self):
        records = [
            {
                "kind": "investments",
                "amount": None,
                "crypto_data": {
                    "current_value": "750.12",
                    "valuation_currency": "BRL",
                    "invested_brl": "25000",
                },
            },
            {
                "kind": "investments",
                "amount": 999,
                "pluggy_data": {"balance": 250, "currency": "BRL"},
            },
            {"kind": "investments", "amount": 7.77},
            {
                "kind": "investments",
                "amount": None,
                "crypto_data": {"current_value": 999, "valuation_currency": "USDT"},
            },
            {"kind": "cards", "amount": 5000},
        ]
        self.assertEqual(position_total(records), Decimal("1007.89"))


if __name__ == "__main__":
    unittest.main()
