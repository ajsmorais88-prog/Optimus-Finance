import unittest
from decimal import Decimal
from unittest.mock import patch
from contextlib import contextmanager
import json

from binance_wallets import wallet_positions
from binance_brl import convert_positions_brl


class WalletTests(unittest.TestCase):
    @patch("crypto.get_balances", side_effect=ValueError("private provider error"))
    @patch("crypto.cipher")
    def test_failed_consolidated_query_preserves_saved_positions(self, cipher, balances):
        from app import app
        from crypto import sync
        statements = []

        class Connection:
            def execute(self, sql, params=None):
                statements.append(sql)
                return self

            def fetchone(self):
                return {"exchange": "binance", "credentials": b"encrypted"}

        @contextmanager
        def connect():
            yield Connection()

        cipher.return_value.decrypt.return_value = json.dumps({"key": "test", "secret": "test"}).encode()
        with patch("app.connect", connect), app.test_request_context(json={}):
            response, code = sync(1)
        self.assertEqual(code, 502)
        self.assertIn("preservado", response.get_json()["error"])
        self.assertNotIn("private provider", response.get_json()["error"])
        self.assertFalse(any("UPDATE records" in sql for sql in statements))
        self.assertFalse(any("balances=" in sql for sql in statements))

    def test_merges_same_asset_across_wallets_once(self):
        wallets = [{"walletName": name, "balance": value, "assetBalances": [
            {"asset": "BTC", "free": value, "btcValuation": value}
        ]} for name, value in [("Spot", "0.1"), ("Earn", "0.2"), ("Funding", "0.3")]]
        rows = wallet_positions(wallets)
        self.assertEqual(len(rows), 1)
        self.assertEqual(Decimal(rows[0]["quantity"]), Decimal("0.6"))
        self.assertEqual(Decimal(rows[0]["valuation_btc"]), Decimal("0.6"))
        self.assertEqual(rows[0]["wallets"], ["Spot", "Earn", "Funding"])

    def test_aggregate_without_detail_and_net_margin_do_not_double_count(self):
        rows = wallet_positions([
            {"walletName": "Earn", "balance": "0.1"},
            {"walletName": "Margin", "balance": "-0.02", "assetBalances": [
                {"asset": "BTC", "free": "1", "btcValuation": "1"}]},
            {"walletName": "Futures", "balance": "0.3"},
            {"walletName": "Funding", "balance": "0", "activate": False},
        ])
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row["wallet_aggregate"] for row in rows))
        self.assertEqual(sum(Decimal(row["valuation_btc"]) for row in rows), Decimal("0.38"))

    def test_rejects_duplicates_and_invalid_response(self):
        for payload in [{"code": -2015}, [{"walletName": "Spot", "balance": "NaN"}],
                        [{"walletName": "Spot", "balance": "0"}] * 2]:
            with self.assertRaises(ValueError):
                wallet_positions(payload)

    @patch("crypto.fetch")
    def test_brl_uses_binance_net_valuation_including_assets_without_pairs(self, fetch):
        fetch.side_effect = [
            {"symbols": [{"symbol": "BTCBRL"}]},
            [{"symbol": "BTCBRL", "price": "500000"}],
        ]
        rows = wallet_positions([{"walletName": "Earn", "balance": "0.002",
                                 "assetBalances": [{"asset": "TOKEN", "free": "10",
                                                    "btcValuation": "0.002"}]}])
        result = convert_positions_brl(rows, object())[0]
        self.assertEqual(Decimal(result["current_value"]), Decimal("1000"))
        self.assertEqual(Decimal(result["unit_price"]), Decimal("100"))


if __name__ == "__main__":
    unittest.main()
