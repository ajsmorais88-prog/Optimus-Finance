"""Lançamentos Pluggy por cartão e ciclo de fechamento, sem efetuar pagamentos."""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode, parse_qs, urlsplit
import re
import unicodedata

from flask import Blueprint, jsonify, request
from psycopg.types.json import Jsonb
from pluggy import call, token, PluggyError
from pluggy_config import read_config

blueprint = Blueprint("billing", __name__)


# BLOCO — Recusa chamadas de escrita vindas de outra origem.
@blueprint.before_request
def protect_origin():
    origin = request.headers.get("Origin")
    if origin and origin != request.host_url.rstrip("/"):
        return jsonify(error="Origem não permitida."), 403


# BLOCO — Impede que extratos e faturas privados sejam armazenados em cache.
@blueprint.after_request
def prevent_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


# BLOCO 1 — O ID local determina a conta externa e as credenciais, nunca o navegador.
def get_card(card_id):
    from app import connect

    with connect() as conn:
        card = conn.execute(
            "SELECT * FROM records WHERE id=%s AND kind='cards'", (card_id,)
        ).fetchone()
    return card


# BLOCO — Determina o intervalo da fatura a partir das datas de fechamento configuradas.
def card_period(card):
    previous, closing = card.get("previous_closing_date"), card.get("closing_date")
    if not previous or not closing:
        raise ValueError(
            "Preencha o fechamento da fatura anterior e o fechamento da fatura em Editar cartão."
        )
    if previous >= closing:
        raise ValueError(
            "O fechamento anterior deve ser uma data anterior ao fechamento da fatura."
        )
    return previous + timedelta(days=1), closing


def cached_cycle_for_month(card, periods, month):
    """Relaciona um ciclo já consultado ao primeiro vencimento após seu fechamento."""
    import calendar

    due = card.get("due_date")
    if not due:
        return None
    matches = []
    for period in periods:
        closing = period.get("closing_date")
        previous = period.get("previous_closing_date")
        if period.get("card_id") != card["id"] or not closing or not previous or previous >= closing:
            continue
        year, number = closing.year, closing.month
        inferred = date(year, number, min(due.day, calendar.monthrange(year, number)[1]))
        if inferred <= closing:
            year, index = divmod(year * 12 + number, 12)
            inferred = date(year, index + 1, min(due.day, calendar.monthrange(year, index + 1)[1]))
        if inferred.replace(day=1) == month:
            matches.append({**period, "due_date": inferred})
    return max(matches, key=lambda p: p["closing_date"], default=None)


def month_bill_transaction_source(saved, cycle):
    """Fonte única dos lançamentos usados em Valor da fatura e no resumo."""
    if not (saved or {}).get("transactions") and cycle and cycle.get("transactions") is not None:
        return cycle
    return saved


def apply_installment_adjustments(card, transactions, due):
    """Correções de ciclo informadas pelo usuário, preservadas após sincronizações."""
    result = [dict(t) for t in transactions]
    for adjustment in card.get('installment_adjustments') or []:
        first = date.fromisoformat(adjustment['first_due_month'])
        number = (due.year - first.year) * 12 + due.month - first.month + 1
        if not 1 <= number <= adjustment['installments']:
            continue
        matching = [t for t in result if
                    re.sub(r'[^A-Z0-9]', '', str(t.get('description', '')).upper()) ==
                    re.sub(r'[^A-Z0-9]', '', adjustment['description'].upper()) and
                    t.get('currency') == adjustment['currency'] and
                    Decimal(str(t.get('amount', 0))) == Decimal(adjustment['amount'])]
        if matching:
            matching[0].update(installment=number, installments=adjustment['installments'])
            continue
        if number == 1:
            # A primeira parcela já foi lançada; não cria uma segunda cópia em outro cache.
            continue
        result.append(dict(id=f"adjustment:{card['id']}:{first}:{number}",
                           date=adjustment['purchase_date'], description=adjustment['description'],
                           amount=adjustment['amount'], currency=adjustment['currency'],
                           installment=number, installments=adjustment['installments'],
                           status='Ajuste informado', type='DEBIT', manual_adjustment=True))
    return result


