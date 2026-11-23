"""Resumo de caixa do mês: usa dados salvos e separa previsão de realização."""

from decimal import Decimal
from datetime import date
import unicodedata
from billing import summarize, card_period, cached_cycle_for_month
from reconciliation import normalize, meaningful_name
import re


def normalized(value):
    return (
        unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().upper()
    )


def future_card_charges(records, bills, official_months, selected_month, cycles=None):
    """Soma Valor da fatura dos ciclos com vencimento no mês seguinte."""
    from billing import bill_transactions_due_in_month

    year, index = divmod(selected_month.year * 12 + selected_month.month, 12)
    next_month = date(year, index + 1, 1)
    cards = [r for r in records if r["kind"] == "cards"]
    total = Decimal(0)
    missing, details = [], []
    known = False
    for card in cards:
        bill = bill_transactions_due_in_month(card, bills, official_months, cycles or [], next_month)
        value = None
        incomplete = False
        if bill is not None:
            groups = summarize(bill["transactions"])
            brl = next((g for g in groups if g["currency"] == "BRL"), None)
            value = Decimal(brl["charges"]) if brl else Decimal(0)
            incomplete = any(g["currency"] != "BRL" for g in groups)
            total += value
            known = True
        if value is None or incomplete:
            missing.append(card["name"])
        details.append(dict(name=card["name"], amount=str(value) if value is not None else None,
                            manual_amount=str(sum((Decimal(t['amount']) for t in bill['transactions'] if t.get('manual_adjustment')), Decimal(0))) if bill else '0',
                            due_date=bill["due_date"].isoformat() if bill else None,
                            closing_date=bill["closing_date"].isoformat() if bill and bill["closing_date"] else None))
    return dict(month=next_month.strftime("%Y-%m"),
                amount=str(total) if known or not cards else None,
                partial=bool(missing), missing_cards=missing, details=details)


