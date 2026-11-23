"""Identidade sintética para testes legados das regras financeiras; não altera usuários reais."""

import time
from contextlib import contextmanager
from unittest.mock import patch


def authenticate_test_client(testcase, client):
    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def execute(self, statement, params=None):
            if "EXISTS" in statement:
                return Result({"present": True})
            return Result(
                {"id": 987654321, "login": "test-only", "role": "administrador", "workspace_id": 1}
            )

    @contextmanager
    def identity():
        yield Connection()

    p = patch("auth.identity_connect", identity)
    p.start()
    testcase.addCleanup(p.stop)
    revision = patch("auto_sync.mark_changed", lambda user_id: None)
    revision.start()
    testcase.addCleanup(revision.stop)
    # Testes financeiros legados não criam eventos globais nem enviam mensagens reais.
    for target in ("push_notifications.record_transaction_push", "push_notifications.flush_transaction_pushes"):
        notification = patch(target, return_value=(0, 0))
        notification.start()
        testcase.addCleanup(notification.stop)
    with client.session_transaction() as session:
        session["user_id"] = 987654321
        session["expires_at"] = time.time() + 3600


@contextmanager
def financial_test_connection():
    import secrets
    from pathlib import Path
    from app import connect
    from psycopg import sql

    with connect(global_scope=True) as conn:
        try:
            schema = "financial_test_" + secrets.token_hex(8)
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            conn.execute(
                sql.SQL("SET LOCAL search_path TO {},pg_catalog").format(sql.Identifier(schema))
            )
            conn.execute(Path("Backend/SQL/schema.sql").read_text(encoding="utf-8"))
            yield conn
        finally:
            conn.rollback()
