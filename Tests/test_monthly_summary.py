# BLOCO — Cenários de teste para classificação de receitas e saídas, sem duplicar despesas.
import unittest
from datetime import date
from monthly_summary import build_summary


class MonthlySummaryTests(unittest.TestCase):
    def test_month_cash_and_deduplication(self):
        start, end = date(2026, 11, 1), date(2026, 11, 30)
        records = [
            dict(id=1, kind="expenses", amount=350, due_date=date(2026, 11, 20), status="Pago"),
            dict(
                id=2,
                kind="cards",
                name="Cartão",
                due_date=date(2026, 11, 25),
                previous_closing_date=date(2026, 10, 15),
                closing_date=date(2026, 11, 15),
            ),
            dict(id=3, kind="cards", name="Outro mês", due_date=date(2026, 12, 5)),
        ]
        payment = dict(
            expense_id=1,
            paid_amount="395.48",
            paid_date=date(2026, 11, 10),
            external_account_id="a",
            transaction_id="fixed",
        )

        def tx(id, value, operation="PIX", category="Groceries", status="POSTED", day="2026-11-10"):
            return dict(
                id=id,
                amount=value,
                operation_type=operation,
                category=category,
                status=status,
                date=day,
                currency="BRL",
            )

        statement = dict(
            external_account_id="a",
            transactions=[
                tx("fixed", "-395.48"),
                tx("pix", "-20"),
                tx("transfer", "-999", category="Transfer - PIX"),
                tx("debit", "-30", "COMPRA_CARTAO"),
                tx("pending", "-88", status="PENDING"),
                tx("other", "-100", day="2026-10-10"),
            ],
        )
        bills = [
            dict(
                card_id=2,
                previous_closing_date=date(2026, 10, 15),
                closing_date=date(2026, 11, 15),
                transactions=[
                    dict(amount="100", currency="BRL"),
                    dict(amount="-10", currency="BRL", operation_type="ESTORNO"),
                    dict(amount="-500", currency="BRL", operation_type="PAGAMENTO_FATURA"),
                ],
            )
        ]
        flows = [
            dict(day=date(2026, 11, 1), direction="entrada", amount="50"),
            dict(day=date(2026, 11, 2), direction="saida", amount="10"),
        ]
        result = build_summary(records, [payment], [statement, statement], bills, flows, start, end)
        self.assertEqual(result["fixed_planned"], "350")
        self.assertEqual(result["fixed_paid"], "395.48")
        self.assertEqual(result["cards"], "90")
        self.assertEqual(result["pix"], "20")
        self.assertEqual(result["debit"], "30")
        self.assertEqual(result["contributions"], "50")
        self.assertEqual(len(result["card_details"]), 1)

    def test_other_paid_excludes_counted_obligations_and_deduplicates(self):
        records = [
            dict(id=1, kind="expenses", amount=100, due_date=date(2026, 11, 10), status="Pago"),
            dict(id=2, kind="cards", name="Cartão Rico", institution="Rico"),
        ]
        payment = dict(
            expense_id=1,
            paid_amount="100",
            paid_date=date(2026, 11, 10),
            external_account_id="bank",
            transaction_id="fixed",
        )
        bill = dict(
            card_id=2,
            month=date(2026, 11, 1),
            bills=[dict(id="bill", due_date="2026-11-10", amount="186.19", currency="BRL")],
        )

        def tx(key, amount, description, status="POSTED", currency="BRL", day="2026-11-12"):
            return dict(
                id=key,
                amount=amount,
                description=description,
                status=status,
                currency=currency,
                date=day,
            )

        statement = dict(
            external_account_id="bank",
            transactions=[
                tx("fixed", "-100", "ENERGIA"),
                tx("card", "-186.19", "PAGTO BANCO XP S.A"),
                tx("pix", "-48.85", "COMPRAS PIX"),
                tx("csf", "-72.88", "PAGTO BANCO CSF"),
                tx("iof", "-1.92", "IOF"),
                tx("fee", "-6.55", "ENCARGOS"),
                tx("credit", "1569.97", "SALARIO"),
                tx("pending", "-15", "PENDENTE", status="PENDING"),
                tx("usd", "-10", "USD", currency="USD"),
                tx("old", "-30", "OUTRO MES", day="2026-10-10"),
            ],
        )
        result = build_summary(
            records,
            [payment],
            [statement, statement],
            [],
            [],
            date(2026, 11, 1),
            date(2026, 11, 30),
            [bill],
        )
        self.assertEqual(result["other_paid"], "130.20")
        self.assertEqual(len(result["other_paid_details"]), 4)
        self.assertEqual(result["fixed_paid"], "100")
        self.assertEqual(result["cards"], "186.19")

    def test_financial_evolution_uses_cash_summary_and_preserves_missing_months(self):
        from monthly_summary import financial_evolution

        account = dict(id=1, kind="accounts", name="Banco", pluggy_data={})

        def tx(key, day, amount):
            return dict(
                id=key,
                date=day,
                amount=amount,
                currency="BRL",
                status="POSTED",
                description="Movimento",
            )

        periods = [
            dict(
                account_id=1,
                external_account_id="bank",
                period_start=date(2026, 10, 1),
                period_end=date(2026, 10, 31),
                transactions=[
                    tx("oct-credit", "2026-10-10", "20"),
                    tx("oct-debit", "2026-10-11", "-30"),
                ],
            ),
            dict(
                account_id=1,
                external_account_id="bank",
                period_start=date(2026, 11, 1),
                period_end=date(2026, 11, 30),
                transactions=[
                    tx("nov-credit", "2026-11-10", "5"),
                    tx("nov-debit", "2026-11-11", "-100"),
                ],
            ),
        ]
        openings = [
            dict(account_id=1, period_start=date(2026, 10, 1), currency="BRL", amount="100")
        ]
        history = financial_evolution(
            [account], [], periods, [], [], openings, [], date(2026, 11, 1)
        )
        self.assertEqual(len(history), 12)
        self.assertEqual(history[0]["month"], "2025-12")
        self.assertFalse(history[0]["available"])
        self.assertIsNone(history[0]["balance"])
        self.assertEqual(history[-2]["income"], "20")
        self.assertEqual(history[-2]["expenses"], "30")
        self.assertEqual(history[-2]["balance"], "90")
        self.assertEqual(history[-1]["balance"], "-5")
        self.assertFalse(history[-1]["partial"])

    def test_unsynced_bill_is_missing_not_zero(self):
        result = build_summary(
            [dict(id=1, kind="cards", name="Sem cache", due_date=date(2026, 11, 5))],
            [],
            [],
            [],
            [],
            date(2026, 11, 1),
            date(2026, 11, 30),
        )
        self.assertIsNone(result["card_details"][0]["amount"])

    def test_official_bill_due_date_overrides_outdated_card_registration(self):
        records = [
            dict(id=18, kind="cards", name="Mercado Pago", due_date=date(2026, 10, 10)),
            dict(id=9, kind="cards", name="Rico", due_date=date(2026, 11, 5)),
        ]
        months = [
            dict(
                card_id=18,
                month=date(2026, 11, 1),
                bills=[dict(id="mp-nov", due_date="2026-11-10", amount="139.99", currency="BRL")],
            ),
            dict(
                card_id=9,
                month=date(2026, 11, 1),
                bills=[dict(id="rico-nov", due_date="2026-11-05", amount="186.19", currency="BRL")],
            ),
        ]
        result = build_summary(
            records, [], [], [], [], date(2026, 11, 1), date(2026, 11, 30), months
        )
        self.assertEqual(result["cards"], "326.18")
        self.assertEqual(len(result["card_details"]), 2)
        self.assertEqual(result["card_details"][0]["due_date"], "2026-11-10")

    def test_official_bill_not_added_to_legacy_cycle_twice(self):
        card = dict(
            id=1,
            kind="cards",
            name="Cartão",
            due_date=date(2026, 11, 10),
            previous_closing_date=date(2026, 10, 5),
            closing_date=date(2026, 11, 5),
        )
        legacy = [
            dict(
                card_id=1,
                previous_closing_date=date(2026, 10, 5),
                closing_date=date(2026, 11, 5),
                transactions=[dict(currency="BRL", amount="999")],
            )
        ]
        bill = dict(id="b", due_date="2026-11-10", amount="139.99", currency="BRL")
        months = [dict(card_id=1, month=date(2026, 11, 1), bills=[bill, bill])]
        result = build_summary(
            [card], [], [], legacy, [], date(2026, 11, 1), date(2026, 11, 30), months
        )
        self.assertEqual(result["cards"], "139.99")
        self.assertEqual(len(result["card_details"]), 1)

    def test_pix_excludes_fixed_cost_and_card_payment_but_keeps_other_purchases(self):
        from monthly_summary import pix_pays_obligation

        costs = [dict(statement_name="DES AMBAR ENERGIA AMAZONA")]
        cards = [dict(name="Mercado Pago", institution="Mercado Pago")]
        details = [dict(name="Mercado Pago", amount="139.99")]

        def tx(description, amount="-139.99", category="Online shopping"):
            return dict(description=description, amount=amount, category=category)

        self.assertTrue(
            pix_pays_obligation(
                tx("PIX DES AMBAR ENERGIA AMAZONA 09/11", "-395.48"), costs, cards, details
            )
        )
        self.assertTrue(
            pix_pays_obligation(tx("PIX DES MERCADO PAGO INSTITUI 06/11"), costs, cards, details)
        )
        self.assertFalse(
            pix_pays_obligation(
                tx("PIX DES MERCADO PAGO INSTITUI 06/11", "-20"), costs, cards, details
            )
        )
        self.assertFalse(
            pix_pays_obligation(tx("PIX MERCADINHO FREITAS", "-139.99"), costs, cards, details)
        )
        self.assertTrue(
            pix_pays_obligation(tx("PIX PAGAMENTO DE FATURA", "-100"), costs, cards, details)
        )

    def test_qr_purchases_survive_incorrect_transfer_categories(self):
        def tx(id, amount, category, description):
            return dict(
                id=id,
                amount=amount,
                currency="BRL",
                status="POSTED",
                date="2026-11-06",
                operation_type="PIX",
                category=category,
                description=description,
            )

        statement = dict(
            external_account_id="a",
            transactions=[
                tx("nova1", "-7", "Transfer - PIX", "PIX QR CODE DINAMICO MERCANTIL NOVA ERA"),
                tx("nova2", "-7.85", "Transfer - PIX", "PIX QR CODE DINAMICO MERCANTIL NOVA ERA"),
                tx("quick", "-5", "Transfer - Bank Slip", "PIX QR CODE DINAMICO QUICK BITES"),
                tx("other", "-25", "Groceries", "PIX QR CODE ESTATICO MERCADINHO"),
                tx("transfer", "-100", "Transfer - PIX", "PIX ENVIADO PARA OUTRA CONTA"),
                tx("fixed", "-350", "Transfer - PIX", "PIX QR CODE DES AMBAR ENERGIA AMAZONA"),
            ],
        )
        costs = [
            dict(
                id=1,
                kind="expenses",
                amount=350,
                due_date=date(2026, 11, 8),
                status="Pago",
                statement_name="DES AMBAR ENERGIA AMAZONA",
            )
        ]
        result = build_summary(
            costs, [], [statement], [], [], date(2026, 11, 1), date(2026, 11, 30)
        )
        self.assertEqual(result["pix"], "44.85")


