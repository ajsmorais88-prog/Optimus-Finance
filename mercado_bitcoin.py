"""Consulta de contas, saldos e cotações do Mercado Bitcoin. Sem ordens ou saques."""

import time
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import quote, urlencode

BASE = "https://api.mercadobitcoin.net/api/v4"


def positions(key, secret):
    from crypto import fetch, numeric

    token = fetch(BASE + "/oauth2/token", {"Content-Type": "application/x-www-form-urlencoded"},
                  urlencode({"grant_type": "client_credentials", "scope": "global",
                             "client_id": key, "client_secret": secret}).encode())
    access = token.get("access_token") if isinstance(token, dict) else None
    if not isinstance(access, str) or not access or "\r" in access or "\n" in access:
        raise ValueError("O Mercado Bitcoin não retornou um token válido.")
    headers = {"Authorization": "Bearer " + access}
    accounts = fetch(BASE + "/accounts", headers)
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("O Mercado Bitcoin não retornou as contas.")
    balances, seen_accounts = {}, set()
    last_query = None
    for account in accounts:
        account_id = account["id"]
        if not isinstance(account_id, str) or not account_id or len(account_id) > 256 or account_id in seen_accounts:
            raise ValueError("Conta Mercado Bitcoin inválida ou repetida.")
        seen_accounts.add(account_id)
        if last_query is not None:
            time.sleep(max(0, .35 - (time.monotonic() - last_query)))
        last_query = time.monotonic()
        rows = fetch(BASE + "/accounts/" + quote(account_id, safe="") + "/balances", headers)
        if not isinstance(rows, list):
            raise ValueError("O Mercado Bitcoin não retornou os saldos.")
        seen_assets = set()
        for row in rows:
            asset = row["symbol"]
            if not isinstance(asset, str) or not asset or len(asset) > 120 or asset in seen_assets:
                raise ValueError("Ativo Mercado Bitcoin inválido ou repetido.")
            seen_assets.add(asset)
            quantity, available, locked = numeric(row["total"]), numeric(row["available"]), numeric(row["on_hold"])
            if quantity < 0 or available < 0 or locked < 0 or quantity != available + locked:
                raise ValueError("O Mercado Bitcoin retornou um saldo inconsistente.")
            if quantity == 0:
                continue
            position = balances.setdefault(asset, {"asset": asset, "quantity": "0", "available": "0",
                "locked": "0", "provider": "mercadobitcoin", "history_status": "não importado"})
            for field, value in (("quantity", quantity), ("available", available), ("locked", locked)):
                position[field] = str(numeric(position[field]) + value)
    assets = [asset for asset in balances if asset != "BRL"]
    prices = {}
    if assets:
        metadata = fetch(BASE + "/symbols")
        symbols = metadata.get("symbol") if isinstance(metadata, dict) else None
        if not isinstance(symbols, list):
            raise ValueError("O Mercado Bitcoin não retornou os pares de negociação.")
        requested = sorted({asset + "-BRL" for asset in assets} & set(symbols))
        for offset in range(0, len(requested), 50):
            if offset:
                time.sleep(1.05)
            batch = requested[offset:offset + 50]
            tickers = fetch(BASE + "/tickers?" + urlencode({"symbols": ",".join(batch)}))
            if not isinstance(tickers, list):
                raise ValueError("O Mercado Bitcoin não retornou as cotações.")
            for ticker in tickers:
                pair = ticker["pair"]
                if pair not in batch or pair in prices:
                    raise ValueError("O Mercado Bitcoin retornou uma cotação inesperada.")
                price = numeric(ticker["last"])
                if price <= 0:
                    raise ValueError("O Mercado Bitcoin retornou uma cotação inválida.")
                prices[pair] = price
            if any(pair not in prices for pair in batch):
                raise ValueError("A consulta de cotações do Mercado Bitcoin ficou incompleta.")
    now = datetime.now(timezone.utc).isoformat()
    for asset, position in balances.items():
        price = Decimal(1) if asset == "BRL" else prices.get(asset + "-BRL")
        position.update(unit_price=str(price) if price is not None else None,
                        current_value=str(price * numeric(position["quantity"])) if price is not None else None,
                        valuation_currency="BRL", quoted_at=now,
                        valuation_status="cotado" if price is not None else "sem cotação BRL")
    return list(balances.values())
