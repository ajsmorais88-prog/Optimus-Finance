/* BLOCO — Fontes ampliadas somente no navegador; o APK mantém a tipografia atual. */
document.documentElement.classList.toggle('web-readable', !isAndroidApp());
document.documentElement.classList.toggle('apk-app', isAndroidApp());

/* BLOCO 1 — Ícones vetoriais locais, sem dependências externas. */
// Identifica o endereço de acesso, mantendo a indicação correta no uso local e online.
const environmentLabel = document.querySelector('#environment-label');
if (environmentLabel) {
  const local =
    location.protocol === 'file:' ||
    ['localhost', '127.0.0.1', '[::1]', '::1'].includes(location.hostname);
  environmentLabel.textContent = local ? 'Ambiente local' : 'Ambiente online';
}

const paths = {
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 2-2.5 2-2.5 4M12 17h.01"/>',
  statement: '<path d="M5 3h10l4 4v14H5zM14 3v5h5M8 12h2m3 0h3M8 16h2m3 0h3"/>',
  receipt: '<path d="M5 3h14v18l-3-2-4 2-4-2-3 2V3zM8 7h8M8 11h8M8 15h5"/>',
  link: '<path d="m10 13 4-4m-6 7-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m0 0 2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/>',
  home: '<path d="m3 10 9-7 9 7v11h-6v-7H9v7H3z"/>',
  card: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 9h20M6 15h4"/>',
  bank: '<path d="m2 8 10-5 10 5H2zm1 13h18M6 11v7m6-7v7m6-7v7"/>',
  trend: '<path d="m3 18 6-7 4 3 8-10m-6 0h6v6"/>',
  // Engrenagem com oito dentes e furo central, legível também no menu lateral.
  settings:
    '<path fill="currentColor" stroke="none" fill-rule="evenodd" d="M9.5 2h5l.6 3 1.1.6 2.9-1 2.5 4.3-2.3 2v1.2l2.3 2-2.5 4.3-2.9-1-1.1.6-.6 3h-5l-.6-3-1.1-.6-2.9 1L2.4 14l2.3-2v-1.2l-2.3-2L4.9 4.5l2.9 1L8.9 5l.6-3ZM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"/>',
  bell: '<path d="M5 17h14l-2-4V9a5 5 0 0 0-10 0v4zm5 4h4M12 2v2"/>',
  calendar:
    '<rect x="3" y="5" width="18" height="17" rx="2"/><path d="M7 2v6m10-6v6M3 11h18m-13 4h1m6 0h1m-8 4h1m6 0h1"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  edit: '<path d="m4 16 12-12 4 4L8 20H4zm10-10 4 4"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
  user: '<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  users:
    '<circle cx="9" cy="7" r="4"/><path d="M2 21v-3a7 7 0 0 1 14 0v3M17 3a4 4 0 0 1 0 8m3 10v-3a7 7 0 0 0-3-6"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  download: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
};
const icon = (name) =>
  /* HTML */ `<svg
    class="icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.8"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    ${paths[name] || paths.grid}
  </svg>`;

/* BLOCO 2 — Estado central e utilitários. Dados do usuário são escapados no HTML. */
const routes = {
  overview: ['Visão Estratégica', 'home'],
  fixed_costs: ['Renda e Custos Fixos', 'receipt'],
  cards: ['Cadastro de cartão', 'card'],
  card_bill: ['Fatura do cartão', 'receipt'],
  accounts: ['Cadastro de conta', 'bank'],
  bank_account: ['Extrato bancário', 'statement'],
  investments: ['Conta de Investimento', 'trend'],
  connect: ['Conecte sua conta', 'link'],
  support: ['Suporte ao usuário', 'help'],
  admin: ['Administrador', 'settings'],
};
const money = (n) => Number(n || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const esc = (s) =>
  String(s ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
const dateText = (d) => (d ? new Date(d + 'T12:00:00').toLocaleDateString('pt-BR') : '—');
let state = { records: [], settings: { user_name: 'Usuário', monthly_income: 5000 } };
// Preferência de período da sessão; não contém dados de acesso.
function currentPeriod() {
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'America/Manaus',
    year: 'numeric',
    month: '2-digit',
  })
    .format(new Date())
    .slice(0, 7);
}
let selectedPeriod = currentPeriod();
// Preferências independentes por usuário e aba; nunca propagam o filtro entre páginas.
const periodsByPage = new Map();
/* BLOCO — Separa a preferência de filtro por usuário e por aba. */
function periodPreferenceKey(page) {
  return `finance-period:${authState.user?.id || 'preview'}:${page}`;
}
/* BLOCO — Restaura somente o período da aba que está sendo aberta. */
function periodForPage(page) {
  const key = periodPreferenceKey(page);
  if (periodsByPage.has(key)) return periodsByPage.get(key);
  try {
    const saved = sessionStorage.getItem(key);
    if (/^\d{4}-(0[1-9]|1[0-2])$/.test(saved || '')) {
      periodsByPage.set(key, saved);
      return saved;
    }
  } catch {
    /* O filtro também funciona sem armazenamento do navegador. */
  }
  return currentPeriod();
}
/* BLOCO — Guarda o filtro da aba na sessão, sem persistir dados financeiros no navegador. */
function savePagePeriod(value, page) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(value)) return;
  const key = periodPreferenceKey(page);
  periodsByPage.set(key, value);
  try {
    sessionStorage.setItem(key, value);
  } catch {
    /* Memória da aba continua disponível. */
  }
}
let route = 'overview';
let authState = { user: null, setup_required: true };
let csrfToken = '';
let demo = false;
let unavailable = false;
let editing = null;
let formKind = '';
let formIsFixedCost = false;
let selectedBillCard = null;
let selectedBankAccount = null;
const rows = (kind) =>
  state.records.filter(
    (r) =>
      (kind === 'investments' || (!r.crypto_data && !r.crypto_connection_id)) &&
      (kind === 'fixed_costs'
        ? r.kind === 'expenses' && r.due_date?.startsWith(selectedPeriod)
        : r.kind === kind &&
          (!['expenses', 'incomes'].includes(kind) || r.due_date?.startsWith(selectedPeriod))),
  );
const sum = (list) => list.reduce((total, item) => total + Number(item.amount), 0);
const content = document.querySelector('#content');
const dialog = document.querySelector('#editor');

/* BLOCO — Centraliza JSON, token CSRF, autenticação e tratamento das respostas da API. */
async function api(path, options = {}) {
  const response = await fetch('/api/' + path, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
  });
  if (response.status === 204) return null;
  const body = await response.json();
  if (body.csrf_token) csrfToken = body.csrf_token;
  if (!response.ok) {
    const error = new Error(body.error || 'Não foi possível concluir a operação.');
    error.status = response.status;
    if (response.status === 401 && !path.startsWith('auth/')) {
      authState.user = null;
      renderLogin();
    }
    throw error;
  }
  return body;
}

/* Carregamento real, sem tempo mínimo artificial; encerra também em caso de erro. */
let pendingPanelLoads = 0;
/* BLOCO — Controla o indicador de carregamento durante consultas do painel. */
function panelLoading(active) {
  pendingPanelLoads = Math.max(0, pendingPanelLoads + (active ? 1 : -1));
  const busy = pendingPanelLoads > 0;
  const loader = document.querySelector('#app-loader');
  if (loader) {
    loader.classList.toggle('is-loaded', !busy);
    loader.setAttribute('aria-hidden', String(!busy));
  }
  content.setAttribute('aria-busy', String(busy));
}

/* BLOCO — Atualiza a identidade e os dados privados antes de renderizar a página. */
async function load({ deferRender = false } = {}) {
  panelLoading(true);
  try {
    // Arquivos locais não têm servidor Python: mostre a prévia sem tentar a API.
    if (location.protocol === 'file:') {
      demo = true;
      unavailable = true;
      state = structuredClone(sample);
      if (!deferRender) render();
      return;
    }
    try {
      authState = await api('auth/me');
      if (!authState.setup_required && !authState.user) {
        if (!deferRender) renderLogin();
        return;
      }
      state = await api('data');
      unavailable = false;
      demo = false;
    } catch (error) {
      unavailable = true;
      toast(error.message);
    }
    if (!deferRender) render();
  } finally {
    panelLoading(false);
  }
}

/* BLOCO — Exibe uma mensagem temporária sem interromper o preenchimento dos formulários. */
function toast(message) {
  const el = document.querySelector('#toast');
  el.textContent = message;
  el.classList.add('visible');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove('visible'), 5000);
}

/* BLOCO 3 — Gráficos SVG calculados com registros reais. */
function chart(list, color = '#0068f5', accumulatedMode = true, monthly = false) {
  // Para posições mensais, conserva a última observação disponível de cada mês.
  // Não soma saldos diários e não cria saldos em meses sem observações.
  const observationDates = new Map();
  if (monthly) {
    const months = new Map();
    [...list]
      .filter((r) => /^\d{4}-\d{2}-\d{2}$/.test(r.due_date || ''))
      .sort((a, b) => a.due_date.localeCompare(b.due_date))
      .forEach((r) => {
        if (Number.isFinite(Number(r.amount)) && Number(r.amount) >= 0) {
          const month = r.due_date.slice(0, 7) + '-01';
          months.set(month, { ...r, due_date: month });
          observationDates.set(month, r.due_date);
        }
      });
    list = [...months.values()];
  }
  // Agrupa aportes do mesmo dia e posiciona o eixo X pelo tempo transcorrido.
  const days = new Map();
  list
    .filter(
      (r) =>
        r.due_date &&
        Number.isFinite(Number(r.amount)) &&
        (accumulatedMode ? Number(r.amount) > 0 : Number(r.amount) >= 0),
    )
    .forEach((r) => days.set(r.due_date, (days.get(r.due_date) || 0) + Number(r.amount)));
  const dated = [...days.entries()].sort(([a], [b]) => a.localeCompare(b));
  if (!dated.length)
    return '<div class="chart-empty">Nenhum aporte com data e valor em BRL disponível.</div>';
  let accumulated = 0;
  const values = dated.map(([date, amount]) => ({
    value: accumulatedMode ? (accumulated += amount) : amount,
    date,
  }));
  const max = Math.max(...values.map((v) => v.value), 1) * 1.15;
  const monthIndex = (day) => Number(day.slice(0, 4)) * 12 + Number(day.slice(5, 7)) - 1;
  const timeValue = (day) => (monthly ? monthIndex(day) : Date.parse(day + 'T12:00:00Z'));
  const first = timeValue(values[0].date);
  const last = timeValue(values.at(-1).date);
  // No celular, o eixo usa a largura disponível e mantém os textos legíveis.
  const chartWidth = matchMedia('(max-width: 520px)').matches
    ? Math.max(240, innerWidth - 80)
    : 550;
  const plotWidth = chartWidth - 110;
  const points = values.map((v) => [
    65 +
      (last === first ? plotWidth / 2 : ((timeValue(v.date) - first) / (last - first)) * plotWidth),
    185 - (v.value / max) * 155,
  ]);
  const ticks = [0, 1, 2, 3]
    .map(
      (i) =>
        /* HTML */ `<line
            x1="60"
            y1="${185 - i * 50}"
            x2="${chartWidth - 25}"
            y2="${185 - i * 50}"
            stroke="#edf1f8"
          /><text x="2" y="${189 - i * 50}"
            >${((max * i) / 3).toLocaleString('pt-BR', { notation: 'compact', maximumFractionDigits: 1 })}</text
          >`,
    )
    .join('');
  // Escolhe datas pelo espaço no eixo, evitando sobreposição quando as compras se concentram.
  const labelIndexes = new Set([0]);
  let previousX = points[0][0];
  for (let i = 1; i < points.length - 1; i++) {
    if (points[i][0] - previousX >= 115 && points.at(-1)[0] - points[i][0] >= 115) {
      labelIndexes.add(i);
      previousX = points[i][0];
    }
  }
  if (points.length > 1) labelIndexes.add(points.length - 1);
  return /* HTML */ `<svg
    class="chart"
    viewBox="0 0 ${chartWidth} 225"
    role="img"
    aria-label="${accumulatedMode ? 'Evolução dos aportes acumulados' : 'Posição atual observada'} em reais, de ${dateText(values[0].date)} a ${dateText(values.at(-1).date)}"
  >
    <defs>
      <linearGradient id="fill-${color.slice(1)}" x1="0" y1="0" x2="0" y2="1">
        <stop stop-color="${color}" stop-opacity=".16" />
        <stop offset="1" stop-color="${color}" stop-opacity=".01" />
      </linearGradient>
    </defs>
    ${ticks}
    <polygon
      points="${points[0][0]},185 ${points.map((p) => p.join(',')).join(' ')} ${points.at(-1)[0]},185"
      fill="url(#fill-${color.slice(1)})"
    />
    <polyline
      points="${points.map((p) => p.join(',')).join(' ')}"
      fill="none"
      stroke="${color}"
      stroke-width="2.5"
    />
    ${points.map((p, i) => /* HTML */ `<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="${color}" tabindex="0"><title>${dateText(observationDates.get(values[i].date) || values[i].date)} · ${accumulatedMode ? 'Acumulado' : 'Posição'}: ${money(values[i].value)}</title></circle>${labelIndexes.has(i) ? /* HTML */ `<text text-anchor="${i === 0 && points.length > 1 ? 'start' : i === points.length - 1 && points.length > 1 ? 'end' : 'middle'}" x="${p[0]}" y="212">${monthly ? values[i].date.slice(5, 7) + '/' + values[i].date.slice(0, 4) : dateText(values[i].date)}</text>` : ''}`).join('')}
  </svg>`;
}

// A curva da posição usa observações do patrimônio; não acumula compras passadas.
function positionEvolution() {
  const observations = state.portfolio_history || [];
  const list = observations.map((row) => ({ due_date: row.date, amount: row.amount }));
  const total = sum(brlInvestmentPositions());
  const last = list.at(-1);
  if (last) last.amount = total;
  return /* HTML */ `<div>
    <h2>Evolução da posição atual</h2>
    <p class="subtitle" style="margin-top:8px">${money(total)} · posição da última consulta</p>
    ${chart(list, '#00b685', false, true)}
    <p class="subtitle">
      ${list.length <= 1 ? 'Primeira observação registrada. Cada mês mostrará a última posição disponível.' : 'Escala mensal: última posição registrada de cada mês. O mês atual usa a última consulta; meses sem dados não recebem valores estimados.'}
    </p>
  </div>`;
}

// Aportes são fluxos externos registrados; negociações Spot não são dinheiro novo.
function investmentContributions() {
  return (state.investment_flows || [])
    .filter((r) => r.direction === 'entrada')
    .map((r) => ({ due_date: r.day, amount: r.amount }));
}

// Barras mensais separadas: entradas acima de zero e saídas abaixo de zero.
function contributionEvolution() {
  const flows = state.investment_flows || [];
  const months = new Map();
  for (const flow of flows) {
    const key = flow.day.slice(0, 7);
    if (!months.has(key)) months.set(key, { entrada: 0, saida: 0 });
    months.get(key)[flow.direction] += Number(flow.amount);
  }
  const dated = [...months].sort(([a], [b]) => a.localeCompare(b));
  const incoming = flows
    .filter((r) => r.direction === 'entrada')
    .reduce((n, r) => n + Number(r.amount), 0);
  const outgoing = flows
    .filter((r) => r.direction === 'saida')
    .reduce((n, r) => n + Number(r.amount), 0);
  const maximum = Math.max(1, ...dated.flatMap(([, r]) => [r.entrada, r.saida]));
  // Rolagem horizontal preserva a leitura dos meses em históricos extensos.
  const width = Math.max(550, dated.length * 90 + 90);
  const bars = dated
    .map(([month, values], i) => {
      const x = 80 + (i * (width - 100)) / Math.max(1, dated.length);
      return /* HTML */ `<rect
          x="${x}"
          y="${110 - (values.entrada / maximum) * 80}"
          width="22"
          height="${(values.entrada / maximum) * 80}"
          fill="#00b685"
          tabindex="0"
          ><title>${month}: entradas ${money(values.entrada)}</title></rect
        >
        <rect
          x="${x + 25}"
          y="110"
          width="22"
          height="${(values.saida / maximum) * 80}"
          fill="#e05263"
          tabindex="0"
          ><title>${month}: saídas ${money(values.saida)}</title></rect
        >
        <text x="${x + 23}" y="215" text-anchor="middle"
          >${month.slice(5)}/${month.slice(0, 4)}</text
        >`;
    })
    .join('');
  return /* HTML */ `<section class="panel" style="margin-bottom:22px">
    <h2>Entradas e saídas dos investimentos</h2>
    <p class="subtitle">
      Entradas: ${money(incoming)} · Saídas: ${money(outgoing)} · Aportes líquidos:
      ${money(incoming - outgoing)}
    </p>
    ${
      dated.length
        ? /* HTML */ `<div style="overflow-x:auto">
            <svg
              class="chart"
              style="min-width:${width}px"
              viewBox="0 0 ${width} 235"
              role="img"
              aria-label="Entradas em verde e saídas em vermelho por mês, em reais"
            >
              <text x="0" y="22">${money(maximum)}</text>
              <text x="0" y="115">0</text>
              <text x="0" y="200">−${money(maximum)}</text>
              <line x1="75" y1="110" x2="${width}" y2="110" stroke="#cbd5e1" />
              ${bars}
            </svg>
          </div>`
        : '<p class="empty">Ainda não há entradas ou saídas registradas. O saldo atual e as compras Spot não permitem reconstruir esses movimentos.</p>'
    }
    <p class="subtitle">
      Verde: dinheiro que entrou nos investimentos. Vermelho: retiradas. Trocas entre criptomoedas
      não são aportes. Este histórico é registrado abaixo; as integrações atuais importam posições e
      compras, sem comprovar todos os depósitos e saques.
    </p>
    <form id="investment-flow-form" class="flow-form">
      <label
        >Movimento<select name="direction">
          <option value="entrada">Entrada / aporte</option>
          <option value="saida">Saída / retirada</option>
        </select></label
      >
      <label>Data<input name="day" type="date" required /></label>
      <label
        >Valor (BRL)<input
          name="amount"
          type="number"
          min="0.01"
          max="999999999999.99"
          step="0.01"
          required
      /></label>
      <label
        >Descrição<input
          name="description"
          maxlength="120"
          required
          placeholder="Ex.: depósito na corretora"
      /></label>
      <button class="button" type="submit">Registrar movimento</button>
    </form>
    ${
      flows.length
        ? /* HTML */ `<div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Movimento</th>
                  <th>Descrição</th>
                  <th>Valor</th>
                  <th>Ação</th>
                </tr>
              </thead>
              <tbody>
                ${flows
                  .map(
                    (r) =>
                      /* HTML */ `<tr>
                        <td>${dateText(r.day)}</td>
                        <td>${r.direction === 'entrada' ? 'Entrada' : 'Saída'}</td>
                        <td>${esc(r.description)}</td>
                        <td>${money(r.amount)}</td>
                        <td>
                          <button
                            class="icon-button"
                            data-delete-flow="${r.id}"
                            aria-label="Excluir movimento"
                          >
                            ${icon('trash')}
                          </button>
                        </td>
                      </tr>`,
                  )
                  .join('')}
              </tbody>
            </table>
          </div>`
        : ''
    }
  </section>`;
}

// Movimentações são independentes do saldo sincronizado e persistidas no PostgreSQL.
document.addEventListener('submit', async (event) => {
  if (event.target.id !== 'investment-flow-form') return;
  event.preventDefault();
  if (demo || unavailable) return toast('Conecte o banco para registrar movimentos.');
  const button = event.submitter;
  button.disabled = true;
  try {
    await api('investment-flows', {
      method: 'POST',
      body: JSON.stringify(Object.fromEntries(new FormData(event.target))),
    });
    await load();
    toast('Movimento registrado.');
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
  }
});
document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-delete-flow]');
  if (!button || demo || unavailable) return;
  try {
    await api(`investment-flows/${button.dataset.deleteFlow}`, { method: 'DELETE' });
    await load();
  } catch (error) {
    toast(error.message);
  }
});

/* BLOCO — Monta o cabeçalho da página e o filtro mensal quando a aba permite filtragem. */
function heading(title, subtitle) {
  const filterable = ['overview', 'fixed_costs', 'bank_account', 'cards', 'card_bill'].includes(
    route,
  );
  const periodControl = ['connect', 'support', 'admin', 'users', 'investments', 'accounts'].includes(route)
    ? ''
    : filterable
      ? /* HTML */ ` <div class="date-chip period-filter">
          ${icon('calendar')}
          <div>
            <label for="period-filter">Filtrar por mês e ano</label
            ><input
              id="period-filter"
              type="month"
              value="${selectedPeriod}"
              min="1900-01"
              max="9999-12"
              aria-label="Filtrar por mês e ano"
            />
          </div>
          <button type="button" class="period-reset" data-action="current-period">Mês atual</button>
        </div>`
      : /* HTML */ `<span class="date-chip"
          >${icon('calendar')}
          ${new Date().toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })}</span
        >`;
  return /* HTML */ `<div class="page-heading">
    <div>
      <div class="eyebrow">Seu dinheiro, com direção</div>
      <h1>${title}</h1>
      <p class="subtitle">${subtitle}</p>
    </div>
    ${periodControl}
  </div>`;
}

/* BLOCO — Altera somente o mês da aba atual e refaz os componentes dependentes do filtro. */
function setPeriod(value) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(value)) return;
  savePagePeriod(value, route);
  render();
}
document.addEventListener('change', (event) => {
  if (event.target.id === 'period-filter' && event.target.checkValidity())
    setPeriod(event.target.value);
});
document.addEventListener('click', (event) => {
  if (event.target.closest('[data-action="current-period"]')) setPeriod(currentPeriod());
});

/* BLOCO — Renda e percentuais com prévia imediata e salvamento explícito. */
function budgetAllocation(income, percentages) {
  const cents = Math.round(income * 100);
  const exact = percentages.map((percent) => (cents * percent) / 100);
  const allocated = exact.map(Math.floor);
  const order = exact
    .map((value, index) => ({ index, remainder: value - allocated[index] }))
    .sort((a, b) => b.remainder - a.remainder);
  const remaining = cents - allocated.reduce((a, b) => a + b, 0);
  for (let i = 0; i < remaining; i++) allocated[order[i % order.length].index]++;
  return allocated.map((value) => value / 100);
}

