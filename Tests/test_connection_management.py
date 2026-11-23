"""Edição e exclusão em schema temporário; não acessa provedores nem altera contas reais."""
import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from cryptography.fernet import Fernet
from psycopg.errors import UniqueViolation
from app import app
from pluggy_config import update_connection, delete_connection
from test_support import financial_test_connection, authenticate_test_client


class ConnectionManagementTests(unittest.TestCase):
    def test_persistence_and_preserved_records(self):
        cipher = Fernet(Fernet.generate_key())
        with financial_test_connection() as conn:
            @contextmanager
            def connection():
                yield conn
            with patch("app.connect", connection), patch("pluggy_config.cipher", return_value=cipher), patch("pluggy_config.read_application", return_value={"client_id": "test-client"}):
                encrypted = cipher.encrypt(json.dumps({"item_id": "old-item"}).encode())
                identifier = conn.execute("INSERT INTO pluggy_connections(connection_key,label,credentials) VALUES('test-key','Original',%s) RETURNING id", (encrypted,)).fetchone()["id"]
                record = conn.execute("INSERT INTO records(kind,name,amount,connection_id) VALUES('accounts','Conta de teste',10,%s) RETURNING id", (identifier,)).fetchone()["id"]
                self.assertTrue(update_connection(identifier, "Novo nome"))
                row = conn.execute("SELECT label,credentials FROM pluggy_connections WHERE id=%s", (identifier,)).fetchone()
                self.assertEqual(row["label"], "Novo nome")
                self.assertEqual(bytes(row["credentials"]), encrypted)
                self.assertTrue(update_connection(identifier, "Novo item", "new-item"))
                row = conn.execute("SELECT credentials FROM pluggy_connections WHERE id=%s", (identifier,)).fetchone()
                self.assertEqual(json.loads(cipher.decrypt(bytes(row["credentials"]))) ["item_id"], "new-item")
                self.assertIsNone(conn.execute("SELECT connection_id FROM records WHERE id=%s", (record,)).fetchone()["connection_id"])
                # Duplicatas não podem sobrescrever outra conexão.
                other = conn.execute("INSERT INTO pluggy_connections(connection_key,label,credentials) VALUES('other-key','Outra',%s) RETURNING id", (encrypted,)).fetchone()["id"]
                with self.assertRaises(UniqueViolation):
                    with conn.transaction():
                        update_connection(other, "Duplicada", "new-item")
                conn.execute("UPDATE records SET connection_id=%s WHERE id=%s", (identifier,record))
                self.assertTrue(delete_connection(identifier))
                self.assertEqual(conn.execute("SELECT amount FROM records WHERE id=%s", (record,)).fetchone()["amount"], 10)
                self.assertFalse(delete_connection(identifier))
                self.assertFalse(update_connection(identifier, "Inexistente"))

    def test_editor_cannot_manage_connections(self):
        client = app.test_client()
        authenticate_test_client(self, client)
        class Result:
            def __init__(self, value): self.value = value
            def fetchone(self): return self.value
        class Connection:
            def execute(self, statement, params=None):
                return Result({"present": True} if "EXISTS" in statement else {"id": 987654321, "login": "editor-test", "role": "editor", "workspace_id": 1})
        @contextmanager
        def identity():
            yield Connection()
        with patch("auth.identity_connect", identity), patch("pluggy.update_connection") as update, patch("pluggy.delete_connection") as delete:
            self.assertEqual(client.put("/api/pluggy/connections/1", json={"label": "Conta"}).status_code, 403)
            self.assertEqual(client.delete("/api/pluggy/connections/1", json={}).status_code, 403)
            update.assert_not_called()
            delete.assert_not_called()

    def test_routes_validation_and_not_found(self):
        client = app.test_client()
        authenticate_test_client(self, client)
        url = "/api/pluggy/connections/999999"
        with patch("pluggy.update_connection", return_value=False) as update:
            self.assertEqual(client.put(url, json={"label": " "}).status_code, 400)
            self.assertEqual(client.put(url, json=[]).status_code, 400)
            self.assertEqual(client.put(url, json={"label": "Conta", "item_id": 1}).status_code, 400)
            update.assert_not_called()
            self.assertEqual(client.put(url, json={"label": "Conta"}).status_code, 404)
        with patch("pluggy.delete_connection", return_value=False):
            self.assertEqual(client.delete(url, json={}).status_code, 404)
        with patch("pluggy.update_connection", side_effect=UniqueViolation):
            self.assertEqual(client.put(url, json={"label": "Conta"}).status_code, 409)

if __name__ == "__main__":
    unittest.main()
