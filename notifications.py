"""Alertas individuais do sino; não envia e-mails nem solicita acesso externo."""

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_FLOOR
from zoneinfo import ZoneInfo
from flask import Blueprint, jsonify, request
from monthly_summary import build_summary

blueprint = Blueprint("notifications", __name__)


def today_local():
    return datetime.now(ZoneInfo("America/Manaus")).date()


def brl(value):
    text = f"{Decimal(str(value)):,.2f}"
    return "R$ " + text.replace(",", "_").replace(".", ",").replace("_", ".")


def allocations(settings):
    cents = int(Decimal(str(settings["monthly_income"])) * 100)
    exact = [
        Decimal(cents) * Decimal(str(settings[field])) / 100
        for field in ("fixed_percent", "credit_percent", "investment_percent")
    ]
    values = [int(v.to_integral_value(rounding=ROUND_FLOOR)) for v in exact]
    order = sorted(range(3), key=lambda i: exact[i] - values[i], reverse=True)
    for i in range(cents - sum(values)):
        values[order[i % 3]] += 1
    return [Decimal(v) / 100 for v in values]


# BLOCO — Calcula alertas de vencimento, saldo negativo e comprometimento do orçamento.
def dynamic_alerts(records, settings, payments, official, bills, today):
    alerts = []
    period = today.strftime("%Y-%m")
    start = today.replace(day=1)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    paid_ids = {p["expense_id"] for p in payments}

    def add(key, title, message, route, level, record_id=None, target_period=None):
        alerts.append(
            dict(
                key=key,
                title=title,
                message=message,
                route=route,
                level=level,
                record_id=record_id,
                period=target_period or period,
            )
        )

    costs = [r for r in records if r["kind"] == "expenses"]
    for cost in costs:
        due = cost.get("due_date")
        if not due or cost.get("status") == "Pago" or cost["id"] in paid_ids:
            continue
        remaining = (due - today).days
        if remaining < 0:
            add(
                f"overdue:{cost['id']}:{due}",
                "Custo fixo vencido",
                f"{cost['name']} venceu em {due.strftime('%d/%m/%Y')}: {brl(cost['amount'] or 0)}.",
                "fixed_costs",
                "danger",
                cost["id"],
                due.strftime("%Y-%m"),
            )
        elif remaining <= 2:
            when = "hoje" if remaining == 0 else "amanhã" if remaining == 1 else "em 2 dias"
            add(
                f"due:{cost['id']}:{due}",
                "Custo fixo próximo do vencimento",
                f"{cost['name']} vence {when}, em {due.strftime('%d/%m/%Y')}: {brl(cost['amount'] or 0)}.",
                "fixed_costs",
                "warning",
                cost["id"],
                due.strftime("%Y-%m"),
            )
    for account in records:
        if (
            account["kind"] == "accounts"
            and account.get("amount") is not None
            and Decimal(str(account["amount"])) < 0
        ):
            currency = (account.get("pluggy_data") or {}).get("currency") or "BRL"
            value = (
                brl(account["amount"])
                if currency == "BRL"
                else str(account["amount"]) + " " + currency
            )
            add(
                f"negative:{account['id']}:{today}",
                "Saldo bancário negativo",
                f"{account['name']}: {value} na última atualização.",
                "bank_account",
                "danger",
                account["id"],
            )
    payment_values = {p["expense_id"]: Decimal(str(p["paid_amount"])) for p in payments}
    fixed = sum(
        (
            payment_values.get(c["id"], Decimal(str(c["amount"] or 0)))
            for c in costs
            if c.get("due_date") and start <= c["due_date"] < next_month
        ),
        Decimal(0),
    )
    summary = build_summary(
        records, payments, [], bills, [], start, next_month - timedelta(days=1), official
    )
    limits = allocations(settings)
    for kind, label, spent, limit, route in [
        ("fixed", "Custos fixos", fixed, limits[0], "fixed_costs"),
        ("cards", "Cartão de crédito", Decimal(summary["cards"]), limits[1], "card_bill"),
    ]:
        if spent <= 0:
            continue
        if limit <= 0 or spent >= limit:
            add(
                f"budget:{kind}:{period}:exceeded",
                label + " acima do orçamento",
                f"{label}: {brl(spent)} para {brl(limit)} planejados na distribuição da renda mensal.",
                "overview",
                "danger",
            )
        elif spent >= limit * Decimal(".9"):
            add(
                f"budget:{kind}:{period}:near",
                label + " próximo do orçamento",
                f"{label}: {brl(spent)} de {brl(limit)} planejados ({spent/limit*100:.0f}%).",
                "overview",
                "warning",
            )
    return alerts


