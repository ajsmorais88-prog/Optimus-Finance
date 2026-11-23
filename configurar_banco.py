"""Configuração interativa do PostgreSQL, sem expor senhas no terminal ou chat."""

import getpass
import os
import secrets
from pathlib import Path
from urllib.parse import quote

import psycopg
from psycopg import sql
from dotenv import dotenv_values


from project_paths import PROJECT_ROOT, SQL_DIR

ROOT = PROJECT_ROOT
ENV_FILE = ROOT / ".env"


# BLOCO 1 — Verifica a configuração existente sem imprimir a URL com senha.
def verify(url):
    with psycopg.connect(url, connect_timeout=5) as conn:
        conn.execute((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))

    # Transação revertida: confirma escrita e leitura sem deixar dados de teste.
    with psycopg.connect(url, connect_timeout=5) as conn:
        row = conn.execute(
            "INSERT INTO records (kind, name, amount) VALUES (%s, %s, %s) RETURNING id",
            ("categories", "Verificação temporária de conexão", 0),
        ).fetchone()
        assert conn.execute("SELECT id FROM records WHERE id = %s", row).fetchone()
        conn.rollback()


def main():
    config = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    existing_url = os.environ.get("DATABASE_URL") or config.get("DATABASE_URL")
    if existing_url:
        print("Verificando a conexão já configurada...")
        try:
            verify(existing_url)
        except psycopg.Error:
            print("A conexão existente falhou. O arquivo .env foi preservado.")
            print("Revise DATABASE_URL no .env e execute novamente.")
            return 1
        print("Conexão, tabelas, gravação e leitura verificadas com sucesso.")
        return 0

    # BLOCO 2 — A senha administrativa é usada apenas nesta configuração.
    print("PostgreSQL local — criação do banco financeiro")
    print("Use a senha definida durante a instalação do PostgreSQL.")
    host = input("Servidor [127.0.0.1]: ").strip() or "127.0.0.1"
    port = int(input("Porta [5432]: ").strip() or "5432")
    admin = input("Usuário administrador [postgres]: ").strip() or "postgres"
    admin_password = getpass.getpass("Senha do administrador (não será exibida): ")

    # Usuário dedicado com senha aleatória; nunca usa o administrador no site.
    role = "financeiro"
    database = "financeiro"
    password = secrets.token_urlsafe(32)
    with psycopg.connect(
        host=host,
        port=port,
        user=admin,
        password=admin_password,
        dbname="postgres",
        connect_timeout=5,
        autocommit=True,
    ) as conn:
        role_exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone()
        if role_exists:
            print("O usuário financeiro já existe; sua senha não será alterada.")
            password = getpass.getpass("Senha do usuário financeiro: ")
        else:
            conn.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE"
                ).format(sql.Identifier(role), sql.Literal(password))
            )

        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (database,)).fetchone()
        if not exists:
            conn.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(database), sql.Identifier(role)
                )
            )
        else:
            print("Banco financeiro existente: os dados serão preservados.")

    # BLOCO 3 — Cria tabelas e testa a persistência antes de gravar a configuração.
    address = f"[{host}]" if ":" in host else host
    url = f"postgresql://{quote(role, safe='')}:{quote(password, safe='')}@{address}:{port}/{database}"
    verify(url)
    prior = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    with ENV_FILE.open("a", encoding="utf-8") as output:
        if prior and not prior.endswith("\n"):
            output.write("\n")
        output.write(f"DATABASE_URL={url}\n")
        if not config.get("PORT"):
            output.write("PORT=5050\n")
    print("Pronto! Banco conectado, tabelas criadas e leitura/gravação verificadas.")
    print("A conexão foi salva no .env, ignorado pelo Git.")
    print("Reinicie o painel: feche o servidor anterior e execute iniciar.bat.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (psycopg.Error, ValueError, OSError):
        print("Não foi possível concluir. Confira servidor, porta, usuário, senha e permissões.")
        print("Nenhuma senha foi exibida. Se o usuário financeiro foi criado nesta tentativa,")
        print("use o pgAdmin para definir uma senha antes de tentar novamente.")
        raise SystemExit(1)
