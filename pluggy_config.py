"""Persistência criptografada da conexão Pluggy do aplicativo pessoal local."""

import json
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


# A chave não entra no banco, no Git ou na resposta da API.
def cipher():
    key = os.getenv("PLUGGY_ENCRYPTION_KEY")
    from project_paths import PROJECT_ROOT

    path = PROJECT_ROOT / ".pluggy.key"
    if not key:
        from deployment_config import is_production

        if is_production():
            raise RuntimeError("Configure PLUGGY_ENCRYPTION_KEY em produção.")
        if not path.exists():
            try:
                with path.open("xb") as output:
                    output.write(Fernet.generate_key())
            except FileExistsError:
                pass
        key = path.read_bytes()
    return Fernet(key)


# BLOCO — Descriptografa a conexão solicitada e combina o Item ID com a aplicação do usuário.
def read_config(connection_id=None):
    from app import connect

    with connect() as conn:
        if connection_id is None:
            row = conn.execute(
                "SELECT credentials FROM pluggy_connections ORDER BY id LIMIT 1"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT credentials FROM pluggy_connections WHERE id=%s", (connection_id,)
            ).fetchone()
    if not row:
        return None
    try:
        values = json.loads(cipher().decrypt(bytes(row["credentials"])))
        if "client_secret" not in values:
            application = read_application()
            if not application:
                raise ValueError("Cadastre as credenciais da aplicação Pluggy.")
            values = {**application, **values}
        return values
    except (InvalidToken, ValueError):
        raise ValueError(
            "Não foi possível abrir a configuração Pluggy. Restaure a chave .pluggy.key ou salve novamente os três campos."
        ) from None


# BLOCO — Persiste o Item ID criptografado e evita duplicar a mesma conexão.
def write_config(values, label="Minha conta"):
    from app import connect

    application = read_application()
    if not application:
        raise ValueError("Cadastre Client ID e Client Secret uma vez antes de adicionar contas.")
    values = {**application, "item_id": values["item_id"]}
    encrypted = cipher().encrypt(json.dumps({"item_id": values["item_id"]}).encode())
    with connect() as conn:
        key = hashlib.sha256(
            json.dumps([values["client_id"], values["item_id"]]).encode()
        ).hexdigest()
        row = conn.execute(
            """INSERT INTO pluggy_connections (connection_key,label,credentials)
            VALUES (%s,%s,%s) ON CONFLICT (connection_key) DO UPDATE
            SET credentials=EXCLUDED.credentials,label=EXCLUDED.label RETURNING id""",
            (key, label, encrypted),
        ).fetchone()
    return row["id"]


# BLOCO — Abre as credenciais compartilhadas entre as conexões do mesmo usuário.
def read_application():
    from app import connect

    with connect() as conn:
        row = conn.execute("SELECT credentials FROM pluggy_application WHERE id=1").fetchone()
    if not row:
        return None
    try:
        return json.loads(cipher().decrypt(bytes(row["credentials"])))
    except InvalidToken:
        raise ValueError(
            "Não foi possível abrir as credenciais Pluggy. Verifique a chave de criptografia."
        ) from None


# BLOCO — Salva as credenciais criptografadas e impede trocar a aplicação de conexões existentes.
def write_application(values):
    from app import connect

    existing = read_application()
    if existing and existing["client_id"] != values["client_id"]:
        raise ValueError(
            "O Client ID já está vinculado às contas existentes. Mantenha o mesmo Client ID."
        )
    encrypted = cipher().encrypt(json.dumps(values).encode())
    with connect() as conn:
        conn.execute(
            """INSERT INTO pluggy_application (id,credentials) VALUES (1,%s)
            ON CONFLICT (id) DO UPDATE SET credentials=EXCLUDED.credentials""",
            (encrypted,),
        )


# BLOCO — Separa credenciais comuns dos Item IDs legados preservando os vínculos existentes.
def migrate_application():
    """Extrai credenciais comuns uma vez, preservando conexões já cadastradas."""
    from app import connect

    with connect() as conn:
        rows = conn.execute("SELECT id,credentials FROM pluggy_connections ORDER BY id").fetchall()
    application = read_application()
    for row in rows:
        values = json.loads(cipher().decrypt(bytes(row["credentials"])))
        if "client_secret" not in values:
            continue
        if not application:
            application = {name: values[name] for name in ("client_id", "client_secret")}
            write_application(application)
        if (
            values["client_id"] == application["client_id"]
            and values["client_secret"] == application["client_secret"]
        ):
            encrypted = cipher().encrypt(json.dumps({"item_id": values["item_id"]}).encode())
            with connect() as conn:
                conn.execute(
                    "UPDATE pluggy_connections SET credentials=%s WHERE id=%s",
                    (encrypted, row["id"]),
                )


