"""Fluxo real em schema temporário: transação nova → outbox → entrega Android, sem rede."""
import unittest
import json
from contextlib import contextmanager
from unittest.mock import patch
from flask import g
from app import app
from notifications import note_transactions
from push_notifications import flush_transaction_pushes
from test_support import financial_test_connection


class TransactionPushTests(unittest.TestCase):
    def test_commit_outbox_deduplication_retry_and_device_isolation(self):
        with financial_test_connection() as raw:
            raw.execute("CREATE TABLE app_users(id BIGINT PRIMARY KEY,session_version INTEGER,deleted_at TIMESTAMPTZ)")
            raw.execute("CREATE TABLE push_subscriptions(endpoint_hash TEXT PRIMARY KEY,user_id BIGINT,session_version INTEGER,android_app BOOLEAN,subscription BYTEA,created_at TIMESTAMPTZ DEFAULT NOW()-INTERVAL '1 hour')")
            raw.execute("CREATE TABLE push_events(id UUID PRIMARY KEY,user_id BIGINT,route TEXT,record_id BIGINT,period TEXT,kind TEXT DEFAULT 'transaction',created_at TIMESTAMPTZ DEFAULT NOW())")
            raw.execute("CREATE TABLE push_deliveries(event_id UUID,endpoint_hash TEXT,PRIMARY KEY(event_id,endpoint_hash))")
            raw.execute("INSERT INTO app_users VALUES(1,1,NULL),(2,1,NULL)")
            raw.execute("INSERT INTO push_subscriptions(endpoint_hash,user_id,session_version,android_app) VALUES('android',1,1,TRUE),('web',1,1,FALSE),('other-user',2,1,TRUE),('old-session',1,0,TRUE)")
            class Connection:
                info = raw.info
                def execute(self, statement, params=None):
                    return raw.execute(statement.replace('public.', ''), params)
                def __enter__(self): return self
                def __exit__(self, *args): pass
            conn = Connection()
            @contextmanager
            def connect(**kwargs): yield conn
            def tx(identifier):
                return dict(id=identifier,amount=10,currency='BRL',description='Sintético',date='2026-11-19')
            account = raw.execute("INSERT INTO records(kind,name,amount) VALUES('accounts','Conta fictícia',10) RETURNING id").fetchone()['id']
            with app.test_request_context('/internal/test'), patch('app.connect',connect), patch('push_notifications.send_subscription',return_value=('android','sent')) as send:
                g.user = {'id':1}
                note_transactions(conn,'bank',account,'Conta',[tx('old')],'2026-11')
                self.assertEqual(raw.execute('SELECT COUNT(*) AS n FROM push_events').fetchone()['n'],0)
                # Rollback elimina tanto a transação conhecida quanto o evento a enviar.
                with self.assertRaises(RuntimeError):
                    with raw.transaction():
                        note_transactions(conn,'bank',account,'Conta',[tx('rollback')],'2026-11')
                        raise RuntimeError('rollback simulado')
                self.assertEqual(raw.execute('SELECT COUNT(*) AS n FROM push_events').fetchone()['n'],0)
                note_transactions(conn,'bank',account,'Conta',[tx('old'),tx('new')],'2026-11')
                note_transactions(conn,'bank',account,'Conta',[tx('old'),tx('new')],'2026-11')
                note_transactions(conn,'bank',account,'Conta',[tx('silent')],'2026-10',silent=True)
                note_transactions(conn,'bank',account,'Conta',[tx('cache')],'2026-11',push=False)
                self.assertEqual(raw.execute('SELECT COUNT(*) AS n FROM push_events').fetchone()['n'],1)
                send.return_value = ('android','retry')
                self.assertEqual(flush_transaction_pushes(1),(0,1))
                send.return_value = ('android','sent')
                self.assertEqual(flush_transaction_pushes(1),(1,0))
                self.assertEqual(flush_transaction_pushes(1),(0,0))
                self.assertEqual(flush_transaction_pushes(2),(0,0))
                self.assertEqual(send.call_count,2)
                self.assertTrue(all(call.args[0]['endpoint_hash']=='android' for call in send.call_args_list))
                self.assertEqual(raw.execute('SELECT COUNT(*) AS n FROM push_deliveries').fetchone()['n'],1)
                card = raw.execute("INSERT INTO records(kind,name,amount) VALUES('cards','Cartão fictício',100) RETURNING id").fetchone()['id']
                note_transactions(conn,'card',card,'Cartão',[tx('old-card')],'2026-11')
                note_transactions(conn,'card',card,'Cartão',[tx('old-card'),tx('new-card')],'2026-11')
                self.assertEqual(flush_transaction_pushes(1),(1,0))
                self.assertIn('cartão de crédito',json.loads(send.call_args.args[1])['body'])
                self.assertEqual(raw.execute('SELECT COUNT(*) AS n FROM push_deliveries').fetchone()['n'],2)


if __name__ == '__main__': unittest.main()
