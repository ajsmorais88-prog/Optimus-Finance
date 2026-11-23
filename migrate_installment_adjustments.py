"""Preserva correções de parcelamentos separadas dos dados recebidos do banco."""
from psycopg import sql


def migrate(conn):
    from user_isolation import install_private_user_factory
    rows = conn.execute("SELECT table_schema FROM information_schema.tables WHERE table_name='records' AND (table_schema ~ '^user_[0-9]+$' OR table_schema='public')").fetchall()
    for row in rows:
        conn.execute(sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS installment_adjustments JSONB NOT NULL DEFAULT '[]'").format(sql.Identifier(row['table_schema'], 'records')))
    install_private_user_factory(conn)
    return len(rows)


if __name__ == '__main__':
    from project_paths import PROJECT_ROOT
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env.production.local', override=True)
    from app import connect
    with connect(global_scope=True, migration=True) as conn:
        count = migrate(conn)
    print(f'Correções de parcelas habilitadas em {count} estruturas.')
