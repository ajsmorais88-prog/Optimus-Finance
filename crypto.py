"""Consultas de saldo em exchanges. Não implementa negociação ou saques."""

import base64
import hashlib
import hmac
import json
import threading
import time
from decimal import Decimal, InvalidOperation
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, request
from psycopg.types.json import Jsonb
from cryptography.fernet import InvalidToken
from pluggy_config import cipher

blueprint = Blueprint("crypto", __name__)
EXCHANGES = {"binance", "bybit", "kraken", "mercadobitcoin"}
_nonce_lock = threading.Lock()
_nonce = 0


# BLOCO 1 — Proteção da API local e respostas sem cache ou segredos.
@blueprint.before_request
def check_origin():
    origin = request.headers.get("Origin")
    if origin and origin != request.host_url.rstrip("/"):
        return jsonify(error="Origem não permitida."), 403


# BLOCO — Mantém as respostas privadas fora dos caches de navegador e intermediários.
@blueprint.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


# BLOCO — Lista as conexões da exchange sem retornar as credenciais criptografadas.
@blueprint.get("/api/crypto/connections")
def connections():
    from app import connect

    with connect() as conn:
        rows = conn.execute("""SELECT id,exchange,label,balances,last_synced_at,last_error
            FROM crypto_connections ORDER BY id""").fetchall()
    for row in rows:
        row["last_synced_at"] = row["last_synced_at"].isoformat() if row["last_synced_at"] else None
    return jsonify(connections=rows)


# BLOCO — Valida a exchange e grava as chaves criptografadas no schema privado.
@blueprint.post("/api/crypto/connections")
def save():
    from app import connect

    if not request.is_json:
        return jsonify(error="Envie os campos em JSON."), 415
    values = request.get_json() or {}
    exchange = values.get("exchange")
    key, secret = values.get("api_key"), values.get("api_secret")
    label = values.get("label") or {"mercadobitcoin": "Mercado Bitcoin"}.get(exchange, str(exchange).title())
    if exchange not in EXCHANGES or any(
        not isinstance(v, str) or not v.strip() or len(v) > 4096 for v in (key, secret)
    ):
        return (
            jsonify(error="Selecione a exchange e informe chave API e chave secreta válidas."),
            400,
        )
    if not isinstance(label, str) or len(label) > 120:
        return jsonify(error="O nome deve ter até 120 caracteres."), 400
    encrypted = cipher().encrypt(
        json.dumps({"key": key.strip(), "secret": secret.strip()}).encode()
    )
    fingerprint = hashlib.sha256(key.strip().encode()).hexdigest()
    with connect() as conn:
        row = conn.execute(
            """INSERT INTO crypto_connections
            (exchange,label,key_fingerprint,credentials) VALUES (%s,%s,%s,%s)
            ON CONFLICT (exchange,key_fingerprint) DO UPDATE
            SET credentials=EXCLUDED.credentials,label=EXCLUDED.label RETURNING id""",
            (exchange, label.strip(), fingerprint, encrypted),
        ).fetchone()
    return jsonify(saved=True, connection_id=row["id"])


class ExchangeHTTPError(ValueError):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


