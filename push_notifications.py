"""Web Push por dispositivo e webhooks Pluggy autenticados, sem dados financeiros na tela bloqueada."""

import base64
import hashlib
import hmac
import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from flask import Blueprint, current_app, g, jsonify, request
from pluggy_config import cipher, read_config
from pluggy import call, token, PluggyError

blueprint = Blueprint("push", __name__)


# BLOCO 1 — Chave VAPID estável derivada do segredo do servidor; só a pública sai pela API.
def vapid_keys():
    order = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)
    seed = hmac.new(current_app.secret_key.encode(), b"finance-webpush-v1", hashlib.sha256).digest()
    key = ec.derive_private_key(int.from_bytes(seed, "big") % (order - 1) + 1, ec.SECP256R1())
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    private = key.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return base64.urlsafe_b64encode(public).decode().rstrip("="), base64.urlsafe_b64encode(
        private
    ).decode().rstrip("=")


# BLOCO — Valida as chaves e restringe o destino aos provedores push permitidos.
def validate_subscription(value):
    if not isinstance(value, dict):
        raise ValueError("Assinatura de notificações inválida.")
    endpoint = value.get("endpoint", "")
    if not isinstance(endpoint, str) or len(endpoint) > 4096:
        raise ValueError("Destino push inválido.")
    url = urlsplit(endpoint)
    host = url.hostname or ""
    permitted = host in {
        "fcm.googleapis.com",
        "updates.push.services.mozilla.com",
        "web.push.apple.com",
    } or bool(re.fullmatch(r"[a-z0-9-]+\.notify\.windows\.com", host))
    if (
        url.scheme != "https"
        or not permitted
        or url.port not in (None, 443)
        or url.username
        or url.password
        or url.fragment
    ):
        raise ValueError("Serviço push não suportado neste dispositivo.")
    keys = value.get("keys") or {}
    if not isinstance(keys, dict) or any(
        not isinstance(keys.get(k), str) or len(keys[k]) > 128 for k in ("p256dh", "auth")
    ):
        raise ValueError("Chaves de notificações inválidas.")
    try:
        public = base64.urlsafe_b64decode(keys["p256dh"] + "=" * (-len(keys["p256dh"]) % 4))
        auth = base64.urlsafe_b64decode(keys["auth"] + "=" * (-len(keys["auth"]) % 4))
        if len(auth) != 16:
            raise ValueError()
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
    except (KeyError, TypeError, ValueError):
        raise ValueError("Chaves de notificações inválidas.") from None
    return {"endpoint": endpoint, "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}}


# BLOCO — Entrega a chave pública e o estado de ativação das notificações.
@blueprint.get("/api/push/config")
def push_config():
    from app import connect

    with connect(global_scope=True) as conn:
        registered = conn.execute(
            "SELECT COUNT(*) AS n FROM public.pluggy_push_channels WHERE user_id=%s AND webhook_id IS NOT NULL",
            (g.user["id"],),
        ).fetchone()["n"]
    return jsonify(
        public_key=vapid_keys()[0],
        webhooks=registered,
        user_id=g.user["id"],
        session_version=g.user["session_version"],
    )


# BLOCO 2 — O mesmo telefone só pertence ao usuário que habilitou a assinatura por último.
@blueprint.post("/api/push/subscribe")
def subscribe():
    from app import connect
    from notifications import collect, today_local

    payload = request.get_json() or {}
    subscription = validate_subscription(payload.get("subscription"))
    android_app = payload.get("android_app") is True
    digest = hashlib.sha256(subscription["endpoint"].encode()).hexdigest()
    with connect(global_scope=True) as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM public.push_subscriptions WHERE user_id=%s AND endpoint_hash<>%s",
            (g.user["id"], digest),
        ).fetchone()["n"]
        if count >= 10:
            raise ValueError(
                "Limite de dez dispositivos. Desative as notificações em um dispositivo antigo."
            )
        conn.execute(
            """INSERT INTO public.push_subscriptions(endpoint_hash,user_id,session_version,subscription,android_app)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(endpoint_hash) DO UPDATE SET
            user_id=EXCLUDED.user_id,session_version=EXCLUDED.session_version,subscription=EXCLUDED.subscription,android_app=EXCLUDED.android_app,
            created_at=CASE WHEN push_subscriptions.user_id=EXCLUDED.user_id AND push_subscriptions.session_version=EXCLUDED.session_version
                THEN push_subscriptions.created_at ELSE NOW() END""",
            (
                digest,
                g.user["id"],
                g.user["session_version"],
                cipher().encrypt(json.dumps(subscription).encode()),
                android_app,
            ),
        )
    # Forma a base histórica antes de habilitar os avisos de novas coletas.
    with connect() as conn:
        collect(conn, today_local())
    if android_app:
        send_user_cost_reminders(g.user["id"])
    try:
        registered = register_webhooks()
        return jsonify(subscribed=True, webhooks=registered, android_reminders=android_app)
    except (PluggyError, ValueError):
        return jsonify(
            subscribed=True,
            webhooks=0,
            warning="Notificações do dispositivo salvas. Conecte ou confira as credenciais Pluggy e toque em Ativar novamente para habilitar os eventos bancários.",
        )