def future_card_schedule(records, bills, official_months, selected_month, cycles=None):
    """Faturas conhecidas mais parcelas restantes, sem repetir parcelas importadas."""
    from billing import bill_transactions_due_in_month, is_bill_payment
    from collections import Counter

    def index(day):
        return day.year * 12 + day.month - 1

    def month_at(number):
        year, month = divmod(number, 12)
        return date(year, month + 1, 1)

    def description(transaction):
        text = normalized(transaction.get('description'))
        text = re.sub(r'\b(?:PARC(?:ELA)?[ .:]*)?\d{1,3}\s*/\s*\d{1,3}\b', '', text)
        return re.sub(r'[^A-Z0-9]', '', text)

    def parcel(transaction):
        current, total = transaction.get('installment'), transaction.get('installments')
        if current is None or total is None:
            match = re.search(r'\bPARC(?:ELA)?[ .:]*(\d{1,3})\s*/\s*(\d{1,3})\b',
                              normalized(transaction.get('description')))
            if not match:
                return None
            current, total = match.groups()
        try:
            current, total = int(current), int(total)
        except (TypeError, ValueError):
            return None
        if not 1 <= current <= total <= 999 or total < 2:
            return None
        amount = Decimal(str(transaction.get('amount', 0)))
        if not amount.is_finite() or amount <= 0 or is_bill_payment(transaction):
            return None
        if transaction.get('status') in {'CANCELED', 'CANCELLED', 'DELETED'}:
            return None
        if transaction.get('currency') != 'BRL':
            return None
        return current, total, amount

    # Cada ciclo fornece uma única fonte, usando o mesmo vencimento do Valor da fatura.
    candidate_months = set(range(index(selected_month), index(selected_month) + 7))
    for row in [*bills, *official_months, *(cycles or [])]:
        for field in ('month', 'closing_date', 'reference_month', 'due_date'):
            value = row.get(field)
            if isinstance(value, date):
                candidate_months.update((index(value), index(value) + 1))
    snapshots, series = {}, {}
    for card in (r for r in records if r['kind'] == 'cards'):
        card_snapshots = {}
        for number in sorted(candidate_months):
            bill = bill_transactions_due_in_month(card, bills, official_months, cycles or [], month_at(number))
            if bill is None:
                continue
            snapshots[(card['id'], number)] = bill
            card_snapshots[number] = bill
        precise_ids = {(t.get('id'), t.get('installment')) for snapshot in card_snapshots.values()
                       if snapshot.get('closing_date') for t in snapshot['transactions'] if t.get('id')}
        seen_ids = set()
        for number, bill in card_snapshots.items():
            occurrences = Counter()
            for transaction in bill['transactions']:
                if any(description(transaction) == description(adjustment)
                       for adjustment in card.get('installment_adjustments') or []):
                    continue
                if (not bill.get('closing_date') and transaction.get('id') and
                    (transaction['id'], transaction.get('installment')) in precise_ids):
                    continue
                # Consultas por conta podem trazer compras pendentes de um ciclo posterior.
                # Elas não podem antecipar o início do parcelamento no cache mais antigo.
                if (bill.get('closing_date') and transaction.get('date', '') > bill['closing_date'].isoformat()):
                    continue
                part = parcel(transaction)
                if not part:
                    continue
                current, total, amount = part
                identity = (transaction.get('id'), current)
                if identity[0] and identity in seen_ids:
                    continue
                if identity[0]:
                    seen_ids.add(identity)
                origin = number - current + 1
                name = description(transaction)
                base_key = (card['id'], origin, total, amount)
                # Alguns bancos abreviam o mesmo estabelecimento entre faturas.
                known = next((key[4] for key in series if key[:4] == base_key
                              and (key[4] == name or (min(len(key[4]), len(name)) >= 8
                                   and (key[4].startswith(name) or name.startswith(key[4]))))), name)
                occurrences[(base_key, known)] += 1
                key = (*base_key, known, occurrences[(base_key, known)])
                observed = min(number, series.get(key, {}).get('observed', number))
                series[key] = dict(card_id=card['id'], origin=origin, total=total, amount=amount, observed=observed,
                                   name=known, description=transaction.get('description') or 'Compra parcelada')

    months = []
    base = index(selected_month)
    for offset in range(6):
        result = future_card_charges(records, bills, official_months, month_at(base + offset), cycles)
        target = base + offset + 1
        projected_total = Decimal(0)
        for card, detail in zip((r for r in records if r['kind'] == 'cards'), result['details']):
            imported = (snapshots.get((card['id'], target)) or {}).get('transactions', [])
            available = Counter((description(t), Decimal(str(t['amount']))) for t in imported
                                if t.get('currency') == 'BRL' and Decimal(str(t['amount'])) > 0
                                and not is_bill_payment(t))
            additions = []
            for purchase in series.values():
                number = target - purchase['origin'] + 1
                if purchase['card_id'] != card['id'] or not 1 < number <= purchase['total']:
                    continue
                # Só projeta a partir de uma parcela já conhecida em vencimento anterior.
                if purchase['observed'] >= target:
                    continue
                matching = next((key for key, count in available.items() if count > 0
                                 and key[1] == purchase['amount'] and
                                 (key[0] == purchase['name'] or (min(len(key[0]),len(purchase['name'])) >= 8
                                  and (key[0].startswith(purchase['name']) or purchase['name'].startswith(key[0]))))), None)
                if matching:
                    available[matching] -= 1
                    continue
                additions.append(dict(description=purchase['description'], installment=number,
                                      installments=purchase['total'], amount=str(purchase['amount'])))
            projected = sum((Decimal(p['amount']) for p in additions), Decimal(0))
            manual = Decimal(detail.get('manual_amount') or '0')
            detail['imported_amount'] = str(Decimal(detail['amount']) - manual) if detail['amount'] is not None else None
            manual_rows = [t for t in imported if t.get('manual_adjustment')]
            detail['projected_installments'] = manual_rows + additions
            detail['projected_amount'] = str(projected + manual)
            if additions:
                detail['amount'] = str(Decimal(detail['amount'] or '0') + projected)
                projected_total += projected
        manual_total = sum((Decimal(d.get('manual_amount') or '0') for d in result['details']), Decimal(0))
        result['projected_amount'] = str(projected_total + manual_total)
        result['estimated'] = projected_total + manual_total > 0
        if projected_total:
            result['amount'] = str(Decimal(result['amount'] or '0') + projected_total)
        months.append(result)
    return months



