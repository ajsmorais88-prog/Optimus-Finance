"""Relatórios privados em PDF a partir dos períodos efetivamente armazenados."""

import calendar
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from flask import Blueprint, g, jsonify, request, send_file

blueprint = Blueprint("financial_reports", __name__)
MONTHS = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
TITLES = {"card": "Fatura do cartão", "bank": "Extrato bancário", "investments": "Conta de investimento"}
ZERO = Decimal(0)


def report_period(args):
    kind, mode = args.get("type"), args.get("period")
    if kind not in TITLES or mode not in {"monthly", "annual"}:
        raise ValueError("Selecione o relatório e a periodicidade.")
    if mode == "monthly":
        value = args.get("month", "")
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
            raise ValueError("Selecione o mês do relatório.")
        year, month = map(int, value.split("-"))
    else:
        value = args.get("year", "")
        if not re.fullmatch(r"\d{4}", value):
            raise ValueError("Informe o ano do relatório.")
        year, month = int(value), 1
    if not 1900 <= year <= 9998:
        raise ValueError("Informe um ano entre 1900 e 9998.")
    start = date(year, month, 1)
    end = date(year, 12, 31) if mode == "annual" else date(year, month, calendar.monthrange(year, month)[1])
    source = args.get("source", "all")
    if source != "all" and (not re.fullmatch(r"[1-9]\d{0,18}", source) or kind == "investments"):
        raise ValueError("Selecione uma conta ou cartão válido.")
    return kind, mode, start, end, source


def number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Um dos valores salvos não é válido para o relatório.")
    return result


def load_data(kind, start, end, source):
    from app import connect

    with connect() as conn:
        if kind == "investments":
            history = conn.execute("SELECT day,amount FROM portfolio_history WHERE day<=%s ORDER BY day", (end,)).fetchall()
            flows = conn.execute("SELECT day,direction,amount,description FROM investment_flows WHERE day BETWEEN %s AND %s ORDER BY day,id", (start, end)).fetchall()
            return {"history": history, "flows": flows, "sources": []}
        record_kind = "cards" if kind == "card" else "accounts"
        sources = conn.execute("SELECT id,name,institution,pluggy_data FROM records WHERE kind=%s ORDER BY name,id", (record_kind,)).fetchall()
        if source != "all":
            sources = [row for row in sources if row["id"] == int(source)]
            if not sources:
                raise ValueError("Conta ou cartão não encontrado no seu painel.")
        ids = [row["id"] for row in sources]
        if kind == "card":
            periods = conn.execute("SELECT card_id AS source_id,month,transactions,bills,synced_at FROM card_month_bills WHERE card_id=ANY(%s) AND month BETWEEN %s AND %s ORDER BY month,card_id", (ids, start, end)).fetchall()
            return {"sources": sources, "periods": periods}
        periods = conn.execute("SELECT account_id AS source_id,period_start AS month,period_end,transactions,synced_at FROM bank_statement_periods WHERE account_id=ANY(%s) AND period_start<=%s ORDER BY period_start,account_id", (ids, end)).fetchall()
        openings = conn.execute("SELECT * FROM bank_opening_balances WHERE account_id=ANY(%s) AND period_start<=%s ORDER BY period_start", (ids, end)).fetchall()
        return {"sources": sources, "periods": periods, "openings": openings}


