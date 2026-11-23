"""Testes de fila usando somente um schema temporário no PostgreSQL local."""

import json, secrets, unittest, uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch
import psycopg
from psycopg.rows import dict_row
from psycopg import sql
from dotenv import dotenv_values
from flask import g
from app import app
from auto_sync import enqueue, run_job, request_auto_sync


class AutoSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = dotenv_values(".env")
        if not config.get("DATABASE_URL"):
            raise unittest.SkipTest("PostgreSQL local não configurado.")
        cls.url = config["DATABASE_URL"]
        cls.schema = "auto_sync_test_" + secrets.token_hex(8)
        with psycopg.connect(cls.url, row_factory=dict_row) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
            conn.execute(
                sql.SQL("SET LOCAL search_path TO {},pg_catalog").format(sql.Identifier(cls.schema))
            )
            conn.execute(
                Path("Backend/SQL/control_schema.sql")
                .read_text()
                .replace("public.", cls.schema + ".")
            )
            conn.execute(Path("Backend/SQL/schema.sql").read_text())
            conn.execute(
                "INSERT INTO app_users(id,login,password_hash,role) VALUES(1,'sync-test','not-a-login-hash','administrador')"
            )

        class Connection:
            def __init__(self):
                self.raw = psycopg.connect(cls.url, row_factory=dict_row)
                self.raw.execute(
                    sql.SQL("SET search_path TO {},pg_catalog").format(sql.Identifier(cls.schema))
                )
                self.raw.commit()

            def execute(self, statement, params=None):
                if isinstance(statement, str):
                    statement = statement.replace("public.", cls.schema + ".")
                return self.raw.execute(statement, params)

            def commit(self):
                self.raw.commit()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.raw.__exit__(*args)

        cls.connection = Connection
        cls.database = patch("app.connect", side_effect=lambda **kwargs: Connection())
        cls.database.start()

    @classmethod
    def tearDownClass(cls):
        cls.database.stop()
        with psycopg.connect(cls.url) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))

    def setUp(self):
        with self.connection() as conn:
            conn.execute("DELETE FROM sync_jobs")
            conn.execute("DELETE FROM sync_revisions")

    def job(self):
        with self.connection() as conn:
            return conn.execute("SELECT * FROM sync_jobs").fetchone()

    def test_repeated_requests_publish_once_without_credentials(self):
        with patch("auto_sync.queue_send") as send:
            self.assertTrue(enqueue(1, "products", 7))
            self.assertFalse(enqueue(1, "products", 7))
            self.assertEqual(send.call_count, 2)
            self.assertEqual(send.call_args_list[0].args[2], send.call_args_list[1].args[2])
            payload = send.call_args.args[1]
            self.assertEqual(set(payload), {"key", "generation"})

    def test_worker_generation_idempotency_and_revision(self):
        with patch("auto_sync.queue_send"):
            enqueue(1, "crypto", 7)
        row = self.job()
        payload = {"key": row["job_key"], "generation": str(row["generation"])}
        with patch("auto_sync.apply_job") as apply:
            run_job({**payload, "generation": str(uuid.uuid4())})
            apply.assert_not_called()
            run_job(payload)
            run_job(payload)
            apply.assert_called_once()
        with self.connection() as conn:
            self.assertEqual(
                conn.execute("SELECT revision FROM sync_revisions").fetchone()["revision"], 1
            )

    def test_error_preserves_retry_and_does_not_mark_success(self):
        with patch("auto_sync.queue_send"):
            enqueue(1, "crypto", 7)
        row = self.job()
        payload = {"key": row["job_key"], "generation": str(row["generation"])}
        with patch("auto_sync.apply_job", side_effect=RuntimeError("provider")):
            with self.assertRaises(RuntimeError):
                run_job(payload)
        self.assertEqual(self.job()["state"], "error")
        self.assertIsNone(self.job()["last_success"])
        with patch("auto_sync.apply_job"):
            run_job(payload)
        self.assertEqual(self.job()["state"], "done")

    def test_event_during_execution_schedules_one_followup(self):
        with patch("auto_sync.queue_send") as send:
            enqueue(1, "crypto", 7)
            row = self.job()
            with patch(
                "auto_sync.apply_job", side_effect=lambda job: enqueue(1, "crypto", 7, force=True)
            ):
                run_job({"key": row["job_key"], "generation": str(row["generation"])})
            self.assertEqual(send.call_count, 2)
            self.assertEqual(self.job()["state"], "queued")

    def test_api_ignores_user_id_supplied_by_client(self):
        with app.test_request_context(
            "/api/auto-sync/request",
            method="POST",
            json={"page": "overview", "month": "2026-11", "user_id": 999},
        ):
            g.user = {"id": 1}
            with patch("auto_sync.dispatch_user") as dispatch:
                response = request_auto_sync()
                self.assertTrue(response.json["queued"])
                dispatch.assert_called_once_with(1, "overview", "2026-11")