# Evita classificar como compra um Pix que já representa uma obrigação do mês.
def pix_pays_obligation(transaction, fixed_costs, cards, card_details):
    description = " " + normalize(transaction.get("description")) + " "
    for cost in fixed_costs:
        name = cost.get("statement_name")
        if meaningful_name(name) and (" " + normalize(name) + " ") in description:
            return True
    # Tipos/categorias de fatura podem vir incorretamente como PIX pelo conector.
    category = normalized(transaction.get("category"))
    if category in {"CREDIT CARD PAYMENT", "CREDIT CARD BILL PAYMENT"}:
        return True
    if re.search(
        r"\b(?:pagamento|pgto|pagto) (?:da |de )?fatura\b",
        normalize(transaction.get("description")),
    ):
        return True
    amount = abs(Decimal(str(transaction["amount"])))
    for card in cards:
        institution = normalize(card.get("institution"))
        if not meaningful_name(institution) or (" " + institution + " ") not in description:
            continue
        # Nome do banco sozinho pode ser uma compra em uma plataforma de pagamentos.
        # Exige também o valor exato de uma fatura apurada para esse cartão no mês.
        if any(
            detail["name"] == card["name"]
            and detail["amount"] is not None
            and Decimal(detail["amount"]) > 0
            and Decimal(detail["amount"]) == amount
            for detail in card_details
        ):
            return True
    return False


# Pagamento de fatura já apurada não é uma segunda saída no resumo.
def pays_counted_card(transaction, cards, card_details):
    description = " " + normalize(transaction.get("description")) + " "
    amount = abs(Decimal(str(transaction["amount"])))
    for card in cards:
        names = [card.get("institution"), card.get("name")]
        # A fatura Rico aparece no extrato com o nome do emissor Banco XP.
        if normalize(card.get("institution")) == "rico":
            names.append("Banco XP")
        if not any(
            normalize(name) and (" " + normalize(name) + " ") in description for name in names
        ):
            continue
        if any(
            d["name"] == card["name"]
            and d["amount"] is not None
            and Decimal(d["amount"]) > 0
            and Decimal(d["amount"]) == amount
            for d in card_details
        ):
            return True
    return False


