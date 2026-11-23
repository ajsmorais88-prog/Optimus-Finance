# BLOCO — Cenários de teste para identificação de pagamentos e recebimentos no extrato.
import unittest
from datetime import date
from reconciliation import find_matches


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.cost = {
            "id": 1,
            "name": "Energia",
            "statement_name": "Âmbar Energia",
            "amount": "350",
            "due_date": date(2026, 11, 8),
            "status": "Pendente",
        }
        self.transaction = {
            "id": "payment",
            "external_account_id": "bank",
            "account_id": 1,
            "date": "2026-11-09",
            "description": "PIX QR CODE DES AMBAR ENERGIA AMAZONA",
            "amount": "-395.48",
            "currency": "BRL",
            "status": "POSTED",
            "type": "DEBIT",
        }

    def test_unique_merchant_can_have_variable_amount(self):
        self.assertEqual(len(find_matches([self.cost], [self.transaction])), 1)

    def test_pending_income_other_month_and_used_are_not_payments(self):
        for change in [
            {"status": "PENDING"},
            {"amount": "395.48"},
            {"currency": "USD"},
            {"date": "2026-10-09"},
            {"type": "CREDIT"},
        ]:
            self.assertEqual(find_matches([self.cost], [{**self.transaction, **change}]), [])
        self.assertEqual(find_matches([self.cost], [self.transaction], {("bank", "payment")}), [])

    def test_ambiguous_transactions_and_costs_stay_pending(self):
        self.assertEqual(
            find_matches([self.cost], [self.transaction, {**self.transaction, "id": "other"}]), []
        )
        self.assertEqual(find_matches([self.cost, {**self.cost, "id": 2}], [self.transaction]), [])

    def test_exact_amount_disambiguates_same_merchant(self):
        exact = {**self.transaction, "id": "exact", "amount": "-350"}
        self.assertEqual(find_matches([self.cost], [self.transaction, exact])[0][1]["id"], "exact")

    def test_never_matches_only_amount_or_generic_identifier(self):
        self.assertEqual(
            find_matches([{**self.cost, "statement_name": "PIX"}], [self.transaction]), []
        )
        self.assertEqual(
            find_matches(
                [{**self.cost, "statement_name": "Outra empresa", "amount": "395.48"}],
                [self.transaction],
            ),
            [],
        )


