# BLOCO — Cenários de teste para validação das regras de billing month.
import unittest
from datetime import date
from unittest.mock import patch
from billing import fetch_month_bills
from pluggy import PluggyError


class MonthBillsTests(unittest.TestCase):
    @patch("billing.call")
    def test_filters_due_month_and_deduplicates_pages(self, call):
        row = dict(
            id="nov",
            dueDate="2026-11-05T00:00:00",
            totalAmount=123.45,
            totalAmountCurrencyCode="BRL",
        )
        call.side_effect = [
            dict(totalPages=2, results=[row, dict(row, id="dec", dueDate="2026-12-05")]),
            dict(totalPages=2, results=[row]),
        ]
        result = fetch_month_bills("account", "key", date(2026, 11, 1), date(2026, 11, 30))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["amount"], "123.45")
        self.assertIn("page=2", call.call_args.args[0])
        self.assertIn("accountId=account", call.call_args.args[0])

    @patch("billing.call", return_value={"results": []})
    def test_absent_bill_not_fabricated(self, call):
        self.assertEqual(
            fetch_month_bills("account", "key", date(2026, 11, 1), date(2026, 11, 30)), []
        )

    @patch(
        "billing.call",
        return_value={
            "results": [dict(id="x", accountId="other", dueDate="2026-11-05", totalAmount=10)]
        },
    )
    def test_rejects_other_account(self, call):
        with self.assertRaises(PluggyError):
            fetch_month_bills("account", "key", date(2026, 11, 1), date(2026, 11, 30))

    @patch("billing.call")
    def test_bill_transactions_keep_old_installment_purchase_date(self, call):
        from billing import fetch_transactions

        call.return_value = {
            "results": [
                dict(
                    id="tx",
                    accountId="account",
                    date="2025-12-01",
                    amount=50,
                    currencyCode="BRL",
                    creditCardMetadata={"billId": "bill-nov"},
                )
            ]
        }
        result = fetch_transactions(
            "account", "key", date(2026, 11, 1), date(2026, 11, 30), "BRL", bill_id="bill-nov"
        )
        self.assertEqual(len(result), 1)
        self.assertNotIn("billId=", call.call_args.args[0])
        self.assertNotIn("dateFrom", call.call_args.args[0])