# BLOCO — Calcula os totais mensais e classifica as demais saídas sem repetir obrigações.
def build_summary(records, payments, statements, bills, flows, start, end, official_months=None):
    # Custos previstos seguem vencimento; pagamentos conciliados seguem a saída real.
    fixed = [r for r in records if r["kind"] == "expenses"]
    planned = sum(
        (
            Decimal(str(r["amount"] or 0))
            for r in fixed
            if r.get("due_date") and start <= r["due_date"] <= end
        ),
        Decimal(0),
    )
    # O histórico de conciliação também guarda rendas; elas não são custos pagos.
    fixed_ids = {r["id"] for r in fixed}
    payments = [p for p in payments if p["expense_id"] in fixed_ids]
    payment_ids = {p["expense_id"] for p in payments}
    paid = sum(
        (Decimal(str(p["paid_amount"])) for p in payments if start <= p["paid_date"] <= end),
        Decimal(0),
    )
    manual_paid = sum(
        (
            Decimal(str(r["amount"] or 0))
            for r in fixed
            if r["id"] not in payment_ids
            and r.get("status") == "Pago"
            and r.get("due_date")
            and start <= r["due_date"] <= end
        ),
        Decimal(0),
    )
    matched = {(p["external_account_id"], p["transaction_id"]) for p in payments}
    totals = {
        "fixed_planned": planned,
        "fixed_paid": paid + manual_paid,
        "manual_paid": manual_paid,
        # O valor pago substitui a previsão; somente obrigações ainda não pagas são somadas.
        "fixed_committed": paid
        + manual_paid
        + sum(
            (
                Decimal(str(r["amount"] or 0))
                for r in fixed
                if r["id"] not in payment_ids
                and r.get("status") != "Pago"
                and r.get("due_date")
                and start <= r["due_date"] <= end
            ),
            Decimal(0),
        ),
        "cards": Decimal(0),
        "contributions": sum(
            (
                Decimal(str(f["amount"]))
                for f in flows
                if f["direction"] == "entrada" and start <= f["day"] <= end
            ),
            Decimal(0),
        ),
        "debit": Decimal(0),
        "pix": Decimal(0),
        "other_paid": Decimal(0),
    }
    card_details = []
    for card in records:
        if card["kind"] != "cards":
            continue
        # A fatura oficial define seu vencimento, independentemente da data do cadastro.
        official = next(
            (
                row
                for row in (official_months or [])
                if row["card_id"] == card["id"] and row["month"] == start
            ),
            None,
        )
        if official is not None:
            seen_bills = set()
            for bill in official["bills"]:
                due = str(bill.get("due_date") or "")
                if not start.isoformat() <= due <= end.isoformat() or bill["id"] in seen_bills:
                    continue
                seen_bills.add(bill["id"])
                value = Decimal(str(bill["amount"])) if bill["currency"] == "BRL" else None
                if value is not None:
                    totals["cards"] += value
                card_details.append(
                    {
                        "name": card["name"],
                        "due_date": due,
                        "amount": str(value) if value is not None else None,
                    }
                )
            # Ausência na consulta oficial não é substituída por saldo de outro período.
            continue
        if not card.get("due_date") or not start <= card["due_date"] <= end:
            continue
        saved = None
        try:
            _, closing = card_period(card)
            saved = next(
                (
                    b
                    for b in bills
                    if b["card_id"] == card["id"]
                    and b["previous_closing_date"] == card["previous_closing_date"]
                    and b["closing_date"] == closing
                ),
                None,
            )
        except ValueError:
            pass
        value = None
        if saved:
            groups = summarize(saved["transactions"])
            brl = next((g for g in groups if g["currency"] == "BRL"), None)
            value = Decimal(brl["net"]) if brl else (Decimal(0) if not groups else None)
        if value is not None:
            totals["cards"] += value
        card_details.append(
            {
                "name": card["name"],
                "due_date": card["due_date"].isoformat(),
                "amount": str(value) if value is not None else None,
            }
        )

    # Deduplica caches sobrepostos pela conta externa e identificador do lançamento.
    seen = set()
    other_details = []
    cards = [r for r in records if r["kind"] == "cards"]
    manual_costs = [
        r
        for r in fixed
        if r["id"] not in payment_ids
        and r.get("status") == "Pago"
        and r.get("due_date")
        and start <= r["due_date"] <= end
    ]
    for statement in statements:
        for t in statement["transactions"]:
            key = (statement["external_account_id"], t["id"])
            if key in seen:
                continue
            seen.add(key)
            if (
                key in matched
                or not start.isoformat() <= t["date"] <= end.isoformat()
                or t.get("status") != "POSTED"
                or t.get("currency") != "BRL"
            ):
                continue
            amount = Decimal(str(t["amount"]))
            if amount >= 0:
                continue
            # Outras saídas incluem Pix, débito, boletos e tarifas, sem repetir
            # custos conciliados, custos pagos manualmente ou faturas já apuradas.
            description = " " + normalize(t.get("description")) + " "
            manual_payment = any(
                meaningful_name(r.get("statement_name"))
                and (" " + normalize(r["statement_name"]) + " ") in description
                for r in manual_costs
            )
            if not manual_payment and not pays_counted_card(t, cards, card_details):
                totals["other_paid"] -= amount
                other_details.append(
                    dict(date=t["date"], description=t.get("description", ""), amount=str(-amount))
                )
            operation = normalized(t.get("operation_type"))
            category = normalized(t.get("category"))
            # Pagamentos por QR Code continuam sendo compras mesmo se o enriquecimento
            # do Pluggy os classificar como transferência ou boleto.
            qr_purchase = operation == "PIX" and "QR CODE" in normalized(t.get("description"))
            if category.startswith("TRANSFER") and not qr_purchase:
                continue
            if operation == "PIX":
                if pix_pays_obligation(
                    t, fixed, [r for r in records if r["kind"] == "cards"], card_details
                ):
                    continue
                totals["pix"] -= amount
            elif operation in {
                "COMPRA_CARTAO",
                "COMPRA_CARTAO_DEBITO",
                "DEBIT_CARD",
                "PURCHASE_WITH_DEBIT_CARD",
            }:
                totals["debit"] -= amount
    return {
        **{key: str(value) for key, value in totals.items()},
        "card_details": card_details,
        "other_paid_details": other_details,
    }


