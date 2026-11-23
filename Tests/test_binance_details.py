# BLOCO — Cenários de teste para enriquecimento das posições com compras e preços históricos.
import unittest
from unittest.mock import patch

from binance_details import enrich_positions


class BinanceDetailsTests(unittest.TestCase):
    @patch("crypto.fetch")
    def test_incremental_cursor_does_not_duplicate_purchases(self, fetch):
        class Store:
            def __init__(self):
                self.data = {}

            def load(self):
                return dict(self.data)

            def save(self, symbol, state):
                self.data[symbol] = state

        store = Store()
        page = [
            {
                "id": 1,
                "isBuyer": True,
                "qty": "1",
                "price": "10",
                "quoteQty": "10",
                "commission": "0",
                "commissionAsset": "BTC",
                "time": 1000,
            }
        ]

        def answer(url, headers=None, data=None):
            if "exchangeInfo" in url:
                return {
                    "symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT"}]
                }
            if "ticker/price" in url:
                return []
            if "/time" in url:
                return {"serverTime": 1000}
            if "fromId=0" in url:
                return page
            self.assertIn("fromId=2", url)
            return []

        fetch.side_effect = answer
        balances = [{"asset": "BTC", "quantity": "1"}]
        first = enrich_positions(balances, "key", "secret", store)
        self.assertEqual(first[0]["purchase_totals"], [{"currency": "USDT", "value": "10"}])
        store.data["BTCUSDT"]["checked_at"] = 0
        second = enrich_positions(balances, "key", "secret", store)
        self.assertEqual(second[0]["purchase_totals"], [{"currency": "USDT", "value": "10"}])
        self.assertEqual(second[0]["purchased_quantity"], "1")

    @patch("crypto.fetch")
    def test_cached_progress_resumes_and_does_not_starve_assets(self, fetch):
        class Store:
            def __init__(self):
                self.data = {}

            def load(self):
                return dict(self.data)

            def save(self, symbol, state):
                self.data[symbol] = state

        store = Store()
        symbols = [
            {"symbol": f"A{i}USDT", "baseAsset": f"A{i}", "quoteAsset": "USDT"} for i in range(61)
        ]
        balances = [{"asset": f"A{i}", "quantity": "1"} for i in range(61)]

        def answer(url, headers=None, data=None):
            if "exchangeInfo" in url:
                return {"symbols": symbols}
            if "ticker/price" in url:
                return []
            if "/time" in url:
                return {"serverTime": 1000}
            return []

        fetch.side_effect = answer
        first = enrich_positions(balances, "key", "secret", store)
        self.assertEqual(sum(r["history_status"] == "parcial" for r in first), 1)
        self.assertEqual(len(store.data), 60)
        second = enrich_positions(balances, "key", "secret", store)
        self.assertEqual(sum(r["history_status"] == "parcial" for r in second), 0)
        self.assertEqual(len(store.data), 61)

    @patch("crypto.fetch")
    def test_weighted_purchase_price(self, fetch):
        fetch.side_effect = [
            {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT"}]},
            [{"symbol": "BTCUSDT", "price": "40"}],
            {"serverTime": 1000},
            [
                {
                    "id": 1,
                    "isBuyer": True,
                    "qty": "1",
                    "price": "10",
                    "quoteQty": "10",
                    "commission": "0",
                    "commissionAsset": "BTC",
                    "time": 1000,
                },
                {
                    "id": 2,
                    "isBuyer": True,
                    "qty": "3",
                    "price": "30",
                    "quoteQty": "90",
                    "commission": "0",
                    "commissionAsset": "BTC",
                    "time": 2000,
                },
            ],
        ]
        row = enrich_positions([{"asset": "BTC", "quantity": "4"}], "key", "secret")[0]
        self.assertEqual(
            row["purchase_prices"], [{"currency": "USDT", "price": "25", "quantity": "4"}]
        )
        self.assertEqual([p["price"] for p in row["purchases"]], ["30", "10"])

    @patch("crypto.fetch")
    def test_buys_separate_from_sales_and_valuation(self, fetch):
        fetch.side_effect = [
            {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT"}]},
            [{"symbol": "BTCUSDT", "price": "100"}, {"symbol": "USDTBRL", "price": "5"}],
            {"serverTime": 1000},
            [
                {
                    "id": 1,
                    "isBuyer": True,
                    "qty": "2",
                    "price": "80",
                    "quoteQty": "160",
                    "commission": "0.01",
                    "commissionAsset": "BNB",
                },
                {
                    "id": 2,
                    "isBuyer": False,
                    "qty": "1",
                    "quoteQty": "90",
                    "commission": "0.01",
                    "commissionAsset": "BNB",
                },
            ],
        ]
        result = enrich_positions([{"asset": "BTC", "quantity": "1"}], "key", "secret")[0]
        self.assertEqual(result["purchased_quantity"], "2")
        self.assertEqual(result["purchase_totals"], [{"currency": "USDT", "value": "160"}])
        self.assertEqual(
            result["purchase_prices"], [{"currency": "USDT", "price": "80", "quantity": "2"}]
        )
        self.assertEqual(result["purchases"][0]["price"], "80")
        self.assertEqual(result["unit_price"], "500")
        self.assertEqual(result["current_value"], "500")
        self.assertEqual(result["valuation_currency"], "BRL")
        self.assertIn("fromId=0", fetch.call_args.args[0])
        self.assertEqual(result["purchase_fees"], [{"currency": "BNB", "value": "0.01"}])

    @patch("crypto.fetch")
    def test_missing_history_and_price_not_invented(self, fetch):
        fetch.side_effect = [{"symbols": []}, [], {"serverTime": 1000}]
        result = enrich_positions([{"asset": "UNKNOWN", "quantity": "10"}], "key", "secret")[0]
        self.assertIsNone(result["purchased_quantity"])
        self.assertIsNone(result["current_value"])

    @patch("crypto.fetch")
    def test_history_failure_keeps_valuation_and_marks_partial(self, fetch):
        fetch.side_effect = [
            {"symbols": [{"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT"}]},
            [{"symbol": "BTCUSDT", "price": "100"}],
            {"serverTime": 1000},
            ValueError("refused"),
        ]
        result = enrich_positions([{"asset": "BTC", "quantity": "1"}], "key", "secret")[0]
        self.assertEqual(result["history_status"], "parcial")
        self.assertEqual(result["current_value"], "100")
        self.assertEqual(result["valuation_currency"], "USDT")


if __name__ == "__main__":
    unittest.main()
