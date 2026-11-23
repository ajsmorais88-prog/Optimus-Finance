"""Conciliação de custos e rendas com movimentações confirmadas do extrato local."""

import re
import unicodedata
from collections import Counter
from datetime import date
from decimal import Decimal


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


# BLOCO — Descarta identificadores genéricos que produziriam conciliações incorretas.
def meaningful_name(name):
    words = normalize(name).split()
    generic = {
        "pagamento",
        "pagto",
        "pgto",
        "eletron",
        "eletronico",
        "cobranca",
        "pix",
        "qr",
        "code",
        "dinamico",
        "estatico",
        "enviado",
        "recebido",
        "des",
        "rem",
        "docto",
        "transferencia",
        "banco",
        "ltda",
        "sa",
        "de",
        "da",
        "do",
        "das",
        "dos",
        "e",
        "s",
        "a",
    }
    return len(" ".join(words)) >= 6 and any(
        len(word) >= 4 and word not in generic for word in words
    )


# BLOCO 1 — Mesma competência: custos pelo nome; rendas pelo nome ou valor exato.
def find_matches(costs, transactions, used=None):
    used = used or set()
    eligible = {}
    for transaction in transactions:
        key = (transaction["external_account_id"], transaction["id"])
        if (
            key in used
            or transaction.get("status") != "POSTED"
            or transaction.get("currency") != "BRL"
        ):
            continue
        eligible[key] = transaction
    candidates = {}
    candidate_scores = {}
    for cost in costs:
        income = cost.get("kind") == "incomes"
        if (
            cost["status"]
            not in ({"Pendente", "Ativo"} if cost.get("kind") == "incomes" else {"Pendente"})
            or not cost.get("due_date")
            or (not income and not meaningful_name(cost.get("statement_name")))
        ):
            continue
        names = (
            [cost.get("statement_name"), cost.get("name")]
            if income
            else [cost.get("statement_name")]
        )
        merchants = [normalize(name) for name in names if meaningful_name(name)]
        due = cost["due_date"]
        due = date.fromisoformat(due) if isinstance(due, str) else due
        matches = []
        scores = {}
        for key, transaction in eligible.items():
            amount = Decimal(transaction["amount"])
            # Renda exige entrada; custo exige saída. Valores pendentes nunca conciliam.
            if cost.get("kind") == "incomes":
                if amount <= 0 or transaction.get("type") == "DEBIT":
                    continue
            elif amount >= 0 or transaction.get("type") == "CREDIT":
                continue
            paid = date.fromisoformat(transaction["date"][:10])
            if (paid.year, paid.month) != (due.year, due.month):
                continue
            description = " " + normalize(transaction["description"]) + " "
            name_matches = any((" " + merchant + " ") in description for merchant in merchants)
            amount_matches = abs(amount) == Decimal(str(cost["amount"]))
            if name_matches or (income and amount_matches):
                matches.append(key)
                # Nome e valor juntos têm prioridade; depois, o valor exato distingue
                # salário, férias e 13º pagos pelo mesmo remetente.
                scores[key] = (2 * int(amount_matches) + int(name_matches)) if income else 0
        if income and matches:
            best = max(scores.values())
            matches = [key for key in matches if scores[key] == best]
        # Se há vários pagamentos ao mesmo favorecido, o valor exato desempata.
        if len(matches) > 1:
            exact = [
                key
                for key in matches
                if abs(Decimal(eligible[key]["amount"])) == Decimal(str(cost["amount"]))
            ]
            if exact:
                matches = exact
        candidates[cost["id"]] = matches
        candidate_scores[cost["id"]] = scores
    # Uma renda com nome E valor exatos prevalece sobre outras rendas que
    # compartilham apenas o remetente. Empates reais continuam sem confirmação.
    strongest = {}
    for record_id, keys in candidates.items():
        for key in keys:
            strongest[key] = max(strongest.get(key, -1), candidate_scores[record_id][key])
    candidates = {
        record_id: [key for key in keys if candidate_scores[record_id][key] == strongest[key]]
        for record_id, keys in candidates.items()
    }
    contenders = Counter(key for keys in candidates.values() for key in keys)
    return [
        (cost, eligible[candidates[cost["id"]][0]])
        for cost in costs
        if len(candidates.get(cost["id"], [])) == 1 and contenders[candidates[cost["id"]][0]] == 1
    ]


# BLOCO 2 — Compara todas as contas salvas do período em uma única transação.
def reconcile_period(conn, start, end):
    costs = conn.execute(
        """SELECT * FROM records WHERE kind IN ('expenses','incomes')
        AND due_date BETWEEN %s AND %s ORDER BY id FOR UPDATE""",
        (start, end),
    ).fetchall()
    statements = conn.execute(
        """SELECT s.account_id,s.transactions,a.pluggy_data
        FROM bank_statement_periods s JOIN records a ON a.id=s.account_id
        WHERE s.period_start<=%s AND s.period_end>=%s""",
        (end, start),
    ).fetchall()
    transactions = []
    for statement in statements:
        external = (statement["pluggy_data"] or {}).get("id")
        if not external:
            continue
        transactions.extend(
            {**row, "account_id": statement["account_id"], "external_account_id": external}
            for row in statement["transactions"]
        )
    existing = conn.execute(
        "SELECT expense_id,external_account_id,transaction_id FROM expense_payments"
    ).fetchall()
    used = {(row["external_account_id"], row["transaction_id"]) for row in existing}
    already_linked = {row["expense_id"] for row in existing}
    costs = [cost for cost in costs if cost["id"] not in already_linked]
    matches = find_matches(costs, transactions, used)
    matched = []
    for cost, transaction in matches:
        paid = abs(Decimal(transaction["amount"]))
        conn.execute(
            """INSERT INTO expense_payments
            (expense_id,account_id,external_account_id,transaction_id,paid_amount,paid_date,description,amount_matches)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                cost["id"],
                transaction["account_id"],
                transaction["external_account_id"],
                transaction["id"],
                paid,
                transaction["date"],
                transaction["description"],
                paid == cost["amount"],
            ),
        )
        conn.execute(
            "UPDATE records SET status='Pago' WHERE id=%s AND status IN ('Pendente','Ativo')",
            (cost["id"],),
        )
        matched.append({"id": cost["id"], "name": cost["name"], "kind": cost["kind"]})
    return matched