def bill_transactions_due_in_month(card, periods, monthly, cycles, month):
    """Escolhe uma fatura pelo vencimento real e mantém seu próprio ciclo/fonte."""
    import calendar

    def effective_due(cycle):
        due, closing = cycle.get("due_date"), cycle.get("closing_date")
        if not due or not closing:
            return None
        if due > closing:
            return due
        # Cadastros antigos podem manter o mês anterior no vencimento.
        # Usa o primeiro dia de vencimento posterior ao fechamento desse ciclo.
        year, number = closing.year, closing.month
        result = date(year, number, min(due.day, calendar.monthrange(year, number)[1]))
        if result <= closing:
            year, index = divmod(year * 12 + number, 12)
            result = date(year, index + 1, min(due.day, calendar.monthrange(year, index + 1)[1]))
        return result

    candidates = []
    for cycle in cycles:
        if cycle["card_id"] != card["id"]:
            continue
        due = effective_due(cycle)
        if not due or due.replace(day=1) != month:
            continue
        saved = next((r for r in monthly if r["card_id"] == card["id"]
                      and r["month"] == cycle["reference_month"]), None)
        period = next((p for p in periods if p["card_id"] == card["id"]
                       and p["previous_closing_date"] == cycle.get("previous_closing_date")
                       and p["closing_date"] == cycle.get("closing_date")), None)
        source = month_bill_transaction_source(saved, period)
        if source is not None and source.get("transactions") is not None:
            candidates.append((3, cycle["reference_month"] == month, cycle["closing_date"],
                               source, due, cycle))
    # Um ciclo já consultado também pode existir sem configuração mensal.
    period = cached_cycle_for_month(card, periods, month)
    if period is not None and period.get("transactions") is not None:
        candidates.append((1, False, period["closing_date"], period, period["due_date"], period))
    # Sem ciclo configurado, o vínculo oficial do mês ainda comprova o vencimento.
    saved = next((r for r in monthly if r["card_id"] == card["id"] and r["month"] == month), None)
    official = [b for b in (saved or {}).get("bills", [])
                if str(b.get("due_date") or "")[:7] == month.strftime("%Y-%m")]
    if official and saved.get("transactions") is not None:
        candidates.append((4, True, month, saved, date.fromisoformat(official[0]["due_date"]), {}))
    if not candidates:
        transactions = apply_installment_adjustments(card, [], month)
        if not transactions:
            return None
        due = card.get('due_date')
        due = date(month.year, month.month, min(due.day, calendar.monthrange(month.year,month.month)[1])) if due else month
        return dict(transactions=transactions, due_date=due, previous_closing_date=None, closing_date=None)
    _, _, _, source, due, cycle = max(candidates, key=lambda c: c[:3])
    return dict(transactions=apply_installment_adjustments(card, source["transactions"], due), due_date=due,
                previous_closing_date=cycle.get("previous_closing_date"),
                closing_date=cycle.get("closing_date"))


# BLOCO 2 — API v2 com cursor; todos os filtros de conta e período são preservados.
def fetch_transactions(account_id, key, start, end, account_currency, bill_id=None):
    params = {"accountId": account_id, "dateFrom": start.isoformat(), "dateTo": end.isoformat()}
    if bill_id:
        # A API v2 não aceita billId: pagina a conta e filtra o vínculo localmente.
        params = {"accountId": account_id}
    transactions = {}
    seen = set()
    for _ in range(200):
        result = call("/v2/transactions?" + urlencode(params), key)
        for transaction in result.get("results", []):
            if transaction.get("accountId") != account_id:
                raise PluggyError(
                    "O Pluggy retornou um lançamento de outra conta. Nenhum dado foi salvo."
                )
            raw_date = transaction.get("date")
            try:
                day = date.fromisoformat(raw_date[:10])
            except (ValueError, TypeError):
                raise PluggyError("O Pluggy retornou um lançamento sem data válida.") from None
            if not bill_id and not start <= day <= end:
                continue
            transaction_id = transaction.get("id")
            if not transaction_id:
                raise PluggyError("O Pluggy retornou um lançamento sem identificador.")
            converted = transaction.get("amountInAccountCurrency")
            value = converted if converted is not None else transaction.get("amount")
            try:
                amount = Decimal(str(value))
                if not amount.is_finite():
                    raise InvalidOperation
            except InvalidOperation:
                raise PluggyError("O Pluggy retornou um valor de lançamento inválido.") from None
            credit = transaction.get("creditCardMetadata") or {}
            if bill_id and credit.get("billId") != bill_id:
                continue
            # O saldo após o lançamento permite identificar o fechamento do dia.
            raw_balance = transaction.get("balance")
            try:
                balance = Decimal(str(raw_balance)) if raw_balance is not None else None
                if balance is not None and not balance.is_finite():
                    balance = None
            except InvalidOperation:
                balance = None
            transactions[transaction_id] = {
                "id": transaction_id,
                "date": day.isoformat(),
                "posted_at": raw_date,
                "balance": str(balance) if balance is not None else None,
                "api_order": len(transactions),
                "description": transaction.get("description")
                or transaction.get("descriptionRaw")
                or "Sem descrição",
                "amount": str(amount),
                "currency": (
                    account_currency
                    if converted is not None
                    else transaction.get("currencyCode") or account_currency
                ),
                "category": transaction.get("category") or "Não informada",
                "operation_type": transaction.get("operationType"),
                "type": transaction.get("type"),
                "status": transaction.get("status") or "Não informado",
                "installment": credit.get("installmentNumber"),
                "installments": credit.get("totalInstallments"),
            }
        next_page = result.get("next")
        if not next_page:
            return sorted(transactions.values(), key=lambda row: (row["date"], row["id"]))
        # Não segue hosts/caminhos enviados pela API; lê somente o cursor opaco.
        cursor = parse_qs(urlsplit(next_page).query).get("after", [None])[0]
        if not cursor or cursor in seen:
            raise PluggyError("A paginação do Pluggy não avançou. Sincronização cancelada.")
        seen.add(cursor)
        params["after"] = cursor
    raise PluggyError("A consulta excedeu o limite de páginas. Nenhum resultado parcial foi salvo.")


