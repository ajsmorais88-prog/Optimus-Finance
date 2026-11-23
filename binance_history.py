"""Cache incremental por chave/par, sem guardar a chave da API."""

import hashlib
from psycopg.types.json import Jsonb


class TradeHistoryStore:
    def __init__(self, api_key):
        self.fingerprint = hashlib.sha256(api_key.encode()).hexdigest()

    def load(self):
        from app import connect

        with connect() as conn:
            rows = conn.execute(
                "SELECT symbol,history FROM binance_trade_history WHERE key_fingerprint=%s",
                (self.fingerprint,),
            ).fetchall()
        return {row["symbol"]: row["history"] for row in rows}

    def save(self, symbol, history):
        from app import connect

        with connect() as conn:
            conn.execute(
                """INSERT INTO binance_trade_history (key_fingerprint,symbol,history)
                VALUES (%s,%s,%s) ON CONFLICT (key_fingerprint,symbol)
                DO UPDATE SET history=EXCLUDED.history""",
                (self.fingerprint, symbol, Jsonb(history)),
            )