/* Comparação do orçamento: mantém o mês da visão estratégica e calcula saldos em centavos. */
let monthlyBudget = null;
/* BLOCO — Compara o valor planejado com os compromissos e o saldo de cada categoria. */
function budgetLegend(income, percentages) {
  const allocation = budgetAllocation(income, percentages);
  const labels = ['Custo Fixo', 'Cartão de Crédito', 'Investimento'];
  const colors = ['#0879ff', '#00be8b', '#ffac5c'];
  const current = monthlyBudget?.period === selectedPeriod ? monthlyBudget : null;
  return labels
    .map((label, i) => {
      const committed = current?.values?.[i];
      const balance =
        committed == null
          ? null
          : (Math.round(allocation[i] * 100) - Math.round(committed * 100)) / 100;
      const pending = current?.error ? 'Indisponível' : 'Carregando…';
      return /* HTML */ `<div class="legend-item budget-category" style="--category-color:${colors[i]}">
        <span class="dot" style="background:${colors[i]}"></span>
        <div>
          <b class="budget-category-heading"><span>${label}</span><span class="budget-percent">${percentages[i].toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%</span></b>
          <dl class="budget-comparison">
            <div>
              <dt>Planejado</dt>
              <dd>${money(allocation[i])}</dd>
            </div>
            <div>
              <dt>Comprometido</dt>
              <dd>${committed == null ? pending : money(committed)}</dd>
            </div>
            <div class="${balance < 0 ? 'budget-negative' : ''}">
              <dt>Saldo</dt>
              <dd>${balance == null ? pending : money(balance)}</dd>
            </div>
          </dl>
        </div>
      </div>`;
    })
    .join('');
}
/* BLOCO — Atualiza a legenda usando o formulário aberto ou o planejamento já salvo. */
function refreshBudgetLegend() {
  const legend = document.querySelector('#budget-legend');
  const form = document.querySelector('#budget-form');
  if (!legend) return;
  if (!form) {
    const percentages = [
      Number(state.settings.fixed_percent ?? 50),
      Number(state.settings.credit_percent ?? 40),
      Number(state.settings.investment_percent ?? 10),
    ];
    legend.innerHTML = budgetLegend(registeredIncomeTotal(), percentages);
    return;
  }
  const percentages = ['fixed_percent', 'credit_percent', 'investment_percent'].map((name) =>
    Number(form.elements[name].value),
  );
  if (
    !form.checkValidity() ||
    Math.abs(percentages.reduce((sum, n) => sum + n, 0) - 100) > 0.000001
  )
    return;
  legend.innerHTML = budgetLegend(Number(form.elements.monthly_income.value), percentages);
}

// Soma em centavos somente as rendas do mês exibido na aba.
function registeredIncomeTotal() {
  return (
    rows('incomes').reduce(
      (total, record) => total + Math.round(Number(record.amount || 0) * 100),
      0,
    ) / 100
  );
}

// O planejamento é editado na aba de rendas; a visão estratégica exibe os valores salvos.
function budgetPlanningPanel() {
  const p = [
    Number(state.settings.fixed_percent ?? 50),
    Number(state.settings.credit_percent ?? 40),
    Number(state.settings.investment_percent ?? 10),
  ];
  return /* HTML */ `<section class="panel" style="margin-bottom:22px">
    <div class="panel-title"><h2>${icon('trend')} Planejamento da renda mensal</h2></div>
    ${budgetForm(registeredIncomeTotal(), p)}
  </section>`;
}
/* BLOCO — Monta renda automática, percentuais e salvamento explícito do planejamento. */
function budgetForm(income, percentages) {
  const fields = [
    ['fixed_percent', 'Custo fixo (%)'],
    ['credit_percent', 'Cartão de crédito (%)'],
    ['investment_percent', 'Investimento (%)'],
  ];
  return /* HTML */ `<form id="budget-form">
    <label for="budget-income">Renda do mês</label>
    <input
      id="budget-income"
      name="monthly_income"
      type="number"
      min="0.01"
      max="999999999999.99"
      step="0.01"
      required
      readonly
      aria-describedby="budget-income-source"
      value="${income}"
    />
    <p id="budget-income-source" class="subtitle">
      Total das rendas cadastradas no mês selecionado. Para alterar, cadastre, edite ou exclua uma
      renda abaixo.
    </p>
    <div class="budget-percentages">
      ${fields.map(([name, label], i) => /* HTML */ `<div><label for="budget-${name}">${label}</label><input id="budget-${name}" name="${name}" type="number" min="0" max="100" step="0.01" required value="${percentages[i]}" /></div>`).join('')}
    </div>
    <p id="budget-status" class="subtitle" role="status" style="margin-top:12px">
      ${income > 0 ? 'Total: 100%. Ajuste os percentuais e salve seu planejamento.' : 'Cadastre uma renda no mês selecionado para salvar o planejamento.'}
    </p>
    <button
      type="submit"
      class="button"
      style="margin-top:12px"
      ${income > 0 && income <= 999999999999.99 ? '' : 'disabled'}
    >
      Salvar planejamento
    </button>
  </form>`;
}

/* BLOCO — Valida os percentuais antes de liberar o salvamento e atualizar a prévia. */
function previewBudget() {
  const form = document.querySelector('#budget-form');
  if (!form) return;
  const income = Number(form.elements.monthly_income.value);
  const inputs = ['fixed_percent', 'credit_percent', 'investment_percent'].map(
    (name) => form.elements[name],
  );
  const percentages = inputs.map((input) => Number(input.value));
  const total = Math.round(percentages.reduce((a, b) => a + b, 0) * 100) / 100;
  const status = document.querySelector('#budget-status');
  const valid =
    income > 0 &&
    income <= 999999999999.99 &&
    form.elements.monthly_income.checkValidity() &&
    inputs.every((input) => input.checkValidity()) &&
    Math.abs(total - 100) < 0.000001;
  status.textContent = valid
    ? 'Total: 100%. Clique em Salvar planejamento para atualizar a distribuição na Visão Estratégica.'
    : `Total: ${total.toLocaleString('pt-BR')}%. Informe uma renda positiva e distribua exatamente 100%.`;
  status.style.color = valid ? '' : '#c13442';
  form.querySelector('[type="submit"]').disabled = !valid;
  if (!valid) return;
  const allocation = budgetAllocation(income, percentages);
  const colors = ['#0879ff', '#00be8b', '#ffac5c'];
  const labels = ['Custo Fixo', 'Cartão de Crédito', 'Investimento'];
  if (!document.querySelector('#budget-donut')) return;
  document.querySelector('#budget-donut').style.background =
    `conic-gradient(${colors[0]} 0 ${percentages[0]}%,${colors[1]} ${percentages[0]}% ${percentages[0] + percentages[1]}%,${colors[2]} ${percentages[0] + percentages[1]}% 100%)`;
  document.querySelector('#budget-income-label').textContent = money(income);
  refreshBudgetLegend();
}