# BLOCO 2 — Cliente HTTPS com destinos fixos, sem registrar URLs assinadas.
def fetch(url, headers=None, data=None):
    try:
        with urlopen(Request(url, headers=headers or {}, data=data), timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        message = {
            401: "Chave ou assinatura recusada.",
            403: "Acesso recusado. Verifique permissões, restrições de IP e região.",
            429: "Limite de consultas atingido. Aguarde.",
        }.get(
            error.code,
            "Consulta recusada pela exchange. Verifique chaves, permissões e relógio do computador.",
        )
        raise ExchangeHTTPError(message, error.code) from None
    except (URLError, TimeoutError, json.JSONDecodeError):
        raise ValueError("A exchange não respondeu corretamente. Tente novamente.") from None


# BLOCO — Aceita somente valores numéricos finitos recebidos das integrações.
def numeric(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise InvalidOperation
        return number
    except InvalidOperation:
        raise ValueError("A exchange retornou um saldo inválido.") from None


# BLOCO 3 — Cada exchange possui autenticação própria, sempre para leitura.
def get_balances(exchange, key, secret):
    if exchange == "mercadobitcoin":
        from mercado_bitcoin import positions

        return positions(key, secret)
    if exchange == "binance":
        timestamp = fetch("https://api.binance.com/api/v3/time")["serverTime"]
        query = urlencode({"timestamp": timestamp, "recvWindow": 5000,
                           "quoteAsset": "BTC", "needBalanceDetail": "true"})
        signature = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        result = fetch(
            "https://api.binance.com/sapi/v1/asset/wallet/balance?" + query + "&signature=" + signature,
            {"X-MBX-APIKEY": key},
        )
        from binance_wallets import wallet_positions

        return wallet_positions(result)

    if exchange == "bybit":
        timestamp = str(int(time.time() * 1000))
        query = "accountType=UNIFIED"
        signature = hmac.new(
            secret.encode(), (timestamp + key + "5000" + query).encode(), hashlib.sha256
        ).hexdigest()
        result = fetch(
            "https://api.bybit.com/v5/account/wallet-balance?" + query,
            {
                "X-BAPI-API-KEY": key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": "5000",
                "X-BAPI-SIGN": signature,
            },
        )
        if result.get("retCode") != 0:
            raise ValueError(
                "A Bybit recusou a consulta. Confira chave HMAC, permissões, IP e relógio do computador."
            )
        return [
            {"asset": r["coin"], "quantity": str(numeric(r["walletBalance"]))}
            for account in result["result"]["list"]
            for r in account.get("coin", [])
            if numeric(r["walletBalance"]) != 0
        ]

    if exchange == "kraken":
        global _nonce
        # Serializa as consultas para a ordem de chegada dos nonces ser preservada.
        with _nonce_lock:
            _nonce = max(_nonce + 1, time.time_ns() // 1000)
            nonce = str(_nonce)
            body = urlencode({"nonce": nonce})
            path = "/0/private/Balance"
            try:
                decoded = base64.b64decode(secret, validate=True)
            except ValueError:
                raise ValueError("A chave secreta Kraken deve estar em Base64.") from None
            digest = hashlib.sha256((nonce + body).encode()).digest()
            signature = base64.b64encode(
                hmac.new(decoded, path.encode() + digest, hashlib.sha512).digest()
            ).decode()
            result = fetch(
                "https://api.kraken.com" + path,
                {
                    "API-Key": key,
                    "API-Sign": signature,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body.encode(),
            )
        if result.get("error"):
            raise ValueError(
                "A Kraken recusou a consulta. Verifique chave, permissão Query Funds, nonce e 2FA da API."
            )
        return [
            {"asset": asset, "quantity": str(numeric(value))}
            for asset, value in result["result"].items()
            if numeric(value) != 0
        ]
    raise ValueError("Exchange não suportada.")


# BLOCO 4 — Persiste a última posição; quantidades não são tratadas como reais.
def save_binance_positions(conn, connection_id, balances, reference_date=None):
    return save_exchange_positions(conn, connection_id, balances, "binance", reference_date)


def save_exchange_positions(conn, connection_id, balances, exchange, reference_date=None):
    """Um registro por conexão/ativo. Mantém precisão decimal sem inventar cotação."""
    reference_date = reference_date or date.today()
    # Uma resposta completa sem um ativo antes presente significa saldo zero.
    conn.execute(
        """UPDATE records SET crypto_data=jsonb_set(jsonb_set(crypto_data,'{quantity}','"0"'),'{current_value}','"0"'),
        amount=NULL,status='Sem saldo',due_date=%s WHERE crypto_connection_id=%s""",
        (reference_date, connection_id),
    )
    for balance in balances:
        asset = balance["asset"]
        quantity = str(numeric(balance["quantity"]))
        key = exchange + ":" + str(connection_id) + ":" + asset
        institution = {"binance": "Binance", "mercadobitcoin": "Mercado Bitcoin"}[exchange]
        conn.execute(
            """INSERT INTO records
            (kind,name,institution,detail,amount,due_date,status,external_key,crypto_connection_id,crypto_data)
            VALUES ('investments',%s,%s,%s,NULL,%s,'Ativo',%s,%s,%s)
            ON CONFLICT (external_key) DO UPDATE SET
            name=EXCLUDED.name,detail=EXCLUDED.detail,crypto_data=EXCLUDED.crypto_data,
            amount=NULL,due_date=EXCLUDED.due_date,status='Ativo' """,
            (
                balance.get("display_name", asset),
                institution,
                "Carteiras Binance" if exchange == "binance" else "Saldos Mercado Bitcoin",
                reference_date,
                key,
                connection_id,
                Jsonb({**balance, "asset": asset, "quantity": quantity}),
            ),
        )


# BLOCO — Consulta saldos, enriquece posições e salva o resultado sem expor as credenciais.
@blueprint.post("/api/crypto/connections/<int:connection_id>/sync")
def sync(connection_id):
    from app import connect

    if not request.is_json:
        return jsonify(error="Envie JSON."), 415
    with connect() as conn:
        row = conn.execute(
            "SELECT exchange,credentials FROM crypto_connections WHERE id=%s", (connection_id,)
        ).fetchone()
    if not row:
        return jsonify(error="Conexão não encontrada."), 404
    try:
        values = json.loads(cipher().decrypt(bytes(row["credentials"])))
        balances = get_balances(row["exchange"], values["key"], values["secret"])
        if row["exchange"] == "binance":
            from binance_details import enrich_positions
            from binance_history import TradeHistoryStore

            balances = enrich_positions(
                balances, values["key"], values["secret"], TradeHistoryStore(values["key"])
            )
            from binance_brl import convert_positions_brl

            balances = convert_positions_brl(balances)
        with connect() as conn:
            if row["exchange"] == "binance":
                save_binance_positions(conn, connection_id, balances)
            elif row["exchange"] == "mercadobitcoin":
                save_exchange_positions(conn, connection_id, balances, "mercadobitcoin")
            conn.execute(
                """UPDATE crypto_connections SET balances=%s,last_synced_at=NOW(),last_error=NULL WHERE id=%s""",
                (Jsonb(balances), connection_id),
            )
        return jsonify(balances=balances)
    except (ValueError, KeyError, TypeError, InvalidToken) as error:
        # Não expõe conteúdo de respostas, assinaturas ou credenciais nos erros.
        message = "Não foi possível consultar os saldos. Verifique as chaves, permissões de leitura, IP, região e relógio do computador."
        if row["exchange"] == "binance":
            message = "Não foi possível consultar as carteiras consolidadas da Binance. Confira a permissão de leitura da chave e as restrições de IP/região. O último saldo foi preservado."
        elif row["exchange"] == "mercadobitcoin":
            message = "Não foi possível consultar o Mercado Bitcoin. Confira o identificador e o segredo da chave, a permissão de leitura e as restrições de acesso. O último saldo foi preservado."
        with connect() as conn:
            conn.execute(
                "UPDATE crypto_connections SET last_error=%s WHERE id=%s", (message, connection_id)
            )
        return jsonify(error=message, provider_status=getattr(error, "status_code", None)), 502
