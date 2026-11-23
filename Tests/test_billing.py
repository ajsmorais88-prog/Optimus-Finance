# BLOCO — Cenários de teste para ciclos e lançamentos das faturas de cartão.
import unittest
from datetime import date
from unittest.mock import patch

from billing import card_period, fetch_transactions, summarize, is_bill_payment
from pluggy import PluggyError


class BillingTests(unittest.TestCase):
    def test_cycle_excludes_previous_closing(self):
        self.assertEqual(
            card_period(
                {"previous_closing_date": date(2026, 10, 29), "closing_date": date(2026, 11, 26)}
            ),
            (date(2026, 10, 30), date(2026, 11, 26)),
        )
        with self.assertRaises(ValueError):
            card_period(
                {"previous_closing_date": date(2026, 11, 26), "closing_date": date(2026, 11, 26)}
            )

    @patch("billing.call")
    def test_cursor_filters_card_and_cycle(self, call):
        def transaction(id, day, amount):
            return {
                "id": id,
                "accountId": "card-a",
                "date": day,
                "amount": amount,
                "currencyCode": "BRL",
                "description": "Compra",
            }

        first = transaction("a", "2026-10-30T00:00:00Z", 100)
        call.side_effect = [
            {
                "results": [transaction("outside", "2026-10-29", 999), first],
                "next": "?accountId=other&after=cursor%2B1",
            },
            {
                "results": [
                    first,
                    transaction("b", "2026-11-26", -20),
                    transaction("later", "2026-11-27", 999),
                ],
                "next": None,
            },
        ]
        result = fetch_transactions("card-a", "key", date(2026, 10, 30), date(2026, 11, 26), "BRL")
        self.assertEqual(len(result), 2)
        self.assertIn("accountId=card-a", call.call_args.args[0])
        self.assertIn("after=cursor%2B1", call.call_args.args[0])
        self.assertEqual(
            summarize(result),
            [
                {
                    "currency": "BRL",
                    "charges": "100",
                    "credits": "20",
                    "net": "80",
                    "payments_for_review": "0",
                }
            ],
        )

    @patch("billing.call")
    def test_rejects_other_card(self, call):
        call.return_value = {"results": [{"accountId": "wrong-card"}], "next": None}
        with self.assertRaises(PluggyError):
            fetch_transactions("card-a", "key", date(2026, 10, 30), date(2026, 11, 26), "BRL")

    @patch("billing.call")
    def test_repeated_cursor_aborts(self, call):
        call.return_value = {"results": [], "next": "?after=again"}
        with self.assertRaises(PluggyError):
            fetch_transactions("card-a", "key", date(2026, 10, 30), date(2026, 11, 26), "BRL")

    def test_different_currencies_are_not_added(self):
        totals = summarize(
            [{"currency": "BRL", "amount": "100"}, {"currency": "USD", "amount": "10"}]
        )
        self.assertEqual(len(totals), 2)

    def test_bill_payment_for_review_does_not_reduce_new_bill(self):
        transactions = [
            {"currency": "BRL", "amount": "100", "description": "Compra"},
            {"currency": "BRL", "amount": "-186.19", "description": "Pagamento Recebido"},
            {
                "currency": "BRL",
                "amount": "-10",
                "description": "Estorno de compra",
                "operation_type": "ESTORNO",
            },
        ]
        self.assertEqual(
            summarize(transactions),
            [
                {
                    "currency": "BRL",
                    "charges": "100",
                    "credits": "10",
                    "net": "90",
                    "payments_for_review": "186.19",
                }
            ],
        )

    def test_structured_payment_and_reversal(self):
        self.assertTrue(
            is_bill_payment(
                {"amount": "-10", "description": "Crédito", "operation_type": "PAGAMENTO_FATURA"}
            )
        )
        self.assertTrue(is_bill_payment({"amount": "-10", "description": "Pagamento Efetuado"}))
        self.assertFalse(is_bill_payment({"amount": "10", "description": "Pagamento Recebido"}))
        self.assertFalse(
            is_bill_payment(
                {"amount": "-10", "description": "Pagamento Recebido", "operation_type": "ESTORNO"}
            )
        )

    def test_previous_bill_payment_descriptions_and_actual_refunds(self):
        payments = ["Pagamentos Validos Normais", "Pagamentos Válidos Normais", "Pagamentos de faturas anteriores", "Pagamento", "PGTO", "PAGTO. FATURA",
                    "Pagamento por débito automático", "PGTO POR DEBITO EM C/C",
                    "Inclusão de pagamento", "Crédito de pagamento", "Pagamento da fatura anterior"]
        for description in payments:
            with self.subTest(description=description):
                self.assertTrue(is_bill_payment({"amount": "-150", "description": description}))
                totals = summarize([{"amount": "-150", "description": description, "currency": "BRL"}])[0]
                self.assertEqual(totals["credits"], "0")
                self.assertEqual(totals["payments_for_review"], "150")
        for description in ["Estorno de compra", "Estorno de pagamento", "Cashback", "Crédito", "Devolução de pagamento"]:
            with self.subTest(description=description):
                self.assertFalse(is_bill_payment({"amount": "-10", "description": description}))


if __name__ == "__main__":
    unittest.main()
