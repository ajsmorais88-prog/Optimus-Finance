"""Amplia somente as exchanges aceitas; não modifica saldos ou credenciais."""
from psycopg import sql


def migrate(conn):
    from user_isolation import install_private_user_factory

    tables = conn.execute("SELECT table_schema FROM information_schema.tables WHERE table_name='crypto_connections' AND (table_schema ~ '^user_[0-9]+$' OR table_schema='public') ORDER BY table_schema").fetchall()
    for row in tables:
        table = sql.Identifier(row["table_schema"], "crypto_connections")
        conn.execute(sql.SQL("ALTER TABLE {} DROP CONSTRAINT IF EXISTS crypto_connections_exchange_check").format(table))
        conn.execute(sql.SQL("ALTER TABLE {} ADD CONSTRAINT crypto_connections_exchange_check CHECK (exchange IN ('binance','bybit','kraken','mercadobitcoin'))").format(table))
    install_private_user_factory(conn)
    return len(tables)


if __name__ == "__main__":
    import argparse
    from project_paths import PROJECT_ROOT
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    if args.production:
        if not (PROJECT_ROOT / ".env.production.local").is_file():
            parser.error("Configuração de produção não encontrada.")
        load_dotenv(PROJECT_ROOT / ".env.production.local", override=True)
    from app import connect

    with connect(global_scope=True, migration=True) as conn:
        count = migrate(conn)
    print(f"Mercado Bitcoin habilitado em {count} estruturas, sem alterar dados financeiros.")
