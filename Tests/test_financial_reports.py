"""Cálculos históricos, PDF real e autorização, sem contas ou serviços externos."""
import calendar
import unittest
from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from financial_reports import report_period, summarize_report, render_pdf, load_data


def fixtures(kind):
    if kind == "investments":
        return {"sources": [], "history": [
            {"day": date(2025, 12, 30), "amount": Decimal("1000")},
            {"day": date(2026, 1, 4), "amount": Decimal("1100")},
            {"day": date(2026, 1, 25), "amount": Decimal("1200")},
            {"day": date(2026, 3, 10), "amount": Decimal("1500")},
        ], "flows": [{"day": date(2026, 1, 4), "amount": Decimal("200"), "direction": "entrada", "description": "Aporte da reserva"},
                     {"day": date(2026, 1, 20), "amount": Decimal("50"), "direction": "saida", "description": "Retirada"}]}
    source = {"id": 1, "name": "Cartão principal" if kind == "card" else "Conta corrente", "institution": "Banco de exemplo", "pluggy_data": {"currency": "BRL"}}
    def tx(id, amount, description, day="2026-01-04", status="POSTED", currency="BRL", **more):
        return {"id": id, "date": day, "amount": amount, "description": description, "status": status, "currency": currency, **more}
    txs = [tx("a", "100", "Compra do mercado <loja> & serviços", day="2025-12-29" if kind == "card" else "2026-01-04"),
           tx("b", "-20", "Estorno", operation_type="ESTORNO"),
           tx("c", "70", "Compra pendente", status="PENDING"),
           tx("d", "-80", "Pagamento da fatura", operation_type="PAGAMENTO_FATURA"),
           tx("usd", "5", "Compra internacional", currency="USD")]
    period = {"source_id": 1, "month": date(2026, 1, 1), "transactions": txs, "bills": [{"amount": "80", "currency": "BRL"}], "synced_at": None, "period_end": date(2026, 1, 31)}
    return {"sources": [source], "periods": [period], "openings": [{"account_id": 1, "period_start": date(2026, 1, 1), "currency": "BRL", "amount": Decimal("500")} ]}


def report(kind="card", mode="annual", data=None):
    return summarize_report(kind, mode, date(2026, 1, 1), date(2026, 12, 31) if mode == "annual" else date(2026, 1, 31), data or fixtures(kind))


