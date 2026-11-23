-- Valores monetários usam NUMERIC para evitar erros de ponto flutuante.
-- BLOCO — Cadastros financeiros do usuário e referências às integrações.
CREATE TABLE IF NOT EXISTS records (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind TEXT NOT NULL CHECK (
        kind IN (
            'cards',
            'accounts',
            'investments',
            'expenses',
            'categories',
            'incomes'
        )
    ),
    name VARCHAR(120) NOT NULL,
    institution VARCHAR(120) NOT NULL DEFAULT '',
    detail VARCHAR(120) NOT NULL DEFAULT '',
    amount NUMERIC(14, 2) NOT NULL DEFAULT 0 CHECK (amount >= 0),
    due_date DATE,
    status VARCHAR(30) NOT NULL DEFAULT 'Ativo',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Categorias anteriores eram utilizadas em custos fixos.
ALTER TABLE records ADD COLUMN IF NOT EXISTS category_type TEXT DEFAULT 'expenses'
    CHECK (category_type IN ('incomes','expenses'));
ALTER TABLE records ADD COLUMN IF NOT EXISTS installment_adjustments JSONB NOT NULL DEFAULT '[]';


-- BLOCO — Preferências pessoais e percentuais do planejamento mensal.
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    user_name VARCHAR(80) NOT NULL DEFAULT 'Usuário',
    monthly_income NUMERIC(14, 2) NOT NULL DEFAULT 5000 CHECK (monthly_income > 0)
);


INSERT INTO
    settings (id)
VALUES
    (1)
ON CONFLICT DO NOTHING;


-- Integração Pluggy: identidade externa evita duplicação e preserva os dados manuais.
ALTER TABLE records
ADD COLUMN IF NOT EXISTS external_key TEXT;


ALTER TABLE records
ADD COLUMN IF NOT EXISTS pluggy_data JSONB;


CREATE UNIQUE INDEX IF NOT EXISTS records_external_key_unique ON records (external_key);


ALTER TABLE records
ALTER COLUMN amount
DROP NOT NULL;


ALTER TABLE records
DROP CONSTRAINT IF EXISTS records_amount_check;


ALTER TABLE records
ADD CONSTRAINT records_amount_check CHECK (
    kind = 'accounts'
    OR amount >= 0
);