class BudgetCommitmentTests(unittest.TestCase):
    def test_commitment_uses_paid_amount_and_unpaid_forecasts_once(self):
        records = [
            dict(id=1, kind="expenses", amount="350", due_date=date(2026, 11, 5), status="Pago"),
            dict(
                id=2, kind="expenses", amount="200", due_date=date(2026, 11, 20), status="Pendente"
            ),
            dict(id=3, kind="expenses", amount="100", due_date=date(2026, 11, 10), status="Pago"),
            dict(
                id=4, kind="expenses", amount="999", due_date=date(2026, 12, 5), status="Pendente"
            ),
        ]
        payments = [
            dict(
                expense_id=1,
                paid_amount="395.48",
                paid_date=date(2026, 11, 5),
                external_account_id="a",
                transaction_id="t",
            )
        ]
        result = build_summary(records, payments, [], [], [], date(2026, 11, 1), date(2026, 11, 30))
        self.assertEqual(result["fixed_committed"], "695.48")
        self.assertEqual(result["fixed_paid"], "495.48")

    def test_payment_in_other_month_is_not_counted_again_as_pending(self):
        cost = dict(
            id=1, kind="expenses", amount="350", due_date=date(2026, 11, 5), status="Pendente"
        )
        payment = dict(
            expense_id=1,
            paid_amount="340",
            paid_date=date(2026, 10, 31),
            external_account_id="a",
            transaction_id="t",
        )
        result = build_summary([cost], [payment], [], [], [], date(2026, 11, 1), date(2026, 11, 30))
        self.assertEqual(result["fixed_committed"], "0")