# BLOCO — Remove a assinatura do dispositivo sem afetar outros usuários.
@blueprint.post("/api/push/unsubscribe")
def unsubscribe():
    from app import connect

    endpoint = (request.get_json() or {}).get("endpoint", "")
    if not isinstance(endpoint, str):
        raise ValueError("Assinatura inválida.")
    with connect(global_scope=True) as conn:
        conn.execute(
            "DELETE FROM public.push_subscriptions WHERE endpoint_hash=%s AND user_id=%s",
            (hashlib.sha256(endpoint.encode()).hexdigest(), g.user["id"]),
        )
    return jsonify(unsubscribed=True)


# BLOCO — Testa apenas a assinatura do dispositivo da sessão atual, sem dados financeiros.
@blueprint.post("/api/push/test")
def test_device_push():
    from app import connect
    from notifications import today_local

    endpoint = (request.get_json() or {}).get("endpoint", "")
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > 4096:
        raise ValueError("Dispositivo inválido. Ative as notificações novamente.")
    digest = hashlib.sha256(endpoint.encode()).hexdigest()
    with connect(global_scope=True) as conn:
        row = conn.execute(
            """SELECT * FROM public.push_subscriptions WHERE endpoint_hash=%s
            AND user_id=%s AND session_version=%s""",
            (digest, g.user["id"], g.user["session_version"]),
        ).fetchone()
        if not row:
            return (
                jsonify(error="Celular não registrado. Toque em Ativar notificações primeiro."),
                409,
            )
        allowed = conn.execute(
            """INSERT INTO public.auth_rate_limits(bucket,attempts) VALUES(%s,1)
            ON CONFLICT(bucket) DO UPDATE SET attempts=1,window_started_at=NOW()
            WHERE auth_rate_limits.window_started_at<NOW()-INTERVAL '30 seconds'
            RETURNING bucket""",
            ("push-test:" + digest,),
        ).fetchone()
        if not allowed:
            return jsonify(error="Aguarde 30 segundos antes de testar novamente."), 429
    message = json.dumps(
        dict(
            id=str(uuid.uuid4()),
            user_id=g.user["id"],
            session_version=g.user["session_version"],
            kind="connection_test",
            route="overview",
            record_id=None,
            period=today_local().strftime("%Y-%m"),
        )
    )
    _, status = send_subscription(row, message, vapid_keys()[1], current_app.config["APP_ORIGIN"])
    if status == "expired":
        with connect(global_scope=True) as conn:
            conn.execute(
                "DELETE FROM public.push_subscriptions WHERE endpoint_hash=%s AND user_id=%s",
                (digest, g.user["id"]),
            )
        return jsonify(error="Registro do celular expirou. Toque em Ativar e teste novamente."), 410
    if status != "sent":
        return (
            jsonify(error="O serviço de notificações não aceitou o teste. Tente ativar novamente."),
            503,
        )
    return jsonify(accepted=True)


