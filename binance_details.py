"""Enriquece posições Spot com compras executadas e preços de referência."""

import hashlib
import hmac
import time
from datetime import datetime, timezone
from decimal import Decimal
from collections import deque
from urllib.parse import urlencode


# BLOCO — Relaciona saldos Spot às compras históricas, sem tratar saldo como aporte.
def enrich_positions(balances, key, secret, history_store=None):
    from crypto import fetch, numeric

    # Metadados evitam adivinhar o ativo-base e a moeda de cada par.
    symbols = fetch("https://api.binance.com/api/v3/exchangeInfo")["symbols"]
    prices = {
        row["symbol"]: numeric(row["price"])
        for row in fetch("https://api.binance.com/api/v3/ticker/price")
    }
    server_time = fetch("https://api.binance.com/api/v3/time")["serverTime"]
    local_time = time.monotonic()
    remaining_requests = 60
    cache = history_store.load() if history_store else {}
    quoted_at = datetime.now(timezone.utc).isoformat()

    def signed(params):
        params = {
            **params,
            "timestamp": int(server_time + (time.monotonic() - local_time) * 1000),
            "recvWindow": 5000,
        }
        query = urlencode(params)
        signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return fetch(
            "https://api.binance.com/api/v3/myTrades?" + query + "&signature=" + signature,
            {"X-MBX-APIKEY": key},
        )

    def rate(base, quote):
        if base == quote:
            return Decimal(1)
        direct = prices.get(base + quote)
        if direct is not None and direct > 0:
            return direct
        reverse = prices.get(quote + base)
        return Decimal(1) / reverse if reverse is not None and reverse > 0 else None

    # Alterna ativos a cada par, em vez de esgotar o limite no primeiro ativo.
    pairs_by_asset = {}
    for balance in balances:
        pairs = [
            row
            for row in symbols
            if row["baseAsset"] == balance["asset"] and row.get("isSpotTradingAllowed", True)
        ]
        preferred = {"BRL": 0, "USDT": 1, "USDC": 2, "BTC": 3, "ETH": 4, "BNB": 5}
        pairs.sort(key=lambda row: (preferred.get(row["quoteAsset"], 6), row["symbol"]))
        pairs_by_asset[balance["asset"]] = pairs
    pending, refresh = [], []
    max_pairs = max((len(pairs) for pairs in pairs_by_asset.values()), default=0)
    for index in range(max_pairs):
        for pairs in pairs_by_asset.values():
            if index >= len(pairs):
                continue
            pair = pairs[index]
            state = cache.get(pair["symbol"])
            if not state or not state.get("complete") or state.get("error"):
                pending.append(pair)
            elif time.time() - state.get("checked_at", 0) >= 900:
                refresh.append(pair)
    queue = deque(pending + refresh)
    while queue and remaining_requests > 0:
        pair = queue.popleft()
        symbol = pair["symbol"]
        state = cache.get(
            symbol,
            {
                "cursor": 0,
                "quantity": "0",
                "total": "0",
                "weighted": "0",
                "fees": {},
                "purchases": [],
                "trade_count": 0,
                "complete": False,
            },
        )
        remaining_requests -= 1
        try:
            trades = signed({"symbol": symbol, "fromId": state["cursor"], "limit": 1000})
            if not isinstance(trades, list):
                raise ValueError("Resposta inválida do histórico.")
            # Valida a página inteira antes de somar: falhas não duplicam negócios.
            quantity, total, weighted = (
                Decimal(state["quantity"]),
                Decimal(state["total"]),
                Decimal(state["weighted"]),
            )
            fees = dict(state["fees"])
            purchases = list(state["purchases"])
            count = state["trade_count"]
            for trade in trades:
                if not trade.get("isBuyer"):
                    continue
                qty, price = numeric(trade["qty"]), numeric(trade["price"])
                if qty <= 0:
                    continue
                quantity += qty
                total += numeric(trade["quoteQty"])
                weighted += price * qty
                fee_asset = trade["commissionAsset"]
                fees[fee_asset] = str(
                    Decimal(fees.get(fee_asset, "0")) + numeric(trade["commission"])
                )
                purchases.append(
                    {
                        "symbol": symbol,
                        "trade_id": trade["id"],
                        "quantity": str(qty),
                        "price": str(price),
                        "quote_value": str(numeric(trade["quoteQty"])),
                        "currency": pair["quoteAsset"],
                        "time": trade.get("time"),
                    }
                )
                count += 1
            cursor = max(int(trade["id"]) for trade in trades) + 1 if trades else state["cursor"]
            if trades and cursor <= state["cursor"]:
                raise ValueError("O cursor do histórico não avançou.")
            state = {
                "cursor": cursor,
                "quantity": str(quantity),
                "total": str(total),
                "weighted": str(weighted),
                "fees": fees,
                "purchases": sorted(purchases, key=lambda row: row["time"] or 0, reverse=True)[
                    :500
                ],
                "trade_count": count,
                "complete": len(trades) < 1000,
                "checked_at": time.time(),
                "error": False,
            }
            cache[symbol] = state
            if history_store:
                history_store.save(symbol, state)
            if not state["complete"]:
                queue.append(pair)
        except (ValueError, KeyError, TypeError):
            # O progresso confirmado permanece disponível mesmo quando a API falha.
            state = {**state, "error": True}
            cache[symbol] = state
            if history_store:
                history_store.save(symbol, state)

    for balance in balances:
        asset = balance["asset"]
        balance.update(
            {
                "purchased_quantity": None,
                "purchase_totals": [],
                "purchase_fees": [],
                "history_status": "não consultado",
                "unit_price": None,
                "current_value": None,
                "valuation_currency": None,
                "quoted_at": quoted_at,
            }
        )
        # Prefere BRL; se necessário cruza via USDT. USDT nunca é chamado de USD.
        value = rate(asset, "BRL")
        currency = "BRL"
        if value is None:
            usdt = rate(asset, "USDT")
            conversion = rate("USDT", "BRL")
            if usdt is not None and conversion is not None:
                value = usdt * conversion
            elif usdt is not None:
                value, currency = usdt, "USDT"
        if value is not None:
            balance.update(
                unit_price=str(value),
                current_value=str(value * numeric(balance["quantity"])),
                valuation_currency=currency,
            )

        pairs = pairs_by_asset[asset]
        bought = Decimal(0)
        totals, fees, quantities, weighted_prices = {}, {}, {}, {}
        purchases = []
        completed = 0
        trade_count = 0
        for pair in pairs:
            state = cache.get(pair["symbol"])
            if not state:
                continue
            if state.get("complete") and not state.get("error"):
                completed += 1
            quantity = Decimal(state["quantity"])
            if quantity > 0:
                quote = pair["quoteAsset"]
                bought += quantity
                quantities[quote] = quantities.get(quote, Decimal(0)) + quantity
                totals[quote] = totals.get(quote, Decimal(0)) + Decimal(state["total"])
                weighted_prices[quote] = weighted_prices.get(quote, Decimal(0)) + Decimal(
                    state["weighted"]
                )
            for fee_asset, fee in state["fees"].items():
                fees[fee_asset] = fees.get(fee_asset, Decimal(0)) + Decimal(fee)
            purchases.extend(state["purchases"])
            trade_count += state["trade_count"]
        partial = completed < len(pairs)
        balance.update(
            purchased_quantity=str(bought) if pairs and (bought or not partial) else None,
            purchase_prices=[
                {
                    "currency": quote,
                    "price": str(weighted_prices[quote] / quantity),
                    "quantity": str(quantity),
                }
                for quote, quantity in quantities.items()
            ],
            purchases=sorted(purchases, key=lambda row: row["time"] or 0, reverse=True)[:500],
            purchase_details_truncated=trade_count > 500,
            history_pairs_total=len(pairs),
            history_pairs_completed=completed,
            purchase_totals=[
                {"currency": quote, "value": str(value)} for quote, value in totals.items()
            ],
            purchase_fees=[
                {"currency": quote, "value": str(value)} for quote, value in fees.items()
            ],
            history_status=(
                "parcial"
                if partial
                else "pares Spot consultados" if pairs else "sem par disponível"
            ),
        )
    return balances
