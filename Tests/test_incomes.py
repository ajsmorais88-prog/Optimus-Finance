# BLOCO — Cenários de teste para validação das regras de incomes.
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from app import app, validate_record
from test_support import financial_test_connection, authenticate_test_client


class IncomeTests(unittest.TestCase):
    def test_income_requires_date(self):
        with self.assertRaises(ValueError):
            validate_record(dict(kind="incomes", name="Salário", amount="100"))

    def test_income_crud(self):
        client = app.test_client()
        authenticate_test_client(self, client)
        with financial_test_connection() as conn:

            @contextmanager
            def connection(**kwargs):
                yield conn

            with patch("app.connect", connection):
                payload = dict(
                    kind="incomes",
                    name="Salário",
                    detail="Trabalho",
                    amount="1250.50",
                    due_date="2026-11-30",
                )
                created = client.post("/api/records", json=payload)
                self.assertEqual(created.status_code, 201)
                record_id = created.get_json()["id"]
                edited = client.put(
                    "/api/records/" + str(record_id), json={**payload, "amount": "1300.25"}
                )
                self.assertEqual(edited.status_code, 200)
                self.assertEqual(edited.get_json()["amount"], 1300.25)
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) AS n FROM records WHERE kind='expenses'"
                    ).fetchone()["n"],
                    0,
                )
                self.assertEqual(
                    client.delete("/api/records/" + str(record_id), json={}).status_code, 204
                )


if __name__ == "__main__":
    unittest.main()