# Cadastra um canal por aplicação Pluggy e usuário; cabeçalho secreto autentica cada entrega.
def register_webhooks(include_sync=False):
    from app import connect
    from psycopg.types.json import Jsonb

    origin = current_app.config["APP_ORIGIN"]
    if not origin.startswith("https://"):
        raise ValueError("Notificações exigem o site publicado em HTTPS.")
    with connect() as conn:
        connections = conn.execute("SELECT id FROM pluggy_connections").fetchall()
    applications = {}
    for row in connections:
        config = read_config(row["id"])
        if config:
            applications[config["client_id"]] = config
    if not applications:
        raise ValueError("Conecte uma conta Pluggy primeiro.")
    required = ["transactions/created"] + (
        ["item/updated", "transactions/updated", "transactions/deleted"] if include_sync else []
    )
    for client, config in applications.items():
        fingerprint = hashlib.sha256(client.encode()).hexdigest()
        import secrets

        with connect(global_scope=True) as conn:
            conn.execute(
                """INSERT INTO public.pluggy_push_channels(id,user_id,client_hash,secret)
                VALUES(%s,%s,%s,%s) ON CONFLICT(user_id,client_hash) DO NOTHING""",
                (
                    uuid.uuid4(),
                    g.user["id"],
                    fingerprint,
                    cipher().encrypt(secrets.token_urlsafe(40).encode()),
                ),
            )
            row = conn.execute(
                "SELECT * FROM public.pluggy_push_channels WHERE user_id=%s AND client_hash=%s",
                (g.user["id"], fingerprint),
            ).fetchone()
        known = dict(row.get("sync_webhooks") or {})
        if row["webhook_id"]:
            known["transactions/created"] = row["webhook_id"]
        if all(event in known for event in required):
            continue
        key = token(config["client_id"], config["client_secret"])
        url = origin + "/hooks/pluggy/" + str(row["id"])
        secret = cipher().decrypt(bytes(row["secret"])).decode()
        existing = []
        for page in range(1, 51):
            result = call("/webhooks?page=" + str(page) + "&pageSize=100", key)
            existing.extend(result.get("results", []))
            if page >= int(result.get("totalPages") or 1):
                break
        for event in required:
            if event in known:
                continue
            # Reaproveita um cadastro remoto se uma tentativa anterior perdeu a resposta.
            hook = next(
                (
                    h
                    for h in existing
                    if h.get("url") == url
                    and h.get("event") == event
                    and not h.get("disabledAt")
                    and (h.get("headers") or {}).get("X-Finance-Webhook-Secret") == secret
                ),
                None,
            )
            if hook is None:
                hook = call(
                    "/webhooks",
                    key,
                    {"event": event, "url": url, "headers": {"X-Finance-Webhook-Secret": secret}},
                )
            if not hook.get("id"):
                raise PluggyError("Não foi possível cadastrar os eventos bancários.")
            known[event] = hook["id"]
            with connect(global_scope=True) as conn:
                if event == "transactions/created":
                    conn.execute(
                        "UPDATE public.pluggy_push_channels SET webhook_id=%s WHERE id=%s",
                        (hook["id"], row["id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE public.pluggy_push_channels SET sync_webhooks=sync_webhooks||%s WHERE id=%s",
                        (Jsonb({event: hook["id"]}), row["id"]),
                    )
    return len(applications)


# BLOCO 3 — O webhook não segue URLs do payload e não aceita uma conta de outro usuário.
@blueprint.post("/hooks/pluggy/<uuid:channel_id>")
def pluggy_webhook(channel_id):
    from app import connect
    from notifications import today_local

    supplied = request.headers.get("X-Finance-Webhook-Secret", "")
    if not supplied or len(supplied) > 200:
        return jsonify(error="Não autorizado."), 401
    with connect(global_scope=True) as conn:
        channel = conn.execute(
            """SELECT c.*,u.session_version,u.deleted_at FROM public.pluggy_push_channels c
            JOIN public.app_users u ON u.id=c.user_id WHERE c.id=%s""",
            (channel_id,),
        ).fetchone()
    if not channel or channel["deleted_at"] is not None:
        return jsonify(received=True)
    expected = cipher().decrypt(bytes(channel["secret"])).decode()
    if not hmac.compare_digest(supplied, expected):
        return jsonify(error="Não autorizado."), 401
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(error="Evento inválido."), 400
    event = payload.get("event")
    if event not in {
        "item/updated",
        "transactions/created",
        "transactions/updated",
        "transactions/deleted",
    }:
        return jsonify(received=True)
    try:
        event_id = uuid.UUID(str(payload.get("eventId")))
    except (ValueError, TypeError):
        return jsonify(error="Evento inválido."), 400
    # A identidade vem exclusivamente do canal secreto, nunca de user_id enviado pelo cliente.
    g.user = {"id": channel["user_id"], "session_version": channel["session_version"]}
    if event == "item/updated":
        from auto_sync import enqueue

        with connect() as conn:
            connections = conn.execute("SELECT id FROM pluggy_connections").fetchall()
        for row in connections:
            config = read_config(row["id"])
            if (
                config
                and config["item_id"] == (payload.get("itemId") or payload.get("id"))
                and hashlib.sha256(config["client_id"].encode()).hexdigest()
                == channel["client_hash"]
            ):
                enqueue(g.user["id"], "products", row["id"], force=True)
        return jsonify(received=True)
    with connect() as conn:
        account = conn.execute(
            "SELECT * FROM records WHERE kind IN ('accounts','cards') AND pluggy_data->>'id'=%s AND connection_id IS NOT NULL",
            (str(payload.get("accountId", ""))[:512],),
        ).fetchone()
    if not account:
        return jsonify(received=True)
    config = read_config(account["connection_id"])
    if (
        not config
        or config["item_id"] != payload.get("itemId")
        or hashlib.sha256(config["client_id"].encode()).hexdigest() != channel["client_hash"]
    ):
        return jsonify(received=True)
    from auto_sync import enqueue

    enqueue(g.user["id"], "products", account["connection_id"], force=True)
    months = {today_local().strftime("%Y-%m")}
    minimum = str(payload.get("transactionsMinDate") or "")[:7]
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", minimum):
        months.add(minimum)
    if payload.get("transactionIds"):
        ids = set(str(value) for value in payload["transactionIds"])
        with connect() as conn:
            if account["kind"] == "accounts":
                caches = conn.execute(
                    "SELECT period_start AS month,transactions FROM bank_statement_periods WHERE account_id=%s",
                    (account["id"],),
                ).fetchall()
            else:
                caches = conn.execute(
                    "SELECT month,transactions FROM card_month_bills WHERE card_id=%s",
                    (account["id"],),
                ).fetchall()
        months.update(
            row["month"].strftime("%Y-%m")
            for row in caches
            if any(str(t["id"]) in ids for t in (row.get("transactions") or []))
        )
    for month in months:
        enqueue(
            g.user["id"],
            "bank" if account["kind"] == "accounts" else "card",
            account["id"],
            month,
            force=True,
        )
    # A notificação sai do worker após salvar uma transação nova, com a mesma
    # deduplicação usada pela sincronização periódica e pelos botões manuais.
    return jsonify(received=True)


# BLOCO — Produz mensagens genéricas sem expor valores ou instituições na tela bloqueada.
def push_body(event):
    if event.get("kind") == "fixed_due":
        return "Você tem um custo fixo próximo do vencimento."
    if event.get("kind") == "fixed_overdue":
        return "Você tem um custo fixo vencido. Confira no aplicativo."
    return (
        "Novas transações na conta bancária."
        if event["route"] == "bank_account"
        else "Novas transações no cartão de crédito."
    )


# BLOCO — Entrega criptografada compartilhada entre movimentações e teste do dispositivo.
def send_subscription(row, message, private, current_origin):
    from pywebpush import webpush, WebPushException
    import requests

    class PushSession(requests.Session):
        def request(self, *args, **kwargs):
            kwargs["allow_redirects"] = False
            return super().request(*args, **kwargs)

    try:
        subscription = validate_subscription(
            json.loads(cipher().decrypt(bytes(row["subscription"])))
        )
        with PushSession() as session:
            session.trust_env = False
            result = webpush(
                subscription,
                data=message,
                vapid_private_key=private,
                vapid_claims={"sub": current_origin},
                ttl=86400,
                timeout=3,
                requests_session=session,
            )
        return row["endpoint_hash"], "sent" if 200 <= result.status_code < 300 else "retry"
    except WebPushException as error:
        code = error.response.status_code if error.response is not None else None
        return row["endpoint_hash"], "expired" if code in (404, 410) else "retry"
    except Exception:
        return row["endpoint_hash"], "retry"


# BLOCO 4 — Conteúdo genérico na tela bloqueada; detalhes financeiros exigem login.
# BLOCO — Outbox gravada na mesma transação do extrato; rollback não deixa avisos pendentes.
def record_transaction_push(conn, source, record_id, transaction_id, period):
    from flask import has_request_context
    user = getattr(g, "user", None) if has_request_context() else None
    if not user:
        return
    identifier = uuid.uuid5(uuid.NAMESPACE_URL, f"optimus:transaction:{user['id']}:{source}:{record_id}:{transaction_id}")
    route = "bank_account" if source == "bank" else "card_bill"
    conn.execute(
        """INSERT INTO public.push_events(id,user_id,route,record_id,period)
        VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
        (identifier, user["id"], route, record_id, period),
    )


# BLOCO — Reenvia pendências recentes somente para dispositivos Android ativos do usuário.
def flush_transaction_pushes(user_id):
    from app import connect
    with connect(global_scope=True) as conn:
        events = conn.execute(
            """SELECT e.id FROM public.push_events e
            JOIN public.app_users u ON u.id=e.user_id
            WHERE e.user_id=%s AND e.kind='transaction' AND u.deleted_at IS NULL
            AND e.created_at>NOW()-INTERVAL '24 hours' AND EXISTS (
                SELECT 1 FROM public.push_subscriptions s
                WHERE s.user_id=e.user_id AND s.session_version=u.session_version
                AND s.android_app AND s.created_at<=e.created_at AND NOT EXISTS (
                    SELECT 1 FROM public.push_deliveries d
                    WHERE d.event_id=e.id AND d.endpoint_hash=s.endpoint_hash))
            ORDER BY e.created_at LIMIT 50""",
            (user_id,),
        ).fetchall()
    failed = 0
    for event in events:
        try:
            if not deliver_event(event["id"]):
                failed += 1
        except Exception:
            failed += 1
            current_app.logger.warning("Notificação de transação pendente; nova tentativa automática.")
    if events:
        current_app.logger.info(
            "transaction-push: events=%s delivered=%s pending=%s",
            len(events), len(events) - failed, failed,
        )
    return len(events) - failed, failed


def deliver_event(event_id):
    from app import connect

    with connect(global_scope=True) as conn:
        # Serializa novas tentativas do mesmo evento; a entrega já concluída não é repetida.
        if not conn.execute(
            "SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0)) AS locked",
            ("push-event:" + str(event_id),),
        ).fetchone()["locked"]:
            return False
        event = conn.execute(
            """SELECT e.*,u.session_version,u.deleted_at FROM public.push_events e
            JOIN public.app_users u ON u.id=e.user_id WHERE e.id=%s""",
            (event_id,),
        ).fetchone()
        if not event or event["deleted_at"] is not None:
            return True
        subscriptions = conn.execute(
            """SELECT s.* FROM public.push_subscriptions s WHERE s.user_id=%s
            AND s.session_version=%s AND (s.created_at<=%s OR %s<>'transaction')
            AND s.android_app AND NOT EXISTS
            (SELECT 1 FROM public.push_deliveries d WHERE d.event_id=%s AND d.endpoint_hash=s.endpoint_hash)
            ORDER BY s.created_at DESC LIMIT 10""",
            (
                event["user_id"],
                event["session_version"],
                event["created_at"],
                event.get("kind", "transaction"),
                event_id,
            ),
        ).fetchall()
        private = vapid_keys()[1]
        # Sem valores ou nomes de banco no push: a mensagem pode aparecer com o celular bloqueado.
        message = json.dumps(
            {
                "id": str(event_id),
                "user_id": event["user_id"],
                "session_version": event["session_version"],
                "title": "Optimus Finance",
                "body": push_body(event),
                "kind": event.get("kind", "transaction"),
                "route": event["route"],
                "record_id": event["record_id"],
                "period": event["period"],
            }
        )

        def send(row):
            return send_subscription(row, message, private, current_origin)

        current_origin = current_app.config["APP_ORIGIN"]
        success = True
        with ThreadPoolExecutor(max_workers=5) as executor:
            for digest, status in executor.map(send, subscriptions):
                if status == "sent":
                    conn.execute(
                        "INSERT INTO public.push_deliveries(event_id,endpoint_hash) VALUES(%s,%s) ON CONFLICT DO NOTHING",
                        (event_id, digest),
                    )
                elif status == "expired":
                    conn.execute(
                        "DELETE FROM public.push_subscriptions WHERE endpoint_hash=%s", (digest,)
                    )
                else:
                    success = False
        return success


# BLOCO 5 — Verificação diária de custos, protegida por segredo e restrita ao APK.
def fixed_cost_reminders(records, payments, today):
    paid = {payment["expense_id"] for payment in payments}
    for cost in records:
        due = cost.get("due_date")
        if (
            cost["kind"] != "expenses"
            or not due
            or cost.get("status") == "Pago"
            or cost["id"] in paid
        ):
            continue
        remaining = (due - today).days
        kind = "fixed_overdue" if remaining < 0 else "fixed_due" if remaining <= 2 else None
        if kind:
            yield dict(
                record_id=cost["id"], kind=kind, period=due.strftime("%Y-%m"), due=due.isoformat()
            )


# BLOCO — Deduplica o aviso por custo, vencimento e fase do lembrete.
def create_reminder_event(user_id, reminder):
    from app import connect

    # Chave estável por obrigação e vencimento: o cron pode repetir sem duplicar avisos.
    event_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"finance-reminder:{user_id}:{reminder['record_id']}:{reminder['due']}:{reminder['kind']}",
    )
    with connect(global_scope=True) as conn:
        conn.execute(
            """INSERT INTO public.push_events(id,user_id,route,record_id,period,kind)
            VALUES(%s,%s,'fixed_costs',%s,%s,%s) ON CONFLICT DO NOTHING""",
            (event_id, user_id, reminder["record_id"], reminder["period"], reminder["kind"]),
        )
    return event_id


# BLOCO — Envia lembretes apenas aos dispositivos Android habilitados do usuário.
def send_user_cost_reminders(user_id):
    from app import connect
    from notifications import today_local

    with connect() as conn:
        records = conn.execute("SELECT * FROM records WHERE kind='expenses'").fetchall()
        payments = conn.execute("SELECT expense_id FROM expense_payments").fetchall()
    processed = 0
    failed = 0
    for reminder in fixed_cost_reminders(records, payments, today_local()):
        event_id = create_reminder_event(user_id, reminder)
        if deliver_event(event_id):
            processed += 1
        else:
            failed += 1
    return processed, failed


# BLOCO — Executa o lembrete diário somente mediante o segredo operacional.
@blueprint.get("/tasks/fixed-cost-reminders")
def send_fixed_cost_reminders():
    from app import connect
    from notifications import today_local

    secret = os.getenv("CRON_SECRET", "")
    supplied = request.headers.get("Authorization", "")
    if not secret or not hmac.compare_digest(supplied, "Bearer " + secret):
        return jsonify(error="Não autorizado."), 401
    with connect(global_scope=True) as conn:
        users = conn.execute("""SELECT DISTINCT u.id,u.session_version FROM public.app_users u
            JOIN public.push_subscriptions s ON s.user_id=u.id AND s.session_version=u.session_version
            WHERE u.deleted_at IS NULL AND s.android_app""").fetchall()
    processed = 0
    failed = 0
    for user in users:
        g.user = dict(user)
        sent, errors = send_user_cost_reminders(user["id"])
        processed += sent
        failed += errors
    return jsonify(processed=processed, failed=failed), 503 if failed else 200


# BLOCO — Impede cache dos endpoints operacionais e de notificações.
@blueprint.after_request
def no_push_cache(response):
    if request.path.startswith(("/tasks/", "/hooks/")):
        response.headers["Cache-Control"] = "no-store"
    return response
