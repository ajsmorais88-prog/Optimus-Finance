"""Cliente Pluggy: credenciais efêmeras e chamadas somente pelo servidor."""

import hashlib
import json
import threading
import time
from datetime import date
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, request, g
from psycopg.types.json import Jsonb
from psycopg.errors import UniqueViolation
from pluggy_config import (
    read_config,
    write_config,
    list_connections,
    read_application,
    write_application,
    update_connection,
    delete_connection,
)

blueprint = Blueprint("pluggy", __name__)
BASE = "https://api.pluggy.ai"
_tokens = {}
_lock = threading.Lock()


# BLOCO — Recusa chamadas de escrita vindas de outra origem.
@blueprint.before_request
def protect_origin():
    origin = request.headers.get("Origin")
    if origin and origin != request.host_url.rstrip("/"):
        return jsonify(error="Origem da solicitação não permitida."), 403


# BLOCO — Informa se há configuração salva sem devolver o Client Secret.
@blueprint.get("/api/pluggy/config")
def config_status():
    saved = read_application()
    return jsonify(saved=bool(saved), client_id=saved["client_id"] if saved else "", item_id="")


# BLOCO — Lista as conexões e os produtos importados do usuário.
@blueprint.get("/api/pluggy/connections")
def connections():
    return jsonify(connections=list_connections())


# BLOCO — Valida e salva a aplicação Pluggy ou uma nova conexão por Item ID.
@blueprint.put("/api/pluggy/config")
def save_config():
    if not request.is_json:
        return jsonify(error="Envie os campos em JSON."), 415
    payload = request.get_json() or {}
    if "client_id" in payload or "client_secret" in payload:
        application = {name: payload.get(name) for name in ("client_id", "client_secret")}
        if any(
            not isinstance(value, str) or not value.strip() or len(value) > 512
            for value in application.values()
        ):
            return jsonify(error="Informe Client ID e Client Secret válidos."), 400
        write_application({name: value.strip() for name, value in application.items()})
    if not payload.get("item_id"):
        return jsonify(saved=True)
    item_id = payload["item_id"]
    if not isinstance(item_id, str) or not item_id.strip() or len(item_id) > 512:
        return jsonify(error="Informe um Item ID válido."), 400
    label = payload.get("label", "Minha conta")
    if not isinstance(label, str) or not label.strip() or len(label.strip()) > 120:
        return jsonify(error="Informe um nome para a conexão, com até 120 caracteres."), 400
    connection_id = write_config({"item_id": item_id.strip()}, label.strip())
    return jsonify(saved=True, connection_id=connection_id)


# BLOCO — As proteções globais exigem administrador, sessão válida e CSRF em produção.
@blueprint.put("/api/pluggy/connections/<int:connection_id>")
def edit_saved_connection(connection_id):
    if not request.is_json:
        return jsonify(error="Envie os campos em JSON."), 415
    payload = request.get_json()
    if not isinstance(payload, dict):
        return jsonify(error="Informe os dados da conexão."), 400
    label = payload.get("label")
    item_id = payload.get("item_id", "")
    if not isinstance(label, str) or not label.strip() or len(label.strip()) > 120:
        return jsonify(error="Informe um nome para a conexão, com até 120 caracteres."), 400
    if not isinstance(item_id, str) or len(item_id) > 512:
        return jsonify(error="Informe um Item ID válido."), 400
    try:
        saved = update_connection(connection_id, label.strip(), item_id.strip() or None)
    except UniqueViolation:
        return jsonify(error="Este Item ID já está cadastrado em outra conexão."), 409
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if not saved:
        return jsonify(error="Conexão não encontrada."), 404
    if getattr(g, "user", None):
        from auto_sync import mark_changed
        mark_changed(g.user["id"])
    return jsonify(saved=True)


@blueprint.delete("/api/pluggy/connections/<int:connection_id>")
def remove_saved_connection(connection_id):
    if not delete_connection(connection_id):
        return jsonify(error="Conexão não encontrada."), 404
    if getattr(g, "user", None):
        from auto_sync import mark_changed
        mark_changed(g.user["id"])
    return jsonify(deleted=True)


class PluggyError(Exception):
    def __init__(self, message, status=502):
        self.message = message
        self.status = status


