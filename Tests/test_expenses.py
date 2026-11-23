# BLOCO — Cenários de teste para validação das regras de expenses.
import unittest
from app import validate_record


class ExpenseTests(unittest.TestCase):
    def test_statement_name_and_fixed_category(self):
        values = validate_record(
            {
                "kind": "expenses",
                "name": "Internet",
                "statement_name": "PROVEDOR NET",
                "detail": "Internet",
                "amount": "99.90",
                "due_date": "2026-12-10",
                "is_fixed_cost": True,
            }
        )
        self.assertEqual(values[6], "Pendente")
        self.assertEqual(values[7], "PROVEDOR NET")
        self.assertTrue(values[8])

    def test_invalid_expense(self):
        base = {
            "kind": "expenses",
            "name": "Internet",
            "detail": "Internet",
            "amount": "99.90",
            "due_date": "2026-12-10",
        }
        for change in [{"detail": ""}, {"due_date": ""}, {"statement_name": "x" * 121}]:
            with self.assertRaises(ValueError):
                validate_record({**base, **change})


if __name__ == "__main__":
    unittest.main()
