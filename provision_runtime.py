"""Cria uma credencial limitada para o backend. Usar apenas com conexão de migração."""

import os
import secrets
from pathlib import Path
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from app import connect

ROLE = "finance_runtime"


# BLOCO — Concede apenas as operações necessárias nas tabelas e sequências do schema.
def grant_workspace(conn, schema):
    conn.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.Identifier(schema), sql.Identifier(ROLE)
        )
    )
    conn.execute(
        sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA {} TO {}").format(
            sql.Identifier(schema), sql.Identifier(ROLE)
        )
    )
    conn.execute(
        sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(
            sql.Identifier(schema), sql.Identifier(ROLE)
        )
    )
    conn.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO {}"
        ).format(sql.Identifier(schema), sql.Identifier(ROLE))
    )
    conn.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT USAGE,SELECT ON SEQUENCES TO {}"
        ).format(sql.Identifier(schema), sql.Identifier(ROLE))
    )


# BLOCO — Cria a credencial limitada de runtime sem rotacionar uma credencial existente.
def provision():
    password = secrets.token_urlsafe(48)
    with connect(global_scope=True, migration=True) as conn:
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (ROLE,)).fetchone():
            raise RuntimeError("Credencial runtime já existe. Não é rotacionada automaticamente.")
        conn.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
            ).format(sql.Identifier(ROLE), sql.Literal(password))
        )
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(ROLE)))
        conn.execute(
            sql.SQL("GRANT SELECT,INSERT ON public.app_users TO {}").format(sql.Identifier(ROLE))
        )
        conn.execute(
            sql.SQL(
                "GRANT UPDATE(password_hash,session_version,deleted_at) ON public.app_users TO {}"
            ).format(sql.Identifier(ROLE))
        )
        conn.execute(
            sql.SQL("GRANT SELECT ON public.workspaces TO {}").format(sql.Identifier(ROLE))
        )
        conn.execute(
            sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON public.auth_rate_limits TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        conn.execute(
            sql.SQL(
                "GRANT SELECT,INSERT,UPDATE,DELETE ON public.push_subscriptions,public.pluggy_push_channels,public.push_events,public.push_deliveries,public.sync_jobs,public.sync_revisions TO {}"
            ).format(sql.Identifier(ROLE))
        )
        conn.execute(
            sql.SQL("GRANT USAGE,SELECT ON SEQUENCE public.app_users_id_seq TO {}").format(
                sql.Identifier(ROLE)
            )
        )
        for row in conn.execute("SELECT id FROM public.app_users").fetchall():
            grant_workspace(conn, "user_" + str(row["id"]))
        if conn.execute(
            "SELECT to_regprocedure('public.create_private_user(bigint,text,text,text)') AS fn"
        ).fetchone()["fn"]:
            conn.execute(
                sql.SQL(
                    "GRANT EXECUTE ON FUNCTION public.create_private_user(BIGINT,TEXT,TEXT,TEXT) TO {}"
                ).format(sql.Identifier(ROLE))
            )
    options = conninfo_to_dict(os.environ["DATABASE_URL"])
    options.update(user=ROLE, password=password)
    return make_conninfo(**options)