class IncomeReconciliationTests(unittest.TestCase):
    def test_credit_only_and_unambiguous(self):
        income = dict(
            id=1,
            kind="incomes",
            name="Salário",
            statement_name="EMPRESA EXEMPLO",
            amount="1500",
            due_date=date(2026, 11, 10),
            status="Pendente",
        )
        credit = dict(
            id="salary",
            external_account_id="bank",
            account_id=2,
            date="2026-11-10",
            description="TED EMPRESA EXEMPLO",
            amount="1500",
            currency="BRL",
            status="POSTED",
            type="CREDIT",
        )
        self.assertEqual(len(find_matches([income], [credit])), 1)
        self.assertEqual(len(find_matches([{**income, "status": "Ativo"}], [credit])), 1)
        for change in [
            {"amount": "-1500", "type": "DEBIT"},
            {"status": "PENDING"},
            {"date": "2026-10-10"},
            {"type": "DEBIT"},
        ]:
            self.assertEqual(find_matches([income], [{**credit, **change}]), [])
        self.assertEqual(find_matches([income], [credit, {**credit, "id": "another"}]), [])
        self.assertEqual(find_matches([income, {**income, "id": 3}], [credit]), [])
        self.assertEqual(find_matches([income], [credit], {("bank", "salary")}), [])

    def test_income_name_or_value_and_same_payer(self):
        income = dict(
            id=1,
            kind="incomes",
            name="Salário",
            statement_name="EMPRESA EXEMPLO",
            amount="1500",
            due_date=date(2026, 11, 10),
            status="Pendente",
        )
        credit = dict(
            id="salary",
            external_account_id="bank",
            account_id=2,
            date="2026-11-10",
            description="TED EMPRESA EXEMPLO",
            amount="1500",
            currency="BRL",
            status="POSTED",
            type="CREDIT",
        )
        self.assertEqual(
            len(find_matches([income], [{**credit, "description": "OUTRO REMETENTE"}])), 1
        )
        self.assertEqual(len(find_matches([income], [{**credit, "amount": "1499"}])), 1)
        self.assertEqual(len(find_matches([{**income, "statement_name": ""}], [credit])), 1)
        self.assertEqual(
            len(
                find_matches(
                    [{**income, "statement_name": ""}],
                    [{**credit, "description": "SALARIO MENSAL", "amount": "1499"}],
                )
            ),
            1,
        )
        bonus = {**income, "id": 3, "name": "13º Salário", "amount": "700"}
        second = {**credit, "id": "bonus", "amount": "700"}
        matches = find_matches([income, bonus], [credit, second])
        self.assertEqual([(r["id"], t["id"]) for r, t in matches], [(1, "salary"), (3, "bonus")])
        self.assertEqual(
            find_matches([income], [{**credit, "description": "SEM RELACAO", "amount": "1499"}]), []
        )

    def test_same_payer_does_not_block_exact_thirteenth_salary(self):
        incomes = [
            dict(
                id=i,
                kind="incomes",
                name=name,
                statement_name="SECRETARIA DE ESTADO E. DESPORTO",
                amount=amount,
                due_date=date(2026, 11, day),
                status="Ativo",
            )
            for i, name, amount, day in [
                (1, "SEDUC", "3715.19", 27),
                (2, "SEDUC-ALIMENTAÇÃO", "500", 27),
                (3, "SEDUC - 13º SALÁRIO", "1569.97", 12),
            ]
        ]
        credit = dict(
            id="thirteenth",
            external_account_id="bank",
            account_id=14,
            date="2026-11-12",
            description="TRANSF SALDO C/SAL P/CC - SECRETARIA DE ESTADO E. DESPORTO - DOCTO: 1203739",
            amount="1569.97",
            currency="BRL",
            status="POSTED",
            type="CREDIT",
        )
        matches = find_matches(incomes, [credit])
        self.assertEqual([(r["id"], t["id"]) for r, t in matches], [(3, "thirteenth")])
        self.assertEqual(find_matches(incomes, [credit], {("bank", "thirteenth")}), [])

    def test_persist_receipt_once_without_increasing_expenses(self):
        from test_support import financial_test_connection
        from psycopg.types.json import Jsonb
        from reconciliation import reconcile_period
        from monthly_summary import build_summary

        start, end = date(2026, 11, 1), date(2026, 11, 30)
        with financial_test_connection() as conn:
            income = conn.execute(
                "INSERT INTO records(kind,name,statement_name,amount,due_date,status) VALUES('incomes','Salário','EMPRESA EXEMPLO',1500,'2026-11-10','Ativo') RETURNING *"
            ).fetchone()
            account = conn.execute(
                "INSERT INTO records(kind,name,pluggy_data) VALUES('accounts','Banco',%s) RETURNING id",
                (Jsonb({"id": "bank"}),),
            ).fetchone()["id"]
            credit = dict(
                id="salary",
                date="2026-11-10",
                description="TED EMPRESA EXEMPLO",
                amount="1500",
                currency="BRL",
                status="POSTED",
                type="CREDIT",
            )
            conn.execute(
                "INSERT INTO bank_statement_periods(account_id,period_start,period_end,transactions) VALUES(%s,%s,%s,%s)",
                (account, start, end, Jsonb([credit])),
            )
            self.assertEqual(reconcile_period(conn, start, end)[0]["kind"], "incomes")
            self.assertEqual(
                conn.execute("SELECT status FROM records WHERE id=%s", (income["id"],)).fetchone()[
                    "status"
                ],
                "Pago",
            )
            self.assertEqual(reconcile_period(conn, start, end), [])
            payments = conn.execute("SELECT * FROM expense_payments").fetchall()
            self.assertEqual(len(payments), 1)
            result = build_summary([income], payments, [], [], [], start, end)
            self.assertEqual(result["fixed_paid"], "0")


if __name__ == "__main__":
    unittest.main()
