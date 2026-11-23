"""Provisionamento explícito: executar localmente com credencial de migração, nunca via HTTP."""

import re
import click
from pathlib import Path
from psycopg import sql
from werkzeug.security import generate_password_hash
from app import app, connect
from auth import validate_user

from project_paths import PROJECT_ROOT, SQL_DIR

ROOT = PROJECT_ROOT
DATA_SQL = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
DATA_TABLES = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", DATA_SQL)


def migrate(conn, adopt_legacy=False):
    from user_isolation import provision_user_data, install_private_user_factory

    conn.execute((SQL_DIR / "control_schema.sql").read_text(encoding="utf-8"))
    if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='finance_runtime'").fetchone():
        conn.execute(
            "GRANT UPDATE(password_hash,session_version,deleted_at) ON public.app_users TO finance_runtime"
        )
        conn.execute(
            "GRANT SELECT,INSERT,UPDATE,DELETE ON public.push_subscriptions,public.pluggy_push_channels,public.push_events,public.push_deliveries,public.sync_jobs,public.sync_revisions TO finance_runtime"
        )
    users = conn.execute(
        "SELECT id,login,workspace_id FROM public.app_users ORDER BY id"
    ).fetchall()
    for user in users:
        legacy = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_schema IN (%s,%s) AND table_name=%s",
            ("public", "tenant_" + str(user["workspace_id"]), "records"),
        ).fetchone()
        if legacy:
            raise click.ClickException(
                "Dados compartilhados encontrados. Use isolate-users --owner-login com o proprietário confirmado."
            )
        provision_user_data(conn, user["id"], user["login"])
        schema = "user_" + str(user["id"])
        conn.execute(
            sql.SQL("SET LOCAL search_path TO {},pg_catalog").format(sql.Identifier(schema))
        )
        conn.execute(DATA_SQL)
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='finance_runtime'").fetchone():
            from provision_runtime import grant_workspace

            grant_workspace(conn, schema)
        conn.execute("SET LOCAL search_path TO public,pg_catalog")
    install_private_user_factory(conn)


@click.group()
def cli():
    """Estrutura, organizações e administradores; nenhuma publicação automática."""


@cli.command("migrate")
@click.option(
    "--adopt-legacy",
    is_flag=True,
    help="Move os dados existentes para tenant_1, preservando IDs e vínculos.",
)
def migrate_command(adopt_legacy):
    with connect(global_scope=True, migration=True) as conn:
        migrate(conn, adopt_legacy)
    click.echo("Migração concluída. Dados financeiros separados por organização.")


@cli.command("create-workspace")
@click.option("--name", prompt="Nome da organização")
@click.option("--login", prompt="Login do administrador")
@click.password_option(confirmation_prompt=True)
def create_workspace(name, login, password):
    login, password, _ = validate_user(dict(login=login, password=password, role="administrador"))
    if not name.strip() or len(name) > 120:
        raise click.ClickException("Informe nome de até 120 caracteres.")
    with connect(global_scope=True, migration=True) as conn:
        workspace = conn.execute(
            "INSERT INTO public.workspaces(name) VALUES(%s) RETURNING id", (name.strip(),)
        ).fetchone()
        user = conn.execute(
            "INSERT INTO public.app_users(login,password_hash,role,workspace_id) VALUES(%s,%s,%s,%s) RETURNING id",
            (login, generate_password_hash(password), "administrador", workspace["id"]),
        ).fetchone()
        from user_isolation import provision_user_data

        provision_user_data(conn, user["id"], login)
    click.echo("Organização e administrador criados.")


@cli.command("create-admin")
@click.option("--workspace", type=click.IntRange(min=1), default=1, show_default=True)
@click.option("--login", prompt="Login do administrador")
@click.password_option(confirmation_prompt=True)
def create_admin(workspace, login, password):
    login, password, _ = validate_user(dict(login=login, password=password, role="administrador"))
    with connect(global_scope=True, migration=True) as conn:
        if not conn.execute("SELECT 1 FROM public.workspaces WHERE id=%s", (workspace,)).fetchone():
            raise click.ClickException("Organização não encontrada.")
        user = conn.execute(
            "INSERT INTO public.app_users(login,password_hash,role,workspace_id) VALUES(%s,%s,%s,%s) RETURNING id",
            (login, generate_password_hash(password), "administrador", workspace),
        ).fetchone()
        from user_isolation import provision_user_data

        provision_user_data(conn, user["id"], login)
    click.echo("Administrador criado. Nenhuma senha foi registrada em logs.")


@cli.command("isolate-users")
@click.option(
    "--owner-login", required=True, help="Proprietário confirmado dos dados já existentes."
)
@click.option(
    "--local-public",
    is_flag=True,
    help="Move tabelas financeiras legadas de public, preservando as identidades.",
)
def isolate_users(owner_login, local_public):
    from user_isolation import migrate_to_private

    with connect(global_scope=True, migration=True) as conn:
        migrate_to_private(conn, owner_login, legacy_public=local_public)
    click.echo(
        "Painéis separados por usuário. Dados existentes preservados com o proprietário confirmado."
    )


if __name__ == "__main__":
    cli()