document.addEventListener('input', (event) => {
  if (event.target.closest('#budget-form')) previewBudget();
});
document.addEventListener('submit', async (event) => {
  if (event.target.id !== 'budget-form') return;
  event.preventDefault();
  if (demo || unavailable) return toast('Conecte o banco para salvar seu planejamento.');
  event.target.elements.monthly_income.value = registeredIncomeTotal();
  previewBudget();
  if (!(registeredIncomeTotal() > 0) || event.target.querySelector('[type="submit"]').disabled)
    return;
  const button = event.submitter;
  button.disabled = true;
  try {
    const result = await api('budget', {
      method: 'PUT',
      body: JSON.stringify(Object.fromEntries(new FormData(event.target))),
    });
    state.settings = result.settings;
    render();
    toast('Renda e percentuais salvos.');
  } catch (error) {
    document.querySelector('#budget-status').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

/* Resumo mensal: faturas futuras ficam separadas das despesas e do saldo do mês. */
async function loadMonthlySummary() {
  const target = document.querySelector('#monthly-summary');
  if (!target) return;
  if (demo || unavailable) {
    target.textContent = 'Conecte o banco para consultar os valores do mês.';
    monthlyBudget = { period: target.dataset.period, error: true };
    refreshBudgetLegend();
    return;
  }
  try {
    const data = await api(`monthly-summary?month=${encodeURIComponent(target.dataset.period)}`);
    if (!target.isConnected) return;
    monthlyBudget = {
      period: target.dataset.period,
      values: [Number(data.fixed_committed), Number(data.cards), Number(data.contributions)],
    };
    refreshBudgetLegend();
    const item = (label, value, extra = '') =>
      /* HTML */ `<div class="expense ${extra}">
        <span>${label}</span><strong>${value == null ? 'Não disponível' : money(value)}</strong>
      </div>`;
    const total =
      [data.fixed_paid, data.cards, data.other_paid].reduce(
        (sum, value) => sum + Math.round(Number(value || 0) * 100),
        0,
      ) / 100;
    // Saldo: abertura + entradas − custos pagos − faturas − outras saídas.
    // Mantém o cálculo disponível sem apresentar saldos ausentes como confirmados.
    const partial =
      data.missing_opening_accounts.length > 0 || data.missing_statement_accounts.length > 0;
    const opening = data.opening_balance ?? data.opening_balance_known;
    const balance =
      opening == null
        ? null
        : (Math.round(Number(opening) * 100) +
            Math.round(Number(data.incoming) * 100) -
            Math.round(Number(data.fixed_paid || 0) * 100) -
            Math.round(Number(data.cards || 0) * 100) -
            Math.round(Number(data.other_paid || 0) * 100)) /
          100;
    target.innerHTML =
      item(
        'Saldo do mês anterior · todas as contas' +
          (data.missing_opening_accounts.length ? ' · parcial' : ''),
        data.opening_balance ?? data.opening_balance_known,
        'summary-opening',
      ) +
      /* HTML */ `<details class="summary-account-balances">
        <summary>Ver saldos por conta do mês anterior</summary>
        ${(data.opening_account_details || []).map((account) => item(esc(account.name), account.amount)).join('')}
      </details>` +
      item(
        'Entradas do mês · confirmadas' +
          (data.missing_statement_accounts.length ? ' · parcial' : ''),
        data.incoming,
        'summary-incoming',
      ) +
      item('Custos fixos pagos', data.fixed_paid) +
      item('Faturas com vencimento no mês · apuradas', data.cards) +
      data.card_details
        .map(
          (card) =>
            /* HTML */ `<p class="subtitle">
              ${esc(card.name)} · ${dateText(card.due_date)}:
              ${card.amount == null ? 'aguardando configuração / sincronização' : money(card.amount)}
            </p>`,
        )
        .join('') +
      item('Outros valores pagos no mês', data.other_paid || 0) +
      /* HTML */ `<details class="summary-account-balances">
        <summary>Ver outros valores pagos no mês</summary>
        ${(data.other_paid_details || []).map((t) => item(`${dateText(t.date)} · ${esc(t.description)}`, t.amount)).join('') || '<p class="subtitle">Nenhum outro valor pago no período.</p>'}
      </details>` +
      item('Total de despesas do mês', total, 'summary-total') +
      item(
        'Saldo após despesas' + (partial ? ' · parcial' : ''),
        balance,
        balance < 0 ? 'summary-negative' : 'summary-balance',
      ) +
      /* HTML */ `<div class="summary-future">
        ${item('Lançamentos futuros' + (data.future_cards?.partial ? ' · parcial' : ''), data.future_cards?.amount)}
        <p class="subtitle">Faturas dos cartões com vencimento em
          ${data.future_cards?.month ? esc(new Date(data.future_cards.month + '-01T12:00:00').toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })) : 'mês seguinte'} · BRL.
          ${(data.future_cards?.missing_cards || []).length ? `Aguardando sincronização: ${data.future_cards.missing_cards.map(esc).join(', ')}.` : 'Valores apurados até a última sincronização.'}
        </p>
        ${(data.future_cards?.details || []).length ? `<details class="summary-account-balances"><summary>Ver faturas do mês seguinte</summary>${data.future_cards.details.map(card => item(esc(card.name) + (card.due_date ? ` · vence em ${dateText(card.due_date)}` : ''), card.amount)).join('')}</details>` : ''}
      </div>`;
  } catch (error) {
    if (target.isConnected) {
      target.textContent = error.message;
      monthlyBudget = { period: target.dataset.period, error: true };
      refreshBudgetLegend();
    }
  }
}

/* BLOCO — Evolução mensal: barras de receitas/despesas e linha do saldo após despesas. */
function financialEvolutionPanel() {
  return /* HTML */ `<section class="panel financial-evolution" style="margin-bottom:22px">
    <div class="panel-title"><h2>${icon('trend')} Evolução financeira mensal</h2></div>
    <p class="subtitle">
      Últimos 12 meses até o mês selecionado. Receitas confirmadas no extrato; despesas = custos
      fixos pagos + faturas do mês + outros valores pagos. Saldo inclui a abertura do mês.
    </p>
    <div id="financial-evolution" data-period="${selectedPeriod}" aria-live="polite">
      Carregando evolução mensal…
    </div>
  </section>`;
}
/* BLOCO — Desenha receitas, despesas e saldo, preservando meses sem dados e valores negativos. */
function financialEvolutionChart(months) {
  // No app, exibe primeiro os meses recentes sem alterar a série recebida nem a ordem do site.
  if (isAndroidApp()) months = [...months].sort((a, b) => b.month.localeCompare(a.month));
  if (!months.some((m) => m.available))
    return '<p class="empty">Ainda não há dados financeiros nos meses deste período. Sincronize extratos e faturas para acompanhar a evolução.</p>';
  const width = Math.max(240, Math.min(1020, document.querySelector('#financial-evolution')?.clientWidth || 1020)),
    height = 300,
    left = width < 600 ? 46 : 75,
    right = 20,
    top = 25,
    bottom = 250;
  const values = months
    .filter((m) => m.available)
    .flatMap((m) => [Number(m.income), Number(m.expenses), Number(m.balance)]);
  let low = Math.min(0, ...values),
    high = Math.max(0, ...values);
  if (high === low) high = low + 1;
  const margin = (high - low) * 0.12;
  high += margin;
  if (low < 0) low -= margin;
  const y = (value) => bottom - ((Number(value) - low) / (high - low)) * (bottom - top);
  const step = (width - left - right) / months.length;
  const barWidth = Math.min(20, step * 0.26);
  const x = (i) => left + step * (i + 0.5);
  const label = (m) => m.slice(5) + '/' + m.slice(0, 4);
  const colors = { income: '#00a678', expenses: '#e05263', balance: '#0068f5' };
  const ticks = Array.from({ length: 5 }, (_, i) => {
    const value = low + ((high - low) * i) / 4;
    return /* HTML */ `<line
        x1="${left}"
        y1="${y(value)}"
        x2="${width - right}"
        y2="${y(value)}"
        stroke="#e8edf6"
      /><text x="${left - 10}" y="${y(value) + 4}" text-anchor="end"
        >${value.toLocaleString('pt-BR', { notation: 'compact', maximumFractionDigits: 1 })}</text
      >`;
  }).join('');
  const bars = months
    .map(
      (m, i) =>
        /* HTML */ `${
            m.available
              ? ['income', 'expenses']
                  .map((key, j) => {
                    const value = Number(m[key]);
                    return /* HTML */ `<rect
                      x="${x(i) - barWidth - 2 + j * (barWidth + 3)}"
                      y="${Math.min(y(0), y(value))}"
                      width="${barWidth}"
                      height="${Math.abs(y(value) - y(0))}"
                      rx="3"
                      fill="${colors[key]}"
                      tabindex="0"
                      ><title>
                        ${label(m.month)} · ${key === 'income' ? 'Receitas' : 'Despesas'}:
                        ${money(value)}
                      </title></rect
                    >`;
                  })
                  .join('')
              : '<text x="' + x(i) + '" y="' + (bottom - 8) + '" text-anchor="middle">—</text>'
          }<text x="${x(i)}" y="${bottom + 18}" text-anchor="${width < 760 ? 'end' : 'middle'}" ${width < 760 ? `transform="rotate(-55 ${x(i)} ${bottom + 18})"` : ''}>${width < 760 ? m.month.slice(5) + '/' + m.month.slice(2, 4) : label(m.month)}</text>`,
    )
    .join('');
  // Meses sem dados interrompem a linha, em vez de inventar saldos zerados.
  let path = '',
    active = false;
  months.forEach((m, i) => {
    if (!m.available) {
      active = false;
      return;
    }
    path += `${active ? 'L' : 'M'}${x(i)},${y(m.balance)} `;
    active = true;
  });
  const points = months
    .map((m, i) =>
      m.available
        ? /* HTML */ `<circle
            cx="${x(i)}"
            cy="${y(m.balance)}"
            r="5"
            fill="${colors.balance}"
            stroke="white"
            stroke-width="2"
            tabindex="0"
            ><title>
              ${label(m.month)} · Saldo após despesas${m.partial ? ' (parcial)' : ''}:
              ${money(m.balance)}
            </title></circle
          >`
        : '',
    )
    .join('');
  return /* HTML */ `<div class="financial-chart-legend">
      <span><i style="background:${colors.income}"></i>Receitas</span
      ><span><i style="background:${colors.expenses}"></i>Despesas</span
      ><span><i style="background:${colors.balance}"></i>Saldo após despesas</span>
    </div>
    <div
      class="financial-chart-scroll"
      aria-label="Gráfico mensal ajustado à largura da tela"
    >
      <svg
        class="chart financial-chart"
        viewBox="0 0 ${width} ${height}"
        role="img"
        aria-label="Evolução mensal de receitas, despesas e saldo, em reais"
      >
        <text x="8" y="18">BRL</text>
        ${ticks}
        <line x1="${left}" y1="${y(0)}" x2="${width - right}" y2="${y(0)}" stroke="#91a4c2" />
        ${bars}
        <path d="${path}" fill="none" stroke="${colors.balance}" stroke-width="3" />
        ${points}
      </svg>
    </div>
    <p class="subtitle">
      Meses sem dados aparecem com
      —.${months.some((m) => m.available && m.partial) ? ' Saldos parciais: há contas sem saldo anterior ou extrato completo.' : ''}
      Toque nos pontos ou consulte os valores abaixo.
    </p>
    <details>
      <summary>Ver valores por mês</summary>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Mês</th>
              <th>Receitas</th>
              <th>Despesas</th>
              <th>Saldo após despesas</th>
            </tr>
          </thead>
          <tbody>
            ${months
              .map(
                (m) =>
                  /* HTML */ `<tr>
                    <td>${label(m.month)}</td>
                    <td>${m.available ? money(m.income) : '—'}</td>
                    <td>${m.available ? money(m.expenses) : '—'}</td>
                    <td>
                      ${m.available ? money(m.balance) + (m.partial ? ' · parcial' : '') : '—'}
                    </td>
                  </tr>`,
              )
              .join('')}
          </tbody>
        </table>
      </div>
    </details>`;
}
/* BLOCO — Carrega a série mensal e descarta a resposta se o usuário já mudou de tela. */
let financialEvolutionResizeObserver;
async function loadFinancialEvolution() {
  const target = document.querySelector('#financial-evolution');
  if (!target) return;
  if (demo || unavailable) {
    target.textContent = 'Conecte o banco para consultar a evolução financeira.';
    return;
  }
  try {
    const data = await api(
      `financial-evolution?month=${encodeURIComponent(target.dataset.period)}`,
    );
    if (target.isConnected) {
      financialEvolutionResizeObserver?.disconnect();
      let chartWidth = target.clientWidth;
      target.innerHTML = financialEvolutionChart(data.months);
      const observer = new ResizeObserver(() => {
        if (!target.isConnected) return observer.disconnect();
        if (target.clientWidth === chartWidth) return;
        chartWidth = target.clientWidth;
        const expanded = target.querySelector('details')?.open;
        target.innerHTML = financialEvolutionChart(data.months);
        if (expanded) target.querySelector('details')?.setAttribute('open', '');
      });
      financialEvolutionResizeObserver = observer;
      observer.observe(target);
    }
  } catch (error) {
    if (target.isConnected) target.textContent = error.message;
  }
}

/* BLOCO — Compõe distribuição da renda, resumo financeiro, evolução e patrimônio. */
function overview() {
  monthlyBudget = null;
  const month = selectedPeriod;
  const expenses = rows('fixed_costs').filter((r) => r.due_date?.startsWith(month));
  const investedMonth = sum(investmentContributions().filter((r) => r.due_date?.startsWith(month)));
  // A renda exibida e a legenda usam a mesma soma mensal do planejamento.
  const income = registeredIncomeTotal();
  const p = [
    Number(state.settings.fixed_percent ?? 50),
    Number(state.settings.credit_percent ?? 40),
    Number(state.settings.investment_percent ?? 10),
  ];
  const allocation = budgetAllocation(income, p);
  const colors = ['#0879ff', '#00be8b', '#ffac5c'];
  const labels = ['Custo Fixo', 'Cartão de Crédito', 'Investimento'];
  const gradient = `conic-gradient(${colors[0]} 0 ${p[0]}%,${colors[1]} ${p[0]}% ${p[0] + p[1]}%,${colors[2]} ${p[0] + p[1]}% ${p.reduce((a, b) => a + b, 0)}%,#edf1f8 0)`;
  return (
    heading(`Olá, ${esc(state.settings.user_name)}!`, 'Confira um resumo da sua vida financeira.') +
    /* HTML */ `<div class="grid strategic-cards">
        <section class="panel income-distribution-panel">
          <div class="panel-title"><h2>Distribuição da sua renda mensal</h2></div>
          <div class="donut-layout">
            <div
              class="donut"
              id="budget-donut"
              style="background:${gradient}"
              role="img"
              aria-label="Distribuição planejada da renda mensal"
            >
              <div class="donut-inner">
                <strong id="budget-income-label">${money(income)}</strong
                ><small>Renda mensal</small>
              </div>
            </div>
            <div class="legend" id="budget-legend">${budgetLegend(income, p)}</div>
          </div>
        </section>
        <section class="panel monthly-summary-panel">
          <div class="panel-title"><h2>${icon('calendar')} Resumo financeiro do mês</h2></div>
          <div id="monthly-summary" data-period="${month}" aria-live="polite">
            <p class="subtitle">Carregando valores do mês…</p>
          </div>
          <button class="text-link" data-action="fixed_costs">Ver renda e custos fixos →</button>
        </section>
      </div>
      ${financialEvolutionPanel()}
      <section class="panel investment-banner">
        <div>
          <div class="panel-title">
            <h2>${icon('trend')} Seus Investimentos</h2>
            <span class="positive">Patrimônio em construção</span>
          </div>
          <div class="stats-row">
            <div>
              <div class="label">Aportes no período</div>
              <div class="value">${money(investedMonth)}</div>
            </div>
            <div>
              <div class="label">Posição atual (BRL)</div>
              <div class="value">${money(sum(brlInvestmentPositions()))}</div>
            </div>
          </div>
        </div>
        ${positionEvolution()}
      </section>`
  );
}

/* BLOCO 4 — Listagens reutilizáveis, pesquisa, botões e estados vazios. */
const titles = {
  incomes: 'Rendas cadastradas',
  fixed_costs: 'Custos fixos',
  cards: 'Meus Cartões',
  accounts: 'Minhas Contas',
  investments: 'Meus Investimentos',
  expenses: 'Custos fixos',
  categories: 'Categorias',
};
const singular = {
  incomes: 'Renda',
  fixed_costs: 'Custo fixo',
  cards: 'Cartão',
  accounts: 'Conta',
  investments: 'Investimento',
  expenses: 'Despesa',
  categories: 'Categoria',
};
/* BLOCO — Identidade bancária: nomes normalizados e imagens locais. */
const bankCatalog = window.BANK_CATALOG || [];
const normalizeBank = (value) =>
  String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
/* BLOCO — Relaciona nomes e aliases do cadastro às identidades visuais disponíveis. */
function identifyBank(record) {
  for (const candidate of [record.institution, record.name]) {
    const text = normalizeBank(candidate);
    const match = bankCatalog.find((bank) =>
      [bank.name, bank.id, ...bank.aliases].some((alias) => {
        const token = normalizeBank(alias);
        return text === token || (' ' + text + ' ').includes(' ' + token + ' ');
      }),
    );
    if (match) return match;
  }
  return null;
}
/* BLOCO — Resolve a imagem local do banco sem depender de serviços externos. */
function bankLogo(bank) {
  return `${location.protocol === 'file:' ? './banks/' : '/static/banks/'}${bank.id}.svg`;
}
// Logos de exchanges carregadas do projeto, sem chamadas a serviços de imagem.
const exchangeNames = { binance: 'Binance', bybit: 'Bybit', kraken: 'Kraken', mercadobitcoin: 'Mercado Bitcoin' };
/* BLOCO — Entrega a identidade visual das exchanges suportadas. */
function exchangeLogo(exchange, size = 36) {
  if (!exchangeNames[exchange]) return '';
  const base = location.protocol === 'file:' ? './exchanges/' : '/static/exchanges/';
  return /* HTML */ `<img
    class="exchange-logo"
    src="${base}${exchange}.svg"
    alt="Logo ${exchangeNames[exchange]}"
    width="${size}"
    height="${size}"
    style="width:${size}px;height:${size}px"
  />`;
}
/* BLOCO — Monta os seletores visuais das exchanges aceitas pelo backend. */
function exchangeChoices() {
  return /* HTML */ `<div class="exchange-choices" role="group" aria-label="Escolha sua exchange">
    ${Object.entries(exchangeNames)
      .map(
        ([id, name]) =>
          /* HTML */ `<button
            type="button"
            class="exchange-choice ${id === 'binance' ? 'active' : ''}"
            data-exchange-select="${id}"
            aria-pressed="${id === 'binance'}"
          >
            ${exchangeLogo(id, 42)}<span>${name}</span>
          </button>`,
      )
      .join('')}
  </div>`;
}
/* BLOCO — Mantém o seletor do formulário e a indicação visual da exchange em sincronia. */
function selectExchange(value) {
  const select = document.querySelector('#crypto-exchange');
  if (!select || !exchangeNames[value]) return;
  select.value = value;
  const mercado = value === 'mercadobitcoin';
  document.querySelector('#crypto-key-label').textContent = mercado ? 'Identificador da chave (API key ID)' : 'Chave API';
  document.querySelector('#crypto-secret-label').textContent = mercado ? 'Segredo da chave (API key secret)' : 'Chave secreta';
  document.querySelector('#crypto-auth-help').textContent = mercado
    ? 'Informe o identificador e o segredo de uma chave de leitura criada no Mercado Bitcoin. As credenciais são criptografadas no servidor. A consulta usa autenticação OAuth2 diretamente no domínio oficial do Mercado Bitcoin.'
    : 'As chaves são salvas criptografadas no servidor e não são devolvidas ao navegador. A consulta autentica diretamente no domínio oficial da exchange.';
  document.querySelector('#crypto-label').placeholder = 'Ex.: Minha conta na ' + exchangeNames[value];
  document.querySelectorAll('[data-exchange-select]').forEach((button) => {
    const active = button.dataset.exchangeSelect === value;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
}
document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-exchange-select]');
  if (button) selectExchange(button.dataset.exchangeSelect);
});
document.addEventListener('change', (event) => {
  if (event.target.id === 'crypto-exchange') selectExchange(event.target.value);
});

/* BLOCO — Escolhe logo ou iniciais para identificar uma instituição desconhecida. */
function mark(record) {
  const exchange = normalizeBank(record.institution);
  if (exchangeNames[exchange]) return exchangeLogo(exchange, 34);
  const bank = identifyBank(record);
  return bank
    ? /* HTML */ `<img
        class="bank-logo"
        src="${bankLogo(bank)}"
        alt="Logo ${esc(bank.name)}"
        width="34"
        height="34"
      />`
    : /* HTML */ `<span class="bank-mark"
        >${esc((record.institution || record.name || 'CF').slice(0, 2).toUpperCase())}</span
      >`;
}

// A arte não exibe dados sensíveis nem pressupõe bandeira ou número do cartão.
function creditCardArt(record) {
  const bank = identifyBank(record);
  const color = bank?.color || '#173f78';
  const foreground = bank?.foreground || '#ffffff';
  const bankName = bank?.name || record.institution || 'Seu banco';
  const credit = record.pluggy_data;
  const limit = record.amount == null ? 'Não informado' : recordMoney(record);
  return /* HTML */ `<div
    class="credit-card-art"
    style="--bank-color:${color};--bank-ink:${foreground}"
    role="img"
    aria-label="Cartão ${esc(record.name || 'de crédito')} · ${esc(bankName)} · limite ${esc(limit)}"
  >
    <div class="credit-card-top">
      <div class="credit-card-bank">
        ${bank ? /* HTML */ `<img src="${bankLogo(bank)}" alt="Logo ${esc(bankName)}" width="48" height="48" />` : icon('bank')}<span
          >${esc(bankName)}</span
        >
      </div>
      <span class="credit-card-tag">CRÉDITO</span>
    </div>
    <div class="credit-card-chip-row">
      <svg class="credit-card-chip" viewBox="0 0 44 34" aria-hidden="true">
        <rect x="1" y="1" width="42" height="32" rx="6" fill="#e3c88b" stroke="#b59761" />
        <path
          d="M15 1v10H1m42 0H29V1M15 33V23H1m42 0H29v10M15 11h14v12H15z"
          fill="none"
          stroke="#a38a5e"
        /></svg
      ><svg
        width="22"
        height="27"
        viewBox="0 0 24 30"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        aria-hidden="true"
      >
        <path d="M6 9a12 12 0 0 1 0 12m5-16a20 20 0 0 1 0 20m5-25a28 28 0 0 1 0 30" />
      </svg>
    </div>
    <div class="credit-card-number" aria-hidden="true">
      •••• &nbsp; •••• &nbsp; •••• &nbsp; ••••
    </div>
    <div class="credit-card-bottom">
      <div><small>NOME DO CARTÃO</small><strong>${esc(record.name || 'Meu cartão')}</strong></div>
      <div class="credit-card-due">
        <small>VENCIMENTO</small><strong>${dateText(record.due_date)}</strong>
      </div>
    </div>
  </div>`;
}
// Cada edição resolve datas somente do mês selecionado, sem herdar outro ciclo.
function cardForMonth(record, month = selectedPeriod) {
  const cycle = (state.card_cycles || []).find(
    (c) => c.card_id === record.id && c.reference_month.slice(0, 7) === month,
  );
  return {
    ...record,
    previous_closing_date: cycle?.previous_closing_date || null,
    closing_date: cycle?.closing_date || null,
    due_date: cycle?.due_date || null,
  };
}

/* BLOCO — Lista os cartões e permite editar seus cadastros e consultar faturas mensais. */
function cardsPage() {
  // Todos os cartões permanecem acessíveis para consultar suas faturas históricas.
  const cards = rows('cards');
  return (
    heading(
      'Cadastro de cartão',
      'Consulte no Pluggy as faturas com vencimento no mês selecionado.',
    ) +
    /* HTML */ `<section class="panel">
      <div class="panel-title">
        <h2>${icon('card')} Meus Cartões <span class="pill">${cards.length}</span></h2>
        <div class="toolbar">
          <input
            type="search"
            id="search"
            class="search"
            placeholder="Pesquisar cartão ou banco…"
            aria-label="Pesquisar cartões"
          /><button class="button" data-new="cards"><span class="record-create-label">Novo cartão</span></button>
        </div>
      </div>
      <div class="credit-card-grid">
        ${cards
          .map(
            (record) =>
              /* HTML */ `<article class="credit-card-item" data-row>
                ${creditCardArt({ ...record, due_date: null })}
                <div class="credit-card-info">
                  <div>
                    <span class="label">Limite total</span><strong>${recordMoney(record)}</strong>
                  </div>
                  <span class="pill ${record.status === 'Bloqueado' ? 'blocked' : ''}"
                    >${esc(record.status)}</span
                  >
                </div>
                ${record.pluggy_data ? /* HTML */ `<p class="subtitle">Limites da última sincronização, sem histórico mensal.</p>` : ''}
                <div
                  data-card-month="${record.id}"
                  data-period="${selectedPeriod}"
                  aria-live="polite"
                >
                  <p class="subtitle">Consultando fatura do mês no Pluggy…</p>
                </div>
                <div class="credit-card-actions">
                  <button
                    class="button secondary"
                    data-edit="${record.id}"
                    aria-label="Editar ${esc(record.name)}"
                  >
                    ${icon('edit')} Editar</button
                  ><button
                    class="button secondary"
                    data-delete="${record.id}"
                    aria-label="Excluir ${esc(record.name)}"
                  >
                    ${icon('trash')} Excluir
                  </button>
                </div>
              </article>`,
          )
          .join('')}
      </div>
      ${cards.length ? '' : '<p class="empty">Nenhum cartão com vencimento no mês selecionado. Escolha outro mês ou cadastre um cartão.</p>'}
      <p class="empty" id="no-results" hidden>Nenhum cartão encontrado para esta pesquisa.</p>
    </section>`
  );
}

/* Cada resposta pertence ao cartão e mês originais, mesmo após troca rápida do filtro. */
async function loadCardsMonth() {
  const targets = [...document.querySelectorAll('[data-card-month]')];
  // Consultas sequenciais evitam rajadas de requisições ao Pluggy.
  for (const target of targets) {
    if (!target.isConnected) return;
    const card = rows('cards').find((r) => String(r.id) === target.dataset.cardMonth);
    if (demo || unavailable || !card?.connection_id || !card?.pluggy_data) {
      target.textContent = 'Consulta mensal disponível para cartões vinculados ao Pluggy.';
      continue;
    }
    try {
      const result = await api(`cards/${card.id}/month`, {
        method: 'POST',
        body: JSON.stringify({ month: target.dataset.period }),
      });
      if (!target.isConnected) return;
      target.innerHTML = result.bills.length
        ? result.bills
            .map(
              (bill) =>
                /* HTML */ `<div class="expense">
                  <span
                    >Valor da fatura ·
                    ${esc(result.month.slice(5) + '/' + result.month.slice(0, 4))}<br /><small
                      >Vencimento: ${dateText(bill.due_date)}<br />Fechamento:
                      ${dateText(bill.closing_date)}</small
                    ></span
                  ><strong>${pluggyValue(bill.amount, bill.currency)}</strong>
                </div>`,
            )
            .join('')
        : '<p class="subtitle">O Pluggy não disponibilizou faturas com vencimento neste mês. Faturas abertas ou dados não fornecidos pelo banco podem não aparecer.</p>';
    } catch (error) {
      if (target.isConnected) target.textContent = error.message;
    }
  }
}

/* BLOCO — Consulta das contas cadastradas, sem duplicar registros financeiros. */
function bankAccountPage() {
  const accounts = rows('accounts');
  if (!accounts.length)
    return (
      heading('Extrato bancário', 'Acompanhe os dados e o saldo das suas contas.') +
      /* HTML */ `<section class="panel">
        <p class="empty">
          Nenhuma conta cadastrada. Adicione uma conta manualmente ou sincronize pelo Pluggy.
        </p>
        <div class="toolbar">
          <a class="button" href="#accounts">${icon('plus')} Cadastrar conta</a
          ><a class="button secondary" href="#connect">Conecte sua conta</a>
        </div>
      </section>`
    );
  const account = accounts.find((record) => record.id === selectedBankAccount) || accounts[0];
  selectedBankAccount = account.id;
  const currency = account.pluggy_data?.currency || 'BRL';
  return (
    heading('Extrato bancário', 'Acompanhe os dados e o saldo das suas contas.') +
    /* HTML */ ` <section class="panel" style="margin-bottom:22px">
        <div class="panel-title">
          <h2>${icon('bank')} Minhas contas bancárias</h2>
          <a class="button secondary" href="#connect">Atualizar pelo Pluggy</a>
        </div>
        <label for="bank-account-select">Selecione a conta</label>
        <select id="bank-account-select">
          ${accounts.map((record) => /* HTML */ `<option value="${record.id}" ${record.id === account.id ? 'selected' : ''}>${esc(record.name)} · ${esc(record.institution || 'Instituição não informada')}</option>`).join('')}
        </select>
      </section>
      <div class="grid">
        <section class="panel">
          <div class="panel-title">
            <h2>${mark(account)} ${esc(account.institution || 'Conta bancária')}</h2>
            <span class="pill ${account.status === 'Bloqueado' ? 'blocked' : ''}"
              >${esc(account.status)}</span
            >
          </div>
          <div class="label">${esc(account.name)}</div>
          <div class="value">${recordMoney(account)}</div>
          <p class="subtitle" style="margin-top:12px">
            Saldo ${account.pluggy_data ? 'da última sincronização' : 'informado manualmente'} ·
            ${esc(currency)}
          </p>
        </section>
        <section class="panel">
          <div class="panel-title">
            <h2>Informações da conta</h2>
            <button class="button secondary" data-edit="${account.id}">
              ${icon('edit')} Editar conta
            </button>
          </div>
          <div class="expense">
            <span>Nome / apelido</span><strong>${esc(account.name)}</strong>
          </div>
          <div class="expense">
            <span>Instituição</span><strong>${esc(account.institution || 'Não informada')}</strong>
          </div>
          <div class="expense">
            <span>Tipo</span><strong>${esc(account.detail || 'Não informado')}</strong>
          </div>
          <div class="expense">
            <span>Origem</span
            ><strong>${account.pluggy_data ? 'Pluggy' : 'Cadastro manual'}</strong>
          </div>
        </section>
      </div>
      <section class="panel" style="margin-top:22px">
        <div class="panel-title">
          <h2>${icon('receipt')} Extrato da conta</h2>
          <button
            type="button"
            class="button secondary"
            data-sync-statement="${account.id}"
            data-period="${selectedPeriod}"
          >
            Sincronizar extrato
          </button>
        </div>
        <div
          id="bank-statement"
          data-account="${account.id}"
          data-period="${selectedPeriod}"
          aria-live="polite"
        >
          <p class="subtitle">Carregando o extrato salvo…</p>
        </div>
      </section>`
  );
}

async function loadFutureCardChart() {
  const target = document.querySelector('#future-card-chart');
  if (!target) return;
  if (demo || unavailable) {
    target.textContent = 'Conecte o banco para consultar as faturas futuras.';
    return;
  }
  try {
    const data = await api('cards/future-charges');
    if (!target.isConnected) return;
    const max = Math.max(1, ...data.months.map(month => Number(month.amount || 0)));
    const label = month => new Date(month + '-01T12:00:00').toLocaleDateString('pt-BR', {month:'short', year:'2-digit'});
    target.innerHTML = `<div class="future-card-bars" role="img" aria-label="${esc(data.months.map(month => label(month.month) + ': ' + (month.amount == null ? 'sem dados' : money(month.amount)) + (month.estimated ? ', estimado' : '') + (month.partial ? ', parcial' : '')).join('; '))}">
      ${data.months.map(month => `<div class="future-card-column">
        <div class="future-card-bar-track"><div class="future-card-bar ${month.amount == null ? 'future-card-unknown' : ''}" style="height:${month.amount == null ? 100 : Math.max(2, Number(month.amount) / max * 100)}%"></div></div>
        <strong>${month.amount == null ? 'Sem dados' : money(month.amount)}</strong>
        <span>${esc(label(month.month))}</span><small>${month.estimated ? 'Estimado' : month.partial && month.amount != null ? 'Parcial' : ''}</small>
      </div>`).join('')}</div>
      <details class="summary-account-balances"><summary>Ver valores por cartão</summary>
      ${data.months.map(month => `<h3>${esc(label(month.month))}</h3>
        ${month.details.map(card => `<div class="expense"><span>${esc(card.name)}${card.due_date ? ' · ' + dateText(card.due_date) : ''}</span><strong>${card.amount == null ? 'Sem dados' : money(card.amount)}</strong></div>
          ${(card.projected_installments || []).map(part => `<p class="subtitle">${esc(part.description)} · parcela ${part.installment}/${part.installments}: ${money(part.amount)} · estimada</p>`).join('')}`).join('') || '<p>Nenhum cartão cadastrado.</p>'}
        ${month.partial ? `<p class="subtitle">Aguardando dados: ${month.missing_cards.map(esc).join(', ')}.</p>` : ''}`).join('')}
      </details>`;
  } catch (error) {
    if (target.isConnected) target.textContent = error.message;
  }
}
document.addEventListener('change', (event) => {
  if (event.target.id !== 'bank-account-select') return;
  selectedBankAccount = Number(event.target.value);
  render();
});

/* Extratos locais por conta e mês. A troca do seletor não consulta a API externa. */
async function loadBankStatement() {
  const target = document.querySelector('#bank-statement');
  if (!target) return;
  const accountId = target.dataset.account;
  const period = target.dataset.period;
  const button = document.querySelector('[data-sync-statement]');
  if (demo || location.protocol === 'file:') {
    target.textContent = 'Abra o painel conectado ao PostgreSQL para consultar o extrato Pluggy.';
    if (button) button.disabled = true;
    return;
  }
  try {
    const statement = await api(
      `accounts/${accountId}/statement?month=${encodeURIComponent(period)}`,
    );
    if (!target.isConnected) return;
    if (button) button.disabled = !statement.linked;
    if (!statement.linked) {
      target.textContent =
        'Esta conta é manual ou ainda não está vinculada ao Pluggy. Conecte a conta para consultar seus lançamentos.';
      return;
    }
    const totals = statement.totals
      .map(
        (total) =>
          /* HTML */ `<div class="metric-grid bill-summary bank-statement-summary" style="margin-top:18px">
              <div class="panel metric">
                <div class="label">Saldo do mês anterior (${esc(total.currency)})</div>
                <div class="value">
                  ${total.opening_balance == null ? 'Saldo anterior indisponível' : pluggyValue(total.opening_balance, total.currency)}
                </div>
                <small
                  >${esc(total.opening_source || 'Sincronize os extratos dos meses anteriores.')}</small
                >
                <button type="button" class="text-link" data-edit-opening="${accountId}"
                  data-period="${esc(period)}" data-currency="${esc(total.currency)}"
                  data-amount="${esc(total.opening_balance ?? '')}">
                  ${icon('edit')} Editar saldo
                </button>
              </div>
              <div class="panel metric">
                <div class="label">Entradas confirmadas (${esc(total.currency)})</div>
                <div class="value">${pluggyValue(total.incoming, total.currency)}</div>
              </div>
              <div class="panel metric">
                <div class="label">Saídas confirmadas</div>
                <div class="value">${pluggyValue(total.outgoing, total.currency)}</div>
              </div>
              <div class="panel metric">
                <div class="label">Saldo do período</div>
                <div class="value">
                  ${total.closing_balance == null ? 'Aguardando saldo / extrato' : pluggyValue(total.closing_balance, total.currency)}
                </div>
              </div>
            </div>
            ${Number(total.pending_incoming) || Number(total.pending_outgoing) ? /* HTML */ `<p class="subtitle">Pendentes / sem confirmação: entradas ${pluggyValue(total.pending_incoming, total.currency)} · saídas ${pluggyValue(total.pending_outgoing, total.currency)}. Não incluídos nos totais confirmados.</p>` : ''}`,
      )
      .join('');
    target.innerHTML = /* HTML */ `<p class="subtitle">
        Período: <b>${dateText(statement.start)} a ${dateText(statement.end)}</b>
      </p>
      <p class="subtitle">
        ${statement.synced_at ? 'Última sincronização: ' + esc(new Date(statement.synced_at).toLocaleString('pt-BR')) : 'Este mês ainda não foi consultado. Clique em Sincronizar extrato.'}
      </p>
      ${totals}
      ${
        statement.transactions.length
          ? /* HTML */ `<label for="statement-search">Pesquisar no extrato</label
              ><input
                type="search"
                id="statement-search"
                placeholder="Descrição, categoria ou valor…"
              />
              <div class="table-wrap" style="margin-top:16px">
                <table class="bank-statement-table">
                  <thead>
                    <tr>
                      <th>Data</th>
                      <th>Descrição</th>
                      <th>Categoria</th>
                      <th>Tipo</th>
                      <th>Status</th>
                      <th>Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${statement.transactions
                      .map(
                        (transaction) =>
                          /* HTML */ `<tr data-statement-row>
                            <td>${dateText(transaction.date)}</td>
                            <td style="white-space:normal;min-width:200px">
                              ${esc(transaction.description)}
                            </td>
                            <td>${esc(transaction.category)}</td>
                            <td>${Number(transaction.amount) < 0 ? 'Saída' : 'Entrada'}</td>
                            <td>
                              ${esc({ POSTED: 'Confirmado', PENDING: 'Pendente' }[transaction.status] || transaction.status)}
                            </td>
                            <td>${pluggyValue(transaction.amount, transaction.currency)}</td>
                          </tr>`,
                      )
                      .join('')}
                  </tbody>
                </table>
              </div>
              <p class="empty" id="statement-no-results" hidden>Nenhum lançamento encontrado.</p>`
          : statement.synced_at
            ? '<p class="empty">O Pluggy não retornou lançamentos desta conta no mês selecionado.</p>'
            : ''
      }`;
  } catch (error) {
    if (target.isConnected) target.textContent = error.message;
  }
}
document.addEventListener('input', (event) => {
  if (event.target.id !== 'statement-search') return;
  const search = event.target.value.toLocaleLowerCase('pt-BR');
  let visible = 0;
  document.querySelectorAll('[data-statement-row]').forEach((row) => {
    row.hidden = !row.textContent.toLocaleLowerCase('pt-BR').includes(search);
    if (!row.hidden) visible++;
  });
  document.querySelector('#statement-no-results').hidden = visible > 0;
});
document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-edit-opening]');
  if (!button) return;
  const account = state.records.find(record => record.id === Number(button.dataset.editOpening));
  const modal = document.createElement('dialog');
  modal.innerHTML = `<form id="opening-balance-form">
    <h2>Editar saldo do mês anterior (${esc(button.dataset.currency)})</h2>
    <p>${esc(account?.name || 'Conta bancária')} · mês de referência: ${esc(button.dataset.period)}</p>
    <label for="opening-amount">Saldo ao iniciar o mês</label>
    <input id="opening-amount" name="amount" type="number" step="0.01" min="-999999999999.99"
      max="999999999999.99" value="${esc(button.dataset.amount)}" required />
    <p class="subtitle">Este valor será a base do extrato deste mês e dos meses seguintes, até outro saldo inicial informado.</p>
    <p data-opening-error role="alert"></p>
    <div class="toolbar"><button type="button" class="button secondary" data-cancel-opening>Cancelar</button>
      <button type="submit" class="button">Salvar saldo</button></div>
  </form>`;
  modal.querySelector('[data-cancel-opening]').onclick = () => modal.close();
  modal.querySelector('form').onsubmit = async event => {
    event.preventDefault();
    const save = modal.querySelector('[type="submit"]');
    save.disabled = true;
    try {
      await api(`accounts/${button.dataset.editOpening}/opening-balance`, {
        method: 'PUT', body: JSON.stringify({month:button.dataset.period,
          currency:button.dataset.currency, amount:modal.querySelector('[name="amount"]').value}),
      });
      modal.close();
      if (route === 'bank_account') await loadBankStatement();
      toast('Saldo inicial atualizado.');
    } catch (error) {
      modal.querySelector('[data-opening-error]').textContent = error.message;
    } finally { save.disabled = false; }
  };
  modal.addEventListener('close', () => modal.remove(), {once:true});
  document.body.append(modal);
  modal.showModal();
});

document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-sync-statement]');
  if (!button) return;
  const accountId = button.dataset.syncStatement;
  const period = button.dataset.period;
  button.disabled = true;
  button.textContent = 'Sincronizando…';
  try {
    const result = await api(`accounts/${accountId}/statement/sync`, {
      method: 'POST',
      body: JSON.stringify({ month: period }),
    });
    const target = document.querySelector('#bank-statement');
    if (target?.dataset.account === accountId && target.dataset.period === period)
      await loadBankStatement();
    state = await api('data');
    await refreshNotifications();
    toast(
      `${result.count} lançamento(s) sincronizado(s). ${result.paid_costs?.length || 0} custo(s) e ${result.paid_incomes?.length || 0} renda(s) marcado(s) como Pago.`,
    );
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = 'Sincronizar extrato';
  }
});

