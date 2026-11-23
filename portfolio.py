"""Registra a posição diária observada no painel, com a mesma base do resumo."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


# BLOCO — Soma posições monetárias compatíveis para registrar o patrimônio observado.
def position_total(records):
    total = Decimal(0)
    for record in records:
        if record["kind"] != "investments":
            continue
        crypto, pluggy = record.get("crypto_data"), record.get("pluggy_data")
        if crypto:
            value = (
                crypto.get("current_value") if crypto.get("valuation_currency") == "BRL" else None
            )
        elif pluggy:
            value = pluggy.get("balance") if pluggy.get("currency") == "BRL" else None
        else:
            value = record["amount"]
        if value is None:
            continue
        try:
            amount = Decimal(str(value))
            if amount.is_finite():
                total += amount
        except InvalidOperation:
            continue
    return total


# BLOCO — Registra uma observação da posição e evita transformar compras em saldo acumulado.
def observe(conn, records):
    today = datetime.now(ZoneInfo("America/Manaus")).date()
    total = position_total(records)
    conn.execute(
        """INSERT INTO portfolio_history (day,amount) VALUES (%s,%s)
        ON CONFLICT (day) DO UPDATE SET amount=EXCLUDED.amount,observed_at=NOW()""",
        (today, total),
    )
    return conn.execute("SELECT day AS date,amount FROM portfolio_history ORDER BY day").fetchall()
