# BLOCO — Cenários de teste para autenticação, sessões e permissões de acesso.
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from app import app, connect
from werkzeug.security import check_password_hash


class AuthTests(unittest.TestCase):
    def test_setup_login_roles_and_logout(self):
        with connect() as conn:
            if conn.execute("SELECT 1 FROM app_users LIMIT 1").fetchone():
                self.skipTest(
                    "Há usuários reais cadastrados; teste de bootstrap exige banco sem usuários."
                )

            @contextmanager
            def isolated(*args, **kwargs):
                yield conn

            try:
                with patch("app.connect", isolated):
                    admin = app.test_client()
                    visitor = app.test_client()
                    self.assertTrue(admin.get("/api/auth/me").json["setup_required"])
                    payload = dict(
                        login="teste.admin", password="SenhaTeste123!", role="administrador"
                    )
                    self.assertEqual(
                        admin.post(
                            "/api/auth/setup", json=payload | {"role": "editor"}
                        ).status_code,
                        400,
                    )
                    created = admin.post("/api/auth/setup", json=payload)
                    self.assertEqual(created.status_code, 201)
                    self.assertNotIn("password", str(created.json))
                    stored = conn.execute(
                        "SELECT * FROM app_users WHERE login=%s", ("teste.admin",)
                    ).fetchone()
                    self.assertNotEqual(stored["password_hash"], payload["password"])
                    self.assertTrue(
                        check_password_hash(stored["password_hash"], payload["password"])
                    )
                    self.assertEqual(visitor.get("/api/data").status_code, 401)
                    self.assertEqual(visitor.post("/api/auth/setup", json=payload).status_code, 409)
                    self.assertEqual(
                        visitor.post(
                            "/api/auth/login", json=dict(login="teste.admin", password="errada")
                        ).status_code,
                        401,
                    )
                    editor = payload | dict(login="teste.editor", role="editor")
                    self.assertEqual(admin.post("/api/users", json=editor).status_code, 201)
                    self.assertEqual(visitor.post("/api/auth/login", json=editor).status_code, 200)
                    self.assertEqual(visitor.get("/api/data").status_code, 200)
                    self.assertEqual(visitor.get("/api/users").status_code, 403)
                    self.assertEqual(visitor.post("/api/users", json=payload).status_code, 403)
                    self.assertEqual(visitor.get("/api/pluggy/config").status_code, 403)
                    self.assertEqual(visitor.get("/api/crypto/connections").status_code, 403)
                    self.assertEqual(visitor.put("/api/settings", json={}).status_code, 403)
                    self.assertEqual(visitor.post("/api/auth/logout", json={}).status_code, 200)
                    self.assertEqual(visitor.get("/api/data").status_code, 401)
                    self.assertEqual(admin.get("/api/users").status_code, 200)
                    self.assertNotIn("password_hash", str(admin.get("/api/users").json))
                    self.assertEqual(
                        admin.post(
                            "/api/users", json=editor, headers={"Origin": "https://other.example"}
                        ).status_code,
                        403,
                    )
            finally:
                conn.rollback()
