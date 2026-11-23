"""Configuração de produção sem arquivos secretos no pacote da função."""

import os
from pathlib import Path
from urllib.parse import urlsplit
from cryptography.fernet import Fernet


# BLOCO — Distingue a execução publicada do ambiente local por variáveis do servidor.
def is_production():
    return os.getenv("VERCEL") == "1" or os.getenv("APP_ENV") == "production"


# BLOCO — Valida as variáveis obrigatórias e configura cookies, origem e isolamento por usuário.
def configure(app):
    production = is_production()
    secret = os.getenv("APP_SECRET_KEY")
    origin = os.getenv("APP_ORIGIN", "").rstrip("/")
    if production:
        if not secret or len(secret) < 32:
            raise RuntimeError("Configure APP_SECRET_KEY com pelo menos 32 caracteres.")
        key = os.getenv("PLUGGY_ENCRYPTION_KEY")
        if not key:
            raise RuntimeError("Configure PLUGGY_ENCRYPTION_KEY antes de iniciar produção.")
        Fernet(key.encode())
        parsed = urlsplit(origin)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.path not in ("", "/")
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("Configure APP_ORIGIN com a origem HTTPS pública exata.")
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError("Configure DATABASE_URL.")
    if not secret:
        import secrets
        from project_paths import PROJECT_ROOT

        path = PROJECT_ROOT / ".auth.key"
        try:
            with path.open("x", encoding="ascii") as f:
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        secret = path.read_text(encoding="ascii").strip()
    app.config.update(
        SECRET_KEY=secret,
        PRODUCTION=production,
        APP_ORIGIN=origin,
        TENANT_ISOLATION=production or os.getenv("TENANT_ISOLATION") == "1",
        SESSION_COOKIE_SECURE=production,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_NAME="__Host-finance-session" if production else "finance-session",
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if production:
        app.config["TRUSTED_HOSTS"] = [urlsplit(origin).hostname]


# BLOCO — Exige PostgreSQL remoto e valida o certificado TLS em produção.
def database_options(url, production):
    from psycopg.conninfo import conninfo_to_dict

    options = conninfo_to_dict(url)
    if production:
        if options.get("host") in {"localhost", "127.0.0.1", "::1", None}:
            raise RuntimeError("Produção exige PostgreSQL remoto com TLS.")
        import certifi

        options.update(sslmode="verify-full", sslrootcert=certifi.where())
    return options
