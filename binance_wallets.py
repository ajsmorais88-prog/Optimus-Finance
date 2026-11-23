"""Posições consolidadas da Binance, sem somar novamente a carteira Spot."""

from decimal import Decimal


def wallet_positions(wallets):
    from crypto import numeric

    if not isinstance(wallets, list):
        raise ValueError("A Binance não retornou as carteiras.")
    positions = {}
    names = set()
    for wallet in wallets:
        name = wallet["walletName"]
        if not isinstance(name, str) or not name or name in names:
            raise ValueError("Carteira inválida ou repetida.")
        names.add(name)
        total = numeric(wallet["balance"])
        details = wallet.get("assetBalances")
        # A avaliação líquida da carteira prevalece sobre saldos brutos (margem/futuros).
        detailed_total = (
            sum((numeric(row["btcValuation"]) for row in details), Decimal(0))
            if isinstance(details, list) else None
        )
        if detailed_total != total:
            if total == 0:
                continue
            asset = "wallet:" + name
            positions[asset] = {
                "asset": asset, "display_name": name + " · total da carteira",
                "quantity": str(total), "quantity_asset": "BTC equivalente",
                "valuation_btc": str(total), "wallets": [name],
                "wallet_aggregate": True, "wallet_scope": "consolidated",
            }
            continue
        for row in details:
            asset = row["asset"]
            quantity = sum((numeric(row.get(field, "0")) for field in
                            ("free", "locked", "freeze", "withdrawing")), Decimal(0))
            value = numeric(row["btcValuation"])
            if quantity == 0 and value == 0:
                continue
            position = positions.setdefault(asset, {
                "asset": asset, "quantity": "0", "valuation_btc": "0",
                "wallets": [], "wallet_scope": "consolidated",
            })
            position["quantity"] = str(numeric(position["quantity"]) + quantity)
            position["valuation_btc"] = str(numeric(position["valuation_btc"]) + value)
            if name not in position["wallets"]:
                position["wallets"].append(name)
    return list(positions.values())
