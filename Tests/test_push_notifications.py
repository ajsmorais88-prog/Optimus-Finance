"""Testes sem envio a dispositivos ou alteração de dados financeiros reais."""

import base64
import json
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from requests import Response
from app import app
from pluggy_config import cipher
from push_notifications import validate_subscription, vapid_keys, deliver_event


def subscription():
    public = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    return dict(
        endpoint="https://fcm.googleapis.com/fcm/send/test-only",
        keys=dict(
            p256dh=base64.urlsafe_b64encode(public).decode().rstrip("="),
            auth=base64.urlsafe_b64encode(b"0123456789abcdef").decode().rstrip("="),
        ),
    )


class PushValidationTests(unittest.TestCase):
    def test_valid_subscription_and_invalid_keys(self):
        value = subscription()
        self.assertEqual(validate_subscription(value), value)
        value["keys"]["auth"] = "wrong"
        with self.assertRaises(ValueError):
            validate_subscription(value)

    def test_push_destination_cannot_be_arbitrary_or_internal(self):
        for url in [
            "http://fcm.googleapis.com/push",
            "https://127.0.0.1/push",
            "https://fcm.googleapis.com.evil.test/push",
            "https://user:pass@fcm.googleapis.com/push",
            "https://fcm.googleapis.com:8443/push",
            "https://example.com/push",
        ]:
            value = subscription()
            value["endpoint"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_subscription(value)

    def test_actual_push_encryption_and_vapid_signing_without_network(self):
        from pywebpush import webpush

        with app.app_context():
            public, private = vapid_keys()
            self.assertEqual((public, private), vapid_keys())
            session = Mock()
            response = Response()
            response.status_code = 201
            session.post.return_value = response
            result = webpush(
                subscription(),
                data='{"body":"teste"}',
                vapid_private_key=private,
                vapid_claims={"sub": "https://controle-financeiro-seven-sooty.vercel.app"},
                requests_session=session,
            )
            self.assertEqual(result.status_code, 201)
            self.assertIn("authorization", session.post.call_args.kwargs["headers"])


class WebhookTests(unittest.TestCase):
    def request(self, payload, secret="valid-secret", item="item-own", account=True):
        channel = dict(
            user_id=3,
            session_version=1,
            deleted_at=None,
            secret=cipher().encrypt(b"valid-secret"),
            client_hash=__import__("hashlib").sha256(b"client-own").hexdigest(),
        )
        record = dict(id=11, kind="accounts", name="Conta privada", connection_id=4)

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql, params=None):
                if "SELECT c.*" in sql:
                    return Mock(fetchone=lambda: channel)
                if "SELECT * FROM records" in sql:
                    return Mock(fetchone=lambda: record if account else None)
                return Mock(fetchone=lambda: None)

        with (
            patch("auto_sync.enqueue"),
            patch("app.connect", return_value=Connection()),
            patch(
                "push_notifications.read_config",
                return_value=dict(item_id=item, client_id="client-own"),
            ),
            patch("push_notifications.deliver_event", return_value=True) as send,
        ):
            result = app.test_client().post(
                "/hooks/pluggy/" + str(uuid.uuid4()),
                json=payload,
                headers={"X-Finance-Webhook-Secret": secret},
            )
            return result, send.call_count

    def test_no_secret_does_not_read_database(self):
        with patch("app.connect") as database:
            result = app.test_client().post("/hooks/pluggy/" + str(uuid.uuid4()), json={})
            self.assertEqual(result.status_code, 401)
            database.assert_not_called()

    def test_wrong_secret_rejected(self):
        result, count = self.request({}, secret="wrong-secret")
        self.assertEqual(result.status_code, 401)
        self.assertEqual(count, 0)

    def test_other_item_or_unknown_account_never_sends(self):
        payload = dict(
            event="transactions/created",
            eventId=str(uuid.uuid4()),
            itemId="other-item",
            accountId="external",
        )
        result, count = self.request(payload)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(count, 0)
        payload["itemId"] = "item-own"
        result, count = self.request(payload, account=False)
        self.assertEqual(count, 0)

    def test_own_event_waits_for_persisted_transactions_and_ignores_payload_url(self):
        payload = dict(
            event="transactions/created",
            eventId=str(uuid.uuid4()),
            itemId="item-own",
            accountId="external",
            createdTransactionsLink="http://127.0.0.1/private",
        )
        with patch("push_notifications.call") as outbound:
            result, count = self.request(payload)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(count, 0)
            outbound.assert_not_called()