# BLOCO 3 — Pagamentos de fatura ficam visíveis, mas não abatem o novo ciclo.
def is_bill_payment(transaction):
    if Decimal(transaction["amount"]) >= 0:
        return False
    operation = str(transaction.get("operation_type") or transaction.get("operationType") or "").strip().upper()
    if operation == "PAGAMENTO_FATURA":
        return True
    if operation in {"ESTORNO", "CASHBACK"}:
        return False
    # Compatibilidade com conectores sem tipo estruturado e registros já salvos.
    text = (
        unicodedata.normalize("NFKD", transaction.get("description", ""))
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return bool(
        re.match(
            r"^(?:(?:inclusao|credito) (?:de )?)?"
            r"(?:pagamentos?|pgtos?|pagtos?)"
            r"(?:$| (?:das?|de) faturas?\b| faturas?\b"
            r"| (?:recebidos?|efetuados?|realizados?|confirmados?)\b"
            r"| validos normais\b"
            r"| (?:parcial|total|minimo)\b"
            r"| (?:por |em |via )?debito (?:automatico|em conta|em c c)\b)",
            text,
        )
    )


# BLOCO — Agrupa débitos e créditos da fatura por moeda sem repetir pagamentos de faturas anteriores.
def summarize(transactions):
    totals = {}
    for transaction in transactions:
        currency = transaction["currency"]
        group = totals.setdefault(
            currency,
            {
                "charges": Decimal(0),
                "credits": Decimal(0),
                "net": Decimal(0),
                "payments_for_review": Decimal(0),
            },
        )
        value = Decimal(transaction["amount"])
        if is_bill_payment(transaction):
            group["payments_for_review"] += abs(value)
            continue
        group["charges"] += max(value, Decimal(0))
        group["credits"] += max(-value, Decimal(0))
        group["net"] += value
    return [
        {"currency": currency, **{name: str(value) for name, value in group.items()}}
        for currency, group in totals.items()
    ]


# BLOCO — Busca a fatura e suas regras de ciclo para o cartão selecionado.
@blueprint.get("/api/cards/<int:card_id>/bill")
def get_bill(card_id):
    from app import connect

    if request.args.get("month"):
        return get_month_bill(card_id)
    card = get_card(card_id)
    if not card:
        return jsonify(error="Cartão não encontrado."), 404
    try:
        start, end = card_period(card)
    except ValueError as error:
        return jsonify(configured=False, message=str(error), transactions=[], totals=[])
    with connect() as conn:
        saved = conn.execute(
            """SELECT transactions,synced_at FROM card_bill_periods
            WHERE card_id=%s AND previous_closing_date=%s AND closing_date=%s""",
            (card_id, card["previous_closing_date"], end),
        ).fetchone()
    transactions = (
        [{**row, "affects_balance": not is_bill_payment(row)} for row in saved["transactions"]]
        if saved
        else []
    )
    return jsonify(
        configured=True,
        linked=bool(card.get("connection_id") and (card.get("pluggy_data") or {}).get("id")),
        start=start.isoformat(),
        end=end.isoformat(),
        transactions=transactions,
        totals=summarize(transactions),
        synced_at=saved["synced_at"].isoformat() if saved else None,
    )


# BLOCO — Atualiza a fatura do cartão respeitando o mês solicitado.
@blueprint.post("/api/cards/<int:card_id>/bill/sync")
def sync_bill(card_id):
    from app import connect

    if not request.is_json:
        return jsonify(error="Envie JSON."), 415
    if (request.get_json() or {}).get("month"):
        return sync_card_month(card_id, include_transactions=True)
    card = get_card(card_id)
    if not card:
        return jsonify(error="Cartão não encontrado."), 404
    start, end = card_period(card)
    external = card.get("pluggy_data") or {}
    if not card.get("connection_id") or not external.get("id"):
        return (
            jsonify(
                error="Este cartão não está vinculado ao Pluggy. Sincronize sua conexão primeiro."
            ),
            400,
        )
    credentials = read_config(card["connection_id"])
    if not credentials:
        return jsonify(error="Credenciais da conexão Pluggy não encontradas."), 400
    try:
        key = token(credentials["client_id"], credentials["client_secret"])
        transactions = fetch_transactions(
            external["id"], key, start, end, external.get("currency") or "BRL"
        )
        with connect() as conn:
            from notifications import note_transactions

            note_transactions(
                conn,
                "card",
                card_id,
                card["name"],
                transactions,
                (
                    card["due_date"].strftime("%Y-%m")
                    if card.get("due_date")
                    else end.strftime("%Y-%m")
                ),
            )
            conn.execute(
                """INSERT INTO card_bill_periods (card_id,previous_closing_date,closing_date,transactions)
                VALUES (%s,%s,%s,%s) ON CONFLICT (card_id,previous_closing_date,closing_date)
                DO UPDATE SET transactions=EXCLUDED.transactions,synced_at=NOW()""",
                (card_id, card["previous_closing_date"], end, Jsonb(transactions)),
            )
        return jsonify(synced=True, count=len(transactions))
    except PluggyError as error:
        return jsonify(error=error.message), error.status


# BLOCO 4 — Faturas oficiais por vencimento; não projeta o saldo atual no passado.
def fetch_month_bills(account_id, key, start, end):
    found = {}
    for page in range(1, 201):
        result = call(
            "/bills?" + urlencode({"accountId": account_id, "page": page, "pageSize": 100}), key
        )
        for bill in result.get("results", []):
            try:
                due = date.fromisoformat(str(bill.get("dueDate", ""))[:10])
            except ValueError:
                raise PluggyError("O Pluggy retornou uma fatura sem vencimento válido.") from None
            if bill.get("accountId") and bill["accountId"] != account_id:
                raise PluggyError("O Pluggy retornou uma fatura de outro cartão.")
            if not start <= due <= end:
                continue
            try:
                amount = Decimal(str(bill.get("totalAmount")))
                if not amount.is_finite() or not bill.get("id"):
                    raise InvalidOperation
            except InvalidOperation:
                raise PluggyError(
                    "O Pluggy retornou uma fatura sem identificação ou valor válido."
                ) from None
            found[bill["id"]] = {
                "id": bill["id"],
                "due_date": due.isoformat(),
                "closing_date": str(bill.get("billClosingDate") or "")[:10] or None,
                "amount": str(amount),
                "currency": bill.get("totalAmountCurrencyCode") or "BRL",
                "minimum_payment": bill.get("minimumPaymentAmount"),
            }
        if page >= int(result.get("totalPages") or 1):
            return sorted(found.values(), key=lambda b: (b["due_date"], b["id"]))
    raise PluggyError("A consulta de faturas excedeu o limite de páginas.")


# BLOCO — Atualiza faturas e, quando solicitado, seus lançamentos, preservando o ciclo mensal.
@blueprint.post("/api/cards/<int:card_id>/month")
def sync_card_month(card_id, include_transactions=False):
    from app import connect
    from bank_statements import month_period

    if not request.is_json:
        return jsonify(error="Envie JSON."), 415
    start, end = month_period((request.get_json() or {}).get("month"))
    card = get_card(card_id)
    if not card:
        return jsonify(error="Cartão não encontrado."), 404
    external = card.get("pluggy_data") or {}
    if not card.get("connection_id") or not external.get("id"):
        return jsonify(error="Cartão sem vínculo com o Pluggy.", linked=False), 400
    credentials = read_config(card["connection_id"])
    if not credentials:
        return jsonify(error="Credenciais Pluggy não encontradas."), 400
    try:
        key = token(credentials["client_id"], credentials["client_secret"])
        bills = fetch_month_bills(external["id"], key, start, end)
        transactions = None
        if include_transactions:
            with connect() as conn:
                cycle = conn.execute(
                    "SELECT * FROM card_reference_cycles WHERE card_id=%s AND reference_month=%s",
                    (card_id, start),
                ).fetchone()
                if not cycle:
                    periods = conn.execute("SELECT * FROM card_bill_periods WHERE card_id=%s", (card_id,)).fetchall()
                    cycle = cached_cycle_for_month(card, periods, start)
            collected = {}
            if cycle and cycle.get("previous_closing_date") and cycle.get("closing_date"):
                cycle_start, cycle_end = card_period(cycle)
                for row in fetch_transactions(
                    external["id"], key, cycle_start, cycle_end, external.get("currency") or "BRL"
                ):
                    collected[row["id"]] = row
            else:
                for bill in bills:
                    for row in fetch_transactions(
                        external["id"],
                        key,
                        start,
                        end,
                        external.get("currency") or "BRL",
                        bill_id=bill["id"],
                    ):
                        collected[row["id"]] = row
            transactions = sorted(collected.values(), key=lambda r: (r["date"], r["id"]))
        with connect() as conn:
            if transactions is not None:
                from notifications import note_transactions

                note_transactions(
                    conn, "card", card_id, card["name"], transactions, start.strftime("%Y-%m")
                )
            conn.execute(
                """INSERT INTO card_month_bills (card_id,month,bills) VALUES (%s,%s,%s)
                ON CONFLICT (card_id,month) DO UPDATE SET bills=EXCLUDED.bills,synced_at=NOW()""",
                (card_id, start, Jsonb(bills)),
            )
            if transactions is not None:
                conn.execute(
                    "UPDATE card_month_bills SET transactions=%s WHERE card_id=%s AND month=%s",
                    (Jsonb(transactions), card_id, start),
                )
        return jsonify(month=start.strftime("%Y-%m"), bills=bills, count=len(transactions or []))
    except PluggyError as error:
        return jsonify(error=error.message), error.status


# Consulta local por mês de vencimento; períodos diferentes nunca compartilham lançamentos.
def get_month_bill(card_id):
    from app import connect
    from bank_statements import month_period

    start, end = month_period(request.args.get("month"))
    card = get_card(card_id)
    if not card:
        return jsonify(error="Cartão não encontrado."), 404
    with connect() as conn:
        saved = conn.execute(
            "SELECT * FROM card_month_bills WHERE card_id=%s AND month=%s", (card_id, start)
        ).fetchone()
        cycle = conn.execute(
            "SELECT * FROM card_reference_cycles WHERE card_id=%s AND reference_month=%s",
            (card_id, start),
        ).fetchone()
        if not cycle:
            periods = conn.execute("SELECT * FROM card_bill_periods WHERE card_id=%s", (card_id,)).fetchall()
            cycle = cached_cycle_for_month(card, periods, start)
    transaction_source = month_bill_transaction_source(saved, cycle)
    saved_transactions = (transaction_source or {}).get("transactions")
    adjustment_due = (cycle or {}).get('due_date')
    if adjustment_due and (cycle or {}).get('closing_date') and adjustment_due <= cycle['closing_date']:
        closing = cycle['closing_date']
        import calendar
        adjustment_due = date(closing.year, closing.month, min(adjustment_due.day, calendar.monthrange(closing.year,closing.month)[1]))
        if adjustment_due <= closing:
            year, index = divmod(adjustment_due.year * 12 + adjustment_due.month, 12)
            adjustment_due = date(year, index + 1, min(adjustment_due.day, calendar.monthrange(year,index+1)[1]))
    if adjustment_due is None:
        official_due = next((b.get('due_date') for b in (saved or {}).get('bills', []) if b.get('due_date')), None)
        adjustment_due = date.fromisoformat(official_due) if official_due else start
    saved_transactions = apply_installment_adjustments(card, saved_transactions or [], adjustment_due)
    if cycle:
        cycle = {**cycle, 'due_date': adjustment_due}
    transactions = [
        {**r, "affects_balance": not is_bill_payment(r)}
        for r in (saved_transactions or [])
    ]
    return jsonify(
        configured=True,
        linked=bool(card.get("connection_id") and (card.get("pluggy_data") or {}).get("id")),
        monthly=True,
        start=start.isoformat(),
        end=end.isoformat(),
        cycle=(
            {
                k: v.isoformat() if v else None
                for k, v in cycle.items()
                if k in {"previous_closing_date", "closing_date", "due_date"}
            }
            if cycle
            else None
        ),
        bills=(saved or {}).get("bills", []),
        transactions=transactions,
        totals=summarize(transactions),
        synced_at=(
            transaction_source["synced_at"].isoformat()
            if transaction_source and transaction_source.get("transactions") is not None
            else None
        ),
    )