/* BLOCO — Resumo da fatura do cartão selecionado, com origem dos dados explícita. */
function cardBillPage() {
  const cards = rows('cards');
  if (!cards.length)
    return (
      heading('Fatura do cartão', 'Consulte o resumo dos seus cartões de crédito.') +
      /* HTML */ `<section class="panel">
        <div class="empty">
          Cadastre um cartão ou sincronize sua conta para consultar os dados disponíveis.
        </div>
        <a class="button" href="#cards">${icon('plus')} Cadastrar cartão</a>
      </section>`
    );
  const selected = cards.find((card) => card.id === selectedBillCard) || cards[0];
  selectedBillCard = selected.id;
  const data = selected.pluggy_data;
  return (
    heading('Fatura do cartão', 'Selecione o cartão para visualizar seu resumo.') +
    /* HTML */ ` <section class="panel" style="margin-bottom:22px">
        <div class="panel-title">
          <h2>${icon('receipt')} Resumo do cartão</h2>
          <button class="button secondary" type="button" data-sync-bill="${selected.id}">
            Sincronizar lançamentos
          </button>
        </div>
        <label for="bill-card-select">Cartão</label>
        <select id="bill-card-select">
          ${cards.map((card) => /* HTML */ `<option value="${card.id}" ${card.id === selected.id ? 'selected' : ''}>${esc(card.name)} · ${esc(identifyBank(card)?.name || card.institution || 'Banco não informado')}</option>`).join('')}
        </select>
      </section>
      <div class="grid card-bill-summary-layout">
        <section class="panel">
          <article class="credit-card-item bill-card-preview">
            ${creditCardArt({ ...selected, due_date: null })}
            <div class="credit-card-info">
              <div>
                <span class="label">Status do cartão</span><strong>${esc(selected.status)}</strong>
              </div>
              <button class="button secondary" data-edit="${selected.id}">
                ${icon('edit')} Editar cartão
              </button>
            </div>
          </article>
        </section>
        <section class="panel">
          <div class="panel-title">
            <h2>Informações disponíveis</h2>
            <span class="pill">${data ? 'Última sincronização' : 'Cadastro manual'}</span>
          </div>
          <div class="expense">
            <span>Valor da fatura</span><strong id="selected-bill-value">Carregando…</strong>
          </div>
          <div class="expense">
            <span>Limite total</span><strong>${recordMoney(selected)}</strong>
          </div>
          <div class="expense">
            <span>Limite disponível</span
            ><strong
              >${data ? pluggyValue(data.available_limit, data.currency) : 'Não informado'}</strong
            >
          </div>
          <div class="expense"><span>Vencimento</span><strong id="bill-due-date">—</strong></div>
          <div class="expense">
            <span>Fechamento da fatura</span><strong id="bill-closing-date">—</strong>
          </div>
          <div class="expense">
            <span>Fechamento da fatura anterior</span
            ><strong id="bill-previous-closing-date">—</strong>
          </div>
        </section>
      </div>
      <section class="panel" style="margin-top:22px">
        <div class="panel-title"><h2>${icon('receipt')} Lançamentos da fatura</h2></div>
        <div
          id="bill-transactions"
          data-card="${selected.id}"
          data-period="${selectedPeriod}"
          aria-live="polite"
        >
          <p class="subtitle">Carregando os lançamentos salvos…</p>
        </div>
      </section>
      <section class="panel" style="margin-top:22px">
        <div class="panel-title"><h2>${icon('calendar')} Lançamentos futuros dos cartões</h2></div>
        <p class="subtitle">Próximos 6 meses a partir do mês seguinte ao atual · todos os cartões · BRL.
          Faturas importadas e estimativa das parcelas restantes por vencimento. Valores estimados podem mudar com novas compras, estornos e ajustes do cartão.</p>
        <div id="future-card-chart" data-period="${selectedPeriod}" aria-live="polite">Carregando faturas futuras…</div>
      </section>`
  );
}
document.addEventListener('change', (event) => {
  if (event.target.id !== 'bill-card-select') return;
  selectedBillCard = Number(event.target.value);
  render();
});

/* Carrega o cache do cartão/ciclo; somente o botão de sincronização consulta o Pluggy. */
async function loadCardBill() {
  const target = document.querySelector('#bill-transactions');
  if (!target) return;
  const cardId = target.dataset.card;
  const summary = document.querySelector('#selected-bill-value');
  // O resumo usa o mesmo ciclo e a mesma apuração da lista de lançamentos.
  // O saldo geral informado pelo banco pode incluir outros meses.
  if (summary) summary.textContent = 'Não disponível';
  if (demo || location.protocol === 'file:') {
    target.textContent =
      'Abra o painel conectado ao PostgreSQL para consultar os lançamentos do Pluggy.';
    return;
  }
  try {
    const bill = await api(
      `cards/${cardId}/bill?month=${encodeURIComponent(target.dataset.period)}`,
    );
    if (!target.isConnected) return;
    const button = document.querySelector('[data-sync-bill]');
    if (button) button.disabled = !bill.configured || !bill.linked;
    if (!bill.configured) {
      target.textContent = bill.message;
      return;
    }
    if (!bill.linked) {
      target.textContent =
        'Este cartão não está vinculado ao Pluggy. Sincronize a conta bancária em Conecte sua conta.';
      return;
    }
    document.querySelector('#bill-due-date').textContent = bill.cycle?.due_date
      ? dateText(bill.cycle.due_date)
      : bill.bills?.map((b) => dateText(b.due_date)).join(' / ') || 'Não disponível';
    document.querySelector('#bill-closing-date').textContent = bill.cycle?.closing_date
      ? dateText(bill.cycle.closing_date)
      : bill.bills?.map((b) => dateText(b.closing_date)).join(' / ') || 'Não disponível';
    document.querySelector('#bill-previous-closing-date').textContent = dateText(
      bill.cycle?.previous_closing_date,
    );
    if (summary && bill.synced_at) {
      // A mesma base do card Débitos (BRL), sem descontar estornos ou pagamentos.
      const brl = bill.totals.find((total) => total.currency === 'BRL');
      summary.textContent = brl
        ? pluggyValue(brl.charges, 'BRL')
        : bill.transactions.length
          ? 'Sem débitos em BRL'
          : pluggyValue(0, 'BRL');
      summary.title = 'Total de débitos em BRL do cartão e mês selecionados.';
    } else if (summary) {
      summary.textContent = 'Sincronize os lançamentos';
    }
    const totals = bill.totals
      .map(
        (total) =>
          /* HTML */ `<div class="metric-grid bill-summary card-bill-metrics" style="margin-top:18px">
            <div class="panel metric">
              <div class="label">Débitos (${esc(total.currency)})</div>
              <div class="value">${pluggyValue(total.charges, total.currency)}</div>
            </div>
            <div class="panel metric">
              <div class="label">Estornos e outros créditos</div>
              <div class="value">${pluggyValue(total.credits, total.currency)}</div>
            </div>
            <div class="panel metric">
              <div class="label">Saldo da fatura no período</div>
              <div class="value">${pluggyValue(total.net, total.currency)}</div>
            </div>
            <div class="panel metric">
              <div class="label">Pagamentos anteriores · conferência</div>
              <div class="value">${pluggyValue(total.payments_for_review, total.currency)}</div>
            </div>
          </div>`,
      )
      .join('');
    target.innerHTML = /* HTML */ `<p class="subtitle">
        Período: <b>${dateText(bill.start)} a ${dateText(bill.end)}</b> · mês de referência.
        ${bill.cycle?.previous_closing_date && bill.cycle?.closing_date ? `Lançamentos de ${dateText(bill.cycle.previous_closing_date)} (exclusivo) a ${dateText(bill.cycle.closing_date)} (inclusive), conforme o ciclo cadastrado deste mês.` : 'Lançamentos vinculados à fatura oficial do Pluggy.'}
      </p>
      <p class="subtitle">
        ${bill.synced_at ? 'Última sincronização: ' + esc(new Date(bill.synced_at).toLocaleString('pt-BR')) : 'Este período ainda não foi consultado. Clique em Sincronizar lançamentos.'}
      </p>
      ${totals}
      ${
        bill.transactions.length
          ? /* HTML */ `<div class="table-wrap">
              <table class="card-bill-table">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Descrição</th>
                    <th>Categoria</th>
                    <th hidden>Parcela</th>
                    <th hidden>Tipo</th>
                    <th>Status</th>
                    <th>Valor</th>
                  </tr>
                </thead>
                <tbody>
                  ${bill.transactions
                    .map(
                      (transaction) =>
                        /* HTML */ `<tr>
                          <td>${dateText(transaction.date)}</td>
                          <td style="white-space:normal;min-width:200px">
                            ${esc(transaction.description)}
                          </td>
                          <td>${esc(transaction.category)}</td>
                          <td hidden>
                            ${transaction.installment ? esc(transaction.installment) + (transaction.installments ? '/' + esc(transaction.installments) : '') : '—'}
                          </td>
                          <td hidden>
                            ${transaction.affects_balance === false ? 'Pagamento de fatura' : Number(transaction.amount) < 0 ? 'Crédito' : 'Débito'}
                          </td>
                          <td>
                            ${esc({ POSTED: 'Confirmado', PENDING: 'Pendente' }[transaction.status] || transaction.status)}
                          </td>
                          <td>${pluggyValue(transaction.amount, transaction.currency)}</td>
                        </tr>`,
                    )
                    .join('')}
                </tbody>
              </table>
            </div>`
          : bill.synced_at
            ? '<p class="empty">O Pluggy não retornou lançamentos deste cartão no período informado.</p>'
            : ''
      }
      <p class="subtitle" style="margin-top:16px">
        Pagamentos de fatura identificados são exibidos apenas para conferência e não reduzem o
        saldo deste período. Estornos e outros créditos continuam abatendo o saldo. Pendentes são
        incluídos quando retornados. A apuração pode diferir da fatura oficial por ajustes ou regras
        da instituição. Moedas diferentes são totalizadas separadamente.
      </p>`;
  } catch (error) {
    if (target.isConnected) target.textContent = error.message;
  }
}
document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-sync-bill]');
  if (!button) return;
  const cardId = button.dataset.syncBill;
  button.disabled = true;
  button.textContent = 'Sincronizando…';
  try {
    const period = document.querySelector('#bill-transactions')?.dataset.period;
    const result = await api(`cards/${cardId}/bill/sync`, {
      method: 'POST',
      body: JSON.stringify({ month: period }),
    });
    if (
      document.querySelector('#bill-transactions')?.dataset.card === cardId &&
      document.querySelector('#bill-transactions')?.dataset.period === period
    )
      await loadCardBill();
    await refreshNotifications();
    toast(`${result.count} lançamento(s) sincronizado(s).`);
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = 'Sincronizar lançamentos';
  }
});

// Valores externos respeitam a moeda e não confundem limite ausente com zero.
function pluggyValue(value, currency) {
  if (value == null) return 'Não informado';
  try {
    return Number(value).toLocaleString('pt-BR', {
      style: 'currency',
      currency: currency || 'BRL',
    });
  } catch {
    return `${esc(value)} ${esc(currency)}`;
  }
}
/* BLOCO — Respeita a moeda ou a quantidade correspondente ao tipo do registro. */
function recordMoney(record) {
  if (record.crypto_data)
    return `${esc(record.crypto_data.quantity)} ${esc(record.crypto_data.quantity_asset || record.crypto_data.asset)}`;
  if (record.amount === null) return 'Não informado';
  const currency = record.pluggy_data?.currency || 'BRL';
  try {
    return Number(record.amount).toLocaleString('pt-BR', { style: 'currency', currency });
  } catch {
    return `${esc(record.amount)} ${esc(currency)}`;
  }
}
// Histórico de compras é bruto e não é o custo das unidades restantes após vendas.
function binanceInvestmentCells(record) {
  const data = record.crypto_data;
  if (!data) return ['—', '—'];
  const partial =
    data.history_status === 'parcial'
      ? /* HTML */ `<br /><small
            >Histórico parcial ·
            ${data.history_pairs_completed ?? 0}/${data.history_pairs_total ?? '?'} pares
            consultados. Sincronize novamente para continuar.</small
          >`
      : '';
  // O custo usa conversão histórica estimada; nunca a cotação atual.
  const brl = (value) =>
    value == null
      ? 'Não disponível em BRL'
      : Number(value).toLocaleString('pt-BR', {
          style: 'currency',
          currency: 'BRL',
          maximumFractionDigits: 5,
        });
  const invested =
    data.invested_brl != null
      ? brl(data.invested_brl)
      : data.purchase_totals?.length
        ? 'Conversão histórica indisponível'
        : data.history_status === 'parcial'
          ? 'Histórico em coleta'
          : data.provider === 'mercadobitcoin' ? 'Histórico de compras não importado'
          : data.wallet_aggregate ? 'Histórico por ativo indisponível' : 'Compra Spot não encontrada';
  const conversionNote =
    data.invested_brl != null ? '<br><small>Conversão histórica estimada · sem taxas</small>' : '';
  const conversionPartial = data.invested_brl_partial
    ? '<br><small>Conversão parcial: nem todas as compras estão representadas.</small>'
    : '';
  const currentValue =
    data.valuation_currency === 'BRL' ? brl(data.current_value) : 'Não disponível em BRL';
  return [
    invested + conversionNote + conversionPartial + partial,
    currentValue +
      (data.provider === 'mercadobitcoin' ? `<br><small>Disponível: ${esc(data.available)} ${esc(data.asset)} · Bloqueado em ordens: ${esc(data.locked)} ${esc(data.asset)}</small>` : '') +
      (data.wallets?.length ? `<br><small>Carteiras: ${data.wallets.map(esc).join(', ')}</small>` : '') +
      (data.quoted_at
        ? /* HTML */ `<br /><small
              >Cotação: ${esc(new Date(data.quoted_at).toLocaleString('pt-BR'))}</small
            >`
        : ''),
  ];
}

// Totais dos custos listados no mês: usa o valor real da conciliação quando disponível.
function fixedCostTotals() {
  let planned = 0,
    paid = 0;
  for (const record of rows('fixed_costs')) {
    planned += Math.round(Number(record.amount || 0) * 100);
    paid += Math.round(
      Number(record.payment_match?.paid_amount ?? (record.status === 'Pago' ? record.amount : 0)) *
        100,
    );
  }
  const line = (label, cents, extra = '') =>
    /* HTML */ `<div class="expense ${extra}">
      <span>${label}</span><strong>${money(cents / 100)}</strong>
    </div>`;
  return /* HTML */ `<div class="fixed-cost-totals">
    ${line('Total previsto no mês', planned)}${line('Total pago', paid)}${line('Diferença (previsto − pago)', planned - paid, planned - paid < 0 ? 'summary-negative' : '')}
    <p class="subtitle">
      Valores dos custos fixos com vencimento no mês selecionado. Pagamentos conciliados usam o
      valor confirmado no extrato; custos marcados como pagos manualmente usam o valor previsto.
    </p>
  </div>`;
}

/* BLOCO — Monta os registros da categoria com pesquisa, edição e exclusão no mesmo painel. */
function table(kind) {
  // Oculta detalhes nas listas, preservando dados, pesquisa e campos dos formulários.
  const hideDetailColumn = (index) =>
    ['fixed_costs', 'incomes'].includes(kind) && [1, 2].includes(index);
  const headers =
    kind === 'incomes'
      ? ['Nome', 'Nome no extrato bancário', 'Categoria', 'Valor', 'Data de recebimento', 'Status']
      : kind === 'cards'
        ? ['Banco', 'Nome do Cartão', 'Limite', 'Vencimento', 'Status']
        : kind === 'accounts'
          ? ['Instituição', 'Tipo', 'Apelido', 'Saldo', 'Status']
          : kind === 'investments'
            ? [
                'Instituição',
                'Investimento',
                'Tipo',
                'Valor / quantidade atual',
                'Valor investido (BRL)',
                'Valor atual da posição (BRL)',
                'Data e origem',
              ]
            : kind === 'categories'
              ? ['Categoria', 'Usar em', 'Descrição']
              : [
                  'Nome',
                  'Nome no extrato bancário',
                  'Categoria',
                  'Valor previsto',
                  'Vencimento',
                  'Status',
                ];
  return /* HTML */ `<section class="panel">
    <div class="panel-title">
      <h2>${icon(routes[kind]?.[1] || 'grid')} ${titles[kind]}</h2>
      <div class="toolbar">
        <input
          type="search"
          class="search"
          placeholder="Pesquisar…"
          aria-label="Pesquisar registros"
          data-record-search
        />${kind === 'fixed_costs' ? '<button type="button" class="button secondary" data-action="reconcile-costs">Conferir pagamentos</button>' : ''}<button
          class="button"
          data-new="${kind}"
        >
          ${['fixed_costs', 'incomes', 'investments', 'accounts'].includes(kind) ? '' : icon('plus')}
          <span class="record-create-label">${kind === 'fixed_costs' ? 'Novo Custo Fixo' : kind === 'incomes' ? 'Nova Renda' : (kind === 'accounts' || kind === 'expenses' || kind === 'categories' ? 'Nova' : 'Novo') + ' ' + singular[kind]}</span>
        </button>
      </div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            ${headers.map((h, index) => /* HTML */ `<th ${hideDetailColumn(index) ? 'hidden' : ''}>${h}</th>`).join('')}
            <th>Ações</th>
          </tr>
        </thead>
        <tbody>
          ${rows(kind)
            .map((r) => {
              const status = /* HTML */ `<span
                  class="pill ${r.status === 'Bloqueado' || r.status === 'Pendente' ? 'blocked' : ''}"
                  >${esc(r.status)}</span
                >${r.payment_match ? /* HTML */ `<small class="payment-proof" title="${esc(r.payment_match.description)} · ${esc(r.payment_match.account_name || 'Extrato bancário')}">Extrato: ${dateText(r.payment_match.paid_date)} · ${money(r.payment_match.paid_amount)}${!r.payment_match.amount_matches ? '<br>Valor pago diferente do previsto' : ''}</small>` : ''}`;
              const bank = /* HTML */ `<div class="institution">
                ${mark(r)} ${esc(r.institution)}
              </div>`;
              const cells =
                kind === 'cards'
                  ? [
                      bank,
                      `${esc(r.name)}${r.pluggy_data ? '<br><small>Pluggy</small>' : ''}`,
                      `${recordMoney(r)}${r.pluggy_data ? /* HTML */ `<br /><small>Disponível: ${pluggyValue(r.pluggy_data.available_limit, r.pluggy_data.currency)}<br />Saldo: ${pluggyValue(r.pluggy_data.balance, r.pluggy_data.currency)}</small>` : ''}`,
                      dateText(r.due_date),
                      status,
                    ]
                  : kind === 'accounts'
                    ? [
                        bank,
                        esc(r.detail),
                        /* HTML */ `<b>${esc(r.name)}</b>`,
                        /* HTML */ `<b>${recordMoney(r)}</b>`,
                        status,
                      ]
                    : kind === 'investments'
                      ? [
                          bank,
                          esc(r.name),
                          esc(r.detail),
                          recordMoney(r),
                          ...binanceInvestmentCells(r),
                          /* HTML */ `${dateText(r.due_date)}<br /><small
                              >${r.crypto_data ? 'Saldo Binance' : r.pluggy_data ? 'Referência Pluggy' : 'Aporte manual'}</small
                            >`,
                        ]
                      : kind === 'categories'
                        ? [esc(r.name), r.category_type === 'incomes' ? 'Renda' : 'Custos fixos', esc(r.detail)]
                        : [
                            esc(r.name),
                            esc(r.statement_name || '—'),
                            esc(r.detail),
                            recordMoney(r),
                            dateText(r.due_date),
                            status,
                          ];
              return /* HTML */ `<tr data-row>
                ${cells.map((c, index) => /* HTML */ `<td ${hideDetailColumn(index) ? 'hidden' : ''}>${c}</td>`).join('')}
                <td>
                  <div class="actions">
                    <button data-edit="${r.id}" aria-label="Editar ${esc(r.name)}">
                      ${icon('edit')}</button
                    ><button data-delete="${r.id}" aria-label="Excluir ${esc(r.name)}">
                      ${icon('trash')}
                    </button>
                  </div>
                </td>
              </tr>`;
            })
            .join('')}
        </tbody>
      </table>
      ${kind === 'fixed_costs' ? fixedCostTotals() : ''}${kind === 'incomes' ? /* HTML */ `<div class="expense"><span>Total das rendas no mês</span><strong>${money(registeredIncomeTotal())}</strong></div>` : ''}${rows(kind).length ? '' : '<p class="empty">Nenhum registro. Comece pelo botão de cadastro.</p>'}
      <p class="empty" data-no-results hidden>Nenhum resultado para esta pesquisa.</p>
    </div>
  </section>`;
}

// Valores atuais Binance com cotação BRL podem compor o total monetário.
function brlInvestmentPositions() {
  return rows('investments')
    .map((record) => {
      // Pluggy fornece a posição líquida; Binance fornece o valor da posição cotada.
      if (record.pluggy_data?.type === 'INVESTMENT') {
        return { ...record, amount: record.pluggy_data.balance };
      }
      if (!record.crypto_data) return record;
      const data = record.crypto_data;
      return { ...record, amount: data.valuation_currency === 'BRL' ? data.current_value : null };
    })
    .filter(
      (record) =>
        record.amount != null &&
        (!record.crypto_data || record.crypto_data.valuation_currency === 'BRL') &&
        (!record.pluggy_data || record.pluggy_data.currency === 'BRL'),
    );
}

