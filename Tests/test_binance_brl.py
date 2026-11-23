# BLOCO — Cenários de teste para conversão histórica e atual das posições Binance para reais.
import unittest
from unittest.mock import patch
from binance_brl import convert_positions_brl


class Store:
    def __init__(self):
        self.data = {}

    def get(self, symbol, minute):
        return self.data.get((symbol, minute))

    def save(self, symbol, minute, price):
        self.data[symbol, minute] = price


class BRLTests(unittest.TestCase):
    @patch("crypto.fetch")
    def test_historical_cost_different_from_current_price(self, fetch):
        fetch.side_effect = [
            {"symbols": [{"symbol": "USDTBRL"}, {"symbol": "BTCUSDT"}]},
            [{"symbol": "USDTBRL", "price": "6"}, {"symbol": "BTCUSDT", "price": "100"}],
            [[60000, "4"]],
        ]
        rows = [
            {
                "asset": "BTC",
                "quantity": "2",
                "history_status": "pares Spot consultados",
                "purchases": [
                    {
                        "currency": "USDT",
                        "time": 65000,
                        "price": "50",
                        "quantity": "2",
                        "quote_value": "100",
                    }
                ],
            }
        ]
        result = convert_positions_brl(rows, Store())[0]
        self.assertEqual(result["invested_brl"], "400")
        self.assertEqual(result["current_value"], "1200")
        self.assertEqual(result["valuation_currency"], "BRL")
        self.assertFalse(result["invested_brl_partial"])

    @patch("crypto.fetch")
    def test_missing_historical_rate_is_not_today_rate(self, fetch):
        fetch.side_effect = [
            {"symbols": [{"symbol": "USDTBRL"}]},
            [{"symbol": "USDTBRL", "price": "6"}],
            [],
        ]
        rows = [
            {
                "asset": "USDT",
                "quantity": "1",
                "purchases": [{"currency": "USDT", "time": 65000, "price": "1", "quantity": "1"}],
            }
        ]
        result = convert_positions_brl(rows, Store())[0]
        self.assertIsNone(result["invested_brl"])
        self.assertTrue(result["invested_brl_partial"])
        self.assertEqual(result["current_value"], "6")


if __name__ == "__main__":
    unittest.main()
