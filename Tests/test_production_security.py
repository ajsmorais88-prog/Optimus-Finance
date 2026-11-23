"""Testes de produção em schemas temporários, sem tocar nas contas financeiras reais."""

import os
import secrets
import unittest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
from dotenv import dotenv_values
from psycopg import sql
from werkzeug.security import generate_password_hash
from app import app, connect


class ProductionSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = dotenv_values(".env")
        if not config.get("DATABASE_URL"):
            raise unittest.SkipTest("Configure o PostgreSQL local de testes.")
        # Somente transporte de teste é local; roteamento por usuário e autorização são reais.
        from psycopg.conninfo import conninfo_to_dict
        from cryptography.fernet import Fernet

        cls.network_patch = patch(
            "app.database_options",
            side_effect=lambda url, production: conninfo_to_dict(config["DATABASE_URL"]),
        )
        cls.network_patch.start()
        cls.env = patch.dict(
            os.environ,
            {
                "DATABASE_URL": config["DATABASE_URL"],
                "PLUGGY_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            },
        )
        cls.env.start()
        cls.old = {
            key: app.config.get(key)
            for key in ("PRODUCTION", "TENANT_ISOLATION", "APP_ORIGIN", "SESSION_COOKIE_SECURE")
        }
        app.config.update(
            PRODUCTION=True,
            TENANT_ISOLATION=True,
            APP_ORIGIN="https://security-test.example",
            SESSION_COOKIE_SECURE=True,
        )
        cls.control = "security_" + secrets.token_hex(8)
        cls.ids = [
            secrets.randbelow(500000000) + 1000000000,
            secrets.randbelow(500000000) + 1600000000,
        ]
        cls.user_ids = [cls.ids[0] + 10, cls.ids[1] + 10, cls.ids[0] + 11]
        cls.schemas = ["user_" + str(i) for i in cls.user_ids]
        cls.password = secrets.token_urlsafe(24)
        with connect(global_scope=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.control)))
            conn.execute(
                Path("Backend/SQL/control_schema.sql")
                .read_text(encoding="utf-8")
                .replace("public.", cls.control + ".")
            )
            for i in cls.ids:
                conn.execute(
                    sql.SQL("INSERT INTO {}.workspaces(id,name) VALUES(%s,%s)").format(
                        sql.Identifier(cls.control)
                    ),
                    (i, "Temporary local test"),
                )
            for schema in cls.schemas:
                conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
                conn.execute(
                    sql.SQL("SET LOCAL search_path TO {},pg_catalog").format(sql.Identifier(schema))
                )
                conn.execute(Path("Backend/SQL/schema.sql").read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO records(kind,name,amount) VALUES('accounts',%s,10)", (schema,)
                )
            conn.execute(
                sql.SQL("SET LOCAL search_path TO {},pg_catalog").format(
                    sql.Identifier(cls.control)
                )
            )
            for user_id, (login, role, workspace) in zip(
                cls.user_ids,
                [
                    ("org-a", "administrador", cls.ids[0]),
                    ("org-b", "administrador", cls.ids[1]),
                    ("editor-a", "editor", cls.ids[0]),
                ],
            ):
                conn.execute(
                    "INSERT INTO app_users(id,login,password_hash,role,workspace_id) VALUES(%s,%s,%s,%s,%s)",
                    (user_id, login, generate_password_hash(cls.password), role, workspace),
                )
            conn.execute(
                "SELECT setval(%s,%s,true)",
                (cls.control + ".app_users_id_seq", max(cls.user_ids) + 100),
            )
            from user_isolation import install_private_user_factory

            install_private_user_factory(conn, cls.control)

        @contextmanager
        def identity():
            with connect(global_scope=True) as conn:
                conn.execute(
                    sql.SQL("SET LOCAL search_path TO {},pg_catalog").format(
                        sql.Identifier(cls.control)
                    )
                )
                yield conn

        cls.identity_patch = patch("auth.identity_connect", identity)
        cls.identity_patch.start()
        cls.origin = app.config["APP_ORIGIN"]

    @classmethod
    def tearDownClass(cls):
        cls.identity_patch.stop()
        try:
            with connect(global_scope=True) as conn:
                ids = conn.execute(
                    sql.SQL("SELECT id FROM {}.app_users").format(sql.Identifier(cls.control))
                ).fetchall()
                for schema in ["user_" + str(row["id"]) for row in ids] + [cls.control]:
                    conn.execute(
                        sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
                    )
        finally:
            app.config.update(cls.old)
            cls.env.stop()
            cls.network_patch.stop()

    def client(self, login=None):
        client = app.test_client()
        me = client.get("/api/auth/me", base_url=self.origin)
        token = me.json["csrf_token"]
        if login:
            response = client.post(
                "/api/auth/login",
                base_url=self.origin,
                json={"login": login, "password": self.password},
                headers={"X-CSRF-Token": token, "Origin": self.origin},
            )
            self.assertEqual(response.status_code, 200, response.json)
            token = response.json["csrf_token"]
        return client, {"X-CSRF-Token": token, "Origin": self.origin}

    def test_unauthenticated_and_setup_closed(self):
        c, h = self.client()
        self.assertEqual(c.get("/api/data", base_url=self.origin).status_code, 401)
        self.assertFalse(c.get("/api/auth/me", base_url=self.origin).json["setup_required"])
        self.assertEqual(
            c.post(
                "/api/auth/setup",
                base_url=self.origin,
                json={"login": "new", "password": self.password, "role": "administrador"},
                headers=h,
            ).status_code,
            403,
        )

    def test_financial_data_and_credentials_isolated(self):
        a, ha = self.client("org-a")
        b, hb = self.client("org-b")
        da = a.get("/api/data", base_url=self.origin).json
        db = b.get("/api/data", base_url=self.origin).json
        self.assertEqual(da["records"][0]["name"], self.schemas[0])
        self.assertEqual(db["records"][0]["name"], self.schemas[1])
        for c, h, label in [(a, ha, "organization-a"), (b, hb, "organization-b")]:
            self.assertEqual(
                c.put(
                    "/api/pluggy/config",
                    base_url=self.origin,
                    json={"client_id": label, "client_secret": "temporary-not-a-real-secret"},
                    headers=h,
                ).status_code,
                200,
            )
        self.assertEqual(
            a.get("/api/pluggy/config", base_url=self.origin).json["client_id"], "organization-a"
        )
        self.assertEqual(
            b.get("/api/pluggy/config", base_url=self.origin).json["client_id"], "organization-b"
        )
        users = a.get("/api/users", base_url=self.origin).json["users"]
        self.assertNotIn("org-b", [u["login"] for u in users])
        # Nem um parâmetro forjado consegue trocar a organização da sessão.
        self.assertEqual(
            a.get("/api/data?workspace_id=" + str(self.ids[1]), base_url=self.origin).json[
                "records"
            ][0]["name"],
            self.schemas[0],
        )

    def test_editor_and_csrf(self):
        c, h = self.client("editor-a")
        self.assertEqual(c.get("/api/users", base_url=self.origin).status_code, 403)
        self.assertEqual(c.get("/api/crypto/connections", base_url=self.origin).status_code, 403)
        self.assertEqual(c.put("/api/budget", base_url=self.origin, json={}).status_code, 403)
        self.assertEqual(
            c.post(
                "/api/auth/logout",
                base_url=self.origin,
                json={},
                headers={**h, "Origin": "https://attacker.example"},
            ).status_code,
            403,
        )
        self.assertEqual(
            c.post("/api/auth/logout", base_url=self.origin, json={}, headers=h).status_code, 200
        )

    def test_rate_limit_shared_between_sessions(self):
        for _ in range(10):
            c, h = self.client()
            response = c.post(
                "/api/auth/login",
                base_url=self.origin,
                json={"login": "nonexistent-test", "password": "wrong-password"},
                headers=h,
            )
            self.assertEqual(response.status_code, 401)
        c, h = self.client()
        self.assertEqual(
            c.post(
                "/api/auth/login",
                base_url=self.origin,
                json={"login": "nonexistent-test", "password": "wrong-password"},
                headers=h,
            ).status_code,
            429,
        )

    def test_no_cache_and_security_headers(self):
        c, h = self.client("org-a")
        response = c.get("/api/data", base_url=self.origin)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        cookie = c.get("/api/auth/me", base_url=self.origin).headers.get("Set-Cookie", "")
        # Uma mutação da sessão garante emissão do cookie para conferir flags.
        response = c.post(
            "/api/auth/login",
            base_url=self.origin,
            json={"login": "org-a", "password": self.password},
            headers=h,
        )
        cookie = response.headers["Set-Cookie"]
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)

    def test_password_change_revokes_sessions(self):
        admin, h = self.client("org-a")
        name = "password-target"
        create = admin.post(
            "/api/users",
            base_url=self.origin,
            headers=h,
            json={"login": name, "password": self.password, "role": "editor"},
        )
        self.assertEqual(create.status_code, 201)
        user_id = create.json["user"]["id"]
        old_session, _ = self.client(name)
        new_password = "Temporary-new-password-123!"
        payload = {"password": new_password, "password_confirmation": new_password}
        self.assertEqual(
            admin.put(
                f"/api/users/{user_id}/password",
                base_url=self.origin,
                headers=h,
                json=payload | {"password_confirmation": "different"},
            ).status_code,
            400,
        )
        response = admin.put(
            f"/api/users/{user_id}/password", base_url=self.origin, headers=h, json=payload
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(old_session.get("/api/data", base_url=self.origin).status_code, 401)
        c, ch = self.client()
        self.assertEqual(
            c.post(
                "/api/auth/login",
                base_url=self.origin,
                headers=ch,
                json={"login": name, "password": self.password},
            ).status_code,
            401,
        )
        self.assertEqual(
            c.post(
                "/api/auth/login",
                base_url=self.origin,
                headers=ch,
                json={"login": name, "password": new_password},
            ).status_code,
            200,
        )

    def test_user_deletion_removes_access_not_finances(self):
        admin, h = self.client("org-a")
        created = admin.post(
            "/api/users",
            base_url=self.origin,
            headers=h,
            json={"login": "delete-target", "password": self.password, "role": "editor"},
        )
        self.assertEqual(created.status_code, 201)
        user_id = created.json["user"]["id"]
        victim, _ = self.client("delete-target")
        before = admin.get("/api/data", base_url=self.origin).json["records"]
        self.assertEqual(
            admin.delete(
                f"/api/users/{user_id}", base_url=self.origin, headers=h, json={}
            ).status_code,
            204,
        )
        self.assertEqual(victim.get("/api/data", base_url=self.origin).status_code, 401)
        self.assertNotIn(
            "delete-target",
            [u["login"] for u in admin.get("/api/users", base_url=self.origin).json["users"]],
        )
        self.assertEqual(before, admin.get("/api/data", base_url=self.origin).json["records"])
        c, ch = self.client()
        self.assertEqual(
            c.post(
                "/api/auth/login",
                base_url=self.origin,
                headers=ch,
                json={"login": "delete-target", "password": self.password},
            ).status_code,
            401,
        )

    def test_user_management_permissions_and_last_admin(self):
        a, ha = self.client("org-a")
        b, hb = self.client("org-b")
        editor, he = self.client("editor-a")
        own = next(
            u
            for u in a.get("/api/users", base_url=self.origin).json["users"]
            if u["login"] == "org-a"
        )
        foreign = b.get("/api/users", base_url=self.origin).json["users"][0]
        payload = {
            "password": "Temporary-password-123",
            "password_confirmation": "Temporary-password-123",
        }
        self.assertEqual(
            a.delete(
                f"/api/users/{own['id']}", base_url=self.origin, headers=ha, json={}
            ).status_code,
            409,
        )
        self.assertEqual(
            a.delete(
                f"/api/users/{foreign['id']}", base_url=self.origin, headers=ha, json={}
            ).status_code,
            404,
        )
        self.assertEqual(
            a.put(
                f"/api/users/{foreign['id']}/password",
                base_url=self.origin,
                headers=ha,
                json=payload,
            ).status_code,
            404,
        )
        self.assertEqual(
            editor.delete(
                f"/api/users/{own['id']}", base_url=self.origin, headers=he, json={}
            ).status_code,
            403,
        )
        self.assertEqual(
            editor.put(
                f"/api/users/{own['id']}/password", base_url=self.origin, headers=he, json=payload
            ).status_code,
            403,
        )

    def test_same_organization_private_and_new_user_empty(self):
        admin, h = self.client("org-a")
        editor, _ = self.client("editor-a")
        own = admin.get("/api/data", base_url=self.origin).json
        other = editor.get("/api/data", base_url=self.origin).json
        self.assertNotEqual(own["records"][0]["name"], other["records"][0]["name"])
        self.assertEqual(other["records"][0]["name"], self.schemas[2])
        forged = editor.get("/api/data?user_id=" + str(self.user_ids[0]), base_url=self.origin).json
        self.assertEqual(forged["records"][0]["name"], self.schemas[2])
        created = admin.post(
            "/api/users",
            base_url=self.origin,
            headers=h,
            json={"login": "private-new", "password": self.password, "role": "administrador"},
        )
        self.assertEqual(created.status_code, 201, created.json)
        new, _ = self.client("private-new")
        data = new.get("/api/data", base_url=self.origin).json
        self.assertEqual(data["records"], [])
        self.assertEqual(data["settings"]["user_name"], "private-new")
        self.assertEqual(
            new.get("/api/crypto/connections", base_url=self.origin).json["connections"], []
        )
        self.assertFalse(new.get("/api/pluggy/config", base_url=self.origin).json["saved"])

    def test_notifications_are_individual_and_read_state_persists(self):
        from notifications import today_local

        a, ha = self.client("org-a")
        b, hb = self.client("org-b")
        response = a.post(
            "/api/records",
            base_url=self.origin,
            headers=ha,
            json={
                "kind": "expenses",
                "name": "Private notification cost",
                "amount": "10",
                "detail": "Custo Fixo",
                "due_date": today_local().isoformat(),
                "status": "Pendente",
                "is_fixed_cost": True,
            },
        )
        self.assertEqual(response.status_code, 201)
        feed = a.get("/api/notifications", base_url=self.origin)
        self.assertEqual(feed.status_code, 200)
        own = next(
            item
            for item in feed.json["notifications"]
            if "Private notification cost" in item["message"]
        )
        self.assertFalse(own["read"])
        other = b.get("/api/notifications", base_url=self.origin).json
        self.assertFalse(
            any("Private notification cost" in item["message"] for item in other["notifications"])
        )
        self.assertEqual(
            a.put(
                "/api/notifications/read",
                base_url=self.origin,
                headers=ha,
                json={"keys": [own["key"]]},
            ).status_code,
            200,
        )
        again = a.get("/api/notifications", base_url=self.origin).json
        self.assertTrue(
            next(item for item in again["notifications"] if item["key"] == own["key"])["read"]
        )

    def test_push_management_requires_login_and_csrf(self):
        guest, headers = self.client()
        self.assertEqual(guest.get("/api/push/config", base_url=self.origin).status_code, 401)
        self.assertEqual(
            guest.post(
                "/api/push/subscribe", base_url=self.origin, json={}, headers=headers
            ).status_code,
            401,
        )
        user, headers = self.client("org-a")
        self.assertEqual(
            user.post("/api/push/subscribe", base_url=self.origin, json={}).status_code, 403
        )
        self.assertEqual(
            user.post("/api/push/unsubscribe", base_url=self.origin, json={}).status_code, 403
        )


if __name__ == "__main__":
    unittest.main()
