import unittest
from contextlib import contextmanager
from unittest.mock import patch
from app import app, validate_record
from test_support import financial_test_connection, authenticate_test_client


class CategoryTypeTests(unittest.TestCase):
    def test_invalid_type_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_record(dict(kind='categories',name='Teste',category_type='cards'))

    def test_category_type_create_and_edit(self):
        client=app.test_client()
        authenticate_test_client(self,client)
        with financial_test_connection() as conn:
            @contextmanager
            def connection(**kwargs):
                yield conn
            with patch('app.connect',connection):
                payload=dict(kind='categories',name='Bônus',detail='Renda extra',category_type='incomes')
                created=client.post('/api/records',json=payload)
                self.assertEqual(created.status_code,201)
                row=created.get_json()
                self.assertEqual(row['category_type'],'incomes')
                updated=client.put('/api/records/'+str(row['id']),json={**payload,'category_type':'expenses'})
                self.assertEqual(updated.status_code,200)
                self.assertEqual(updated.get_json()['category_type'],'expenses')

    def test_legacy_client_defaults_to_fixed_cost(self):
        self.assertEqual(validate_record(dict(kind='categories',name='Moradia'))[-1],'expenses')