def summarize_report(kind, mode, start, end, data):
    """Mantém datas de lançamento e mês de referência da fatura como conceitos distintos."""
    from billing import is_bill_payment

    months = [date(start.year, m, 1) for m in range(start.month, end.month + 1)]
    report = {"kind": kind, "mode": mode, "start": start, "end": end, "months": months,
              "sources": data["sources"], "details": [], "notes": [], "coverage": {}, "groups": {}}
    if kind == "investments":
        history = [r for r in data["history"] if start <= r["day"] <= end]
        before = [r for r in data["history"] if r["day"] < start]
        report.update(history=history, flows=data["flows"], opening=number(before[-1]["amount"]) if before else None,
                      closing=number(history[-1]["amount"]) if history else None)
        report["notes"] = ["Posições históricas observadas em BRL. A última posição disponível de cada mês representa sua evolução; meses sem observações não são estimados.",
                           "Variação patrimonial não é rentabilidade: pode incluir aportes, retiradas e mudanças nas posições. Compras de criptomoedas não são tratadas como novos aportes."]
        return report
    sources = {r["id"]: r for r in data["sources"]}
    saved = {(r["source_id"], r["month"]): r for r in data["periods"]}
    currencies = {(r.get("pluggy_data") or {}).get("currency") or "BRL" for r in sources.values()} or {"BRL"}
    stats = defaultdict(lambda: {"incoming": ZERO, "outgoing": ZERO, "net": ZERO, "payments": ZERO, "pending": ZERO, "official": ZERO, "official_count": 0})
    seen = set()
    for month in months:
        covered = 0
        for source_id, src in sources.items():
            period = saved.get((source_id, month))
            if not period or period.get("transactions") is None:
                continue
            if kind == "bank" and period["period_end"] != date(month.year, month.month, calendar.monthrange(month.year, month.month)[1]):
                continue
            covered += 1
            for tx in period["transactions"]:
                # O extrato é calendário; a fatura usa os lançamentos do mês de referência,
                # inclusive compras de datas anteriores vinculadas ao ciclo daquele mês.
                day = date.fromisoformat(tx["date"][:10])
                if kind == "bank" and (day.year, day.month) != (month.year, month.month):
                    continue
                key = (source_id, tx["id"])
                if key in seen:
                    continue
                seen.add(key)
                currency = tx.get("currency") or "BRL"
                currencies.add(currency)
                value = number(tx["amount"])
                group = stats[month, currency]
                pending = tx.get("status") != "POSTED"
                payment = kind == "card" and is_bill_payment(tx)
                if pending:
                    group["pending"] += abs(value)
                elif payment:
                    group["payments"] += abs(value)
                else:
                    # Cartão: débito positivo; banco: entrada positiva.
                    group["incoming"] += max(value, ZERO)
                    group["outgoing"] += max(-value, ZERO)
                    group["net"] += value
                report["details"].append({**tx, "source": src["name"], "month": month,
                                          "pending": pending, "payment": payment})
        report["coverage"][month] = (covered, len(sources))
        if kind == "card":
            for source_id in sources:
                for bill in (saved.get((source_id, month)) or {}).get("bills", []):
                    currency = bill.get("currency") or "BRL"
                    currencies.add(currency)
                    stats[month, currency]["official"] += number(bill["amount"])
                    stats[month, currency]["official_count"] += 1
    for currency in sorted(currencies):
        report["groups"][currency] = {m: stats[m, currency] for m in months}
    report["notes"] = ["Valores apurados somente dos lançamentos confirmados salvos. Pendentes e pagamentos de faturas anteriores ficam separados e não compõem os gastos.",
                       "Moedas não são somadas nem convertidas entre si. Períodos sem sincronização não significam gasto zero. Dados refletem as últimas consultas salvas."]
    if kind == "card":
        report["notes"].append("A evolução usa o mês de referência/vencimento da fatura, e não o mês da compra. Débitos menos estornos/créditos representam o gasto líquido; o valor oficial da fatura é apresentado separadamente.")
    else:
        from bank_statements import resolve_openings
        # Saldos só são consolidados quando todas as contas na moeda têm base conhecida.
        for currency, groups in report["groups"].items():
            for month, group in groups.items():
                opening_sum, closing_sum, complete = ZERO, ZERO, True
                matching = [r for r in sources.values() if ((r.get("pluggy_data") or {}).get("currency") or "BRL") == currency]
                if not matching:
                    complete = False
                for src in matching:
                    sid = src["id"]
                    prior = [p for p in data["periods"] if p["source_id"] == sid and p["month"] < month]
                    previous_month = (month - timedelta(days=1)).replace(day=1)
                    previous = saved.get((sid, previous_month)) or {}
                    periods = [{**p, "period_start": p["month"]} for p in prior]
                    opening = resolve_openings([o for o in data["openings"] if o["account_id"] == sid], periods, previous.get("transactions") or [], month).get(currency)
                    current = saved.get((sid, month))
                    if opening is None or current is None or current["period_end"] != date(month.year, month.month, calendar.monthrange(month.year, month.month)[1]):
                        complete = False
                        break
                    opening_sum += opening["amount"]
                    closing_sum += opening["amount"] + sum((number(t["amount"]) for t in current["transactions"] if t.get("currency") == currency and t.get("status") == "POSTED" and t["date"][:7] == month.strftime("%Y-%m")), ZERO)
                group["opening"] = opening_sum if complete else None
                group["closing"] = closing_sum if complete else None
    report["details"].sort(key=lambda t: (t["date"], t["source"], t["id"]))
    return report