/* Distribuição por investimento: somente posições positivas expressas em reais. */
function investmentDistribution() {
  const all = rows('investments');
  const included = brlInvestmentPositions().filter(
    (record) => Number.isFinite(Number(record.amount)) && Number(record.amount) > 0,
  );
  const total = sum(included);
  const currentMoney = (value) =>
    Number(value).toLocaleString('pt-BR', {
      style: 'currency',
      currency: 'BRL',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  const excluded = all.length - included.length;
  const positions = [...included].sort((a, b) => Number(b.amount) - Number(a.amount));
  const palette = ['#0879ff', '#00ba88', '#ffac5c', '#8759e8', '#00a9c5', '#ec6389', '#5965bc'];
  let offset = 0;
  const slices = positions.map((record, index) => {
    const percent = (Number(record.amount) / total) * 100;
    const color = palette[index % palette.length];
    const start = offset;
    offset += percent;
    return { record, percent, color, start, end: offset };
  });
  const gradient = slices.length
    ? `conic-gradient(${slices.map((slice) => `${slice.color} ${slice.start}% ${slice.end}%`).join(',')})`
    : '#edf1f8';
  const description = slices.length
    ? slices
        .map(
          (slice) =>
            `${slice.record.name}: ${slice.percent.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`,
        )
        .join('; ')
    : 'Nenhuma posição positiva em reais disponível.';
  return /* HTML */ `<section class="panel investment-distribution" style="margin-bottom:22px">
    <div class="panel-title">
      <h2>${icon('trend')} Distribuição dos investimentos</h2>
      <span class="pill">Valor atual em BRL</span>
    </div>
    <div class="donut-layout">
      <div class="donut" style="background:${gradient}" role="img" aria-label="${esc(description)}">
        <div class="donut-inner">
          <strong>${currentMoney(total)}</strong><small>Valor atual total</small>
        </div>
      </div>
      <div class="legend investment-legend">
        ${
          slices.length
            ? slices
                .map(
                  (slice) =>
                    /* HTML */ ` <div class="legend-item">
                      <span class="dot" style="background:${slice.color}"></span>
                      <div>
                        <b>${esc(slice.record.name)}</b
                        ><small
                          >${esc(slice.record.institution)} · Valor atual:
                          ${currentMoney(slice.record.amount)} ·
                          ${slice.percent.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%</small
                        >
                      </div>
                    </div>`,
                )
                .join('')
            : '<p class="subtitle">Cadastre ou sincronize investimentos com saldo em reais para visualizar a distribuição.</p>'
        }
      </div>
    </div>
    <p class="subtitle">
      Distribuição pelo valor atual da posição na última sincronização: cotação em reais das exchanges
      e saldo líquido do Pluggy. Cadastros manuais usam o último valor informado. Valores sem
      cotação BRL, ausentes ou não positivos ficam fora do
      cálculo.${excluded ? ` ${excluded} registro(s) fora do gráfico.` : ''}
    </p>
  </section>`;
}

/* BLOCO — Compõe posição observada, distribuição e registros de investimento. */
function investments() {
  return (
    heading('Conta de Investimento', 'Acompanhe seus investimentos e construa seu futuro.') +
    /* HTML */ `<section class="panel" style="margin-bottom:22px">
      <div class="panel-title">
        <h2>${icon('trend')} Visão do patrimônio</h2>
        <span class="positive">Posições observadas</span>
      </div>
      <div class="invest-layout">
        <div class="invest-stats">
          <div class="invest-stat">
            <div class="label">Posição atual (BRL)</div>
            <div class="value">${money(sum(brlInvestmentPositions()))}</div>
          </div>
        </div>
        ${positionEvolution()}
      </div>
    </section>` +
    investmentDistribution() +
    table('investments')
  );
}

/* BLOCO — Login e cadastro de usuários; senhas não entram no estado do painel. */
// Ilustração vetorial local: crescimento e moedas, sem serviços externos de imagem.
function loginIllustration() {
  const stacks = [
    { x: 35, h: 48 },
    { x: 145, h: 78 },
    { x: 255, h: 112 },
    { x: 365, h: 154 },
    { x: 475, h: 207 },
  ];
  return /* HTML */ `<svg class="login-coins" viewBox="0 0 600 350" aria-hidden="true">
    <defs>
      <linearGradient id="coin-metal">
        <stop stop-color="#6b6155" />
        <stop offset=".2" stop-color="#f5dfae" />
        <stop offset=".45" stop-color="#b98d4c" />
        <stop offset=".65" stop-color="#fff0c6" />
        <stop offset="1" stop-color="#645444" />
      </linearGradient>
      <linearGradient id="growth-glow" x2="1" y2="0">
        <stop stop-color="#17a77d" />
        <stop offset="1" stop-color="#8affd8" />
      </linearGradient>
      <filter id="soft-glow"><feGaussianBlur stdDeviation="8" /></filter>
      <linearGradient id="floor-shine" x2="0" y2="1">
        <stop stop-color="#a9d8ff" stop-opacity=".35" />
        <stop offset="1" stop-color="#082442" stop-opacity="0" />
      </linearGradient>
    </defs>
    <path
      d="M20 230Q280 186 550 45"
      fill="none"
      stroke="#35ffd2"
      stroke-width="14"
      opacity=".5"
      filter="url(#soft-glow)"
    />
    <path d="M20 230Q280 186 550 45" fill="none" stroke="url(#growth-glow)" stroke-width="5" />
    <path d="m519 47 42-12-17 40-3-23z" fill="#73ffd7" />
    <ellipse cx="300" cy="293" rx="300" ry="52" fill="url(#floor-shine)" />
    ${stacks.map(({ x, h }) => Array.from({ length: Math.floor(h / 6) }, (_, i) => /* HTML */ `<g transform="translate(${x},${278 - i * 6})"><path d="M0 0v5c0 9 85 9 85 0V0" fill="url(#coin-metal)" stroke="#d6c29a" stroke-width=".6" /><ellipse cx="42.5" rx="42.5" ry="7" fill="#c7ae7e" stroke="#f2dfbb" /><path d="M5 2v5m5-4v5m6-4v5m6-4v5m6-4v5m6-4v5m6-4v5m6-4v5m6-4v5m6-4v5m6-4v5m6-5v5m6-6v5" stroke="#66594c" opacity=".7" stroke-width="1" /></g>`).join('')).join('')}
  </svg>`;
}

/* BLOCO — Arte exclusiva do login no aplicativo, fornecida pelo proprietário.
   A janela CSS mostra somente o dragão; marca, frases e campos continuam em HTML. */
function apkLoginIllustration() {
  const image =
    (location.protocol === 'file:' ? './branding/' : '/static/branding/') +
    'app-login-reference.jpg';
  return /* HTML */ `<div class="apk-login-art" aria-hidden="true">
    <img src="${image}" width="1536" height="2752" alt="" decoding="async" fetchpriority="low" />
  </div>`;
}

/* BLOCO — Arte decorativa do login web, reaproveitada da referência do proprietário.
   O picture evita baixar a imagem grande em celulares; o APK mantém sua ilustração atual. */
function webLoginIllustration() {
  const image =
    (location.protocol === 'file:' ? './branding/' : '/static/branding/') +
    'site-login-reference.jpg';
  return /* HTML */ `<picture class="web-login-art" aria-hidden="true">
    <source media="(min-width: 601px)" srcset="${image}" />
    <img
      src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='1' height='1'/%3E"
      width="2752"
      height="1536"
      alt=""
      decoding="async"
      fetchpriority="low"
    />
    <svg class="web-chart-rise" viewBox="0 0 2752 1536" aria-hidden="true"><path class="web-chart-rise-line" d="M850 1200 C1000 1170 1130 1050 1252 778" pathLength="1"/><path class="web-chart-rise-tip" d="M1230 782 L1270 744 L1268 799 L1253 778 Z"/></svg>
  </picture>`;
}

/* BLOCO — Prepara o formulário de login e adapta a apresentação para o APK. */
function renderLogin() {
  document.querySelector('#mobile-menu')?.close();
  clearNotifications();
  if (pushSupported())
    navigator.serviceWorker
      .getRegistration('/')
      .then((registration) => registration && pushWorkerMessage(registration, null))
      .catch(() => {});
  document.body.classList.remove('onboarding-mode');
  document.body.classList.add('login-mode');
  document.body.classList.toggle('login-apk', isAndroidApp());
  state = { records: [], settings: { user_name: 'Usuário' } };
  document.querySelector('#navigation').innerHTML = '';
  document.querySelector('#profile').textContent = 'Entrar';
  document.querySelector('#logout').hidden = true;
  // A apresentação inicial é opcional e exclusiva da instalação Android.
  if (!authState.user && window.ApkIntro?.shouldShow(isAndroidApp())) {
    window.ApkIntro.show(content, renderLogin);
    return;
  }
  const lock =
    '<svg viewBox="0 0 48 54" fill="none" aria-hidden="true"><path d="M12 24V15a12 12 0 0 1 24 0v9" stroke="currentColor" stroke-width="6"/><rect x="4" y="22" width="40" height="30" rx="6" fill="currentColor"/><circle cx="24" cy="35" r="4" fill="white"/><path d="M24 37v6" stroke="white" stroke-width="3"/></svg>';
  content.innerHTML = /* HTML */ `<div class="login-screen">
    <svg
      class="login-background"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="login-navy">
          <stop stop-color="#061b3c" />
          <stop offset="1" stop-color="#073b68" />
        </linearGradient>
        <linearGradient id="login-green" x2="0" y2="1">
          <stop stop-color="#69f0a2" />
          <stop offset="1" stop-color="#00bda0" />
        </linearGradient>
      </defs>
      <path d="M0 0H63C40 18 48 36 51 58S54 86 45 100H0Z" fill="#007ac9" />
      <path d="M0 0H62C39 18 49 35 51 58S54 86 45 100H0Z" fill="url(#login-green)" />
      <path d="M0 0H54C39 23 49 37 51 60S53 87 43 100H0Z" fill="url(#login-navy)" />
      <path d="M75 100Q84 91 100 85V100Z" fill="#c5ddff" opacity=".65" />
    </svg>
    <section class="login-hero" aria-label="Optimus Finance">
      <div class="login-brand">
        <img
          class="optimus-logo"
          src="${location.protocol === 'file:' ? './icons/' : '/static/icons/'}app-icon-512.png?v=20261118-dragon"
          width="112"
          height="112"
          alt=""
        />
        <span>Optimus<strong>Finance</strong></span>
      </div>
      <h2>Organize suas finanças,<br /><strong>realize seus planos!</strong></h2>
      ${
        !isAndroidApp()
          ? /* HTML */ ` <ul class="login-benefits">
              <li><span>${icon('trend')}</span>Controle seus gastos</li>
              <li>
                <span
                  ><svg
                    viewBox="0 0 28 28"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.6"
                    aria-hidden="true"
                  >
                    <path
                      d="M8 9 6 5l7 3c8-1 12 3 12 9h-3l-2 5h-4l-1-3h-5l-1 3H5l-1-7H1v-4l4-1M12 11h5M20 12h1"
                    />
                    <circle cx="14" cy="4" r="3" /></svg></span
                >Acompanhe seus investimentos
              </li>
              <li>
                <span
                  ><svg
                    viewBox="0 0 28 28"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    aria-hidden="true"
                  >
                    <circle cx="13" cy="15" r="10" />
                    <circle cx="13" cy="15" r="6" />
                    <path d="m13 15 11-12m-5 0h5v5" /></svg></span
                >Planeje seu futuro
              </li>
            </ul>`
          : ''
      }
      ${isAndroidApp() ? apkLoginIllustration() : webLoginIllustration()}
    </section>
    <section class="login-form-side">
      <div class="login-card">
        <div class="login-lock">${lock}</div>
        <h1>Bem-vindo de volta!</h1>
        <p class="login-intro">Faça login para acessar sua conta</p>
        <form id="login-form">
          <div class="login-field">
            <span>${isAndroidApp() ? icon('user') : icon('users')}</span
            ><input
              aria-label="Usuário"
              name="login"
              placeholder="Usuário"
              autocomplete="username"
              required
              maxlength="64"
            />
          </div>
          <div class="login-field">
            <span>${lock}</span
            ><input
              id="login-password"
              aria-label="Senha"
              name="password"
              type="password"
              placeholder="Senha"
              autocomplete="current-password"
              required
              maxlength="128"
            /><button
              type="button"
              class="password-toggle"
              aria-label="Mostrar senha"
              aria-pressed="false"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                aria-hidden="true"
              >
                <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" />
                <circle cx="12" cy="12" r="3" />
                <path class="eye-slash" d="m3 21 18-18" />
              </svg>
            </button>
          </div>
          <div class="login-options">
            <label><input type="checkbox" name="remember" value="true" />Lembrar-me</label
            ><button type="button" class="login-forgot">Esqueceu sua senha?</button>
          </div>
          <p id="auth-error" role="alert"></p>
          <button class="login-submit" type="submit">
            <svg
              viewBox="0 0 30 30"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              aria-hidden="true"
            >
              <path d="M16 4h9v22h-9M3 15h17m-7-7 7 7-7 7" /></svg
            >Entrar
          </button>
        </form>
        <div class="login-safety">
          <svg viewBox="0 0 24 28" aria-hidden="true">
            <path d="m12 1 10 4v8c0 7-10 13-10 13S2 20 2 13V5Z" fill="#2fd479" />
            <path d="m7 13 3 3 7-8" fill="none" stroke="white" stroke-width="2.5" /></svg
          ><span>Seus dados estão seguros conosco</span>
        </div>
      </div>
    </section>
  </div>`;
  // No app, a marca ocupa o topo do card em vez do cadeado e da saudação.
  // O mesmo nó é movido para não duplicar imagem ou nome; o site mantém sua estrutura.
  if (isAndroidApp()) {
    const brand = content.querySelector('.login-hero .login-brand');
    const card = content.querySelector('.login-card');
    card.querySelector('.login-lock')?.remove();
    card.querySelector('h1')?.remove();
    brand.setAttribute('role', 'heading');
    brand.setAttribute('aria-level', '1');
    brand.setAttribute('aria-label', 'Optimus Finance');
    card.prepend(brand);
  } else {
    // No site, nome e frase formam uma coluna ao lado da logo, alinhada ao centro.
    const hero = content.querySelector('.login-hero');
    const brand = hero.querySelector('.login-brand');
    const copy = document.createElement('div');
    copy.className = 'web-login-brand-copy';
    copy.append(brand.querySelector(':scope > span'), hero.querySelector('h2'));
    brand.append(copy);
  }
}

document.addEventListener('click', (event) => {
  const toggle = event.target.closest('.password-toggle');
  if (toggle) {
    const input = document.querySelector('#login-password');
    const visible = input.type === 'password';
    input.type = visible ? 'text' : 'password';
    toggle.setAttribute('aria-label', visible ? 'Ocultar senha' : 'Mostrar senha');
    toggle.setAttribute('aria-pressed', String(visible));
  }
  if (event.target.closest('.login-forgot'))
    document.querySelector('#auth-error').textContent =
      'Solicite a recuperação do acesso ao administrador do painel.';
});

/* BLOCO — Monta o cadastro de acessos e a área de gestão restrita aos administradores. */
function usersPage() {
  const setup = authState.setup_required;
  return (
    heading('Perfil e usuários', 'Cadastre os acessos ao painel e escolha as permissões.') +
    /* HTML */ ` <section class="panel">
        <h2>${setup ? 'Cadastrar primeiro administrador' : 'Adicionar usuário'}</h2>
        <p class="subtitle">
          ${setup ? 'Após cadastrar o primeiro administrador, o painel passará a exigir login.' : 'Administrador: usuários, conexões e configurações. Editor: consulta e edição dos dados financeiros. Cada usuário possui um painel financeiro privado e suas próprias conexões. Administrar acessos não abre os dados financeiros de outro usuário. Novos usuários começam com o painel vazio.'}
        </p>
        <form id="user-form" class="auth-panel">
          <label
            >Login<input
              name="login"
              autocomplete="off"
              pattern="[a-zA-Z0-9._-]{3,64}"
              minlength="3"
              maxlength="64"
              required
          /></label>
          <label
            >Senha<input
              name="password"
              type="password"
              autocomplete="new-password"
              minlength="8"
              maxlength="128"
              required /></label
          ><small>De 8 a 128 caracteres.</small>
          <label
            >Tipo de perfil<select name="role">
              <option value="administrador">Administrador</option>
              ${setup ? '' : '<option value="editor">Editor</option>'}
            </select></label
          >
          <p id="user-error" role="alert"></p>
          <button class="button" type="submit">Cadastrar usuário</button>
        </form>
      </section>
      <section class="panel" style="margin-top:22px">
        <h2>Usuários cadastrados</h2>
        <div id="user-list">Carregando…</div>
      </section>`
  );
}

let managedUsers = [];
/* BLOCO — Busca acessos autorizados e exibe ações de alteração de senha e exclusão. */
async function loadUsers() {
  const target = document.querySelector('#user-list');
  if (authState.setup_required) {
    target.textContent = 'Nenhum usuário cadastrado.';
    return;
  }
  try {
    const result = await api('users');
    if (!target.isConnected) return;
    managedUsers = result.users;
    target.innerHTML = /* HTML */ `<div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Login</th>
              <th>Perfil</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            ${result.users
              .map(
                (user) =>
                  /* HTML */ `<tr>
                    <td>${esc(user.login)}${user.id === authState.user?.id ? ' (você)' : ''}</td>
                    <td>${user.role === 'administrador' ? 'Administrador' : 'Editor'}</td>
                    <td>
                      <button
                        type="button"
                        class="button secondary"
                        data-user-password="${user.id}"
                      >
                        Alterar senha
                      </button>
                      <button
                        type="button"
                        class="button secondary"
                        data-user-delete="${user.id}"
                        ${user.id === authState.user?.id ? 'disabled title="Use outro administrador para excluir seu acesso"' : ''}
                      >
                        ${icon('trash')} Excluir
                      </button>
                    </td>
                  </tr>`,
              )
              .join('')}
          </tbody>
        </table>
      </div>
      <dialog id="user-password-dialog">
        <form id="user-password-form">
          <h2 id="user-password-title">Alterar senha</h2>
          <label
            >Nova senha<input
              name="password"
              type="password"
              autocomplete="new-password"
              minlength="8"
              maxlength="128"
              required /></label
          ><label
            >Confirmar nova senha<input
              name="password_confirmation"
              type="password"
              autocomplete="new-password"
              minlength="8"
              maxlength="128"
              required
          /></label>
          <p class="subtitle">
            As sessões anteriores do usuário serão encerradas após a alteração.
          </p>
          <p id="user-password-error" role="alert"></p>
          <div class="dialog-actions">
            <button type="button" class="button secondary" data-close-password>Cancelar</button
            ><button class="button" type="submit">Salvar senha</button>
          </div>
        </form>
      </dialog>`;
  } catch (error) {
    if (target.isConnected) target.textContent = error.message;
  }
}

// Exclusão remove o acesso; dados financeiros da organização permanecem preservados.
document.addEventListener('click', async (event) => {
  const change = event.target.closest('[data-user-password]');
  if (change) {
    const user = managedUsers.find((u) => String(u.id) === change.dataset.userPassword);
    const modal = document.querySelector('#user-password-dialog');
    const form = document.querySelector('#user-password-form');
    form.reset();
    form.dataset.userId = user.id;
    document.querySelector('#user-password-title').textContent = 'Alterar senha de ' + user.login;
    document.querySelector('#user-password-error').textContent = '';
    modal.showModal();
    return;
  }
  if (event.target.closest('[data-close-password]')) {
    document.querySelector('#user-password-form').reset();
    document.querySelector('#user-password-dialog').close();
    return;
  }
  const remove = event.target.closest('[data-user-delete]');
  if (!remove) return;
  const user = managedUsers.find((u) => String(u.id) === remove.dataset.userDelete);
  if (
    !confirm(
      `Excluir o acesso de "${user.login}"? As sessões serão encerradas. Os dados financeiros privados desse usuário serão preservados e o acesso será bloqueado.`,
    )
  )
    return;
  remove.disabled = true;
  try {
    await api(`users/${user.id}`, { method: 'DELETE', body: '{}' });
    await loadUsers();
    toast('Acesso do usuário excluído.');
  } catch (error) {
    toast(error.message);
    remove.disabled = false;
  }
});
document.addEventListener('submit', async (event) => {
  const form = event.target;
  if (form.id !== 'user-password-form') return;
  event.preventDefault();
  const errorTarget = document.querySelector('#user-password-error');
  const payload = Object.fromEntries(new FormData(form));
  if (payload.password !== payload.password_confirmation) {
    errorTarget.textContent = 'A confirmação deve ser igual à nova senha.';
    return;
  }
  const button = event.submitter;
  button.disabled = true;
  try {
    const result = await api(`users/${form.dataset.userId}/password`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    form.reset();
    document.querySelector('#user-password-dialog').close();
    if (result.reauthenticate) {
      authState.user = null;
      await load();
    }
    toast(
      result.reauthenticate
        ? 'Senha alterada. Entre novamente.'
        : 'Senha alterada. As sessões anteriores foram encerradas.',
    );
  } catch (error) {
    errorTarget.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

document.addEventListener('submit', async (event) => {
  const form = event.target;
  if (!['login-form', 'user-form'].includes(form.id)) return;
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  const login = form.id === 'login-form';
  const errorTarget = form.querySelector(login ? '#auth-error' : '#user-error');
  errorTarget.textContent = '';
  try {
    const payload = Object.fromEntries(new FormData(form));
    await api(login ? 'auth/login' : authState.setup_required ? 'auth/setup' : 'users', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    form.reset();
    if (login) location.hash = 'overview';
    await load();
    toast(login ? 'Login realizado.' : 'Usuário cadastrado.');
  } catch (error) {
    errorTarget.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
document.addEventListener('click', async (event) => {
  if (!event.target.closest('#logout')) return;
  try {
    await disableDevicePush().catch(() => {});
    await api('auth/logout', { method: 'POST', body: '{}' });
    authState.user = null;
    await load();
  } catch (error) {
    toast(error.message);
  }
});

/* BLOCO — Reúne os atalhos administrativos, relatórios e exportações. */
function admin() {
  const cards = [
    ['users', 'Perfil', 'Cadastre usuários e defina os perfis Administrador e Editor.', 'users'],
    ['grid', 'Categorias', 'Organize categorias de despesas e receitas.', 'categories'],
    ['trend', 'Relatórios', 'Gere PDFs mensais ou anuais de investimentos, extratos bancários e faturas, com totais e gráficos.', 'report'],
    ['settings', 'Configurações', 'Defina as preferências do seu painel.', 'settings'],
    ['download', 'Backup de Dados', 'Baixe uma cópia dos registros em JSON.', 'backup'],
  ];
  return (
    heading('Administrador', 'Gerencie o sistema e suas configurações.') +
    /* HTML */ `<div class="admin-grid">
      ${cards
        .map(
          ([i, t, d, a]) =>
            /* HTML */ `<section class="panel admin-card">
              ${icon(i)}
              <h2>${t}</h2>
              <p>${d}</p>
              <button class="button secondary" data-action="${a}">Acessar →</button>
            </section>`,
        )
        .join('')}
    </div>`
  );
}

function openReportForm() {
  if (demo || !authState.user) {
    toast('Entre na sua conta para gerar relatórios com os dados salvos.');
    return;
  }
  const modal = document.createElement('dialog');
  modal.id = 'reports-dialog';
  modal.setAttribute('aria-labelledby', 'report-title');
  modal.innerHTML = /* HTML */ `<form id="report-form">
    <div class="dialog-heading"><h2 id="report-title">Relatório em PDF</h2>
      <button type="button" class="icon-button" data-close-report aria-label="Fechar relatório">×</button></div>
    <label for="report-type">Relatório</label>
    <select id="report-type" name="type">
      <option value="card">Fatura do cartão</option>
      <option value="bank">Extrato bancário</option>
      <option value="investments">Conta de investimento</option>
    </select>
    <div id="report-source-field"><label for="report-source">Cartão ou conta</label>
      <select id="report-source" name="source"></select></div>
    <label for="report-period">Periodicidade</label>
    <select id="report-period" name="period"><option value="monthly">Mensal</option><option value="annual">Anual</option></select>
    <div id="report-month-field"><label for="report-month">Mês de referência</label>
      <input id="report-month" name="month" type="month" value="${esc(selectedPeriod)}" required></div>
    <div id="report-year-field" hidden><label for="report-year">Ano</label>
      <input id="report-year" name="year" type="number" min="1900" max="9998" step="1" value="${esc(selectedPeriod.slice(0, 4))}" disabled required></div>
    <p class="subtitle">O PDF usa o histórico salvo das sincronizações. Mensal: totais e movimentação do mês.
      Anual: evolução mês a mês. Períodos sem histórico serão indicados como sem dados.
      Investimentos usam posições observadas, aportes e retiradas registrados.</p>
    <p id="report-error" role="alert"></p>
    <div class="dialog-actions"><button type="button" class="button secondary" data-close-report>Cancelar</button>
      <button type="submit" class="button">Gerar PDF</button></div>
  </form>`;
  const form = modal.querySelector('form');
  const update = () => {
    const type = form.elements.type.value;
    const annual = form.elements.period.value === 'annual';
    modal.querySelector('#report-source-field').hidden = type === 'investments';
    form.elements.source.disabled = type === 'investments';
    form.elements.source.innerHTML = '<option value="all">' + (type === 'card' ? 'Todos os cartões' : 'Todas as contas') + '</option>' +
      state.records.filter(row => row.kind === (type === 'card' ? 'cards' : 'accounts'))
        .map(row => `<option value="${row.id}">${esc(row.name)}${row.institution ? ' - ' + esc(row.institution) : ''}</option>`).join('');
    modal.querySelector('#report-month-field').hidden = annual;
    modal.querySelector('#report-year-field').hidden = !annual;
    form.elements.month.disabled = annual;
    form.elements.year.disabled = !annual;
  };
  form.elements.type.addEventListener('change', update);
  form.elements.period.addEventListener('change', () => {
    const annual = form.elements.period.value === 'annual';
    modal.querySelector('#report-month-field').hidden = annual;
    modal.querySelector('#report-year-field').hidden = !annual;
    form.elements.month.disabled = annual;
    form.elements.year.disabled = !annual;
  });
  modal.querySelectorAll('[data-close-report]').forEach(button => button.addEventListener('click', () => modal.close()));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('[type="submit"]');
    const error = modal.querySelector('#report-error');
    const params = new URLSearchParams(new FormData(form));
    error.textContent = '';
    button.disabled = true;
    button.textContent = 'Gerando PDF…';
    try {
      const response = await fetch('/api/reports/pdf?' + params, { credentials: 'same-origin' });
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.error || 'Não foi possível gerar o relatório. Tente novamente.');
      }
      if (!response.headers.get('Content-Type')?.includes('application/pdf')) throw new Error('A resposta não contém um PDF. Entre novamente na sua conta.');
      const period = params.get('period') === 'annual' ? params.get('year') : params.get('month');
      download(`optimus-${params.get('type')}-${period}.pdf`, await response.blob(), 'application/pdf');
      toast('Relatório PDF gerado.');
    } catch (failure) {
      error.textContent = failure.message;
    } finally {
      button.disabled = false;
      button.textContent = 'Gerar PDF';
    }
  });
  modal.addEventListener('close', () => modal.remove(), { once: true });
  document.body.append(modal);
  update();
  modal.showModal();
}

/* BLOCO — Consulta Pluggy. As credenciais não entram no estado ou no armazenamento local. */
document.addEventListener('click', async event => {
  const button = event.target.closest('[data-tutorial-sound]');
  if (!button) return;
  const section = button.closest('.connection-tutorial');
  const video = section.querySelector('video');
  const status = section.querySelector('.tutorial-sound-status');
  video.defaultMuted = false;
  video.muted = false;
  video.volume = 1;
  video.removeAttribute('muted');
  try {
    await video.play();
    status.textContent = 'Reprodução iniciada com o áudio ativado. Confira também o volume do dispositivo.';
  } catch {
    status.textContent = 'Use o botão de reprodução do vídeo e ative o alto-falante do player. Você também pode baixar o MP4.';
  }
});

function userSupport() {
  const tutorialBase = location.protocol === 'file:' ? './tutorials/' : '/static/tutorials/';
  return heading('Suporte ao usuário', 'Vídeos e orientações para usar o Optimus Finance.') +
    /* HTML */ `<section class="panel connection-tutorial" style="margin-bottom:22px">
          <h2>Vídeo: como conectar sua conta pela Pluggy</h2>
          <p class="subtitle">Tutorial com telas reais da Pluggy e do Optimus Finance: onde obter e preencher Client ID, Client Secret e Item ID, com destaques, voz masculina em português brasileiro e legendas.
            O vídeo mostra o caminho de uso pessoal com Meu Pluggy; Sandbox contém apenas dados de teste.</p>
          <video controls playsinline preload="none" poster="${tutorialBase}pluggy-conectar-conta.jpg"
            aria-label="Tutorial de conexão Pluggy: cadastro, credenciais e Item ID">
            <source src="${tutorialBase}pluggy-conectar-conta.mp4?v=20261121-optimus-campos" type="video/mp4">
            <track kind="captions" src="${tutorialBase}pluggy-conectar-conta.vtt?v=20261121-optimus-campos" srclang="pt-BR" label="Português" default>
            Seu navegador não reproduz este vídeo. Use o link para baixar o MP4.
          </video>
          <div class="toolbar">
            <button type="button" class="button" data-tutorial-sound>Reproduzir com som</button>
            <a class="button secondary" href="${tutorialBase}pluggy-conectar-conta.mp4?v=20261121-optimus-campos" download="Optimus-Finance-Tutorial-Pluggy.mp4">Baixar vídeo MP4</a>
            <a href="https://meu.pluggy.ai/api-guide" target="_blank" rel="noopener">Guia oficial do Meu Pluggy</a>
            <a href="https://docs.pluggy.ai/en/docs/guides/dashboard-connectors" target="_blank" rel="noopener">Credenciais e Item ID</a>
          </div>
          <p class="subtitle tutorial-sound-status" role="status" aria-live="polite"></p>
          <p class="subtitle">Capturas reais com dados privados ocultados e cursor animado para orientar a navegação. Narração sintética masculina em português brasileiro. Criação de chaves e nova autorização não executadas na captura. Conteúdo conferido em 21/11/2026.</p>
      </section>`;
}

function connectAccount() {
  return (
    heading(
      'Conecte sua conta',
      'Consulte contas bancárias, cartões e investimentos pelo Pluggy.',
    ) +
    /* HTML */ `<p class="subtitle" style="margin-bottom:22px">Precisa de ajuda para conectar? <a href="#support">Assista ao tutorial em Suporte ao usuário</a>.</p>
      <section class="panel" style="margin-bottom:22px">
        <div class="panel-title">
          <h2>${icon('link')} Exchanges de criptomoedas</h2>
          <span class="pill">Consulta de saldos</span>
        </div>
        <p class="subtitle">
          Use uma chave de leitura. Binance: carteiras retornadas na consulta consolidada
          (chave HMAC), incluindo Spot e outras carteiras disponíveis na conta. Bybit: carteira
          UNIFIED (chave HMAC). Kraken: saldos Spot com permissão Query Funds. Mercado Bitcoin:
          saldos de criptomoedas e reais com chave de leitura. Os saldos da Binance e do Mercado Bitcoin
          são enviados à Conta de Investimento. Carteiras sem detalhamento aparecem pelo total;
          o histórico de compras da Binance continua limitado às negociações Spot. O histórico de
          compras do Mercado Bitcoin não é importado nesta consulta.
        </p>
        <form id="crypto-form" autocomplete="off">
          ${exchangeChoices()}
          <label for="crypto-exchange">Exchange</label>
          <select id="crypto-exchange" name="exchange">
            <option value="binance">Binance</option>
            <option value="bybit">Bybit</option>
            <option value="kraken">Kraken</option>
            <option value="mercadobitcoin">Mercado Bitcoin</option>
          </select>
          <label for="crypto-label">Nome da conexão (opcional)</label>
          <input id="crypto-label" name="label" maxlength="120" placeholder="Ex.: Minha Binance" />
          <label for="crypto-key" id="crypto-key-label">Chave API</label>
          <input
            id="crypto-key"
            name="api_key"
            type="password"
            required
            maxlength="4096"
            autocomplete="off"
            spellcheck="false"
          />
          <label for="crypto-secret" id="crypto-secret-label">Chave secreta</label>
          <input
            id="crypto-secret"
            name="api_secret"
            type="password"
            required
            maxlength="4096"
            autocomplete="off"
            spellcheck="false"
          />
          <p class="subtitle" id="crypto-auth-help" style="margin-top:14px">
            As chaves são salvas criptografadas no servidor e não são devolvidas ao navegador. A
            consulta autentica diretamente no domínio oficial da exchange.
          </p>
          <p id="crypto-error" role="alert" style="color:#c13442"></p>
          <button type="submit" class="button" style="margin-top:14px">
            Salvar conexão da exchange
          </button>
        </form>
        <p class="subtitle" style="margin-top:16px">
          Documentação oficial:
          <a
            href="https://developers.binance.com/en/docs/products/spot/rest-api"
            target="_blank"
            rel="noopener"
            >Binance</a
          >
          ·
          <a
            href="https://bybit-exchange.github.io/docs/v5/account/wallet-balance"
            target="_blank"
            rel="noopener"
            >Bybit</a
          >
          ·
          <a
            href="https://docs.kraken.com/api-reference/account-data/get-account-balance"
            target="_blank"
            rel="noopener"
            >Kraken</a
          > · <a href="https://api.mercadobitcoin.net/api/v4/docs" target="_blank" rel="noopener">Mercado Bitcoin</a>
        </p>
        <div id="crypto-connections" style="margin-top:22px" aria-live="polite"></div>
      </section>

      <section class="panel" style="margin-bottom:22px">
        <div class="panel-title">
          <h2>${icon('settings')} Credenciais da aplicação Pluggy</h2>
          <span id="application-status" class="pill">Carregando…</span>
        </div>
        <p class="subtitle">
          Client ID e Client Secret são cadastrados uma única vez e reutilizados nas novas contas.
        </p>
        <details id="application-details">
          <summary style="cursor:pointer;margin-top:16px">Configurar credenciais</summary>
          <form id="pluggy-application-form" autocomplete="off">
            <label for="pluggy-client">Client ID</label>
            <input
              id="pluggy-client"
              name="client_id"
              required
              maxlength="512"
              autocomplete="off"
              spellcheck="false"
            />
            <label for="pluggy-secret">Client Secret</label>
            <input
              id="pluggy-secret"
              name="client_secret"
              type="password"
              required
              maxlength="512"
              autocomplete="off"
            />
            <p id="application-error" role="alert" style="color:#c13442"></p>
            <button class="button" type="submit" style="margin-top:16px">
              Salvar credenciais da aplicação
            </button>
          </form>
        </details>
      </section>
      <section class="panel" style="margin-bottom:22px">
        <div class="panel-title">
          <h2>${icon('bank')} Conexões cadastradas</h2>
          <button class="button" type="button" data-action="add-connection">
            <span class="record-create-label">Adicionar outra conta</span>
          </button>
        </div>
        <div id="connection-list" aria-live="polite">Carregando conexões…</div>
      </section>
      <section class="panel" id="new-connection">
        <div class="panel-title">
          <h2>${icon('link')} Cadastrar conexão Pluggy</h2>
          <span class="pill">Sincronização</span>
        </div>
        <p class="subtitle">
          Para cada nova conta, informe apenas o Item ID de uma conexão já autorizada. O nome abaixo
          é opcional.
        </p>
        <form id="pluggy-form" autocomplete="off">
          <label for="pluggy-label">Nome da conexão</label>
          <input
            id="pluggy-label"
            name="label"
            maxlength="120"
            placeholder="Ex.: Conta principal, Nubank, Itaú"
          />
          <label for="pluggy-item">Item ID da conta</label>
          <input
            id="pluggy-item"
            name="item_id"
            required
            maxlength="512"
            autocomplete="off"
            spellcheck="false"
          />
          <p class="subtitle" style="margin-top:16px">
            Esta conta usará as credenciais da aplicação já salvas. Os dados de acesso permanecem
            criptografados no servidor.
          </p>
          <p id="pluggy-config-status" class="subtitle" role="status"></p>
          <p id="pluggy-error" role="alert" style="color:#c13442"></p>
          <div class="toolbar" style="margin-top:20px">
            <button type="submit" class="button" data-mode="save">Salvar configuração</button
            ><button type="submit" class="button secondary" data-mode="new">
              Salvar e sincronizar</button
            ><button type="button" class="button secondary" data-action="clear-pluggy">
              Limpar consulta
            </button>
          </div>
        </form>
      </section>
      <div id="pluggy-results" aria-live="polite" style="margin-top:22px"></div>
      <p class="subtitle" style="margin-top:20px">
        As contas são salvas em Cadastro de conta e os cartões em Cadastro de cartão. Novas
        consultas atualizam os mesmos produtos, sem duplicar. Os investimentos são salvos em Conta
        de Investimento. Os cadastros manuais são preservados. A disponibilidade e a atualização
        dependem da instituição e da conexão no Pluggy.
      </p>`
  );
}

// A prévia é temporária; os cadastros sincronizados persistem no PostgreSQL.
function pluggyResults(accounts) {
  const format = (value, currency) => {
    if (value === null || value === undefined) return 'Não informado';
    try {
      return Number(value).toLocaleString('pt-BR', { style: 'currency', currency });
    } catch {
      return `${esc(value)} ${esc(currency)}`;
    }
  };
  return ['BANK', 'CREDIT']
    .map((type) => {
      const list = accounts.filter((a) => a.type === type);
      const credit = type === 'CREDIT';
      return /* HTML */ `<section class="panel" style="margin-bottom:22px">
        <div class="panel-title">
          <h2>
            ${icon(credit ? 'card' : 'bank')} ${credit ? 'Cartões de crédito' : 'Contas bancárias'}
          </h2>
          <span class="pill">${list.length} encontrados</span>
        </div>
        ${
          list.length
            ? /* HTML */ `<div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Nome</th>
                      <th>${credit ? 'Saldo informado pelo Pluggy' : 'Saldo disponível'}</th>
                      ${credit ? '<th>Limite total</th><th>Limite disponível</th><th>Vencimento</th>' : ''}
                    </tr>
                  </thead>
                  <tbody>
                    ${list
                      .map(
                        (a) =>
                          /* HTML */ `<tr>
                            <td>${esc(a.name || 'Sem nome')}</td>
                            <td>${format(a.balance, a.currency)}</td>
                            ${
                              credit
                                ? /* HTML */ `<td>${format(a.credit_limit, a.currency)}</td>
                                    <td>${format(a.available_limit, a.currency)}</td>
                                    <td>
                                      ${a.due_date ? esc(dateText(a.due_date.slice(0, 10))) : 'Não informado'}
                                    </td>`
                                : ''
                            }
                          </tr>`,
                      )
                      .join('')}
                  </tbody>
                </table>
              </div>`
            : '<p class="empty">Nenhum produto deste tipo retornado para o Item ID.</p>'
        }
        ${credit ? '<p class="subtitle">O saldo de crédito pode representar fatura em aberto ou limite utilizado, conforme o conector.</p>' : ''}
      </section>`;
    })
    .join('');
}

document.addEventListener('submit', async (event) => {
  if (event.target.id !== 'pluggy-form') return;
  event.preventDefault();
  const form = event.target;
  const button = event.submitter;
  const errorBox = form.querySelector('#pluggy-error');
  const results = document.querySelector('#pluggy-results');
  if (location.protocol === 'file:') {
    errorBox.textContent = 'Abra o painel pelo servidor Python para consultar o Pluggy.';
    return;
  }
  errorBox.textContent = '';
  results.textContent = 'Consultando o Pluggy…';
  button.disabled = true;
  try {
    const mode = button.dataset.mode;
    let connectionId;
    if (mode !== 'saved') {
      const values = Object.fromEntries(new FormData(form));
      values.label = values.label.trim() || 'Minha conta';
      const saved = await api('pluggy/config', { method: 'PUT', body: JSON.stringify(values) });
      connectionId = saved.connection_id;

      await loadPluggyConfig();
      if (mode === 'save') {
        results.textContent =
          'Conexão salva. Clique em Sincronizar na lista de conexões para coletar os dados.';
        toast('Configuração Pluggy salva com segurança.');
        return;
      }
    }
    const result = await api('pluggy/accounts', {
      method: 'POST',
      body: JSON.stringify({ use_saved: true, connection_id: connectionId }),
    });
    state = await api('data');
    if (results.isConnected)
      results.innerHTML =
        /* HTML */ `<div class="notice">Sincronização concluída: ${result.synced.accounts} conta(s) e ${result.synced.cards} cartão(ões) e ${result.synced.investments || 0} investimento(s). <a class="button secondary" href="#accounts">Ver contas</a> <a class="button secondary" href="#cards">Ver cartões</a> <a class="button secondary" href="#investments">Ver investimentos</a></div>` +
        pluggyResults(result.accounts);
    await loadPluggyConfig();
    toast('Contas e cartões atualizados nos cadastros.');
  } catch (error) {
    errorBox.textContent = error.message;
    results.textContent = '';
  } finally {
    button.disabled = false;
  }
});

document.addEventListener('click', (event) => {
  if (!event.target.closest('[data-action="clear-pluggy"]')) return;
  document.querySelector('#pluggy-form').reset();
  document.querySelector('#pluggy-error').textContent = '';
  document.querySelector('#pluggy-results').textContent = '';
});

// O formulário da aplicação é independente do cadastro das contas.
document.addEventListener('submit', async (event) => {
  if (event.target.id !== 'pluggy-application-form') return;
  event.preventDefault();
  const form = event.target;
  const button = event.submitter;
  const errorBox = document.querySelector('#application-error');
  button.disabled = true;
  errorBox.textContent = '';
  try {
    await api('pluggy/config', {
      method: 'PUT',
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    await loadPluggyConfig();
    toast('Credenciais salvas. Adicione as contas somente pelo Item ID.');
  } catch (error) {
    errorBox.textContent = error.message;
  } finally {
    form.querySelector('[name="client_secret"]').value = '';
    button.disabled = false;
  }
});

// Exibe conexões persistentes e seus produtos sem retornar Client Secret.
async function loadPluggyConfig() {
  if (location.protocol === 'file:') return;
  const target = document.querySelector('#connection-list');
  if (!target) return;
  try {
    const [data, application] = await Promise.all([
      api('pluggy/connections'),
      api('pluggy/config'),
    ]);
    if (!target.isConnected) return;
    document.querySelector('#application-status').textContent = application.saved
      ? 'Credenciais cadastradas'
      : 'Cadastro necessário';
    document.querySelector('#application-details').open = !application.saved;
    document.querySelector('#pluggy-client').value = application.client_id;
    document.querySelector('#pluggy-secret').placeholder = application.saved
      ? 'Preencha apenas para atualizar o segredo'
      : '';
    document
      .querySelectorAll('#pluggy-form button[type="submit"]')
      .forEach((button) => (button.disabled = !application.saved));
    target.innerHTML = data.connections.length
      ? data.connections
          .map(
            (connection) =>
              /* HTML */ ` <article class="panel" style="margin-bottom:14px;box-shadow:none">
                <div class="panel-title">
                  <h2>${esc(connection.label)}</h2>
                  <span class="pill ${connection.last_error ? 'blocked' : ''}"
                    >${connection.last_error ? 'Falha na última tentativa' : connection.last_synced_at ? 'Sincronizada' : 'Aguardando primeira sincronização'}</span
                  >
                </div>
                <p class="subtitle">
                  Última sincronização:
                  ${connection.last_synced_at ? esc(new Date(connection.last_synced_at).toLocaleString('pt-BR')) : 'Ainda não realizada'}
                </p>
                ${connection.last_error ? /* HTML */ `<p role="status" style="color:#c13442">${esc(connection.last_error)}</p>` : ''}
                ${
                  connection.products.length
                    ? /* HTML */ `<ul>
                        ${connection.products.map((p) => /* HTML */ `<li>${esc(p.name)} · ${p.kind === 'cards' ? 'Cartão de crédito' : p.kind === 'investments' ? 'Investimento' : 'Conta bancária'}</li>`).join('')}
                      </ul>`
                    : '<p class="subtitle">Nenhum produto importado nesta conexão.</p>'
                }
                <div class="connection-actions">
                  <button type="button" class="button secondary" data-sync-connection="${connection.id}">Sincronizar esta conexão</button>
                  <button type="button" class="button secondary" data-edit-connection="${connection.id}">Editar</button>
                  <button type="button" class="button connection-delete" data-delete-connection="${connection.id}" data-connection-label="${esc(connection.label)}">Excluir</button>
                </div>
                <form class="connection-edit-form" data-connection-form="${connection.id}" hidden autocomplete="off">
                  <h3>Editar conexão</h3>
                  <label for="connection-label-${connection.id}">Nome da conexão</label>
                  <input id="connection-label-${connection.id}" name="label" value="${esc(connection.label)}" maxlength="120" required />
                  <label for="connection-item-${connection.id}">Novo Item ID (opcional)</label>
                  <input id="connection-item-${connection.id}" name="item_id" maxlength="512" autocomplete="off" spellcheck="false" aria-describedby="connection-help-${connection.id}" />
                  <p class="subtitle" id="connection-help-${connection.id}">Deixe vazio para manter o Item ID atual. Ao substituí-lo, os dados anteriores ficam salvos e a próxima sincronização importa os dados da nova conexão.</p>
                  <p class="connection-edit-error" role="alert"></p>
                  <div class="connection-actions">
                    <button type="submit" class="button">Salvar alterações</button>
                    <button type="button" class="button secondary" data-cancel-connection="${connection.id}">Cancelar</button>
                  </div>
                </form>
              </article>`,
          )
          .join('')
      : '<p class="empty">Nenhuma conexão cadastrada. Adicione a primeira conta abaixo.</p>';
    const status = document.querySelector('#pluggy-config-status');
    if (status)
      status.textContent =
        'Cada Item ID é salvo como uma conexão usando as mesmas credenciais da aplicação. Repetir o Item ID atualiza a conta existente.';
  } catch (error) {
    if (target.isConnected) target.textContent = error.message;
  }
}

/* Conexões: edição no próprio card e exclusão apenas do acesso salvo. */
document.addEventListener('submit', async (event) => {
  const form = event.target.closest('[data-connection-form]');
  if (!form) return;
  event.preventDefault();
  const button = event.submitter;
  const errorBox = form.querySelector('.connection-edit-error');
  button.disabled = true;
  errorBox.textContent = '';
  try {
    await api(`pluggy/connections/${form.dataset.connectionForm}`, {
      method: 'PUT',
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    state = await api('data');
    await loadPluggyConfig();
    toast('Conexão atualizada.');
  } catch (error) {
    errorBox.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

document.addEventListener('click', async (event) => {
  const edit = event.target.closest('[data-edit-connection]');
  const cancel = event.target.closest('[data-cancel-connection]');
  if (edit || cancel) {
    const id = edit?.dataset.editConnection || cancel.dataset.cancelConnection;
    const form = document.querySelector(`[data-connection-form="${id}"]`);
    form.hidden = Boolean(cancel);
    if (cancel) {
      form.reset();
      autoSyncDirtyForms.delete(form);
      document.querySelector(`[data-edit-connection="${id}"]`)?.focus();
    } else form.querySelector('[name="label"]').focus();
    return;
  }
  const remove = event.target.closest('[data-delete-connection]');
  if (remove) {
    if (!confirm(`Excluir a conexão "${remove.dataset.connectionLabel}"? Ela deixará de sincronizar. Contas, cartões, investimentos e extratos já importados serão mantidos.`)) return;
    remove.disabled = true;
    try {
      await api(`pluggy/connections/${remove.dataset.deleteConnection}`, { method: 'DELETE', body: '{}' });
      state = await api('data');
      await loadPluggyConfig();
      toast('Conexão excluída. Os dados importados foram preservados.');
    } catch (error) {
      toast(error.message);
      remove.disabled = false;
    }
    return;
  }
});

document.addEventListener('click', async (event) => {
  if (event.target.closest('[data-action="add-connection"]')) {
    const form = document.querySelector('#pluggy-form');
    form.reset();
    document.querySelector('#pluggy-error').textContent = '';
    document.querySelector('#new-connection').scrollIntoView({ behavior: 'smooth' });
    document.querySelector('#pluggy-label').focus({ preventScroll: true });
    return;
  }
  const button = event.target.closest('[data-sync-connection]');
  if (!button) return;
  button.disabled = true;
  button.textContent = 'Sincronizando…';
  try {
    const result = await api('pluggy/accounts', {
      method: 'POST',
      body: JSON.stringify({
        use_saved: true,
        connection_id: Number(button.dataset.syncConnection),
      }),
    });
    state = await api('data');
    toast(
      `Sincronizados: ${result.synced.accounts} conta(s) e ${result.synced.cards} cartão(ões) e ${result.synced.investments || 0} investimento(s).`,
    );
  } catch (error) {
    toast(error.message);
  } finally {
    await loadPluggyConfig();
  }
});

/* BLOCO — Sino de notificações: leitura persistente e atualização a cada minuto. */
let notificationItems = [];
let notificationRequest = null;
let tickerKey = null;
/* BLOCO — Interrompe os temporizadores e limpa avisos ao trocar de identidade. */
function clearNotifications() {
  notificationItems = [];
  const modal = document.querySelector('#notifications-dialog');
  if (modal?.open) modal.close();
  paintNotifications(0);
}
// Só mensagens não lidas percorrem a faixa. Passar o mouse ou focar pausa o texto.
function paintNotificationTicker() {
  const ticker = document.querySelector('#notification-ticker');
  if (!ticker) return;
  const unread = notificationItems.filter((item) => !item.read);
  if (!unread.length) {
    ticker.hidden = true;
    tickerKey = null;
    delete ticker.dataset.notificationIndex;
    return;
  }
  const item = unread.find((item) => item.key === tickerKey) || unread[0];
  tickerKey = item.key;
  ticker.hidden = false;
  ticker.dataset.notificationIndex = String(notificationItems.indexOf(item));
  const message = item.title + ' · ' + item.message;
  ticker.title = message + ' Clique para ler e abrir os detalhes.';
  ticker.setAttribute('aria-label', message + '. Clique para ler e abrir os detalhes.');
  const window = ticker.querySelector('.ticker-window');
  if (window.dataset.message === message) return;
  window.dataset.message = message;
  window.innerHTML = /* HTML */ `<span class="ticker-text">${esc(message)}</span>`;
  const text = window.querySelector('.ticker-text');
  text.style.animationDuration = Math.min(35, Math.max(12, message.length * 0.075 + 6)) + 's';
  text.addEventListener('animationiteration', () => {
    const pending = notificationItems.filter((item) => !item.read);
    if (!pending.length) {
      paintNotificationTicker();
      return;
    }
    const index = pending.findIndex((item) => item.key === tickerKey);
    tickerKey = pending[(index + 1) % pending.length].key;
    paintNotificationTicker();
  });
}

/* BLOCO — Atualiza o sino, o contador e a lista de notificações individuais. */
function paintNotifications(unread) {
  const bell = document.querySelector('#notifications');
  bell.innerHTML =
    icon('bell') +
    (unread
      ? /* HTML */ `<span class="notification-badge" aria-hidden="true"
          >${unread > 99 ? '99+' : unread}</span
        >`
      : '');
  bell.setAttribute('aria-label', `Notificações${unread ? ', ' + unread + ' não lidas' : ''}`);
  paintNotificationTicker();
  const list = document.querySelector('#notifications-list');
  if (!list) return;
  list.innerHTML = notificationItems.length
    ? notificationItems
        .map(
          (item, index) =>
            /* HTML */ `<button
              type="button"
              class="notification-item ${esc(item.level)} ${item.read ? 'is-read' : ''}"
              data-notification-index="${index}"
            >
              <span class="notification-indicator" aria-hidden="true"></span
              ><span
                ><strong>${esc(item.title)}</strong><small>${esc(item.message)}</small
                ><span class="notification-state"
                  >${item.read ? 'Lida' : 'Não lida'} · Ver detalhes →</span
                ></span
              >
            </button>`,
        )
        .join('')
    : '<p class="empty">Nenhuma notificação no momento.</p>';
  document.querySelector('#notifications-read-all').disabled = !unread;
}
/* BLOCO — Busca avisos persistidos e mantém a leitura sincronizada com o servidor. */
async function refreshNotifications() {
  if (!authState.user || demo || unavailable) {
    clearNotifications();
    return;
  }
  if (notificationRequest) return notificationRequest;
  const userId = authState.user.id;
  notificationRequest = (async () => {
    try {
      const result = await api('notifications');
      if (authState.user?.id !== userId) return;
      notificationItems = result.notifications;
      paintNotifications(result.unread);
    } catch (error) {
      if (document.querySelector('#notifications-dialog')?.open)
        document.querySelector('#notifications-list').textContent = error.message;
    } finally {
      notificationRequest = null;
      if (authState.user && authState.user.id !== userId) refreshNotifications();
    }
  })();
  return notificationRequest;
}
document.addEventListener('click', async (event) => {
  if (event.target.closest('[data-close-notifications]'))
    document.querySelector('#notifications-dialog').close();
  if (event.target.closest('#notifications-read-all')) {
    const button = document.querySelector('#notifications-read-all');
    button.disabled = true;
    try {
      await api('notifications/read', {
        method: 'PUT',
        body: JSON.stringify({ all: true, keys: notificationItems.map((i) => i.key) }),
      });
      notificationItems.forEach((item) => (item.read = true));
      paintNotifications(0);
      await refreshNotifications();
    } catch (error) {
      toast(error.message);
      button.disabled = false;
    }
  }
  const target = event.target.closest('[data-notification-index]');
  if (!target) return;
  const item = notificationItems[Number(target.dataset.notificationIndex)];
  if (!item) return;
  try {
    await api('notifications/read', { method: 'PUT', body: JSON.stringify({ keys: [item.key] }) });
  } catch (error) {
    toast(error.message);
    return;
  }
  item.read = true;
  paintNotifications(notificationItems.filter((item) => !item.read).length);
  document.querySelector('#notifications-dialog').close();
  if (/^\d{4}-(0[1-9]|1[0-2])$/.test(item.period || '')) {
    savePagePeriod(item.period, item.route);
  }
  if (item.route === 'bank_account') selectedBankAccount = Number(item.record_id);
  if (item.route === 'card_bill') selectedBillCard = Number(item.record_id);
  if (location.hash === '#' + item.route) render();
  else location.hash = item.route;
});
document
  .querySelector('#notifications-dialog')
  .addEventListener('close', () =>
    document.querySelector('#notifications').setAttribute('aria-expanded', 'false'),
  );
setInterval(() => {
  if (!document.hidden && authState.user) refreshNotifications();
}, 60000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && authState.user) refreshNotifications();
});

/* BLOCO — Navegação móvel do Optimus: atalhos principais e acesso a todas as páginas.
   Os hashes e as permissões continuam sendo resolvidos pelo roteador existente. */
function renderMobileNavigation() {
  const navigation = document.querySelector('#mobile-navigation');
  if (!navigation) return;
  const mobile = document.documentElement.classList.contains('apk-app');
  navigation.hidden = !mobile;
  if (!mobile) return;
  document.documentElement.dataset.mobilePage = route;
  const tabs = [
    ['overview', 'Início', 'home'],
    ['bank_account', 'Contas', 'bank'],
    ['card_bill', 'Cartões', 'card'],
    ['investments', 'Investir', 'trend'],
  ];
  const active = ['accounts'].includes(route)
    ? 'bank_account'
    : route === 'cards'
      ? 'card_bill'
      : route;
  const signature = route + ':' + authState.user?.role;
  if (navigation.dataset.signature !== signature) {
    navigation.dataset.signature = signature;
    navigation.innerHTML =
      tabs
        .map(
          ([key, label, symbol]) =>
            /* HTML */ ` <a
              href="#${key}"
              class="mobile-tab ${active === key ? 'active' : ''}"
              ${active === key ? 'aria-current="page"' : ''}
              >${icon(symbol)}<span>${label}</span></a
            >`,
        )
        .join('') +
      /* HTML */ `<button
        type="button"
        class="mobile-tab ${tabs.some(([key]) => key === active) ? '' : 'active'}"
        data-open-mobile-menu
        aria-label="Abrir todas as páginas"
        aria-haspopup="dialog"
        aria-expanded="false"
        aria-controls="mobile-menu"
      >
        ${icon('grid')}<span>Menu</span>
      </button>`;
    document.querySelector('#mobile-menu-links').innerHTML = Object.entries(routes)
      .filter(([key]) => authState.user?.role !== 'editor' || !['admin', 'connect'].includes(key))
      .map(
        ([key, [label, symbol]]) =>
          /* HTML */ `<a
            href="#${key}"
            class="mobile-menu-link ${route === key ? 'active' : ''}"
            ${route === key ? 'aria-current="page"' : ''}
            >${icon(symbol)}<span>${label}</span><span aria-hidden="true">›</span></a
          >`,
      )
      .join('');
  }
  prepareMobileTables();
}

/* BLOCO — Cada célula recebe o nome da coluna para formar cartões legíveis no celular.
   Extratos e faturas preservam suas três colunas; gráficos mantêm suas tabelas de apoio. */
function prepareMobileTables() {
  if (!document.documentElement.classList.contains('apk-app')) return;
  document.querySelectorAll('#content table').forEach((table) => {
    if (
      table.matches('.bank-statement-table, .card-bill-table') ||
      table.closest('.financial-evolution')
    )
      return;
    const headers = [...table.querySelectorAll('thead th')].map((header) =>
      header.textContent.trim(),
    );
    if (!headers.length) return;
    table.classList.add('mobile-record-table');
    table.setAttribute('role', 'table');
    table.querySelectorAll('tbody tr').forEach((row) => {
      row.setAttribute('role', 'row');
      [...row.cells].forEach((cell, index) => {
        cell.dataset.label = headers[index] || 'Detalhes';
        cell.setAttribute('role', 'cell');
      });
    });
  });
}

// A atualização assíncrona de conexões, usuários e dados também recebe o layout móvel.
new MutationObserver(prepareMobileTables).observe(content, { childList: true, subtree: true });
document.addEventListener('click', (event) => {
  const menu = document.querySelector('#mobile-menu');
  if (event.target.closest('[data-open-mobile-menu]')) {
    menu.showModal();
    event.target.closest('[data-open-mobile-menu]').setAttribute('aria-expanded', 'true');
  }
  if (event.target.closest('[data-close-mobile-menu], #mobile-menu-links a, [data-mobile-logout]'))
    menu.close();
  if (event.target.closest('[data-mobile-logout]')) document.querySelector('#logout').click();
});
document.querySelector('#mobile-menu').addEventListener('close', () => {
  document.querySelector('[data-open-mobile-menu]')?.setAttribute('aria-expanded', 'false');
});

/* Atualizações em segundo plano conservam os nós existentes, inclusive gráficos e mídia. */
function reconcileBackgroundView(current, next) {
  if (current.isEqualNode(next)) return;
  if (current.nodeType !== next.nodeType || current.nodeName !== next.nodeName ||
      (current.nodeType === 1 && current.id !== next.id)) {
    current.replaceWith(next.cloneNode(true));
    return;
  }
  if (current.nodeType !== 1) {
    current.nodeValue = next.nodeValue;
    return;
  }
  for (const attribute of [...current.attributes]) {
    if (!next.hasAttribute(attribute.name)) current.removeAttribute(attribute.name);
  }
  for (const attribute of next.attributes) {
    if (current.getAttribute(attribute.name) !== attribute.value)
      current.setAttribute(attribute.name, attribute.value);
  }
  const oldChildren = [...current.childNodes];
  const newChildren = [...next.childNodes];
  for (let index = 0; index < Math.max(oldChildren.length, newChildren.length); index++) {
    if (!newChildren[index]) oldChildren[index].remove();
    else if (!oldChildren[index]) current.append(newChildren[index].cloneNode(true));
    else reconcileBackgroundView(oldChildren[index], newChildren[index]);
  }
}

/* BLOCO — Escolhe a tela, aplica seu filtro e dispara somente os carregamentos necessários. */
function render({ preserveView = false } = {}) {
  // Na sincronização em segundo plano, conserva os painéis enquanto as novas consultas terminam.
  const previousPanels = preserveView
    ? [...content.querySelectorAll('#monthly-summary, #financial-evolution, #future-card-chart, #bill-transactions, #bank-statement, #selected-bill-value, [data-card-month]')]
        .map((element) => [
          element.id ? '#' + element.id : '[data-card-month="' + element.dataset.cardMonth + '"]',
          element.innerHTML,
        ])
    : [];
  const openDetails = preserveView
    ? [...content.querySelectorAll('details')].map((element) => element.open)
    : [];
  const previousMinHeight = content.style.minHeight;
  content.style.minHeight = preserveView ? content.getBoundingClientRect().height + 'px' : '';

  if ((!authState.setup_required && !authState.user && !demo) || location.hash === '#login') {
    renderLogin();
    return;
  }
  document.body.classList.remove('login-mode', 'onboarding-mode');
  route = location.hash.slice(1) || 'overview';
  if (authState.user?.role === 'editor' && ['admin', 'users', 'connect'].includes(route))
    route = 'overview';
  if (route === 'expenses') {
    location.replace('#fixed_costs');
    return;
  }
  if (![...Object.keys(routes), 'categories', 'users'].includes(route)) route = 'overview';
  // Links de notificações só alteram o período e a conta do próprio usuário.
  const notificationUrl = new URL(location.href);
  if (authState.user && notificationUrl.searchParams.has('notification_user')) {
    if (Number(notificationUrl.searchParams.get('notification_user')) === authState.user.id) {
      const destination = notificationUrl.searchParams.get('notification_route');
      if (['bank_account', 'card_bill', 'fixed_costs'].includes(destination)) {
        route = destination;
        notificationUrl.hash = route;
      }
      const month = notificationUrl.searchParams.get('notification_month');
      const record = Number(notificationUrl.searchParams.get('notification_record'));
      if (/^\d{4}-(0[1-9]|1[0-2])$/.test(month || '')) savePagePeriod(month, route);
      if (Number.isSafeInteger(record) && state.records.some((r) => r.id === record)) {
        if (route === 'bank_account') selectedBankAccount = record;
        if (route === 'card_bill') selectedBillCard = record;
      }
    }
    [
      'notification_user',
      'notification_month',
      'notification_record',
      'notification_route',
    ].forEach((key) => notificationUrl.searchParams.delete(key));
    history.replaceState(null, '', notificationUrl.href);
  }
  selectedPeriod = periodForPage(route);
  document.querySelector('#navigation').innerHTML = Object.entries(routes)
    .filter(([key]) => authState.user?.role !== 'editor' || !['admin', 'connect'].includes(key))
    .map(
      ([key, [label, i]]) =>
        /* HTML */ `<a
          href="#${key}"
          class="nav-link ${route === key ? 'active' : ''}"
          ${route === key ? 'aria-current="page"' : ''}
          >${icon(i)}${label}</a
        >`,
    )
    .join('');
  document.querySelector('#profile').innerHTML = icon('settings');
  document.querySelector('#profile').setAttribute('aria-label', 'Configurações do perfil');
  document.querySelector('#profile').setAttribute('title', 'Configurações do perfil');
  document.querySelector('#logout').hidden = !authState.user;
  document.querySelector('.avatar').textContent = state.settings.user_name.charAt(0).toUpperCase();
  document.querySelector('#breadcrumb').textContent =
    routes[route]?.[0] || (route === 'users' ? 'Perfil e usuários' : titles[route]);
  const notice =
    location.protocol === 'file:'
      ? '<div class="notice">Prévia visual · Dados ilustrativos, sem gravação. Para salvar informações no PostgreSQL, execute iniciar.bat e acesse http://127.0.0.1:5050.</div>'
      : demo
        ? '<div class="notice">Modo de demonstração · Dados ilustrativos, sem gravação. <button class="button secondary" data-action="reconnect">Conectar ao banco</button></div>'
        : unavailable
          ? '<div class="notice">PostgreSQL não conectado. Configure o banco conforme o README para cadastrar e salvar informações. <button class="button secondary" data-action="demo">Visualizar exemplo da referência</button> <button class="button secondary" data-action="reconnect">Tentar novamente</button></div>'
          : '';
  const nextContent =
    notice +
    (route === 'users'
      ? usersPage()
      : route === 'overview'
        ? overview()
        : route === 'connect'
          ? connectAccount()
          : route === 'support'
            ? userSupport()
          : route === 'admin'
            ? admin()
            : route === 'cards'
              ? cardsPage()
              : route === 'card_bill'
                ? cardBillPage()
                : route === 'bank_account'
                  ? bankAccountPage()
                  : route === 'investments'
                    ? investments()
                    : heading(
                        routes[route]?.[0] || titles[route],
                        route === 'cards'
                          ? 'Gerencie seus cartões de crédito.'
                          : route === 'accounts'
                            ? 'Adicione e gerencie suas contas financeiras.'
                            : route === 'fixed_costs'
                              ? 'Cadastre e acompanhe suas rendas e custos fixos no mês e ano selecionados.'
                              : 'Organize seus registros financeiros.',
                      ) +
                      (route === 'fixed_costs' ? budgetPlanningPanel() : '') +
                      table(route) +
                      (route === 'fixed_costs' ? table('incomes') : ''));
  if (preserveView) {
    const next = content.cloneNode(false);
    next.innerHTML = nextContent;
    for (const [selector, html] of previousPanels) {
      const panel = next.querySelector(selector);
      if (panel) panel.innerHTML = html;
    }
    next.querySelectorAll('details').forEach((element, index) => {
      element.open = openDetails[index] || false;
    });
    reconcileBackgroundView(content, next);
  } else content.innerHTML = nextContent;
  if (route === 'connect') {
    loadPluggyConfig();
    loadCryptoConnections();
  }
  const panelRequests = [];
  if (route === 'card_bill') panelRequests.push(loadCardBill(), loadFutureCardChart());
  if (route === 'bank_account') panelRequests.push(loadBankStatement());
  if (route === 'overview') {
    panelRequests.push(loadMonthlySummary(), loadFinancialEvolution());
  }
  if (route === 'cards') panelRequests.push(loadCardsMonth());
  if (preserveView) {
    // Restaura antes da próxima pintura; as respostas substituem os dados antigos quando prontas.
    content.querySelectorAll('details').forEach((element, index) => {
      element.open = openDetails[index] || false;
    });
    const currentPage = route;
    Promise.allSettled(panelRequests).then(() => {
      if (route !== currentPage) return;
      content.style.minHeight = previousMinHeight;
      content.querySelectorAll('details').forEach((element, index) => {
        element.open = openDetails[index] || false;
      });
    });
  }
  if (route === 'users') loadUsers();
  renderMobileNavigation();
  refreshNotifications();
  restoreDevicePush();
  setTimeout(autoSyncPulse, 0);
}

/* BLOCO 5 — Formulários de criação e edição; salvamento sempre na API. */
function field(name, label, value = '', type = 'text', required = false) {
  return /* HTML */ `<label for="field-${name}">${label}</label
    ><input
      id="field-${name}"
      name="${name}"
      type="${type}"
      value="${esc(value)}"
      ${required ? 'required' : ''}
      ${type === 'number' ? 'min="0" max="999999999999.99" step="0.01"' : 'maxlength="120"'}
    />`;
}
/* BLOCO — Prepara o formulário correto para cada cadastro, preservando dados e ciclos existentes. */
function openForm(kind, record = null) {
  if (demo || unavailable)
    return toast('Conecte o PostgreSQL para cadastrar e alterar informações.');
  // Custos fixos reutilizam despesas, com a categoria definida automaticamente.
  const fixedCost =
    kind === 'fixed_costs' ||
    (record?.kind === 'expenses' &&
      (record.is_fixed_cost || record.detail === 'Custo Fixo' || route === 'fixed_costs'));
  formIsFixedCost = Boolean(fixedCost);
  if (fixedCost) kind = 'expenses';
  formKind = kind;
  editing = record;
  document.querySelector('#form-error').textContent = '';
  document.querySelector('#dialog-title').textContent =
    kind === 'settings'
      ? 'Configurações do perfil'
      : `${record ? 'Editar' : 'Cadastrar'} ${fixedCost ? 'custo fixo' : singular[kind].toLowerCase()}`;
  const r =
    kind === 'cards' && record
      ? cardForMonth(record)
      : record || { detail: fixedCost ? 'Custo Fixo' : '' };
  let html;
  if (kind === 'settings')
    html =
      field('user_name', 'Seu nome', state.settings.user_name, 'text', true) +
      field('monthly_income', 'Renda mensal (R$)', state.settings.monthly_income, 'number', true);
  else if (kind === 'cards') {
    html =
      /* HTML */ `<input type="hidden" name="reference_month" value="${selectedPeriod}"><p class="subtitle">Datas da fatura para o mês de referência: <b>${selectedPeriod.slice(5)}/${selectedPeriod.slice(0, 4)}</b>. Nome, banco, limite e status valem para todos os meses.</p><div id="card-preview" class="card-preview">${creditCardArt(r)}</div>` +
      field('name', 'Nome do cartão', r.name, 'text', true) +
      /* HTML */ `<label for="field-institution">Escolha seu banco</label
        ><input
          id="field-institution"
          name="institution"
          list="bank-options"
          value="${esc(r.institution || '')}"
          placeholder="Selecione ou digite o banco"
          maxlength="120"
          required
          autocomplete="off"
        /><datalist id="bank-options">
          ${bankCatalog.map((bank) => /* HTML */ `<option value="${esc(bank.name)}"></option>`).join('')}
        </datalist>` +
      field('amount', 'Limite (R$)', r.amount ?? '', 'number', true) +
      field(
        'previous_closing_date',
        'Data de fechamento da fatura anterior',
        r.previous_closing_date,
        'date',
      ) +
      field('closing_date', 'Data de fechamento da fatura', r.closing_date, 'date') +
      field('due_date', 'Vencimento da fatura', r.due_date, 'date', true) +
      /* HTML */ `<label for="field-status">Status</label
        ><select id="field-status" name="status">
          ${[...new Set(['Ativo', 'Bloqueado', r.status].filter(Boolean))].map((status) => /* HTML */ `<option ${r.status === status ? 'selected' : ''}>${esc(status)}</option>`).join('')}
        </select>`;
  } else if (kind === 'incomes') {
    html =
      field('name', 'Nome da renda', r.name, 'text', true) +
      field('statement_name', 'Nome no extrato bancário', r.statement_name) +
      '<p class="subtitle">A conferência identifica entradas confirmadas do mesmo mês pelo nome da renda, nome no extrato ou valor exato. Nomes repetidos são diferenciados pelo valor; correspondências ambíguas ficam pendentes.</p>' +
      /* HTML */ `<label for="field-detail">Categoria</label
        ><select name="detail" id="field-detail" required>
          ${[...new Set(['Salário', '13º Salário', 'Férias', 'Freelance', 'Aluguel', 'Rendimentos', ...rows('categories').filter(c => c.category_type === 'incomes').map(c => c.name), r.detail].filter(Boolean))].map((category) => /* HTML */ `<option value="${esc(category)}" ${r.detail === category ? 'selected' : ''}>${esc(category)}</option>`).join('')}
        </select>` +
      field('amount', 'Valor (R$)', r.amount ?? '', 'number', true) +
      field('due_date', 'Data de recebimento', r.due_date || selectedPeriod + '-01', 'date', true) +
      '<p class="subtitle">Cadastro manual de renda. As entradas confirmadas do resumo financeiro continuam vindo do extrato bancário, evitando duplicidade.</p>';
  } else if (kind === 'expenses') {
    const categories = [
      ...new Set(
        [
          'Custo Fixo',
          'Moradia',
          'Água',
          'Energia',
          'Internet',
          'Alimentação',
          'Transporte',
          'Saúde',
          'Educação',
          'Assinaturas',
          'Cartão de Crédito',
          'Outros',
          ...rows('categories').filter(category => category.category_type !== 'incomes').map((category) => category.name),
          r.detail,
        ].filter(Boolean),
      ),
    ];
    html =
      field('name', 'Nome', r.name, 'text', true) +
      field('statement_name', 'Nome no extrato bancário', r.statement_name) +
      '<p class="subtitle">Use o nome como aparece no extrato, por exemplo: HAPVIDA ou AMBAR ENERGIA. A conferência usa pagamentos confirmados do mesmo mês.</p>' +
      /* HTML */ `<label for="field-detail">Categoria</label
        ><select name="detail" id="field-detail" required>
          ${categories.map((category) => /* HTML */ `<option ${r.detail === category ? 'selected' : ''}>${esc(category)}</option>`).join('')}
        </select>` +
      field('amount', 'Valor Previsto (R$)', r.amount ?? '', 'number', true) +
      field('due_date', 'Vencimento', r.due_date, 'date', true);
  } else if (kind === 'categories') {
    html = field('name', 'Nome da categoria', r.name, 'text', true) +
      /* HTML */ `<label for="field-category-type">Usar em</label>
        <select id="field-category-type" name="category_type" required>
          <option value="" ${record ? '' : 'selected'} disabled>Selecione renda ou custos fixos</option>
          <option value="incomes" ${record && r.category_type === 'incomes' ? 'selected' : ''}>Renda</option>
          <option value="expenses" ${record && r.category_type !== 'incomes' ? 'selected' : ''}>Custos fixos</option>
        </select>` + field('detail', 'Descrição', r.detail);
  } else {
    html = field('name', kind === 'accounts' ? 'Apelido' : 'Nome', r.name, 'text', true);
    if (!['expenses', 'categories'].includes(kind))
      html += field('institution', 'Banco / instituição', r.institution);
    if (kind !== 'cards') {
      const options = fixedCost
        ? ['Custo Fixo']
        : kind === 'expenses'
          ? [
              'Custo Fixo',
              'Cartão de Crédito',
              'Investimento',
              ...rows('categories').filter(c => c.category_type !== 'incomes').map((c) => c.name),
            ]
          : null;
      html += options
        ? /* HTML */ `<label for="field-detail">Categoria</label
            ><select name="detail" id="field-detail">
              ${[...new Set([...options, r.detail].filter(Boolean))].map((o) => /* HTML */ `<option ${r.detail === o ? 'selected' : ''}>${esc(o)}</option>`).join('')}
            </select>`
        : field('detail', kind === 'categories' ? 'Descrição' : 'Tipo', r.detail);
    }
    if (kind !== 'categories')
      html += field(
        'amount',
        kind === 'cards' ? 'Limite (R$)' : kind === 'accounts' ? 'Saldo (R$)' : 'Valor (R$)',
        r.amount ?? '',
        'number',
        true,
      );
    if (!['accounts', 'categories'].includes(kind))
      html += field(
        'due_date',
        kind === 'investments' ? 'Data do aporte' : 'Vencimento',
        r.due_date,
        'date',
        true,
      );
    if (!['investments', 'categories'].includes(kind))
      html += /* HTML */ `<label for="field-status">Status</label
        ><select id="field-status" name="status">
          ${(kind === 'expenses' ? ['Pendente', 'Pago'] : ['Ativo', 'Bloqueado']).map((s) => /* HTML */ `<option ${r.status === s ? 'selected' : ''}>${s}</option>`).join('')}
        </select>`;
  }
  document.querySelector('#fields').innerHTML = html;
  dialog.showModal();
}

document.querySelector('#record-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  const payload = Object.fromEntries(new FormData(event.target));
  if (formKind === 'incomes') payload.status = editing?.status || 'Pendente';
  if (formKind === 'expenses') {
    payload.is_fixed_cost = formIsFixedCost;
    payload.status = editing?.status || 'Pendente';
  }
  try {
    if (formKind === 'settings')
      await api('settings', { method: 'PUT', body: JSON.stringify(payload) });
    else
      await api(editing ? `records/${editing.id}` : 'records', {
        method: editing ? 'PUT' : 'POST',
        body: JSON.stringify({ ...payload, kind: formKind }),
      });
    dialog.close();
    await load();
    toast('Informações salvas com sucesso.');
  } catch (error) {
    document.querySelector('#form-error').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
document.querySelector('#close-dialog').onclick = () => dialog.close();
document.querySelector('#cancel-dialog').onclick = () => dialog.close();
document.querySelector('#profile').onclick = () => {
  if (authState.user?.role === 'editor') return toast('Perfil: Editor');
  openForm('settings');
};
document.querySelector('#notifications').innerHTML = icon('bell');
document.querySelector('#notifications').onclick = async () => {
  const modal = document.querySelector('#notifications-dialog');
  modal.showModal();
  document.querySelector('#notifications').setAttribute('aria-expanded', 'true');
  await refreshPushStatus();
  await refreshNotifications();
};

/* BLOCO 6 — Downloads locais, pesquisa e delegação de eventos. */
function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
document.addEventListener('input', (event) => {
  if (event.target.id !== 'search' && !event.target.matches('[data-record-search]')) return;
  const searchScope = event.target.closest('.panel') || document;
  let count = 0;
  searchScope.querySelectorAll('[data-row]').forEach((row) => {
    row.hidden = !row.textContent
      .toLocaleLowerCase('pt-BR')
      .includes(event.target.value.toLocaleLowerCase('pt-BR'));
    if (!row.hidden) count++;
  });
  const empty = searchScope.querySelector('[data-no-results],#no-results');
  if (empty) empty.hidden = count > 0;
});
document.addEventListener('click', async (event) => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.dataset.new) openForm(button.dataset.new);
  if (button.dataset.edit) {
    const r = state.records.find((r) => r.id === Number(button.dataset.edit));
    openForm(r.kind, r);
  }
  if (button.dataset.delete) {
    if (demo || unavailable) return toast('Conecte o banco para alterar dados.');
    const r = state.records.find((r) => r.id === Number(button.dataset.delete));
    if (!confirm(`Excluir "${r.name}"? Esta ação não pode ser desfeita.`)) return;
    try {
      await api(`records/${r.id}`, { method: 'DELETE' });
      await load();
      toast('Registro excluído.');
    } catch (e) {
      toast(e.message);
    }
  }
  const action = button.dataset.action;
  if (['fixed_costs', 'expenses', 'categories'].includes(action))
    location.hash = action === 'expenses' ? 'fixed_costs' : action;
  if (action === 'settings') openForm('settings');
  if (action === 'users') location.hash = 'users';
  if (action === 'reconnect') {
    content.innerHTML = '<p class="loading">Conectando ao banco…</p>';
    await load();
  }
  if (action === 'demo') {
    demo = true;
    state = structuredClone(sample);
    render();
  }
  if (action === 'backup')
    download(
      'backup-financeiro.json',
      JSON.stringify(
        { ...state, exported_at: new Date().toISOString(), demonstration: demo },
        null,
        2,
      ),
      'application/json',
    );
  if (action === 'report') openReportForm();
});
window.addEventListener('hashchange', render);

/* BLOCO 7 — Exemplo visual explícito, isolado do banco e somente para leitura. */
const sample = {
  settings: { user_name: 'Usuário', monthly_income: 5000 },
  records: [
    ['cards', 'Nubank', 'Nubank', '', 5000, '2026-11-15', 'Ativo'],
    ['cards', 'Itaú Gold', 'Itaú', '', 8000, '2026-12-10', 'Ativo'],
    ['cards', 'Santander Elite', 'Santander', '', 10000, '2026-11-05', 'Bloqueado'],
    ['accounts', 'Conta Principal', 'Banco do Brasil', 'Conta Corrente', 3250, null, 'Ativo'],
    ['accounts', 'Poupança', 'Caixa Econômica', 'Conta Poupança', 1280, null, 'Ativo'],
    ['accounts', 'PicPay', 'PicPay', 'Carteira Digital', 320, null, 'Ativo'],
    ['investments', 'Reserva de emergência', 'Nubank', 'Renda fixa', 10000, '2026-01-10', 'Ativo'],
    ['investments', 'Tesouro IPCA+', 'Tesouro Direto', 'Renda fixa', 2750, '2026-06-10', 'Ativo'],
    [
      'expenses',
      'Fatura do Cartão de Crédito',
      '',
      'Cartão de Crédito',
      2000,
      '2026-11-15',
      'Pendente',
    ],
    ['expenses', 'Contas Fixas (Água, Luz, etc.)', '', 'Custo Fixo', 850, '2026-11-20', 'Pendente'],
    [
      'expenses',
      'Pagamentos à Vista (Pix, Débito)',
      '',
      'Custo Fixo',
      120,
      '2026-11-25',
      'Pendente',
    ],
  ].map((v, i) =>
    Object.fromEntries(
      ['id', 'kind', 'name', 'institution', 'detail', 'amount', 'due_date', 'status'].map(
        (k, j) => [k, [i + 1, ...v][j]],
      ),
    ),
  ),
};
/* A apresentação do app cobre a consulta inicial; o site mantém seu carregador habitual. */
async function startApplication() {
  if (!isAndroidApp() || !window.ApkIntro) {
    content.innerHTML = '<p class="loading">Carregando seu painel financeiro…</p>';
    return load();
  }
  let dataReady = false;
  let presentationFinished = false;
  document.body.classList.add('login-mode', 'login-apk');
  window.ApkIntro.show(content, () => {
    presentationFinished = true;
    if (dataReady) render();
    else document.body.classList.add('onboarding-mode');
  });
  await load({ deferRender: true });
  dataReady = true;
  if (presentationFinished) render();
}
startApplication();

/* BLOCO — Conexões cripto independentes do Pluggy, com quantidades por ativo. */
async function loadCryptoConnections() {
  const target = document.querySelector('#crypto-connections');
  if (!target || location.protocol === 'file:') return;
  try {
    const result = await api('crypto/connections');
    if (!target.isConnected) return;
    target.innerHTML = result.connections.length
      ? result.connections
          .map(
            (connection) =>
              /* HTML */ ` <article class="panel" style="margin-top:14px;box-shadow:none">
                <div class="panel-title">
                  <h2 class="exchange-heading">
                    ${exchangeLogo(connection.exchange, 40)}<span
                      >${esc(connection.label)}<small
                        >${esc(exchangeNames[connection.exchange] || connection.exchange)}</small
                      ></span
                    >
                  </h2>
                  <span class="pill ${connection.last_error ? 'blocked' : ''}"
                    >${connection.last_error ? 'Falha na consulta' : connection.last_synced_at ? 'Consultada' : 'Chaves salvas, ainda não validadas'}</span
                  >
                </div>
                <p class="subtitle">
                  Última consulta:
                  ${connection.last_synced_at ? esc(new Date(connection.last_synced_at).toLocaleString('pt-BR')) : 'Ainda não realizada'}
                </p>
                ${connection.last_error ? /* HTML */ `<p role="status" style="color:#c13442">${esc(connection.last_error)}</p>` : ''}
                <p class="subtitle">
                  Ativos, saldos e lançamentos desta exchange estão na
                  <a href="#investments">Conta de Investimento</a>.
                </p>
                <button
                  type="button"
                  class="button secondary"
                  data-crypto-sync="${connection.id}"
                  style="margin-top:14px"
                >
                  Sincronizar investimentos
                </button>
              </article>`,
          )
          .join('')
      : '<p class="subtitle">Nenhuma exchange cadastrada.</p>';
  } catch (error) {
    if (target.isConnected) target.textContent = error.message;
  }
}

document.addEventListener('submit', async (event) => {
  if (event.target.id !== 'crypto-form') return;
  event.preventDefault();
  const form = event.target;
  const button = event.submitter;
  const errors = document.querySelector('#crypto-error');
  errors.textContent = '';
  button.disabled = true;
  try {
    await api('crypto/connections', {
      method: 'POST',
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });
    form.reset();
    selectExchange('binance');
    await loadCryptoConnections();
    toast('Chaves salvas. Use Consultar saldos para validar a conexão.');
  } catch (error) {
    errors.textContent = error.message;
  } finally {
    form.querySelector('[name="api_secret"]').value = '';
    form.querySelector('[name="api_key"]').value = '';
    button.disabled = false;
  }
});

document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-crypto-sync]');
  if (!button) return;
  button.disabled = true;
  button.textContent = 'Consultando…';
  try {
    await api(`crypto/connections/${button.dataset.cryptoSync}/sync`, {
      method: 'POST',
      body: '{}',
    });
    state = await api('data');
    toast('Saldos atualizados. Ativos Binance disponíveis em Conta de Investimento.');
  } catch (error) {
    toast(error.message);
  } finally {
    await loadCryptoConnections();
  }
});

/* BLOCO — Atualiza a arte do cartão enquanto os campos do formulário são editados. */
function updateCardPreview(event) {
  const form = event.target.closest('#record-form');
  if (!form || formKind !== 'cards') return;
  const preview = form.querySelector('#card-preview');
  if (!preview) return;
  const values = Object.fromEntries(new FormData(form));
  preview.innerHTML = creditCardArt({
    ...values,
    amount: values.amount === '' ? null : Number(values.amount),
  });
}
document.addEventListener('input', updateCardPreview);
document.addEventListener('change', updateCardPreview);

/* Concilia extratos já salvos, sem exigir nova consulta externa. */
document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-action="reconcile-costs"]');
  if (!button) return;
  if (demo || unavailable) return toast('Conecte o banco para conferir os pagamentos.');
  button.disabled = true;
  button.textContent = 'Conferindo…';
  try {
    const result = await api('fixed-costs/reconcile', {
      method: 'POST',
      body: JSON.stringify({ month: selectedPeriod }),
    });
    await load();
    toast(
      result.paid_costs.length || result.paid_incomes?.length
        ? `${result.paid_costs.length} custo(s) e ${result.paid_incomes?.length || 0} renda(s) marcado(s) como Pago pelo extrato.`
        : 'Nenhuma nova correspondência segura. Confira os nomes no extrato bancário e o período.',
    );
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = 'Conferir pagamentos';
  }
});

// Instalação do app web: não grava dados financeiros em cache offline.
if ('serviceWorker' in navigator && location.protocol === 'https:') {
  window.addEventListener('load', () =>
    navigator.serviceWorker.register('/service-worker.js').catch(() => {}),
  );
}

/* BLOCO — Ativação explícita: a permissão do Android só é solicitada após o toque. */
function isAndroidApp() {
  return (
    /Android/i.test(navigator.userAgent) &&
    (matchMedia('(display-mode: standalone)').matches ||
      matchMedia('(display-mode: fullscreen)').matches ||
      document.referrer.startsWith('android-app://br.com.controlefinanceiro.app'))
  );
}
/* BLOCO — Confere se o navegador possui os recursos necessários para notificações push. */
function pushSupported() {
  return (
    location.protocol === 'https:' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  );
}
/* BLOCO — Aguarda confirmação do service worker ao vincular ou limpar o dispositivo. */
async function pushWorkerMessage(registration, binding) {
  const worker = registration.active;
  if (!worker) throw new Error('Feche e abra o aplicativo para atualizar as notificações.');
  await new Promise((resolve, reject) => {
    const channel = new MessageChannel();
    const timeout = setTimeout(
      () => reject(new Error('Não foi possível preparar as notificações. Reabra o aplicativo.')),
      5000,
    );
    channel.port1.onmessage = () => {
      clearTimeout(timeout);
      resolve();
    };
    worker.postMessage({ type: 'push-binding', binding }, [channel.port2]);
  });
}
/* BLOCO — Exibe o estado real da assinatura antes de oferecer ativação ou desativação. */
async function refreshPushStatus() {
  const status = document.querySelector('#push-status');
  if (!status) return;
  if (!pushSupported()) {
    status.textContent =
      'Abra o aplicativo Android atualizado ou um navegador com suporte a notificações.';
    return;
  }
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    document.querySelector('#push-disable').hidden = !subscription;
    document.querySelector('#push-test').hidden = !subscription;
    status.textContent =
      Notification.permission === 'denied'
        ? 'Notificações bloqueadas. Habilite nas configurações do Android para este aplicativo.'
        : subscription
          ? 'Permissão concedida. Toque em Ativar para confirmar o registro e em Testar notificação para conferir a entrega.'
          : 'Toque em Ativar e permita as notificações no Android. Os avisos seguem as atualizações do Pluggy.';
  } catch {
    status.textContent = 'Reabra o aplicativo para preparar as notificações.';
  }
}
/* BLOCO — Solicita permissão após o toque e registra a assinatura na sessão autenticada. */
// BLOCO — Evita registros repetidos durante renderizações e respeita a desativação voluntária.
const pushRestoredSessions = new Set();
let pushRegistrationPending = false;
function pushOptOutKey() {
  return 'finance-push-disabled:' + authState.user?.id;
}
async function restoreDevicePush() {
  if (!isAndroidApp() || !authState.user || demo || unavailable || !pushSupported()) return;
  const key = authState.user.id + ':' + authState.user.session_version;
  if (pushRegistrationPending || pushRestoredSessions.has(key)) return;
  try {
    if (localStorage.getItem(pushOptOutKey()) === '1') return;
  } catch {
    /* A indisponibilidade de armazenamento não impede a ativação. */
  }
  if (Notification.permission !== 'granted') return;
  pushRegistrationPending = true;
  try {
    await enableDevicePush(false);
    pushRestoredSessions.add(key);
  } catch (error) {
    document.querySelector('#push-status').textContent = error.message;
  } finally {
    pushRegistrationPending = false;
  }
}
async function enableDevicePush(askPermission = true) {
  const status = document.querySelector('#push-status');
  if (!pushSupported())
    throw new Error(
      'Este navegador não oferece notificações push. Use o aplicativo Android atualizado.',
    );
  const permission = askPermission
    ? await Notification.requestPermission()
    : Notification.permission;
  if (permission !== 'granted')
    throw new Error('Permita as notificações no aplicativo e toque em Ativar no sino.');
  const userId = authState.user?.id;
  if (!userId) throw new Error('Entre na sua conta para ativar as notificações.');
  const registration = await navigator.serviceWorker.ready;
  const config = await api('push/config');
  let subscription = await registration.pushManager.getSubscription();
  const raw = atob(
    config.public_key.replace(/-/g, '+').replace(/_/g, '/') +
      '='.repeat((4 - (config.public_key.length % 4)) % 4),
  );
  const key = Uint8Array.from(raw, (c) => c.charCodeAt(0));
  // Renova inscrições criadas com uma chave de servidor antiga.
  if (
    subscription?.options?.applicationServerKey &&
    [...new Uint8Array(subscription.options.applicationServerKey)].join(',') !== [...key].join(',')
  ) {
    await subscription.unsubscribe();
    subscription = null;
  }
  if (!subscription)
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: key,
    });
  if (authState.user?.id !== userId)
    throw new Error('O acesso mudou. Ative novamente na sua conta.');
  await pushWorkerMessage(registration, {
    user_id: config.user_id,
    session_version: config.session_version,
  });
  const result = await api('push/subscribe', {
    method: 'POST',
    body: JSON.stringify({ subscription: subscription.toJSON(), android_app: isAndroidApp() }),
  });
  try {
    localStorage.removeItem(pushOptOutKey());
  } catch {
    /* Preferência opcional. */
  }
  document.querySelector('#push-disable').hidden = false;
  document.querySelector('#push-test').hidden = false;
  status.textContent =
    result.warning ||
    'Celular registrado para novas movimentações. Toque em Testar notificação para conferir a entrega.';
}
/* BLOCO — Remove a assinatura local e comunica a desativação ao servidor. */
async function disableDevicePush() {
  pushRestoredSessions.clear();
  if (!pushSupported()) return;
  const registration = await navigator.serviceWorker.getRegistration('/');
  if (!registration) return;
  await pushWorkerMessage(registration, null);
  const subscription = await registration.pushManager.getSubscription();
  if (subscription) {
    try {
      await api('push/unsubscribe', {
        method: 'POST',
        body: JSON.stringify({ endpoint: subscription.endpoint }),
      });
    } finally {
      await subscription.unsubscribe();
    }
  }
}
document.querySelector('#push-enable').addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await enableDevicePush();
  } catch (error) {
    document.querySelector('#push-status').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
document.querySelector('#push-disable').addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await disableDevicePush();
    try {
      localStorage.setItem(pushOptOutKey(), '1');
    } catch {
      /* Preferência opcional. */
    }
    pushRestoredSessions.clear();
    document.querySelector('#push-test').hidden = true;
    button.hidden = true;
    document.querySelector('#push-status').textContent =
      'Notificações desativadas neste dispositivo.';
  } catch {
    document.querySelector('#push-status').textContent =
      'Não foi possível concluir. Confira as permissões do Android.';
  } finally {
    button.disabled = false;
  }
});

