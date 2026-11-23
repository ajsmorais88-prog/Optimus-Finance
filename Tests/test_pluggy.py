"""Testes isolados: não enviam credenciais nem consultam contas reais."""

import unittest
from unittest.mock import patch

from app import app
from pluggy import PluggyError, _tokens


class PluggyTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        from test_support import authenticate_test_client

        authenticate_test_client(self, self.client)
        _tokens.clear()
        self.payload = {"client_id": "test", "client_secret": "secret", "item_id": "item"}
        saver = patch(
            "pluggy.save_accounts", return_value={"accounts": 1, "cards": 1, "investments": 0}
        )
        self.save = saver.start()
        self.addCleanup(saver.stop)
        application = patch("pluggy.read_application", return_value=self.payload)
        application.start()
        self.addCleanup(application.stop)

    def test_validation_and_origin(self):
        self.assertEqual(self.client.post("/api/pluggy/accounts", json={}).status_code, 400)
        result = self.client.post(
            "/api/pluggy/accounts", json=self.payload, headers={"Origin": "https://other.example"}
        )
        self.assertEqual(result.status_code, 403)

    @patch("pluggy.call")
    def test_pagination_and_data_minimization(self, call):
        call.side_effect = [
            {"apiKey": "private-key"},
            {
                "totalPages": 2,
                "results": [{"type": "BANK", "balance": -10, "taxNumber": "private"}],
            },
            {"totalPages": 2, "results": [{"type": "CREDIT", "creditData": {"creditLimit": 5000}}]},
            {"results": []},
        ]
        response = self.client.post("/api/pluggy/accounts", json=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["accounts"]), 2)
        self.assertEqual(response.json["accounts"][0]["balance"], -10)
        self.assertEqual(response.json["accounts"][1]["credit_limit"], 5000)
        self.assertNotIn("private", response.get_data(as_text=True))
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertIn("page=2", call.call_args_list[2].args[0])

    @patch("pluggy.call")
    def test_auth_cache(self, call):
        call.side_effect = [
            {"apiKey": "key"},
            {"results": []},
            {"results": []},
            {"results": []},
            {"results": []},
        ]
        for _ in range(2):
            self.assertEqual(
                self.client.post("/api/pluggy/accounts", json=self.payload).status_code, 200
            )
        self.assertEqual(sum(c.args[0] == "/auth" for c in call.call_args_list), 1)

    @patch("pluggy.call")
    def test_investment_pagination(self, call):
        call.side_effect = [
            {"apiKey": "key"},
            {"results": []},
            {
                "totalPages": 2,
                "results": [
                    {
                        "id": "asset-a",
                        "name": "CDB",
                        "balance": 1200,
                        "amount": 1300,
                        "date": "2026-11-12",
                        "owner": "private",
                    }
                ],
            },
            {"totalPages": 2, "results": [{"id": "asset-b", "name": "Fundo", "balance": None}]},
        ]
        response = self.client.post("/api/pluggy/accounts", json=self.payload)
        self.assertEqual(response.status_code, 200)
        records = self.save.call_args.args[0]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["type"], "INVESTMENT")
        self.assertEqual(records[0]["balance"], 1200)
        self.assertIsNone(records[1]["balance"])
        self.assertNotIn("owner", records[0])
        self.assertIn("/investments?", call.call_args.args[0])
        self.assertIn("page=2", call.call_args.args[0])

    @patch("pluggy.call", side_effect=PluggyError("Autenticação recusada.", 401))
    def test_external_error(self, call):
        response = self.client.post("/api/pluggy/accounts", json=self.payload)
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("secret", response.get_data(as_text=True))

    @patch("pluggy.read_config")
    @patch("pluggy.call")
    def test_reuse_saved_without_exposing_secret(self, call, read):
        read.return_value = self.payload
        status = self.client.get("/api/pluggy/config")
        self.assertTrue(status.json["saved"])
        self.assertNotIn("secret", status.get_data(as_text=True))
        call.side_effect = [{"apiKey": "key"}, {"results": []}, {"results": []}]
        result = self.client.post("/api/pluggy/accounts", json={"use_saved": True})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(call.call_args_list[0].kwargs["payload"]["clientSecret"], "secret")


if __name__ == "__main__":
    unittest.main()