def money(value, currency="BRL"):
    if value is None:
        return "Sem dados"
    text = f"{number(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return ("R$ " if currency == "BRL" else currency + " ") + text


def render_pdf(report):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.graphics.shapes import Drawing, Rect, Line, String, Circle
    from project_paths import FRONTEND_DIR

    navy, green = colors.HexColor("#082b40"), colors.HexColor("#00a881")
    blue, red = colors.HexColor("#1672ce"), colors.HexColor("#cc5361")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportText", fontName="Helvetica", fontSize=9, leading=13, textColor=navy, spaceAfter=7, wordWrap="CJK"))
    styles.add(ParagraphStyle(name="ReportCell", parent=styles["ReportText"], fontSize=7.5, leading=10, spaceAfter=0))
    styles.add(ParagraphStyle(name="ReportTitle", fontName="Helvetica-Bold", fontSize=20, leading=25, textColor=navy, spaceAfter=8))
    styles.add(ParagraphStyle(name="ReportHeading", fontName="Helvetica-Bold", fontSize=12, leading=17, textColor=navy, spaceBefore=13, spaceAfter=8, keepWithNext=True))
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=38, rightMargin=38, topMargin=104, bottomMargin=35, title=TITLES[report["kind"]] + " - Optimus Finance", author="Optimus Finance")
    width = A4[0] - 76
    story = []
    def p(text, style="ReportText"):
        return Paragraph(escape(str(text)), styles[style])
    def heading(text):
        story.append(p(text, "ReportHeading"))
    def table(headers, rows, widths=None):
        cells = [[p(v, "ReportCell") for v in row] for row in [headers] + rows]
        t = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcece9")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f7fa")]), ("LINEBELOW", (0, 0), (-1, 0), .5, green), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
        story.extend([t, Spacer(1, 10)])
    def chart(labels, series, line=False):
        # None cria lacuna real; não desenha barra nem liga observações desconhecidas.
        d = Drawing(width, 225)
        left, right, bottom, top = 70, width - 12, 48, 195
        values = [float(v) for _, values, _ in series for v in values if v is not None]
        low, high = min([0] + values), max([0] + values)
        if high == low:
            high = low + 1
        scale = (top - bottom) / (high - low)
        yy = lambda value: bottom + (float(value) - low) * scale
        for step in range(5):
            value = low + (high - low) * step / 4
            y = yy(value)
            d.add(Line(left, y, right, y, strokeColor=colors.HexColor("#dce5ed"), strokeWidth=.5))
            label = f"{value:,.0f}".replace(",", ".")
            d.add(String(left - 7, y - 3, label, fontSize=7, textAnchor="end", fillColor=navy))
        slot = (right - left) / max(len(labels), 1)
        for j, (name, values, color) in enumerate(series):
            last = None
            for i, value in enumerate(values):
                x = left + (i + .5) * slot
                if value is None:
                    last = None
                    continue
                y = yy(value)
                if line:
                    if last:
                        d.add(Line(last[0], last[1], x, y, strokeColor=color, strokeWidth=2))
                    d.add(Circle(x, y, 2, fillColor=color, strokeColor=color))
                    last = (x, y)
                else:
                    bar = slot * .72 / len(series)
                    x = left + i * slot + slot * .14 + j * bar
                    d.add(Rect(x, min(y, yy(0)), max(bar - 1, .5), max(abs(y - yy(0)), .4), fillColor=color, strokeColor=None))
            # Legendas em posições fixas para as duas séries financeiras.
            x = left + j * 190
            d.add(Rect(x, 8, 8, 8, fillColor=color, strokeColor=None))
            d.add(String(x + 13, 8, name, fontSize=8, fillColor=navy))
        stride = max(1, (len(labels) + 11) // 12)
        for i, label in enumerate(labels):
            if i % stride == 0 or i == len(labels) - 1:
                d.add(String(left + (i + .5) * slot, bottom - 16, label, fontSize=7, textAnchor="middle", fillColor=navy))
        story.append(d)

    def page_brand(canvas, _):
        canvas.saveState()
        canvas.setFillColor(navy)
        canvas.rect(0, A4[1] - 80, A4[0], 80, fill=1, stroke=0)
        logo = FRONTEND_DIR / "Assets" / "icons" / "app-icon-192.png"
        if logo.exists():
            canvas.drawImage(str(logo), 38, A4[1] - 66, width=48, height=48, mask="auto", preserveAspectRatio=True)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 19)
        canvas.drawString(99, A4[1] - 38, "Optimus Finance")
        canvas.setFont("Helvetica", 9)
        canvas.drawString(99, A4[1] - 55, "Relatório financeiro")
        # Rodapé solicitado: somente a cor do cabeçalho, sem texto ou numeração.
        canvas.setFillColor(navy)
        canvas.rect(0, 0, A4[0], 14, fill=1, stroke=0)
        canvas.restoreState()

    kind, mode = report["kind"], report["mode"]
    story.append(p(TITLES[kind], "ReportTitle"))
    period = f"{report['start']:%m/%Y}" if mode == "monthly" else str(report["start"].year)
    story.append(p(("Relatório mensal | " if mode == "monthly" else "Relatório anual | ") + period))
    story.append(p("Emitido em " + datetime.now(ZoneInfo("America/Manaus")).strftime("%d/%m/%Y às %H:%M") + " (Manaus)"))
    if report["sources"]:
        story.append(p("Seleção: " + "; ".join(r["name"] + (" - " + r["institution"] if r.get("institution") else "") for r in report["sources"])))
    for note in report["notes"]:
        story.append(p(note))
    if kind == "investments":
        inflows = sum((number(r["amount"]) for r in report["flows"] if r["direction"] == "entrada"), ZERO)
        outflows = sum((number(r["amount"]) for r in report["flows"] if r["direction"] == "saida"), ZERO)
        opening, closing = report["opening"], report["closing"]
        heading("Resumo do período - BRL")
        table(["Indicador", "Valor"], [["Última posição anterior ao período", money(opening)], ["Última posição observada no período", money(closing)], ["Aportes registrados", money(inflows)], ["Retiradas registradas", money(outflows)], ["Variação da posição (não é lucro)", money(closing - opening if closing is not None and opening is not None else None)]], [width * .7, width * .3])
        if mode == "annual":
            labels, values, rows = [], [], []
            for month in report["months"]:
                points = [r for r in report["history"] if r["day"].month == month.month]
                value = number(points[-1]["amount"]) if points else None
                ins = sum((number(r["amount"]) for r in report["flows"] if r["day"].month == month.month and r["direction"] == "entrada"), ZERO)
                outs = sum((number(r["amount"]) for r in report["flows"] if r["day"].month == month.month and r["direction"] == "saida"), ZERO)
                labels.append(MONTHS[month.month - 1]); values.append(value)
                rows.append([labels[-1], money(value), money(ins), money(outs)])
            heading("Evolução mensal da posição - BRL")
            chart(labels, [("Última posição observada", values, green)], line=True)
            table(["Mês", "Posição", "Aportes", "Retiradas"], rows, [50, 170, 150, width - 370])
        else:
            heading("Movimentação da posição observada - BRL")
            chart([r["day"].strftime("%d/%m") for r in report["history"]], [("Posição observada", [number(r["amount"]) for r in report["history"]], green)], line=True)
            if not report["history"]:
                story.append(p("Sem posições históricas observadas neste mês."))
            else:
                table(["Data observada", "Posição BRL"], [[r["day"].strftime("%d/%m/%Y"), money(r["amount"])] for r in report["history"]], [width * .5] * 2)
        heading("Aportes e retiradas registrados")
        if report["flows"]:
            table(["Data", "Movimento", "Descrição", "Valor"], [[r["day"].strftime("%d/%m/%Y"), "Aporte" if r["direction"] == "entrada" else "Retirada", r["description"], money(r["amount"])] for r in report["flows"]], [68, 62, width - 230, 100])
        else:
            story.append(p("Nenhum aporte ou retirada registrado no período. Isso não comprova ausência de movimentos externos não cadastrados."))
    else:
        incomplete = [m for m, (n, total) in report["coverage"].items() if n != total or total == 0]
        if incomplete:
            story.append(p("Cobertura incompleta: " + ", ".join(MONTHS[m.month - 1] for m in incomplete) + ". Sincronize os períodos na aba correspondente. Totais parciais abrangem somente os dados disponíveis."))
        for currency, months in report["groups"].items():
            heading("Resumo do período - " + currency)
            available = [v for m, v in months.items() if report["coverage"][m][0] > 0]
            total = lambda key: sum((v[key] for v in available), ZERO) if available else None
            names = ("Débitos confirmados", "Estornos e créditos", "Gasto líquido") if kind == "card" else ("Entradas confirmadas", "Saídas confirmadas", "Movimentação líquida")
            rows = [[names[0], money(total("incoming"), currency)], [names[1], money(total("outgoing"), currency)], [names[2], money(total("net"), currency)], ["Pendentes (fora dos totais)", money(total("pending"), currency)]]
            if kind == "card":
                rows.append(["Pagamentos de faturas (conferência)", money(total("payments"), currency)])
                official = sum((v["official"] for v in months.values()), ZERO)
                # Oficial só é conhecido quando há faturas oficiais armazenadas.
                rows.append(["Faturas oficiais salvas (não somar aos débitos)", money(official, currency) if any(v["official_count"] for v in months.values()) else "Sem dados"])
            elif mode == "monthly":
                rows.extend([["Saldo inicial", money(next(iter(months.values())).get("opening"), currency)], ["Saldo final calculado", money(next(iter(months.values())).get("closing"), currency)]])
            table(["Indicador", "Valor"], rows, [width * .7, width * .3])
            heading(("Evolução mensal" if mode == "annual" else "Movimentação por data do lançamento") + " - " + currency)
            if mode == "annual":
                labels = [MONTHS[m.month - 1] for m in months]
                values = [[months[m][key] if report["coverage"][m][0] else None for m in months] for key in ("incoming", "outgoing")]
            else:
                txs = [t for t in report["details"] if t.get("currency") == currency and not t["pending"] and not t["payment"]]
                daily = defaultdict(lambda: [ZERO, ZERO])
                for t in txs:
                    value = number(t["amount"])
                    daily[t["date"]][0] += max(value, ZERO); daily[t["date"]][1] += max(-value, ZERO)
                days = sorted(daily)
                labels = [date.fromisoformat(day[:10]).strftime("%d/%m") for day in days]
                values = [[daily[day][j] for day in days] for j in (0, 1)]
            chart(labels, [(names[0], values[0], blue), (names[1], values[1], red)])
            if not labels:
                story.append(p("Sem lançamentos confirmados disponíveis para o gráfico."))
            if mode == "annual":
                rows = [[MONTHS[m.month - 1], money(v["incoming"], currency) if report["coverage"][m][0] else "Sem dados", money(v["outgoing"], currency) if report["coverage"][m][0] else "Sem dados", money(v["net"], currency) if report["coverage"][m][0] else "Sem dados", f"{report['coverage'][m][0]}/{report['coverage'][m][1]}"] for m, v in months.items()]
                table(["Mês", names[0], names[1], names[2], "Cobertura"], rows, [35, 125, 125, 125, width - 410])
        if mode == "monthly":
            heading("Lançamentos do período")
            if report["details"]:
                table(["Data", "Conta / cartão e descrição", "Situação", "Valor"], [[date.fromisoformat(t["date"][:10]).strftime("%d/%m/%Y"), t["source"] + " - " + t.get("description", "Sem descrição"), "Pendente" if t["pending"] else "Pagamento" if t["payment"] else "Confirmado", money(t["amount"], t.get("currency") or "BRL")] for t in report["details"]], [65, width - 235, 70, 100])
            else:
                story.append(p("Nenhum lançamento disponível. Consulte a cobertura do período antes de interpretar os totais."))
    doc.build(story, onFirstPage=page_brand, onLaterPages=page_brand)
    return out.getvalue()


@blueprint.get("/api/reports/pdf")
def download_report():
    if not getattr(g, "user", None):
        return jsonify(error="Entre com seu login e senha."), 401
    kind, mode, start, end, source = report_period(request.args)
    report = summarize_report(kind, mode, start, end, load_data(kind, start, end, source))
    filename = f"optimus-{kind}-{start:%Y-%m}.pdf" if mode == "monthly" else f"optimus-{kind}-{start.year}.pdf"
    return send_file(BytesIO(render_pdf(report)), mimetype="application/pdf", as_attachment=True, download_name=filename, max_age=0)