# IDs são comparados entre sincronizações; a primeira coleta forma a base histórica.
def note_transactions(conn, source, record_id, name, transactions, period, silent=False, push=True):
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
        (
            conn.info.dbname
            + ":"
            + conn.execute("SELECT current_schema() AS name").fetchone()["name"]
            + ":"
            + source
            + ":"
            + str(record_id),
        ),
    )
    first = (
        conn.execute(
            "INSERT INTO notification_sources(source,record_id) VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING record_id",
            (source, record_id),
        ).fetchone()
        is not None
    )
    known = {
        r["transaction_id"]
        for r in conn.execute(
            "SELECT transaction_id FROM notification_transactions WHERE source=%s AND record_id=%s",
            (source, record_id),
        ).fetchall()
    }
    for transaction in transactions:
        transaction_id = str(transaction["id"])
        if transaction_id in known:
            continue
        known.add(transaction_id)
        fresh = conn.execute(
            "INSERT INTO notification_transactions(source,record_id,transaction_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING RETURNING transaction_id",
            (source, record_id, str(transaction["id"])),
        ).fetchone()
        if not fresh or first or silent:
            continue
        route = "bank_account" if source == "bank" else "card_bill"
        title = (
            "Novo lançamento no extrato bancário"
            if source == "bank"
            else "Novo lançamento na fatura do cartão"
        )
        money = (
            brl(transaction["amount"])
            if transaction.get("currency") == "BRL"
            else str(transaction["amount"]) + " " + str(transaction.get("currency", ""))
        )
        message = f"{name}: {transaction.get('description','Lançamento')} · {money} · {transaction.get('date','')}."
        key = f"{source}:{record_id}:{transaction['id']}"
        conn.execute(
            "INSERT INTO notification_events(event_key,title,message,route,record_id,period) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (
                key,
                title,
                message,
                route,
                record_id,
                transaction.get("_notification_period", period),
            ),
        )
        if push:
            from push_notifications import record_transaction_push
            record_transaction_push(conn, source, record_id, transaction_id, transaction.get("_notification_period", period))


# BLOCO — Combina alertas atuais e eventos novos antes de montar o feed individual.
def collect(conn, today):
    records = conn.execute("SELECT * FROM records").fetchall()
    names = {r["id"]: r["name"] for r in records}
    settings = conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
    payments = conn.execute("SELECT * FROM expense_payments").fetchall()
    bills = conn.execute("SELECT * FROM card_bill_periods").fetchall()
    official = conn.execute("SELECT * FROM card_month_bills").fetchall()
    statements = conn.execute("SELECT * FROM bank_statement_periods").fetchall()
    # União dos caches evita notificar duas vezes a mesma transação em ciclos diferentes.
    grouped = {}
    for source, rows, field in [
        ("bank", statements, "account_id"),
        ("card", bills, "card_id"),
        ("card", official, "card_id"),
    ]:
        for row in rows:
            if row.get("transactions") is None:
                continue
            key = (source, row[field])
            group = grouped.setdefault(key, {})
            for t in row["transactions"]:
                group[str(t["id"])] = {
                    **t,
                    "_notification_period": (
                        row["period_start"].strftime("%Y-%m")
                        if source == "bank"
                        else (
                            row["month"].strftime("%Y-%m")
                            if row.get("month")
                            else next(
                                (
                                    r["due_date"].strftime("%Y-%m")
                                    for r in records
                                    if r["id"] == row[field] and r.get("due_date")
                                ),
                                today.strftime("%Y-%m"),
                            )
                        )
                    ),
                }
    for (source, record_id), items in grouped.items():
        note_transactions(
            conn,
            source,
            record_id,
            names.get(record_id, "Conta"),
            list(items.values()),
            today.strftime("%Y-%m"),
            push=False,
        )
    alerts = dynamic_alerts(records, settings, payments, official, bills, today)
    events = conn.execute(
        "SELECT * FROM notification_events WHERE created_at>NOW()-INTERVAL '90 days' ORDER BY created_at DESC LIMIT 200"
    ).fetchall()
    alerts.extend(
        dict(
            key="tx:" + e["event_key"],
            title=e["title"],
            message=e["message"],
            route=e["route"],
            record_id=e["record_id"],
            period=e["period"],
            level="info",
        )
        for e in events
    )
    reads = {r["key"] for r in conn.execute("SELECT key FROM notification_reads").fetchall()}
    for alert in alerts:
        alert["read"] = alert["key"] in reads
    priority = {"danger": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (a["read"], priority[a["level"]]))
    return alerts


# BLOCO — Entrega as notificações e o estado de leitura do usuário atual.
@blueprint.get("/api/notifications")
def notifications():
    from app import connect

    with connect() as conn:
        alerts = collect(conn, today_local())
    return jsonify(notifications=alerts, unread=sum(not a["read"] for a in alerts))


# BLOCO — Marca somente os avisos pertencentes ao painel autenticado.
@blueprint.put("/api/notifications/read")
def read_notifications():
    from app import connect

    payload = request.get_json() or {}
    keys = payload.get("keys", [])
    if (
        not isinstance(keys, list)
        or len(keys) > 1000
        or any(not isinstance(key, str) or len(key) > 500 for key in keys)
    ):
        raise ValueError("Notificações inválidas.")
    with connect() as conn:
        for key in keys:
            conn.execute(
                "INSERT INTO notification_reads(key) VALUES(%s) ON CONFLICT(key) DO UPDATE SET read_at=NOW()",
                (key,),
            )
        if payload.get("all") is True:
            conn.execute(
                "INSERT INTO notification_reads(key) SELECT 'tx:'||event_key FROM notification_events ON CONFLICT(key) DO UPDATE SET read_at=NOW()"
            )
    return jsonify(updated=True)
