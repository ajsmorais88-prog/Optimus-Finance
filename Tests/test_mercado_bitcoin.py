import json
import unittest
from decimal import Decimal
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import parse_qs

from crypto import get_balances, save_exchange_positions


class MercadoBitcoinTests(unittest.TestCase):
    @patch("crypto.cipher")
    def test_connection_accepts_provider_and_encrypts_credentials(self, cipher):
        from app import app
        from crypto import save
        calls = []
        class Connection:
            def execute(self, sql, params=None): calls.append((sql, params)); return self
            def fetchone(self): return {"id": 12}
        @contextmanager
        def connect(): yield Connection()
        cipher.return_value.encrypt.return_value = b"encrypted-only"
        with patch("app.connect", connect), app.test_request_context(json={"exchange": "mercadobitcoin", "api_key": "test-id", "api_secret": "test-secret"}):
            response = save()
        self.assertEqual(response.get_json(), {"saved": True, "connection_id": 12})
        self.assertEqual(calls[0][1][0:2], ("mercadobitcoin", "Mercado Bitcoin"))
        self.assertEqual(calls[0][1][-1], b"encrypted-only")
        self.assertNotIn("test-secret", response.get_data(as_text=True))

    @patch("mercado_bitcoin.time.sleep")
    @patch("crypto.fetch")
    def test_authentication_multiple_accounts_and_brl_valuation(self, fetch, sleep):
        fetch.side_effect = [
            {"access_token": "test-token"}, [{"id": "one"}, {"id": "two"}],
            [{"symbol": "BTC", "available": "0.1", "on_hold": "0.02", "total": "0.12"},
             {"symbol": "BRL", "available": "10", "on_hold": "5", "total": "15"}],
            [{"symbol": "BTC", "available": "0.03", "on_hold": "0", "total": "0.03"}],
            {"symbol": ["BTC-BRL"]}, [{"pair": "BTC-BRL", "last": "500000"}],
        ]
        result = get_balances("mercadobitcoin", "test-id", "test-secret")
        btc = next(row for row in result if row["asset"] == "BTC")
        self.assertEqual(Decimal(btc["quantity"]), Decimal("0.15"))
        self.assertEqual(Decimal(btc["locked"]), Decimal("0.02"))
        self.assertEqual(Decimal(btc["current_value"]), Decimal("75000"))
        self.assertEqual(next(row for row in result if row["asset"] == "BRL")["current_value"], "15")
        first = fetch.call_args_list[0]
        self.assertTrue(first.args[0].endswith("/api/v4/oauth2/token"))
        body = parse_qs(first.args[2].decode())
        self.assertEqual(body["grant_type"], ["client_credentials"])
        self.assertEqual(body["client_id"], ["test-id"])
        self.assertEqual(body["client_secret"], ["test-secret"])
        self.assertEqual(fetch.call_args_list[2].args[1], {"Authorization": "Bearer test-token"})
        self.assertTrue(all("test-secret" not in call.args[0] for call in fetch.call_args_list))
        self.assertFalse(any("orders" in call.args[0] or "withdraw" in call.args[0] for call in fetch.call_args_list))

    @patch("crypto.fetch")
    def test_asset_without_brl_market_is_not_invented(self, fetch):
        fetch.side_effect = [{"access_token": "test"}, [{"id": "one"}],
                             [{"symbol": "UNKNOWN", "available": "2", "on_hold": "0", "total": "2"}], {"symbol": []}]
        row = get_balances("mercadobitcoin", "test", "test")[0]
        self.assertIsNone(row["current_value"])
        self.assertEqual(row["quantity"], "2")
        self.assertEqual(row["valuation_status"], "sem cotação BRL")

    @patch("crypto.fetch")
    def test_zero_balance_is_a_complete_empty_position(self, fetch):
        fetch.side_effect = [{"access_token": "test"}, [{"id": "one"}], []]
        self.assertEqual(get_balances("mercadobitcoin", "test", "test"), [])

    @patch("crypto.fetch")
    def test_rejects_invalid_token_and_inconsistent_balances(self, fetch):
        fetch.return_value = {"error": "unauthorized"}
        with self.assertRaises(ValueError):
            get_balances("mercadobitcoin", "test", "test")
        fetch.side_effect = [{"access_token": "test"}, [{"id": "one"}],
                             [{"symbol": "BRL", "available": "10", "on_hold": "5", "total": "10"}]]
        with self.assertRaises(ValueError):
            get_balances("mercadobitcoin", "test", "test")

    @patch("crypto.fetch")
    def test_incomplete_price_response_rejected(self, fetch):
        fetch.side_effect = [{"access_token": "test"}, [{"id": "one"}],
                             [{"symbol": "BTC", "available": "2", "on_hold": "0", "total": "2"}],
                             {"symbol": ["BTC-BRL"]}, []]
        with self.assertRaises(ValueError):
            get_balances("mercadobitcoin", "test", "test")

    def test_persistence_identity_and_zeroes_scope_to_connection(self):
        class Connection:
            def __init__(self): self.calls = []
            def execute(self, sql, params): self.calls.append((sql, params))
        conn = Connection()
        save_exchange_positions(conn, 12, [{"asset": "BTC", "quantity": "0.1", "current_value": "50000", "provider": "mercadobitcoin"}], "mercadobitcoin")
        self.assertIn("WHERE crypto_connection_id=%s", conn.calls[0][0])
        self.assertEqual(conn.calls[0][1][-1], 12)
        self.assertEqual(conn.calls[1][1][1], "Mercado Bitcoin")
        self.assertIn("mercadobitcoin:12:BTC", conn.calls[1][1])

    @patch("crypto.cipher")
    @patch("crypto.get_balances", side_effect=ValueError("private provider payload"))
    def test_sync_failure_preserves_prior_positions(self, balances, cipher):
        from app import app
        from crypto import sync
        calls = []
        class Connection:
            def execute(self, sql, params=None): calls.append(sql); return self
            def fetchone(self): return {"exchange": "mercadobitcoin", "credentials": b"test"}
        @contextmanager
        def connect(): yield Connection()
        cipher.return_value.decrypt.return_value = json.dumps({"key": "test", "secret": "test"}).encode()
        with patch("app.connect", connect), app.test_request_context(json={}):
            response, code = sync(12)
        self.assertEqual(code, 502)
        self.assertIn("Mercado Bitcoin", response.get_json()["error"])
        self.assertNotIn("private provider", response.get_json()["error"])
        self.assertFalse(any("UPDATE records" in statement for statement in calls))