class PushDeliveryTests(unittest.TestCase):
    def test_delivery_deduplicated_private_and_bound_to_session_version(self):
        identifier = uuid.uuid4()
        sent = set()
        payloads = []
        event = dict(
            id=identifier,
            user_id=3,
            session_version=4,
            deleted_at=None,
            created_at=datetime.now(timezone.utc),
            route="card_bill",
            record_id=18,
            period="2026-11",
        )
        row = dict(
            endpoint_hash="endpoint",
            subscription=cipher().encrypt(json.dumps(subscription()).encode()),
        )

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql, params=None):
                if "pg_try_advisory" in sql:
                    return Mock(fetchone=lambda: dict(locked=True))
                if "SELECT e.*" in sql:
                    return Mock(fetchone=lambda: event)
                if "SELECT s.*" in sql:
                    self_test.assertEqual(params[:2], (3, 4))
                    return Mock(fetchall=lambda: [] if sent else [row])
                if "INSERT INTO public.push_deliveries" in sql:
                    sent.add(params)
                return Mock()

        def send(*args, **kwargs):
            payloads.append(json.loads(kwargs["data"]))
            response = Response()
            response.status_code = 201
            return response

        self_test = self
        with (
            app.app_context(),
            patch("app.connect", return_value=Connection()),
            patch("pywebpush.webpush", side_effect=send),
        ):
            self.assertTrue(deliver_event(identifier))
            self.assertTrue(deliver_event(identifier))
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["user_id"], 3)
        self.assertEqual(payloads[0]["body"], "Novas transações no cartão de crédito.")
        self.assertNotIn("amount", payloads[0])
        self.assertNotIn("message", payloads[0])


class FixedCostReminderTests(unittest.TestCase):
    def test_due_window_overdue_and_paid_are_filtered(self):
        from datetime import date, timedelta
        from push_notifications import fixed_cost_reminders

        today = date(2026, 11, 14)
        records = [
            dict(id=i, kind="expenses", due_date=today + timedelta(days=days), status=status)
            for i, days, status in [
                (1, 2, "Pendente"),
                (2, 0, "Pendente"),
                (3, -1, "Pendente"),
                (4, 3, "Pendente"),
                (5, -4, "Pago"),
                (6, -2, "Pendente"),
            ]
        ]
        result = list(fixed_cost_reminders(records, [dict(expense_id=6)], today))
        self.assertEqual(
            [(r["record_id"], r["kind"]) for r in result],
            [(1, "fixed_due"), (2, "fixed_due"), (3, "fixed_overdue")],
        )

    def test_reminder_identifier_is_stable_per_user_due_date_and_phase(self):
        from push_notifications import create_reminder_event

        row = dict(record_id=12, due="2026-11-16", period="2026-11", kind="fixed_due")

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, *args):
                return Mock()

        with patch("app.connect", return_value=Connection()):
            first = create_reminder_event(3, row)
            self.assertEqual(first, create_reminder_event(3, row))
            self.assertNotEqual(first, create_reminder_event(4, row))
            self.assertNotEqual(first, create_reminder_event(3, {**row, "kind": "fixed_overdue"}))

    def test_daily_task_rejects_missing_or_wrong_secret_without_database(self):
        import os

        with (
            patch.dict(os.environ, {"CRON_SECRET": "test-reminder-secret"}),
            patch("app.connect") as database,
        ):
            client = app.test_client()
            self.assertEqual(client.get("/tasks/fixed-cost-reminders").status_code, 401)
            self.assertEqual(
                client.get(
                    "/tasks/fixed-cost-reminders", headers={"Authorization": "Bearer wrong"}
                ).status_code,
                401,
            )
            database.assert_not_called()

    def test_cost_delivery_selects_only_android_subscriptions(self):
        from push_notifications import deliver_event, push_body

        event = dict(
            id=uuid.uuid4(),
            user_id=3,
            session_version=4,
            deleted_at=None,
            created_at=datetime.now(timezone.utc),
            kind="fixed_overdue",
            route="fixed_costs",
            record_id=12,
            period="2026-11",
        )
        queries = []

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql, params=None):
                if "pg_try_advisory" in sql:
                    return Mock(fetchone=lambda: dict(locked=True))
                if "SELECT e.*" in sql:
                    return Mock(fetchone=lambda: event)
                if "SELECT s.*" in sql:
                    queries.append((sql, params))
                    return Mock(fetchall=lambda: [])
                return Mock()

        with app.app_context(), patch("app.connect", return_value=Connection()):
            self.assertTrue(deliver_event(event["id"]))
        self.assertIn("s.android_app", queries[0][0])
        self.assertEqual(queries[0][1][3], "fixed_overdue")
        self.assertIn("vencido", push_body(event))
        self.assertIn("próximo", push_body({**event, "kind": "fixed_due"}))


