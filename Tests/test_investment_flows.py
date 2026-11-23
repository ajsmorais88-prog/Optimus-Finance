# BLOCO — Cenários de teste para validação das regras de investment flows.
import unittest
from app import app, validate_investment_flow
from decimal import Decimal


class FlowTests(unittest.TestCase):
    def test_direction_and_amount(self):
        for direction in ("entrada", "saida"):
            result = validate_investment_flow(
                dict(
                    day="2026-01-01", direction=direction, amount="1007.89", description="Depósito"
                )
            )
            self.assertEqual(result[1:3], (direction, Decimal("1007.89")))

    def test_reject_invalid(self):
        base = dict(day="2026-01-01", direction="entrada", amount="10", description="Teste")
        for change in [
            dict(amount="NaN"),
            dict(amount="-1"),
            dict(amount="1.001"),
            dict(direction="compra"),
            dict(day="2099-01-01"),
            dict(description=""),
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_investment_flow(base | change)

    def test_persistence_without_changing_positions(self):
        from app import connect

        # A transação de teste é sempre revertida, sem alterar dados do usuário.
        from unittest.mock import patch
        from contextlib import contextmanager

        with __import__("test_support").financial_test_connection() as conn:

            @contextmanager
            def isolated(*args, **kwargs):
                yield conn

            with patch("app.connect", isolated):
                client = app.test_client()
                from test_support import authenticate_test_client

                authenticate_test_client(self, client)
                response = client.post(
                    "/api/investment-flows",
                    json=dict(
                        day="2026-01-01",
                        direction="saida",
                        amount="10.25",
                        description="Teste temporário",
                    ),
                )
                self.assertEqual(response.status_code, 201)
                flow_id = response.json["id"]
                self.assertEqual(
                    conn.execute(
                        "SELECT amount FROM investment_flows WHERE id=%s", (flow_id,)
                    ).fetchone()["amount"],
                    Decimal("10.25"),
                )
                self.assertEqual(
                    client.delete(f"/api/investment-flows/{flow_id}", json={}).status_code, 204
                )
            conn.rollback()


if __name__ == "__main__":
    unittest.main()