# BLOCO — Caixa consolidado em BRL, com a mesma abertura mensal do extrato.
def monthly_cash_position(records, periods, openings, start, end):
    from datetime import timedelta
    from bank_statements import resolve_openings

    previous_end = start - timedelta(days=1)
    previous_start = previous_end.replace(day=1)
    incoming = Decimal(0)
    opening_total = Decimal(0)
    missing_openings = []
    missing_statements = []
    seen_accounts = set()
    seen_transactions = set()
    opening_details = []
    for account in records:
        if (
            account["kind"] != "accounts"
            or account.get("crypto_data")
            or account.get("crypto_connection_id")
        ):
            continue
        data = account.get("pluggy_data") or {}
        account_key = ("pluggy", data["id"]) if data.get("id") else ("manual", account["id"])
        if (data.get("currency") or "BRL") != "BRL" or account_key in seen_accounts:
            continue
        seen_accounts.add(account_key)
        history = [p for p in periods if p["account_id"] == account["id"]]
        previous = next(
            (
                p
                for p in history
                if p["period_start"] == previous_start and p["period_end"] == previous_end
            ),
            None,
        )
        balances = resolve_openings(
            [o for o in openings if o["account_id"] == account["id"]],
            [p for p in history if p["period_start"] < start],
            previous["transactions"] if previous else [],
            start,
        )
        opening = balances.get("BRL")
        # Quando o extrato anterior tem saldo calculado, usa exatamente seu fechamento.
        # Não utiliza o saldo atual do cadastro para representar um mês passado.
        explicit_opening = any(
            o["account_id"] == account["id"] and o["period_start"] == start and o["currency"] == "BRL"
            for o in openings
        )
        if previous and not explicit_opening:
            older_end = previous_start - timedelta(days=1)
            older = next(
                (
                    p
                    for p in history
                    if p["period_start"] == older_end.replace(day=1)
                    and p["period_end"] == older_end
                ),
                None,
            )
            prior_opening = resolve_openings(
                [o for o in openings if o["account_id"] == account["id"]],
                [p for p in history if p["period_start"] < previous_start],
                older["transactions"] if older else [],
                previous_start,
            ).get("BRL")
            if prior_opening is not None:
                net = sum(
                    (
                        Decimal(str(t["amount"]))
                        for t in previous["transactions"]
                        if t.get("currency") == "BRL"
                        and t.get("status") == "POSTED"
                        and previous_start.isoformat()
                        <= t.get("date", "")
                        <= previous_end.isoformat()
                    ),
                    Decimal(0),
                )
                opening = {
                    "amount": prior_opening["amount"] + net,
                    "source": "Saldo do período do mês anterior",
                }
        opening_details.append(
            dict(
                account_id=account["id"],
                name=account["name"],
                amount=str(opening["amount"]) if opening else None,
            )
        )
        if opening is None:
            missing_openings.append(account["name"])
        else:
            opening_total += opening["amount"]
        current = [p for p in history if p["period_start"] <= start and p["period_end"] >= end]
        if not current:
            missing_statements.append(account["name"])
        for period in current:
            for transaction in period["transactions"]:
                key = (account_key, transaction["id"])
                if key in seen_transactions:
                    continue
                seen_transactions.add(key)
                if (
                    transaction.get("status") == "POSTED"
                    and transaction.get("currency") == "BRL"
                    and start.isoformat() <= transaction.get("date", "") <= end.isoformat()
                ):
                    incoming += max(Decimal(str(transaction["amount"])), Decimal(0))
    return dict(
        opening_balance=None if missing_openings else str(opening_total),
        opening_balance_known=str(opening_total),
        opening_account_details=opening_details,
        incoming=str(incoming),
        missing_opening_accounts=missing_openings,
        missing_statement_accounts=missing_statements,
    )


# BLOCO — Série mensal do resumo financeiro; usa os mesmos critérios dos cards.
def financial_evolution(
    records, payments, statements, bills, flows, openings, official_months, end_month
):
    import calendar

    history = []
    month_index = end_month.year * 12 + end_month.month - 1
    for offset in range(11, -1, -1):
        year, index = divmod(month_index - offset, 12)
        start = date(year, index + 1, 1)
        end = date(year, index + 1, calendar.monthrange(year, index + 1)[1])
        summary = build_summary(
            records, payments, statements, bills, flows, start, end, official_months
        )
        cash = monthly_cash_position(records, statements, openings, start, end)
        available = any(p["period_start"] <= start and p["period_end"] >= end for p in statements)
        available = available or any(
            r["kind"] == "expenses" and r.get("due_date") and start <= r["due_date"] <= end
            for r in records
        )
        available = available or any(d["amount"] is not None for d in summary["card_details"])
        expenses = sum(
            (Decimal(summary[k]) for k in ("fixed_paid", "cards", "other_paid")), Decimal(0)
        )
        opening = (
            cash["opening_balance"]
            if cash["opening_balance"] is not None
            else cash["opening_balance_known"]
        )
        balance = Decimal(opening) + Decimal(cash["incoming"]) - expenses
        history.append(
            dict(
                month=start.strftime("%Y-%m"),
                available=available,
                income=cash["incoming"] if available else None,
                expenses=str(expenses) if available else None,
                balance=str(balance) if available else None,
                partial=bool(
                    cash["missing_opening_accounts"] or cash["missing_statement_accounts"]
                ),
            )
        )
    return history
