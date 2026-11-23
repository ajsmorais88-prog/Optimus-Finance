# BLOCO — Cenários de teste para geração e leitura dos alertas individuais do painel.
import unittest
from datetime import date, timedelta
from decimal import Decimal
from psycopg.types.json import Jsonb
from notifications import dynamic_alerts, allocations, note_transactions, collect
from test_support import financial_test_connection


class NotificationTests(unittest.TestCase):
    def test_due_dates_paid_and_negative_balance(self):
        today = date(2026, 11, 14)

        def cost(i, days, status="Pendente"):
            return dict(
                id=i,
                kind="expenses",
                name="Cost " + str(i),
                amount=10,
                due_date=today + timedelta(days=days),
                status=status,
            )

        records = [
            cost(1, 2),
            cost(2, 3),
            cost(3, -1),
            cost(4, -10, "Pago"),
            cost(5, 0),
            dict(id=6, kind="accounts", name="Account", amount=-20),
        ]
        settings = dict(
            monthly_income=100000, fixed_percent=50, credit_percent=40, investment_percent=10
        )
        alerts = dynamic_alerts(records, settings, [], [], [], today)
        keys = [a["key"].split(":")[0] for a in alerts]
        self.assertEqual(keys.count("due"), 2)
        self.assertEqual(keys.count("overdue"), 1)
        self.assertEqual(keys.count("negative"), 1)
        self.assertFalse(any(a["record_id"] == 2 for a in alerts))

    def test_budget_90_percent_and_rounding(self):
        settings = dict(
            monthly_income=1000, fixed_percent=50, credit_percent=40, investment_percent=10
        )
        records = [
            dict(
                id=1,
                kind="expenses",
                name="Fixed",
                amount=450,
                due_date=date(2026, 11, 20),
                status="Pendente",
            ),
            dict(id=2, kind="cards", name="Card", due_date=None),
        ]
        bills = [
            dict(
                card_id=2,
                month=date(2026, 11, 1),
                bills=[dict(id="bill", due_date="2026-11-20", amount="360", currency="BRL")],
            )
        ]
        alerts = dynamic_alerts(records, settings, [], bills, [], date(2026, 11, 14))
        self.assertEqual(sum(a["key"].endswith(":near") for a in alerts), 2)
        records[0]["amount"] = 501
        alerts = dynamic_alerts(records, settings, [], bills, [], date(2026, 11, 14))
        self.assertTrue(any(a["key"] == "budget:fixed:2026-11:exceeded" for a in alerts))
        settings["monthly_income"] = Decimal(".03")
        self.assertEqual(allocations(settings), [Decimal(".02"), Decimal(".01"), Decimal("0")])

    def test_transactions_baseline_deduplication_and_reads(self):
        with financial_test_connection() as conn:
            account = conn.execute(
                "INSERT INTO records(kind,name,amount) VALUES('accounts','Test account',100) RETURNING id"
            ).fetchone()["id"]

            def tx(i):
                return dict(
                    id=str(i),
                    date="2026-11-14",
                    amount="-10",
                    currency="BRL",
                    status="POSTED",
                    description="Purchase",
                )

            note_transactions(conn, "bank", account, "Test account", [tx(1)], "2026-11")
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM notification_events").fetchone()["n"], 0
            )
            note_transactions(conn, "bank", account, "Test account", [tx(1), tx(2)], "2026-11")
            note_transactions(conn, "bank", account, "Test account", [tx(1), tx(2)], "2026-11")
            note_transactions(
                conn, "bank", account, "Test account", [tx(3)], "2026-10", silent=True
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS n FROM notification_events").fetchone()["n"], 1
            )
            alerts = collect(conn, date(2026, 11, 14))
            event = next(a for a in alerts if a["key"].startswith("tx:"))
            self.assertFalse(event["read"])
            conn.execute("INSERT INTO notification_reads(key) VALUES(%s)", (event["key"],))
            self.assertTrue(
                next(a for a in collect(conn, date(2026, 11, 14)) if a["key"] == event["key"])[
                    "read"
                ]
            )