# BLOCO 1 — Destino fixo, TLS validado e timeout; erros externos não expõem segredos.
def call(path, key=None, payload=None):
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if key:
        headers["X-API-KEY"] = key
    req = Request(
        BASE + path,
        headers=headers,
        data=json.dumps(payload).encode() if payload is not None else None,
    )
    try:
        with urlopen(req, timeout=20) as response:
            if response.status == 204:
                return {"results": [], "totalPages": 1}
            return json.load(response)
    except HTTPError as error:
        messages = {
            401: "Autenticação recusada pelo Pluggy. Verifique Client ID e Client Secret.",
            403: "A aplicação não tem permissão para acessar este Item ou produto.",
            404: "Item não encontrado no Pluggy. Confira o Item ID.",
            429: "Limite de consultas do Pluggy atingido. Aguarde antes de tentar novamente.",
        }
        raise PluggyError(
            messages.get(error.code, "O Pluggy não conseguiu concluir a consulta."),
            error.code if error.code in messages else 502,
        ) from None
    except (URLError, TimeoutError, ValueError):
        raise PluggyError(
            "Não foi possível obter uma resposta válida do Pluggy. Tente novamente."
        ) from None


# BLOCO 2 — Cache em memória por até 110 minutos; nunca persiste Client Secret.
def token(client_id, secret):
    fingerprint = hashlib.sha256(json.dumps([client_id, secret]).encode()).hexdigest()
    with _lock:
        now = time.monotonic()
        for old in list(_tokens):
            if _tokens[old][1] <= now:
                del _tokens[old]
        if fingerprint in _tokens:
            return _tokens[fingerprint][0]
        result = call("/auth", payload={"clientId": client_id, "clientSecret": secret})
        key = result.get("apiKey")
        if not key:
            raise PluggyError("O Pluggy não retornou uma chave de acesso válida.")
        if len(_tokens) >= 32:
            _tokens.pop(next(iter(_tokens)))
        _tokens[fingerprint] = (key, now + 6600)
        return key


# BLOCO 3 — Consulta o Pluggy e sincroniza produtos nos cadastros locais.
@blueprint.post("/api/pluggy/accounts")
def accounts():
    # O endpoint é administrativo no aplicativo pessoal local. Impede requisições
    # de outras origens e exige JSON (formulários externos não podem enviá-lo).
    origin = request.headers.get("Origin")
    if origin and origin != request.host_url.rstrip("/"):
        return jsonify(error="Origem da solicitação não permitida."), 403
    if not request.is_json:
        return jsonify(error="Envie os campos em JSON."), 415
    payload = request.get_json() or {}
    connection_id = payload.get("connection_id")
    if connection_id is not None and (type(connection_id) is not int or connection_id <= 0):
        return jsonify(error="Conexão inválida."), 400
    if payload.get("use_saved") is True:
        payload = read_config(connection_id) if connection_id is not None else read_config()
        payload = payload or {}
    fields = [payload.get(name) for name in ("client_id", "client_secret", "item_id")]
    if any(not isinstance(value, str) or not value.strip() or len(value) > 512 for value in fields):
        return jsonify(error="Preencha Client ID, Client Secret e Item ID válidos."), 400
    client_id, secret, item_id = [value.strip() for value in fields]
    try:
        key = token(client_id, secret)
        records = []
        page = 1
        while True:
            result = call(
                "/accounts?" + urlencode({"itemId": item_id, "page": page, "pageSize": 100}), key
            )
            for account in result.get("results", []):
                # Retorna apenas os campos exibidos, sem CPF, titular ou número da conta.
                credit = account.get("creditData") or {}
                records.append(
                    {
                        "id": account.get("id"),
                        "name": account.get("name"),
                        "type": account.get("type"),
                        "subtype": account.get("subtype"),
                        "balance": account.get("balance"),
                        "currency": account.get("currencyCode") or "BRL",
                        "credit_limit": credit.get("creditLimit"),
                        "available_limit": credit.get("availableCreditLimit"),
                        "due_date": credit.get("balanceDueDate"),
                        "brand": credit.get("brand"),
                        "status": credit.get("status"),
                    }
                )
            if page >= result.get("totalPages", 1):
                break
            if page >= 50:
                raise PluggyError(
                    "A consulta excedeu o limite de páginas. Nenhum resultado parcial foi exibido."
                )
            page += 1
        # Investimentos são posições atuais, não aportes ou transações bancárias.
        page = 1
        while True:
            result = call(
                "/investments?" + urlencode({"itemId": item_id, "page": page, "pageSize": 100}), key
            )
            for investment in result.get("results", []):
                records.append(
                    {
                        "id": investment.get("id"),
                        "type": "INVESTMENT",
                        "name": investment.get("name"),
                        "subtype": investment.get("subtype") or investment.get("type"),
                        "balance": investment.get("balance"),
                        "gross_amount": investment.get("amount"),
                        "currency": investment.get("currencyCode") or "BRL",
                        "due_date": investment.get("date"),
                        "status": investment.get("status"),
                        "institution": (investment.get("institution") or {}).get("name")
                        or investment.get("issuer"),
                    }
                )
            if page >= result.get("totalPages", 1):
                break
            if page >= 50:
                raise PluggyError(
                    "A consulta de investimentos excedeu o limite de páginas. Sincronização cancelada."
                )
            page += 1
        counts = save_accounts(records, client_id, item_id, connection_id)
        return jsonify(accounts=records, synced=counts)
    except PluggyError as error:
        if connection_id:
            from app import connect

            with connect() as conn:
                conn.execute(
                    "UPDATE pluggy_connections SET last_error=%s WHERE id=%s",
                    (error.message, connection_id),
                )
        return jsonify(error=error.message), error.status