class MonthlyCashTests(unittest.TestCase):
    def account(self, id=1, currency="BRL"):
        return dict(
            id=id,
            kind="accounts",
            name="Conta " + str(id),
            connection_id=1,
            pluggy_data=dict(id="bank-" + str(id), type="BANK", currency=currency),
        )

    def test_confirmed_income_deduplicated_and_manual_opening_carried(self):
        from monthly_summary import monthly_cash_position

        start, end = date(2026, 12, 1), date(2026, 12, 31)

        def tx(id, amount, day, status="POSTED", currency="BRL"):
            return dict(id=id, amount=amount, date=day, status=status, currency=currency)

        previous = dict(
            account_id=1,
            period_start=date(2026, 11, 1),
            period_end=date(2026, 11, 30),
            transactions=[tx("salary", "1000", "2026-11-03"), tx("paid", "-200", "2026-11-05")],
        )
        current = dict(
            account_id=1,
            period_start=start,
            period_end=end,
            transactions=[
                tx("in", "500", "2026-12-03"),
                tx("out", "-100", "2026-12-04"),
                tx("pending", "999", "2026-12-05", "PENDING"),
                tx("usd", "999", "2026-12-05", currency="USD"),
            ],
        )
        opening = dict(
            account_id=1, period_start=date(2026, 11, 1), currency="BRL", amount="4753.39"
        )
        result = monthly_cash_position(
            [self.account()], [previous, current, current], [opening], start, end
        )
        self.assertEqual(result["opening_balance"], "5553.39")
        self.assertEqual(result["incoming"], "500")
        self.assertEqual(result["missing_statement_accounts"], [])

    def test_missing_opening_or_statement_is_not_a_zero_balance(self):
        from monthly_summary import monthly_cash_position

        result = monthly_cash_position(
            [self.account()], [], [], date(2026, 11, 1), date(2026, 11, 30)
        )
        self.assertIsNone(result["opening_balance"])
        self.assertEqual(result["missing_opening_accounts"], ["Conta 1"])
        self.assertEqual(result["missing_statement_accounts"], ["Conta 1"])

    def test_pluggy_previous_close_and_accounts_sum_without_foreign_currencies(self):
        from monthly_summary import monthly_cash_position

        start, end = date(2026, 11, 1), date(2026, 11, 30)
        previous = dict(
            account_id=1,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            transactions=[
                dict(
                    id="close",
                    date="2026-10-31",
                    balance="123.45",
                    amount="0",
                    currency="BRL",
                    status="POSTED",
                )
            ],
        )
        current = dict(account_id=1, period_start=start, period_end=end, transactions=[])
        second = dict(account_id=2, period_start=start, period_end=end, transactions=[])
        opening = dict(account_id=2, period_start=start, currency="BRL", amount="-50")
        result = monthly_cash_position(
            [self.account(), self.account(2), self.account(3, "USD")],
            [previous, current, second],
            [opening],
            start,
            end,
        )
        self.assertEqual(result["opening_balance"], "73.45")
        self.assertEqual(result["incoming"], "0")
        self.assertEqual(result["missing_statement_accounts"], [])

    def test_all_statement_accounts_including_manual_and_negative_balances(self):
        from monthly_summary import monthly_cash_position

        start, end = date(2026, 12, 1), date(2026, 12, 31)
        accounts = [
            self.account(),
            dict(id=2, kind="accounts", name="Conta manual", amount="999999"),
            self.account(3),
        ]
        openings = [
            dict(account_id=1, period_start=start, currency="BRL", amount="100"),
            dict(account_id=2, period_start=start, currency="BRL", amount="-20"),
        ]
        result = monthly_cash_position(accounts, [], openings, start, end)
        self.assertIsNone(result["opening_balance"])
        self.assertEqual(result["opening_balance_known"], "80")
        self.assertEqual(result["missing_opening_accounts"], ["Conta 3"])
        self.assertEqual(
            [row["amount"] for row in result["opening_account_details"]], ["100", "-20", None]
        )

    def test_edited_opening_precedes_carry_and_carry_remains_the_default(self):
        from monthly_summary import monthly_cash_position

        start, end = date(2026, 12, 1), date(2026, 12, 31)
        openings = [
            dict(account_id=1, period_start=date(2026, 11, 1), currency="BRL", amount="4753.39"),
            dict(account_id=1, period_start=start, currency="BRL", amount="9999"),
        ]
        previous = dict(
            account_id=1,
            period_start=date(2026, 11, 1),
            period_end=date(2026, 11, 30),
            transactions=[
                dict(id="out", currency="BRL", status="POSTED", date="2026-11-05", amount="-100")
            ],
        )
        result = monthly_cash_position([self.account()], [previous], openings, start, end)
        self.assertEqual(result["opening_balance"], "9999")
        carried = monthly_cash_position([self.account()], [previous], openings[:1], start, end)
        self.assertEqual(carried["opening_balance"], "4653.39")
