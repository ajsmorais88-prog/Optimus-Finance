# BLOCO — Cenários de teste para validação das regras de bank balances.
import unittest
from datetime import date
from decimal import Decimal
from bank_statements import pluggy_month_closing


class BankBalancesTests(unittest.TestCase):
    def test_latest_posted_balance_is_month_closing(self):
        tx = [
            dict(
                currency="BRL",
                date="2026-10-30",
                posted_at="2026-10-30T18:00:00Z",
                balance="1300.25",
                status="POSTED",
                api_order=0,
            ),
            dict(
                currency="BRL",
                date="2026-10-30",
                posted_at="2026-10-30T17:00:00Z",
                balance="1500",
                status="POSTED",
                api_order=1,
            ),
            dict(currency="BRL", date="2026-10-31", balance="999", status="PENDING"),
            dict(currency="BRL", date="2026-11-01", balance="888", status="POSTED"),
        ]
        self.assertEqual(
            pluggy_month_closing(tx, date(2026, 10, 31))["BRL"]["amount"], Decimal("1300.25")
        )

    def test_api_order_resolves_same_timestamp_and_negative_balance(self):
        tx = [
            dict(currency="BRL", date="2026-10-31", balance="-50", status="POSTED", api_order=0),
            dict(currency="BRL", date="2026-10-31", balance="100", status="POSTED", api_order=1),
        ]
        self.assertEqual(
            pluggy_month_closing(tx, date(2026, 10, 31))["BRL"]["amount"], Decimal("-50")
        )

    def test_missing_final_balance_not_replaced_by_older_value(self):
        tx = [
            dict(currency="BRL", date="2026-10-31", balance=None, status="POSTED"),
            dict(currency="BRL", date="2026-10-30", balance="100", status="POSTED"),
        ]
        self.assertEqual(pluggy_month_closing(tx, date(2026, 10, 31)), {})
        self.assertEqual(pluggy_month_closing([], date(2026, 10, 31)), {})

    def test_currencies_not_combined_and_zero_valid(self):
        tx = [
            dict(currency="BRL", date="2026-10-31", balance="0", status="POSTED"),
            dict(currency="USD", date="2026-10-31", balance="12", status="POSTED"),
        ]
        result = pluggy_month_closing(tx, date(2026, 10, 31))
        self.assertEqual(result["BRL"]["amount"], Decimal(0))
        self.assertEqual(result["USD"]["amount"], Decimal(12))


class CarriedBalancesTests(unittest.TestCase):
    def test_chain_recalculates_and_ignores_pending(self):
        from bank_statements import carried_openings

        seed = [dict(currency="BRL", period_start=date(2026, 11, 1), amount="4019.61")]
        tx = [
            dict(currency="BRL", amount="1000", date="2026-11-03", status="POSTED"),
            dict(currency="BRL", amount="-200", date="2026-11-04", status="POSTED"),
            dict(currency="BRL", amount="-99", date="2026-11-05", status="PENDING"),
        ]
        periods = [
            dict(period_start=date(2026, 11, 1), period_end=date(2026, 11, 30), transactions=tx),
            dict(
                period_start=date(2026, 12, 1),
                period_end=date(2026, 12, 31),
                transactions=[
                    dict(currency="BRL", amount="-50", date="2026-12-02", status="POSTED")
                ],
            ),
        ]
        self.assertEqual(
            carried_openings(seed, periods, date(2026, 11, 1))["BRL"]["amount"], Decimal("4019.61")
        )
        self.assertEqual(
            carried_openings(seed, periods, date(2026, 12, 1))["BRL"]["amount"], Decimal("4819.61")
        )
        self.assertEqual(
            carried_openings(seed, periods, date(2027, 1, 1))["BRL"]["amount"], Decimal("4769.61")
        )
        tx[0]["amount"] = "1100"
        self.assertEqual(
            carried_openings(seed, periods, date(2027, 1, 1))["BRL"]["amount"], Decimal("4869.61")
        )

    def test_missing_month_not_zero_and_currency_isolation(self):
        from bank_statements import carried_openings

        seed = [dict(currency="BRL", period_start=date(2026, 11, 1), amount="4019.61")]
        self.assertIsNone(carried_openings(seed, [], date(2026, 12, 1))["BRL"])
        self.assertEqual(carried_openings(seed, [], date(2026, 10, 1)), {})
