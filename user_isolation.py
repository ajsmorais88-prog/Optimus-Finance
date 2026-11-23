"""Painéis privados; administrar acessos não abre as finanças de outro usuário."""

from pathlib import Path
import re
from psycopg import sql

from project_paths import PROJECT_ROOT, SQL_DIR

ROOT = PROJECT_ROOT
DATA_SQL = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
DATA_TABLES = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", DATA_SQL)


# BLOCO — Cria o schema privado e suas tabelas sem compartilhar registros de outro usuário.
def provision_user_data(conn, user_id, login):
    schema = "user_" + str(int(user_id))
    if conn.execute("SELECT 1 FROM pg_namespace WHERE nspname=%s", (schema,)).fetchone():
        return
    conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    conn.execute(sql.SQL("SET LOCAL search_path TO {},pg_catalog").format(sql.Identifier(schema)))
    conn.execute(DATA_SQL)
    conn.execute("UPDATE settings SET user_name=%s WHERE id=1", (login,))
    if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='finance_runtime'").fetchone():
        from provision_runtime import grant_workspace

        grant_workspace(conn, schema)
    conn.execute("SET LOCAL search_path TO public,pg_catalog")


# BLOCO — Instala uma função restrita que cria acessos e estruturas usando apenas DDL constante.
def install_private_user_factory(conn, control_schema="public"):
    # Apenas DDL constante, do repositório. Nenhum SQL é aceito do navegador.
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", control_schema):
        raise ValueError("Schema inválido.")
    definition = (
        """
CREATE OR REPLACE FUNCTION public.create_private_user(actor BIGINT,new_login TEXT,hashed TEXT,new_role TEXT)
RETURNS TABLE(id BIGINT,login VARCHAR,role TEXT)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $factory$
DECLARE organization BIGINT; created_id BIGINT; namespace TEXT;
BEGIN
 SELECT u.workspace_id INTO organization FROM public.app_users u
 WHERE u.id=actor AND u.role='administrador' AND u.deleted_at IS NULL;
 IF organization IS NULL THEN RAISE EXCEPTION 'Administrador não autorizado' USING ERRCODE='42501'; END IF;
 IF new_role NOT IN ('administrador','editor') OR new_login !~ '^[a-z0-9._-]{3,64}$' THEN
  RAISE EXCEPTION 'Usuário inválido' USING ERRCODE='22023';
 END IF;
 INSERT INTO public.app_users(login,password_hash,role,workspace_id)
 VALUES(new_login,hashed,new_role,organization) RETURNING app_users.id INTO created_id;
 namespace='user_'||created_id;
 EXECUTE format('CREATE SCHEMA %I',namespace);
 PERFORM set_config('search_path',format('%I,pg_catalog',namespace),true);
 EXECUTE $financial$"""
        + DATA_SQL
        + """$financial$;
 EXECUTE format('UPDATE %I.settings SET user_name=$1 WHERE id=1',namespace) USING new_login;
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='finance_runtime') THEN
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO finance_runtime',namespace);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA %I TO finance_runtime',namespace);
  EXECUTE format('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA %I TO finance_runtime',namespace);
 END IF;
 PERFORM set_config('search_path','pg_catalog,public',true);
 RETURN QUERY SELECT u.id,u.login,u.role FROM public.app_users u WHERE u.id=created_id;
END;
$factory$;
REVOKE ALL ON FUNCTION public.create_private_user(BIGINT,TEXT,TEXT,TEXT) FROM PUBLIC;
"""
    )
    conn.execute(definition.replace("public.", control_schema + "."))
    if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='finance_runtime'").fetchone():
        conn.execute(
            sql.SQL(
                "GRANT EXECUTE ON FUNCTION {}.create_private_user(BIGINT,TEXT,TEXT,TEXT) TO finance_runtime"
            ).format(sql.Identifier(control_schema))
        )


# BLOCO — Move os dados legados para o proprietário confirmado sem mesclar painéis existentes.
def migrate_to_private(conn, owner_login, legacy_public=False):
    owner = conn.execute(
        "SELECT id,workspace_id FROM public.app_users WHERE login=%s AND deleted_at IS NULL",
        (owner_login,),
    ).fetchone()
    if not owner:
        raise RuntimeError("Proprietário confirmado não encontrado.")
    destination = "user_" + str(owner["id"])
    source = "public" if legacy_public else "tenant_" + str(owner["workspace_id"])
    source_exists = conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
        (source, "records"),
    ).fetchone()
    destination_exists = conn.execute(
        "SELECT 1 FROM pg_namespace WHERE nspname=%s", (destination,)
    ).fetchone()
    if source_exists and destination_exists:
        raise RuntimeError("Origem e destino coexistem. Nenhum dado foi mesclado.")
    if source_exists:
        if legacy_public:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(destination)))
            for table in DATA_TABLES:
                if conn.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
                    ("public", table),
                ).fetchone():
                    conn.execute(
                        sql.SQL("ALTER TABLE public.{} SET SCHEMA {}").format(
                            sql.Identifier(table), sql.Identifier(destination)
                        )
                    )
        else:
            conn.execute(
                sql.SQL("ALTER SCHEMA {} RENAME TO {}").format(
                    sql.Identifier(source), sql.Identifier(destination)
                )
            )
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='finance_runtime'").fetchone():
            from provision_runtime import grant_workspace

            grant_workspace(conn, destination)
    for user in conn.execute(
        "SELECT id,login FROM public.app_users WHERE workspace_id=%s", (owner["workspace_id"],)
    ).fetchall():
        provision_user_data(conn, user["id"], user["login"])
    if source_exists:
        conn.execute(
            "UPDATE public.app_users SET session_version=session_version+1 WHERE workspace_id=%s",
            (owner["workspace_id"],),
        )
    install_private_user_factory(conn)
