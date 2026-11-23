# BLOCO — Cenários de teste para validação das regras de login options.
import unittest
import time
from contextlib import contextmanager
from unittest.mock import patch
from werkzeug.security import generate_password_hash
from app import app


class LoginOptionTests(unittest.TestCase):
    def test_remember_and_session_expiry(self):
        user = dict(
            id=123,
            workspace_id=1,
            login="mock-user",
            role="administrador",
            password_hash=generate_password_hash("Temporary-test-only"),
        )

        class Result:
            def __init__(self, row):
                self.row = row

            def fetchone(self):
                return self.row

        class Connection:
            def execute(self, sql, args=None):
                return Result({"present": True} if "EXISTS" in sql else user)

        @contextmanager
        def mocked(*args, **kwargs):
            yield Connection()

        with patch("app.connect", mocked), patch("auth.consume_attempt", return_value=True):
            for remember in (False, True):
                client = app.test_client()
                r = client.post(
                    "/api/auth/login",
                    json=dict(login="mock-user", password="Temporary-test-only", remember=remember),
                )
                self.assertEqual(r.status_code, 200)
                with client.session_transaction() as session:
                    self.assertEqual(session.permanent, remember)
                    remaining = session["expires_at"] - time.time()
                    self.assertGreater(remaining, 29 * 86400 if remember else 7 * 3600)
                    session["expires_at"] = time.time() - 1
                self.assertIsNone(client.get("/api/auth/me").json["user"])