class DevicePushTestEndpointTests(unittest.TestCase):
    def request_test(self, registered=True, allowed=True, delivery="sent"):
        from flask import g
        from push_notifications import test_device_push

        queries = []

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, query, params=None):
                queries.append((query, params))
                if "SELECT * FROM public.push_subscriptions" in query:
                    return Mock(fetchone=lambda: dict(endpoint_hash="own") if registered else None)
                if "RETURNING bucket" in query:
                    return Mock(fetchone=lambda: dict(bucket="test") if allowed else None)
                return Mock()

        with app.test_request_context(
            "/api/push/test",
            method="POST",
            json={"endpoint": "https://fcm.googleapis.com/fcm/send/own"},
        ):
            g.user = dict(id=3, session_version=4)
            with (
                patch("app.connect", return_value=Connection()),
                patch(
                    "push_notifications.send_subscription", return_value=("own", delivery)
                ) as send,
            ):
                response = test_device_push()
                code = response[1] if isinstance(response, tuple) else response.status_code
                payload = json.loads(send.call_args.args[1]) if send.called else None
                return code, queries, payload, send.call_count

    def test_test_is_bound_to_own_device_and_current_session(self):
        code, queries, payload, calls = self.request_test()
        self.assertEqual(code, 200)
        self.assertEqual(queries[0][1][1:], (3, 4))
        self.assertIn("endpoint_hash=%s", queries[0][0])
        self.assertEqual(payload["kind"], "connection_test")
        self.assertEqual(payload["user_id"], 3)
        self.assertNotIn("amount", payload)
        self.assertEqual(calls, 1)

    def test_unregistered_or_rate_limited_device_is_not_contacted(self):
        for kwargs, expected in [(dict(registered=False), 409), (dict(allowed=False), 429)]:
            code, _, _, calls = self.request_test(**kwargs)
            self.assertEqual(code, expected)
            self.assertEqual(calls, 0)

    def test_expired_subscription_is_removed_and_transient_failure_is_reported(self):
        code, queries, _, _ = self.request_test(delivery="expired")
        self.assertEqual(code, 410)
        self.assertTrue(any("DELETE FROM public.push_subscriptions" in q for q, _ in queries))
        code, queries, _, _ = self.request_test(delivery="retry")
        self.assertEqual(code, 503)
        self.assertFalse(any("DELETE FROM public.push_subscriptions" in q for q, _ in queries))

    def test_endpoint_requires_login(self):
        with patch("app.connect"):
            response = app.test_client().post("/api/push/test", json={"endpoint": "test"})
        self.assertEqual(response.status_code, 401)