# BLOCO 4 — Uma transação atualiza os produtos pelo ID externo, sem apagar cadastros.
def save_accounts(records, client_id, item_id, connection_id=None):
    from app import connect

    counts = {"accounts": 0, "cards": 0, "investments": 0}
    names = {"CHECKING_ACCOUNT": "Conta Corrente", "SAVINGS_ACCOUNT": "Conta Poupança"}
    with connect() as conn:
        for product in records:
            kind = {"BANK": "accounts", "CREDIT": "cards", "INVESTMENT": "investments"}.get(
                product["type"]
            )
            if not kind:
                continue
            if not product.get("id"):
                raise PluggyError(
                    "O Pluggy retornou um produto sem ID. Nenhum cadastro foi atualizado."
                )
            external_key = hashlib.sha256(
                json.dumps([client_id, item_id, product["id"]]).encode()
            ).hexdigest()
            if kind == "investments":
                external_key = "investment:" + external_key
            value = product["credit_limit"] if kind == "cards" else product.get("balance")
            amount = Decimal(str(value)) if value is not None else None
            if amount is not None and (
                not amount.is_finite() or abs(amount) > Decimal("999999999999.99")
            ):
                raise PluggyError(
                    "Um valor retornado está fora do intervalo suportado. Sincronização cancelada."
                )
            due = product.get("due_date")
            due = date.fromisoformat(due[:10]) if due else None
            name = str(product.get("name") or "Produto Pluggy")[:120]
            detail = names.get(
                product.get("subtype"), product.get("brand") or product.get("subtype") or ""
            )[:120]
            status = {
                "BLOCKED": "Bloqueado",
                "CANCELLED": "Cancelado",
                "PENDING": "Pendente",
                "TOTAL_WITHDRAWAL": "Resgatado",
            }.get(product.get("status"), "Ativo")
            institution = str(product.get("institution") or "Pluggy")[:120]
            conn.execute(
                """INSERT INTO records
                (kind,name,institution,detail,amount,due_date,status,external_key,pluggy_data,connection_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (external_key) DO UPDATE SET
                kind=EXCLUDED.kind,name=EXCLUDED.name,detail=EXCLUDED.detail,
                institution=CASE WHEN EXCLUDED.institution='Pluggy' AND records.institution<>'Pluggy'
                    THEN records.institution ELSE EXCLUDED.institution END,
                amount=EXCLUDED.amount,due_date=EXCLUDED.due_date,status=EXCLUDED.status,
                pluggy_data=EXCLUDED.pluggy_data,connection_id=COALESCE(EXCLUDED.connection_id,records.connection_id)""",
                (
                    kind,
                    name,
                    institution,
                    detail,
                    amount,
                    due,
                    status,
                    external_key,
                    Jsonb(product),
                    connection_id,
                ),
            )
            counts[kind] += 1
        if connection_id:
            conn.execute(
                "UPDATE pluggy_connections SET last_synced_at=NOW(),last_error=NULL WHERE id=%s",
                (connection_id,),
            )
    return counts


# BLOCO — Mantém as respostas privadas fora dos caches de navegador e intermediários.
@blueprint.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response
