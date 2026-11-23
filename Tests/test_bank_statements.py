# BLOCO — Cenários de teste para extratos mensais e continuidade dos saldos bancários.
import unittest
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from flask import Flask, g
from datetime import date
from bank_statements import month_period, summarize_bank
from bank_statements import save_opening_balance


class BankStatementTests(unittest.TestCase):
    def save_opening(self, payload, account=True):
        app = Flask(__name__)
        execute = Mock()
        @contextmanager
        def connection():
            yield SimpleNamespace(execute=execute)
        with app.test_request_context(json=payload, method='PUT'):
            g.user = {'id': 123}
            with patch.dict('sys.modules', {'app': SimpleNamespace(connect=connection)}), \
                 patch('bank_statements.get_account', return_value={'id': 14} if account else None), \
                 patch('auto_sync.mark_changed') as changed:
                response = save_opening_balance(14)
                return response, execute, changed.call_args

    def test_edit_opening_accepts_negative_and_zero_for_selected_month(self):
        for amount in ('-29.90', '0', '4723.49'):
            response, execute, revision = self.save_opening({'month':'2026-11', 'currency':'BRL', 'amount':amount})
            self.assertTrue(response.json['saved'])
            self.assertEqual(execute.call_args.args[1], (14,date(2026,11,1),'BRL',Decimal(amount)))
            self.assertEqual(revision.args, (123,))

    def test_edit_opening_rejects_invalid_values_and_unknown_account(self):
        for amount in ('NaN', 'Infinity', '1.001', '1000000000000', ''):
            with self.assertRaises(ValueError):
                self.save_opening({'month':'2026-11','currency':'BRL','amount':amount})
        response, execute, revision = self.save_opening({'month':'2026-11','currency':'BRL','amount':'1'},account=False)
        self.assertEqual(response[1],404)
        execute.assert_not_called()
        self.assertIsNone(revision)

    def test_summary_preserves_an_edited_opening_in_later_month(self):
        from monthly_summary import monthly_cash_position
        records = [{'id':14,'kind':'accounts','name':'Teste'}]
        openings = [dict(account_id=14,period_start=date(2026,11,1),currency='BRL',amount=Decimal('100')),
                    dict(account_id=14,period_start=date(2026,12,1),currency='BRL',amount=Decimal('300'))]
        periods = [dict(account_id=14,period_start=date(2026,11,1),period_end=date(2026,11,30),
                        transactions=[dict(id='tx',date='2026-11-10',currency='BRL',status='POSTED',amount='50')])]
        cash = monthly_cash_position(records,periods,openings,date(2026,12,1),date(2026,12,31))
        self.assertEqual(Decimal(cash['opening_balance']),Decimal('300'))

    def test_calendar_period_and_leap_year(self):
        self.assertEqual(month_period("2024-02"), (date(2024, 2, 1), date(2024, 2, 29)))
        self.assertEqual(month_period("2026-02"), (date(2026, 2, 1), date(2026, 2, 28)))
        for month in ["2026-13", "2026-00", "0000-01", "invalid", {}]:
            with self.assertRaises(ValueError):
                month_period(month)

    def test_bank_totals_pending_and_bill_payments(self):
        transactions = [
            {"currency": "BRL", "amount": "1000", "status": "POSTED"},
            {
                "currency": "BRL",
                "amount": "-200",
                "status": "POSTED",
                "description": "Pagamento de fatura",
            },
            {"currency": "BRL", "amount": "-50", "status": "PENDING"},
            {"currency": "USD", "amount": "10", "status": "POSTED"},
        ]
        totals = summarize_bank(transactions)
        self.assertEqual(
            totals[0],
            {
                "currency": "BRL",
                "incoming": "1000",
                "outgoing": "200",
                "net": "800",
                "pending_incoming": "0",
                "pending_outgoing": "50",
            },
        )
        self.assertEqual(totals[1]["incoming"], "10")


if __name__ == "__main__":
    unittest.main()