class ReportsTests(unittest.TestCase):
    def test_validation(self):
        for args in [{}, {"type": "card", "period": "monthly", "month": "2026-13"}, {"type": "bank", "period": "annual", "year": "1 OR 1=1"}, {"type": "investments", "period": "annual", "year": "2026", "source": "1"}]:
            with self.assertRaises(ValueError):
                report_period(args)
        parsed = report_period({"type": "bank", "period": "monthly", "month": "2024-02"})
        self.assertEqual(parsed[3], date(2024, 2, 29))

    def test_card_reference_month_payment_pending_and_currency(self):
        data = report()
        january = data["groups"]["BRL"][date(2026, 1, 1)]
        self.assertEqual(january["incoming"], Decimal("100"))
        self.assertEqual(january["outgoing"], Decimal("20"))
        self.assertEqual(january["net"], Decimal("80"))
        self.assertEqual(january["payments"], Decimal("80"))
        self.assertEqual(january["pending"], Decimal("70"))
        self.assertEqual(data["groups"]["USD"][date(2026, 1, 1)]["net"], Decimal("5"))
        self.assertEqual(data["coverage"][date(2026, 2, 1)], (0, 1))
        self.assertEqual(data["details"][0]["date"], "2025-12-29")

    def test_duplicate_transactions_not_counted_twice(self):
        data = fixtures("card")
        data["periods"][0]["transactions"] *= 2
        self.assertEqual(report(data=data)["groups"]["BRL"][date(2026, 1, 1)]["net"], Decimal("80"))

    def test_previous_payments_are_not_refunds_in_monthly_and_annual_pdf(self):
        from pypdf import PdfReader
        data = fixtures("card")
        payment = data["periods"][0]["transactions"][3]
        payment.pop("operation_type")
        payment["description"] = "Pagamentos de faturas anteriores"
        for mode in ["monthly", "annual"]:
            result = report("card", mode, data)
            totals = result["groups"]["BRL"][date(2026, 1, 1)]
            self.assertEqual(totals["outgoing"], Decimal("20"))
            self.assertEqual(totals["payments"], Decimal("80"))
            self.assertEqual(totals["net"], Decimal("80"))
            self.assertTrue(next(t for t in result["details"] if t["id"] == "d")["payment"])
            pdf = PdfReader(BytesIO(render_pdf(result)))
            self.assertIn("Pagamentos de faturas", "".join(p.extract_text() for p in pdf.pages))

    def test_bank_signs_and_opening_balance(self):
        data = report("bank", "monthly")
        values = data["groups"]["BRL"][date(2026, 1, 1)]
        self.assertEqual(values["incoming"], Decimal("100"))
        self.assertEqual(values["outgoing"], Decimal("100"))
        self.assertEqual(values["closing"], Decimal("500"))
        self.assertEqual(values["opening"], Decimal("500"))

    def test_actual_validos_normais_description_for_445_03(self):
        data = fixtures("card")
        period = data["periods"][0]
        period["month"] = date(2026, 10, 1)
        period["transactions"] = [
            {"id": "buy", "date": "2026-09-28", "amount": "500", "currency": "BRL", "status": "POSTED", "description": "Compra"},
            {"id": "refund", "date": "2026-09-29", "amount": "-30", "currency": "BRL", "status": "POSTED", "description": "Estorno da compra"},
            {"id": "pay", "date": "2026-09-29", "amount": "-445.03", "currency": "BRL", "status": "POSTED", "description": "Pagamentos Validos Normais"},
        ]
        for mode, start in [("monthly", date(2026, 10, 1)), ("annual", date(2026, 1, 1))]:
            result = summarize_report("card", mode, start, date(2026, 12, 31) if mode == "annual" else date(2026, 10, 31), data)
            values = result["groups"]["BRL"][date(2026, 10, 1)]
            self.assertEqual(values["outgoing"], Decimal("30"))
            self.assertEqual(values["payments"], Decimal("445.03"))
            self.assertEqual(values["net"], Decimal("470"))

    def test_investments_historical_positions_not_current_holdings(self):
        data = report("investments")
        self.assertEqual(data["opening"], Decimal("1000"))
        self.assertEqual(data["closing"], Decimal("1500"))
        self.assertFalse(any(r["day"].month == 2 for r in data["history"]))

    def test_six_pdfs_and_branding(self):
        from pypdf import PdfReader
        for kind in ("card", "bank", "investments"):
            for mode in ("monthly", "annual"):
                pdf = render_pdf(report(kind, mode))
                self.assertTrue(pdf.startswith(b"%PDF"))
                reader = PdfReader(BytesIO(pdf))
                text = "\n".join(page.extract_text() for page in reader.pages)
                self.assertIn("Optimus Finance", text)
                self.assertIn("2026", text)
                self.assertNotIn("2025-12-30", text)
                self.assertTrue(reader.pages[0].images)

    def test_pdf_pagination_and_escaped_descriptions(self):
        from pypdf import PdfReader
        data = fixtures("card")
        original = data["periods"][0]["transactions"][0]
        data["periods"][0]["transactions"] = [{**original, "id": str(i), "description": "Compra <teste> & revisão " + str(i)} for i in range(90)]
        pdf = render_pdf(report("card", "monthly", data))
        reader = PdfReader(BytesIO(pdf))
        self.assertGreater(len(reader.pages), 2)
        self.assertTrue(all("Optimus Finance" in page.extract_text() for page in reader.pages))
        self.assertIn("Compra <teste> & revisão", "".join(p.extract_text() for p in reader.pages))

    def test_private_endpoint_and_pdf_response(self):
        from app import app
        from test_support import authenticate_test_client
        client = app.test_client()
        authenticate_test_client(self, client)
        with patch("financial_reports.load_data", return_value=fixtures("card")) as load:
            response = client.get("/api/reports/pdf?type=card&period=monthly&month=2026-01&source=all")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn("no-store", response.headers["Cache-Control"])
        load.assert_called_once_with("card", date(2026, 1, 1), date(2026, 1, 31), "all")
        with client.session_transaction() as session:
            session.clear()
        self.assertEqual(client.get("/api/reports/pdf?type=card&period=annual&year=2026").status_code, 401)


if __name__ == "__main__":
    unittest.main()