# A listagem não precisa descriptografar os segredos para exibir o estado.
def list_connections():
    from app import connect

    with connect() as conn:
        connections = conn.execute("""SELECT id,label,last_synced_at,last_error
            FROM pluggy_connections ORDER BY id""").fetchall()
        products = conn.execute("""SELECT connection_id, name, kind FROM records
            WHERE connection_id IS NOT NULL ORDER BY id""").fetchall()
    return [
        {
            **row,
            "last_synced_at": row["last_synced_at"].isoformat() if row["last_synced_at"] else None,
            "products": [
                {"name": p["name"], "kind": p["kind"]}
                for p in products
                if p["connection_id"] == row["id"]
            ],
        }
        for row in connections
    ]


# BLOCO — Atualiza o formato legado das conexões sem apagar produtos importados.
def migrate_legacy():
    """Preserva a primeira configuração e vincula seus produtos já importados."""
    from app import connect

    with connect() as conn:
        old = conn.execute("SELECT credentials FROM pluggy_config WHERE id=1").fetchone()
    if not old:
        return
    values = json.loads(cipher().decrypt(bytes(old["credentials"])))
    key = hashlib.sha256(json.dumps([values["client_id"], values["item_id"]]).encode()).hexdigest()
    with connect() as conn:
        row = conn.execute(
            """INSERT INTO pluggy_connections (connection_key,label,credentials)
            VALUES (%s,%s,%s) ON CONFLICT (connection_key) DO UPDATE
            SET connection_key=EXCLUDED.connection_key RETURNING id""",
            (key, "Conexão já cadastrada", bytes(old["credentials"])),
        ).fetchone()
        products = conn.execute(
            "SELECT id,external_key,pluggy_data FROM records WHERE connection_id IS NULL AND pluggy_data IS NOT NULL"
        ).fetchall()
        for product in products:
            external = hashlib.sha256(
                json.dumps(
                    [values["client_id"], values["item_id"], product["pluggy_data"].get("id")]
                ).encode()
            ).hexdigest()
            if external == product["external_key"]:
                conn.execute(
                    "UPDATE records SET connection_id=%s WHERE id=%s", (row["id"], product["id"])
                )
        conn.execute("DELETE FROM pluggy_config WHERE id=1")


# BLOCO — Edita somente a conexão do schema privado atual e mantém o Item ID criptografado.
def update_connection(connection_id, label, item_id=None):
    from app import connect

    with connect() as conn:
        existing = conn.execute(
            "SELECT id,credentials FROM pluggy_connections WHERE id=%s FOR UPDATE",
            (connection_id,),
        ).fetchone()
        if not existing:
            return False
        if item_id:
            application = read_application()
            if not application:
                raise ValueError("Cadastre as credenciais da aplicação Pluggy.")
            key = hashlib.sha256(
                json.dumps([application["client_id"], item_id]).encode()
            ).hexdigest()
            current = json.loads(cipher().decrypt(bytes(existing["credentials"])))
            if current["item_id"] != item_id:
                # O histórico antigo continua salvo, mas não pertence à nova conexão externa.
                conn.execute("UPDATE records SET connection_id=NULL WHERE connection_id=%s", (connection_id,))
                conn.execute(
                    "UPDATE pluggy_connections SET last_synced_at=NULL,last_error=NULL WHERE id=%s",
                    (connection_id,),
                )
            encrypted = cipher().encrypt(json.dumps({"item_id": item_id}).encode())
            conn.execute(
                "UPDATE pluggy_connections SET label=%s,connection_key=%s,credentials=%s WHERE id=%s",
                (label, key, encrypted, connection_id),
            )
        else:
            conn.execute("UPDATE pluggy_connections SET label=%s WHERE id=%s", (label, connection_id))
    return True


# BLOCO — Exclui o acesso salvo, sem apagar contas, cartões, investimentos ou extratos importados.
def delete_connection(connection_id):
    from app import connect

    with connect() as conn:
        row = conn.execute("SELECT id FROM pluggy_connections WHERE id=%s FOR UPDATE", (connection_id,)).fetchone()
        if not row:
            return False
        conn.execute("UPDATE records SET connection_id=NULL WHERE connection_id=%s", (connection_id,))
        conn.execute("DELETE FROM pluggy_connections WHERE id=%s", (connection_id,))
    return True
