# BLOCO — Cenários de teste para validação das regras de card cycles.
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from app import app, connect


class CardCycleTests(unittest.TestCase):
    def test_dates_are_isolated_by_reference_month(self):
        with __import__("test_support").financial_test_connection() as conn:

            @contextmanager
            def isolated(*args, **kwargs):
                yield conn

            try:
                with patch("app.connect", isolated):
                    client = app.test_client()
                    from test_support import authenticate_test_client

                    authenticate_test_client(self, client)
                    payload = dict(
                        kind="cards",
                        name="Teste mensal temporário",
                        institution="Teste",
                        amount="1000",
                        status="Ativo",
                        reference_month="2026-10",
                        previous_closing_date="2026-09-05",
                        closing_date="2026-10-05",
                        due_date="2026-10-10",
                    )
                    created = client.post("/api/records", json=payload)
                    self.assertEqual(created.status_code, 201)
                    card_id = created.json["id"]
                    november = payload | dict(
                        reference_month="2026-11",
                        previous_closing_date="2026-10-06",
                        closing_date="2026-11-06",
                        due_date="2026-11-11",
                    )
                    self.assertEqual(
                        client.put(f"/api/records/{card_id}", json=november).status_code, 200
                    )
                    cycles = conn.execute(
                        "SELECT * FROM card_reference_cycles WHERE card_id=%s ORDER BY reference_month",
                        (card_id,),
                    ).fetchall()
                    self.assertEqual(len(cycles), 2)
                    self.assertEqual(cycles[0]["closing_date"].isoformat(), "2026-10-05")
                    self.assertEqual(cycles[1]["closing_date"].isoformat(), "2026-11-06")
                    original = conn.execute(
                        "SELECT * FROM records WHERE id=%s", (card_id,)
                    ).fetchone()
                    self.assertEqual(original["closing_date"].isoformat(), "2026-10-05")
                    data = client.get(f"/api/cards/{card_id}/bill?month=2026-11").json
                    self.assertEqual(data["cycle"]["previous_closing_date"], "2026-10-06")
                    self.assertIsNone(
                        client.get(f"/api/cards/{card_id}/bill?month=2026-12").json["cycle"]
                    )
            finally:
                conn.rollback()
