"""Importação explícita dos dados locais, após autorização da transferência."""

import os
from pathlib import Path
import click
import psycopg
from psycopg.rows import dict_row
from psycopg import sql
from psycopg.types.json import Jsonb
from dotenv import dotenv_values

TABLES = [
    "pluggy_config",
    "pluggy_connections",
    "pluggy_application",
    "crypto_connections",
    "records",
    "settings",
    "binance_trade_history",
    "binance_fx_history",
    "portfolio_history",
    "card_bill_periods",
    "bank_statement_periods",
    "expense_payments",
    "investment_flows",
    "card_month_bills",
    "card_reference_cycles",
    "bank_opening_balances",
]


def copy_table(source, target, table, schema):
    rows = source.execute(
        sql.SQL("SELECT * FROM public.{}").format(sql.Identifier(table))
    ).fetchall()
    for row in rows:
        columns = list(row)
        statement = sql.SQL("INSERT INTO {}.{} ({}) OVERRIDING SYSTEM VALUE VALUES ({})").format(
            sql.Identifier(schema),
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, columns)),
            sql.SQL(",").join(sql.Placeholder() for _ in columns),
        )
        target.execute(
            statement,
            [Jsonb(row[c]) if isinstance(row[c], (dict, list)) else row[c] for c in columns],
        )
    if rows and "id" in rows[0]:
        sequence = target.execute(
            "SELECT pg_get_serial_sequence(%s,%s) AS seq", (schema + "." + table, "id")
        ).fetchone()["seq"]
        if sequence:
            target.execute("SELECT setval(%s,%s,true)", (sequence, max(r["id"] for r in rows)))
    return len(rows)


@click.command()
@click.option(
    "--confirm-transfer",
    is_flag=True,
    help="Confirma o envio de dados financeiros e usuários locais ao Neon configurado.",
)
def main(confirm_transfer):
    if not confirm_transfer:
        raise click.ClickException(
            "Transferência não autorizada. Revise o destino e use --confirm-transfer somente após consentimento."
        )
    from project_paths import PROJECT_ROOT

    root = PROJECT_ROOT
    local = dotenv_values(root / ".env")
    remote = dotenv_values(root / ".env.production.local")
    if not local.get("DATABASE_URL") or not remote.get("MIGRATION_DATABASE_URL"):
        raise click.ClickException("Conexões de origem e destino não configuradas.")
    os.environ.update({k: v for k, v in remote.items() if v is not None})
    from app import connect

    # O destino tem de estar vazio; nunca mescla nem apaga dados financeiros existentes.
    with (
        psycopg.connect(local["DATABASE_URL"], row_factory=dict_row) as source,
        connect(global_scope=True, migration=True) as target,
    ):
        source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        target.execute("LOCK TABLE tenant_1.records,public.app_users IN EXCLUSIVE MODE")
        for table in TABLES:
            if table == "settings":
                continue
            if target.execute(
                sql.SQL("SELECT 1 FROM tenant_1.{} LIMIT 1").format(sql.Identifier(table))
            ).fetchone():
                raise click.ClickException("O destino já contém dados. Não foi sobrescrito.")
        if target.execute("SELECT 1 FROM public.app_users LIMIT 1").fetchone():
            raise click.ClickException("O destino já contém usuários. Não foi sobrescrito.")
        target.execute("DELETE FROM tenant_1.settings")
        for table in TABLES:
            copy_table(source, target, table, "tenant_1")
        users = copy_table(source, target, "app_users", "public")
        # Verificação de integridade antes do commit; qualquer falha reverte a importação.
        source_count = source.execute("SELECT COUNT(*) AS n FROM public.records").fetchone()["n"]
        target_count = target.execute("SELECT COUNT(*) AS n FROM tenant_1.records").fetchone()["n"]
        if source_count != target_count:
            raise click.ClickException("Contagens divergentes; transação revertida.")
        # Credenciais criptografadas continuam legíveis com a mesma chave, sem as exibir.
        from cryptography.fernet import Fernet

        cipher = Fernet(remote["PLUGGY_ENCRYPTION_KEY"].encode())
        for table in (
            "pluggy_config",
            "pluggy_connections",
            "pluggy_application",
            "crypto_connections",
        ):
            for row in target.execute(
                sql.SQL("SELECT credentials FROM tenant_1.{}").format(sql.Identifier(table))
            ).fetchall():
                cipher.decrypt(bytes(row["credentials"]))
    click.echo(
        "Importação verificada. Banco local preservado. Usuários transferidos: " + str(users)
    )


if __name__ == "__main__":
    main()