/* BLOCO — O teste percorre servidor, provedor push e service worker deste dispositivo. */
document.querySelector('#push-test').addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  const status = document.querySelector('#push-status');
  try {
    await enableDevicePush();
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    await api('push/test', {
      method: 'POST',
      body: JSON.stringify({ endpoint: subscription.endpoint }),
    });
    status.textContent =
      'Teste aceito pelo serviço de entrega. Confira a notificação no celular. Se não aparecer, verifique também a permissão do site no Chrome e os canais de notificação do aplicativo.';
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

/* BLOCO — Site e APK observam a mesma revisão, sem interromper formulários ou filtros. */
const autoSyncRevisions = new Map();
const autoSyncRequests = new Map();
const autoSyncDirtyForms = new WeakSet();
let autoSyncPending = false;
document.addEventListener('input', (event) => {
  const form = event.target.closest('#content form');
  if (form) autoSyncDirtyForms.add(form);
});
/* BLOCO — Adia atualizações visuais quando há formulário alterado ou diálogo aberto. */
function autoSyncEditing() {
  return (
    Boolean(document.querySelector('dialog[open]')) ||
    [...content.querySelectorAll('form')].some((form) => autoSyncDirtyForms.has(form))
  );
}
/* BLOCO — Solicita tarefas com intervalo e atualiza o painel somente quando a revisão muda. */
async function autoSyncPulse() {
  if (
    autoSyncPending ||
    document.hidden ||
    !authState.user ||
    demo ||
    unavailable ||
    location.protocol !== 'https:'
  )
    return;
  autoSyncPending = true;
  const user = authState.user.id;
  try {
    const key = user + ':' + route + ':' + selectedPeriod;
    if (Date.now() - (autoSyncRequests.get(key) || 0) > 900000) {
      await api('auto-sync/request', {
        method: 'POST',
        body: JSON.stringify({ page: route, month: selectedPeriod }),
      });
      autoSyncRequests.set(key, Date.now());
    }
    const status = await api('auto-sync/status');
    if (authState.user?.id !== user || autoSyncEditing()) return;
    if (autoSyncRevisions.get(user) !== status.revision) {
      const updated = await api('data');
      if (authState.user?.id !== user || autoSyncEditing()) return;
      state = updated;
      autoSyncRevisions.set(user, status.revision);
      render({ preserveView: true });
    }
  } catch {
    /* Falhas transitórias preservam a tela e os botões de sincronização manual. */
  } finally {
    autoSyncPending = false;
  }
}
setInterval(autoSyncPulse, 30000);
window.addEventListener('hashchange', () => setTimeout(autoSyncPulse, 0));
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) autoSyncPulse();
});
window.addEventListener('load', () => setTimeout(autoSyncPulse, 1500));
