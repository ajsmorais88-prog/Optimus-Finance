"""Testes com respostas simuladas; nunca consultam contas reais."""

import base64
import hashlib
import hmac
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

from app import app
from crypto import get_balances


class CryptoTests(unittest.TestCase):
    @patch("crypto.fetch")
    def test_binance_signature_and_precision(self, fetch):
        fetch.side_effect = [
            {"serverTime": 123},
            [{"walletName": "Spot", "balance": "0.00000003", "assetBalances": [
                {"asset": "BTC", "free": "0.00000001", "locked": "0.00000002", "btcValuation": "0.00000003"},
                {"asset": "ETH", "free": "0", "locked": "0", "btcValuation": "0"},
            ]}],
        ]
        result = get_balances("binance", "key", "secret")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["quantity"], "3E-8")
        self.assertEqual(result[0]["wallets"], ["Spot"])
        url = fetch.call_args.args[0]
        self.assertIn("/sapi/v1/asset/wallet/balance?", url)
        self.assertIn("needBalanceDetail=true", url)
        query = urlsplit(url).query
        text, signature = query.split("&signature=")
        self.assertEqual(signature, hmac.new(b"secret", text.encode(), hashlib.sha256).hexdigest())
        self.assertEqual(fetch.call_args.args[1]["X-MBX-APIKEY"], "key")

    @patch("crypto.time.time", return_value=1)
    @patch("crypto.fetch")
    def test_bybit_signature(self, fetch, time):
        fetch.return_value = {
            "retCode": 0,
            "result": {"list": [{"coin": [{"coin": "BTC", "walletBalance": "0.5"}]}]},
        }
        self.assertEqual(
            get_balances("bybit", "key", "secret"), [{"asset": "BTC", "quantity": "0.5"}]
        )
        headers = fetch.call_args.args[1]
        expected = hmac.new(
            b"secret", b"1000key5000accountType=UNIFIED", hashlib.sha256
        ).hexdigest()
        self.assertEqual(headers["X-BAPI-SIGN"], expected)

    @patch("crypto.fetch")
    def test_kraken_signature_and_nonce(self, fetch):
        fetch.return_value = {"error": [], "result": {"XXBT": "0.25"}}
        secret = base64.b64encode(b"secret").decode()
        get_balances("kraken", "key", secret)
        url, headers, body = fetch.call_args.args
        nonce = parse_qs(body.decode())["nonce"][0]
        digest = hashlib.sha256(nonce.encode() + body).digest()
        expected = base64.b64encode(
            hmac.new(b"secret", b"/0/private/Balance" + digest, hashlib.sha512).digest()
        ).decode()
        self.assertEqual(headers["API-Sign"], expected)

    def test_validation_and_origin(self):
        client = app.test_client()
        from test_support import authenticate_test_client

        authenticate_test_client(self, client)
        self.assertEqual(client.post("/api/crypto/connections", json={}).status_code, 400)
        self.assertEqual(
            client.post(
                "/api/crypto/connections", json={}, headers={"Origin": "https://other.example"}
            ).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