-- Configuração única do aplicativo pessoal; segredo criptografado com chave externa ao banco.
CREATE TABLE IF NOT EXISTS pluggy_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    credentials BYTEA NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- Uma conexão por aplicação/Item, com credenciais criptografadas e histórico de estado.
CREATE TABLE IF NOT EXISTS pluggy_connections (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    connection_key TEXT NOT NULL UNIQUE,
    label VARCHAR(120) NOT NULL,
    credentials BYTEA NOT NULL,
    last_synced_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


ALTER TABLE records
ADD COLUMN IF NOT EXISTS connection_id BIGINT REFERENCES pluggy_connections (id);


CREATE TABLE IF NOT EXISTS pluggy_application (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    credentials BYTEA NOT NULL
);


CREATE TABLE IF NOT EXISTS crypto_connections (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exchange TEXT NOT NULL CHECK (exchange IN ('binance', 'bybit', 'kraken', 'mercadobitcoin')),
    label VARCHAR(120) NOT NULL,
    key_fingerprint TEXT NOT NULL,
    credentials BYTEA NOT NULL,
    balances JSONB,
    last_synced_at TIMESTAMPTZ,
    last_error TEXT,
    UNIQUE (exchange, key_fingerprint)
);


ALTER TABLE crypto_connections DROP CONSTRAINT IF EXISTS crypto_connections_exchange_check;
ALTER TABLE crypto_connections ADD CONSTRAINT crypto_connections_exchange_check
CHECK (exchange IN ('binance', 'bybit', 'kraken', 'mercadobitcoin'));

ALTER TABLE records
ADD COLUMN IF NOT EXISTS crypto_connection_id BIGINT REFERENCES crypto_connections (id);


ALTER TABLE records
ADD COLUMN IF NOT EXISTS crypto_data JSONB;


-- Progresso por par: consultas seguintes continuam do último negócio recebido.
CREATE TABLE IF NOT EXISTS binance_trade_history (
    key_fingerprint TEXT NOT NULL,
    symbol TEXT NOT NULL,
    history JSONB NOT NULL,
    PRIMARY KEY (key_fingerprint, symbol)
);


CREATE TABLE IF NOT EXISTS binance_fx_history (
    symbol TEXT NOT NULL,
    MINUTE BIGINT NOT NULL,
    price TEXT NOT NULL,
    PRIMARY KEY (symbol, MINUTE)
);


-- Observações reais do patrimônio; não reconstrói saldos a partir de compras.
CREATE TABLE IF NOT EXISTS portfolio_history (
    DAY DATE PRIMARY KEY,
    amount NUMERIC(24, 8) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- Percentuais de planejamento da renda; independem das despesas lançadas.
ALTER TABLE settings
ADD COLUMN IF NOT EXISTS fixed_percent NUMERIC(5, 2) NOT NULL DEFAULT 50 CHECK (fixed_percent BETWEEN 0 AND 100);


ALTER TABLE settings
ADD COLUMN IF NOT EXISTS credit_percent NUMERIC(5, 2) NOT NULL DEFAULT 40 CHECK (credit_percent BETWEEN 0 AND 100);


ALTER TABLE settings
ADD COLUMN IF NOT EXISTS investment_percent NUMERIC(5, 2) NOT NULL DEFAULT 10 CHECK (investment_percent BETWEEN 0 AND 100);


ALTER TABLE settings
DROP CONSTRAINT IF EXISTS budget_percent_total;


ALTER TABLE settings
ADD CONSTRAINT budget_percent_total CHECK (
    fixed_percent + credit_percent + investment_percent = 100
);


ALTER TABLE records
ADD COLUMN IF NOT EXISTS statement_name VARCHAR(120) NOT NULL DEFAULT '';


ALTER TABLE records
ADD COLUMN IF NOT EXISTS is_fixed_cost BOOLEAN NOT NULL DEFAULT FALSE;


UPDATE records
SET
    is_fixed_cost = TRUE
WHERE
    kind = 'expenses'
    AND detail = 'Custo Fixo';


-- Data informada manualmente; sincronizações não sobrescrevem este campo.
ALTER TABLE records
ADD COLUMN IF NOT EXISTS previous_closing_date DATE;


ALTER TABLE records
ADD COLUMN IF NOT EXISTS closing_date DATE;


CREATE TABLE IF NOT EXISTS card_bill_periods (
    card_id BIGINT NOT NULL REFERENCES records (id) ON DELETE CASCADE,
    previous_closing_date DATE NOT NULL,
    closing_date DATE NOT NULL,
    transactions JSONB NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (card_id, previous_closing_date, closing_date),
    CHECK (previous_closing_date < closing_date)
);


CREATE TABLE IF NOT EXISTS bank_statement_periods (
    account_id BIGINT NOT NULL REFERENCES records (id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    transactions JSONB NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (account_id, period_start, period_end)
);


-- Evidência da conciliação: um pagamento por custo e sem reutilizar o lançamento.
CREATE TABLE IF NOT EXISTS expense_payments (
    expense_id BIGINT PRIMARY KEY REFERENCES records (id) ON DELETE CASCADE,
    account_id BIGINT REFERENCES records (id) ON DELETE SET NULL,
    external_account_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    paid_amount NUMERIC(24, 8) NOT NULL CHECK (paid_amount > 0),
    paid_date DATE NOT NULL,
    description TEXT NOT NULL,
    amount_matches BOOLEAN NOT NULL,
    matched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (external_account_id, transaction_id)
);


-- Fluxos externos: compras/vendas entre ativos não são novos aportes.
CREATE TABLE IF NOT EXISTS investment_flows (
    id BIGSERIAL PRIMARY KEY,
    DAY DATE NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('entrada', 'saida')),
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    description VARCHAR(120) NOT NULL
);


-- Faturas oficiais segregadas por mês de vencimento, sem alterar o cadastro atual.
CREATE TABLE IF NOT EXISTS card_month_bills (
    card_id BIGINT NOT NULL REFERENCES records (id) ON DELETE CASCADE,
    MONTH DATE NOT NULL,
    bills JSONB NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (card_id, MONTH)
);


ALTER TABLE card_month_bills
ADD COLUMN IF NOT EXISTS transactions JSONB;


-- Datas do ciclo pertencem ao mês de referência, não ao cartão inteiro.
CREATE TABLE IF NOT EXISTS card_reference_cycles (
    card_id BIGINT NOT NULL REFERENCES records (id) ON DELETE CASCADE,
    reference_month DATE NOT NULL,
    previous_closing_date DATE,
    closing_date DATE,
    due_date DATE,
    PRIMARY KEY (card_id, reference_month),
    CHECK (
        previous_closing_date IS NULL
        OR closing_date IS NULL
        OR previous_closing_date < closing_date
    )
);


-- Preserva o cadastro legado apenas no seu mês de vencimento original.
INSERT INTO
    card_reference_cycles (
        card_id,
        reference_month,
        previous_closing_date,
        closing_date,
        due_date
    )
SELECT
    id,
    date_trunc('month', due_date)::date,
    previous_closing_date,
    closing_date,
    due_date
FROM
    records
WHERE
    kind = 'cards'
    AND due_date IS NOT NULL
    AND (
        previous_closing_date IS NULL
        OR closing_date IS NULL
        OR previous_closing_date < closing_date
    )
ON CONFLICT DO NOTHING;


-- Saldo de abertura por conta, moeda e mês; não se confunde com o saldo atual.
CREATE TABLE IF NOT EXISTS bank_opening_balances (
    account_id BIGINT NOT NULL REFERENCES records (id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    currency VARCHAR(3) NOT NULL,
    amount NUMERIC(24, 8) NOT NULL,
    PRIMARY KEY (account_id, period_start, currency)
);


-- Notificações e leitura pertencem exclusivamente ao painel do usuário.
CREATE TABLE IF NOT EXISTS notification_sources (
    source TEXT NOT NULL,
    record_id BIGINT NOT NULL REFERENCES records (id) ON DELETE CASCADE,
    PRIMARY KEY (source, record_id)
);


CREATE TABLE IF NOT EXISTS notification_transactions (
    source TEXT NOT NULL,
    record_id BIGINT NOT NULL REFERENCES records (id) ON DELETE CASCADE,
    transaction_id TEXT NOT NULL,
    PRIMARY KEY (source, record_id, transaction_id)
);


CREATE TABLE IF NOT EXISTS notification_events (
    event_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    route TEXT NOT NULL,
    record_id BIGINT NOT NULL REFERENCES records (id) ON DELETE CASCADE,
    period VARCHAR(7),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS notification_reads (
    key TEXT PRIMARY KEY,
    read_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- BLOCO — Rendas manuais usam o mesmo isolamento por usuário dos demais registros.
ALTER TABLE records
DROP CONSTRAINT IF EXISTS records_kind_check;


ALTER TABLE records
ADD CONSTRAINT records_kind_check CHECK (
    kind IN (
        'cards',
        'accounts',
        'investments',
        'expenses',
        'categories',
        'incomes'
    )
);
