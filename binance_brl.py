"""Conversão BRL atual e histórica, preservando as moedas originais das compras."""

from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode


class HistoricalRates:
    def get(self, symbol, minute):
        from app import connect

        with connect() as conn:
            row = conn.execute(
                "SELECT price FROM binance_fx_history WHERE symbol=%s AND minute=%s",
                (symbol, minute),
            ).fetchone()
        return Decimal(row["price"]) if row else None

    def save(self, symbol, minute, price):
        from app import connect

        with connect() as conn:
            conn.execute(
                """INSERT INTO binance_fx_history (symbol,minute,price) VALUES (%s,%s,%s)
                ON CONFLICT (symbol,minute) DO NOTHING""",
                (symbol, minute, str(price)),
            )


# BLOCO — Converte custos e posições para BRL usando as referências disponíveis.
def convert_positions_brl(balances, store=None):
    from crypto import fetch, numeric

    store = store or HistoricalRates()
    symbols = {
        row["symbol"] for row in fetch("https://api.binance.com/api/v3/exchangeInfo")["symbols"]
    }
    prices = {
        row["symbol"]: numeric(row["price"])
        for row in fetch("https://api.binance.com/api/v3/ticker/price")
    }
    memo = {}

    def historical(symbol, timestamp):
        minute = int(timestamp) // 60000 * 60000
        key = (symbol, minute)
        if key in memo:
            return memo[key]
        value = store.get(symbol, minute)
        if value is None:
            try:
                candles = fetch(
                    "https://api.binance.com/api/v3/klines?"
                    + urlencode(
                        {
                            "symbol": symbol,
                            "interval": "1m",
                            "startTime": minute,
                            "endTime": minute + 59999,
                            "limit": 1,
                        }
                    )
                )
                # Nunca substitui uma data sem histórico pela cotação de outra data.
                if candles and int(candles[0][0]) == minute:
                    value = numeric(candles[0][1])  # abertura do minuto da execução
                    if value > 0:
                        store.save(symbol, minute, value)
                    else:
                        value = None
            except (ValueError, KeyError, IndexError, TypeError):
                value = None
        memo[key] = value
        return value

    def pair_rate(base, quote, timestamp=None):
        if base == quote:
            return Decimal(1)
        if base + quote in symbols:
            value = (
                historical(base + quote, timestamp)
                if timestamp is not None
                else prices.get(base + quote)
            )
            if value is not None and value > 0:
                return value
        if quote + base in symbols:
            value = (
                historical(quote + base, timestamp)
                if timestamp is not None
                else prices.get(quote + base)
            )
            if value is not None and value > 0:
                return Decimal(1) / value
        return None

    def brl_rate(asset, timestamp=None):
        direct = pair_rate(asset, "BRL", timestamp)
        if direct is not None:
            return direct
        first = pair_rate(asset, "USDT", timestamp)
        second = pair_rate("USDT", "BRL", timestamp)
        return first * second if first is not None and second is not None else None

    now = datetime.now(timezone.utc).isoformat()
    for balance in balances:
        asset = balance["asset"]
        rate = brl_rate(asset)
        current_value = rate * numeric(balance["quantity"]) if rate is not None else None
        if "valuation_btc" in balance:
            btc_rate = brl_rate("BTC")
            current_value = (
                numeric(balance["valuation_btc"]) * btc_rate if btc_rate is not None else None
            )
            quantity = numeric(balance["quantity"])
            rate = current_value / quantity if current_value is not None and quantity else None
        balance.update(
            valuation_currency="BRL",
            unit_price=str(rate) if rate is not None else None,
            current_value=str(current_value) if current_value is not None else None,
            quoted_at=now,
        )
        purchases = balance.get("purchases") or []
        total = Decimal(0)
        converted = 0
        missing = 0
        for purchase in purchases:
            currency = purchase["currency"]
            timestamp = purchase.get("time")
            fx = (
                Decimal(1)
                if currency == "BRL"
                else brl_rate(currency, timestamp) if timestamp is not None else None
            )
            if fx is None:
                missing += 1
                purchase["value_brl"] = None
                continue
            paid = numeric(
                purchase.get("quote_value")
                or numeric(purchase["price"]) * numeric(purchase["quantity"])
            )
            purchase["value_brl"] = str(paid * fx)
            total += paid * fx
            converted += 1
        balance.update(
            invested_brl=str(total) if converted else None,
            invested_brl_partial=bool(
                missing
                or balance.get("purchase_details_truncated")
                or balance.get("history_status") == "parcial"
            ),
            invested_brl_missing=missing,
            brl_conversion_method="abertura do minuto da compra",
        )
    return balances
