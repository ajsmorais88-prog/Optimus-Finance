"""Acrescenta finalidade das categorias, preservando os cadastros existentes."""
from psycopg import sql


def migrate(conn):
    from user_isolation import install_private_user_factory
    tables = conn.execute("SELECT table_schema FROM information_schema.tables WHERE table_name='records' AND (table_schema ~ '^user_[0-9]+$' OR table_schema='public') ORDER BY table_schema").fetchall()
    for row in tables:
        conn.execute(sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS category_type TEXT DEFAULT 'expenses' CHECK (category_type IN ('incomes','expenses'))").format(sql.Identifier(row['table_schema'], 'records')))
    install_private_user_factory(conn)
    return len(tables)


if __name__ == '__main__':
    from project_paths import PROJECT_ROOT
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env.production.local', override=True)
    from app import connect
    with connect(global_scope=True, migration=True) as conn:
        count = migrate(conn)
    print(f'Tipo de categoria habilitado em {count} estruturas.')
