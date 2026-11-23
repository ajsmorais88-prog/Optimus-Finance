/* Detecta o APK antes da primeira pintura para não exibir o carregador do site. */
if (
  /Android/i.test(navigator.userAgent) &&
  (matchMedia('(display-mode: standalone)').matches ||
    matchMedia('(display-mode: fullscreen)').matches ||
    document.referrer.startsWith('android-app://br.com.controlefinanceiro.app'))
) document.documentElement.classList.add('apk-app');

/* BLOCO — Apresentação inicial exclusiva do APK; guarda apenas uma preferência visual. */
(() => {
  const STORAGE_KEY = 'finance-apk-intro-v1';
  let completed = false;
  let currentStep = 0;
  let container = null;
  let onComplete = null;
  let logoTimer = null;

  const slides = [
    {
      eyebrow: 'CLAREZA PARA COMEÇAR',
      title: 'Seu dinheiro merece um plano.',
      description: 'Veja o que entra, entenda o que sai e encontre espaço para os seus objetivos.',
      highlight: 'Organize suas finanças, um mês de cada vez.',
      visual: 'organize',
    },
    {
      eyebrow: 'CONSTÂNCIA PARA CONSTRUIR',
      title: 'Pequenos passos. Uma reserva maior.',
      description:
        'Defina suas prioridades e acompanhe o dinheiro que você consegue guardar ao longo do tempo.',
      highlight: 'Cada valor guardado faz parte da sua evolução.',
      visual: 'reserve',
    },
    {
      eyebrow: 'VISÃO PARA SEGUIR EM FRENTE',
      title: 'Transforme controle em progresso.',
      description:
        'Acompanhe receitas, despesas e saldo. Use essa visão para ajustar o seu planejamento e cuidar do seu futuro.',
      highlight: 'Seus números, suas decisões, seus próximos passos.',
      visual: 'progress',
    },
  ];

  /* BLOCO — A logo abre uma vez por carregamento do APK; etapas só no primeiro acesso. */
  function shouldShow(isApk) {
    return isApk && !completed;
  }

  function afterLogo() {
    cancelLogoAnimation();
    try {
      if (localStorage.getItem(STORAGE_KEY) === 'complete') return finish();
    } catch {
      // Sem armazenamento, a apresentação continua disponível nesta abertura.
    }
    renderStep();
  }

  /* BLOCO — Ilustrações locais em SVG; os valores são exemplos, nunca dados financeiros reais. */
  function illustration(kind) {
    if (kind === 'organize') {
      return /* HTML */ `<svg viewBox="0 0 440 270" aria-hidden="true">
        <rect
          x="45"
          y="25"
          width="350"
          height="220"
          rx="24"
          fill="#ffffff"
          opacity=".07"
          stroke="#9cd7ff"
          stroke-opacity=".2"
        />
        <rect x="68" y="50" width="140" height="72" rx="14" fill="#123f65" />
        <text x="84" y="74" fill="#b8d2e8" font-size="12">Receitas</text>
        <text x="84" y="103" fill="#6aefb1" font-size="24" font-weight="700">+ R$ 250</text>
        <rect x="228" y="50" width="144" height="72" rx="14" fill="#123f65" />
        <text x="244" y="74" fill="#b8d2e8" font-size="12">Despesas</text>
        <text x="244" y="103" fill="#f9b8b7" font-size="24" font-weight="700">− R$ 180</text>
        <circle cx="117" cy="177" r="32" fill="none" stroke="#124a72" stroke-width="13" />
        <circle
          cx="117"
          cy="177"
          r="32"
          fill="none"
          stroke="#54e3a5"
          stroke-width="13"
          stroke-dasharray="145 201"
          transform="rotate(-90 117 177)"
        />
        <text x="178" y="165" fill="#b8d2e8" font-size="13">Saldo para planejar</text>
        <text x="178" y="197" fill="#ffffff" font-size="32" font-weight="700">R$ 70</text>
      </svg>`;
    }
    if (kind === 'reserve') {
      return /* HTML */ `<svg viewBox="0 0 440 270" aria-hidden="true">
        <path d="M70 230H380" stroke="#5c93b6" stroke-opacity=".4" />
        <path
          d="M80 148Q230 105 345 35"
          fill="none"
          stroke="#59edb1"
          stroke-width="5"
          stroke-linecap="round"
        />
        <path
          d="m321 36 27-7-5 28"
          fill="none"
          stroke="#59edb1"
          stroke-width="5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <rect x="93" y="177" width="64" height="53" rx="10" fill="#48d8ae" opacity=".6" />
        <rect x="187" y="137" width="64" height="93" rx="10" fill="#48d8ae" opacity=".8" />
        <rect x="281" y="94" width="64" height="136" rx="10" fill="#68edac" />
        <text x="125" y="164" text-anchor="middle" fill="#d8f7ec" font-size="15">R$ 250</text>
        <text x="219" y="124" text-anchor="middle" fill="#d8f7ec" font-size="15">R$ 500</text>
        <text x="313" y="81" text-anchor="middle" fill="#d8f7ec" font-size="15">R$ 750</text>
        <text x="125" y="252" text-anchor="middle" fill="#b8d2e8" font-size="12">1º depósito</text>
        <text x="219" y="252" text-anchor="middle" fill="#b8d2e8" font-size="12">2º depósito</text>
        <text x="313" y="252" text-anchor="middle" fill="#b8d2e8" font-size="12">3º depósito</text>
      </svg>`;
    }
    return /* HTML */ `<svg viewBox="0 0 440 270" aria-hidden="true">
      <rect
        x="45"
        y="25"
        width="350"
        height="220"
        rx="24"
        fill="#ffffff"
        opacity=".07"
        stroke="#9cd7ff"
        stroke-opacity=".2"
      />
      <text x="70" y="58" fill="#d3e8f8" font-size="14">Acompanhe sua evolução</text>
      <path d="M75 95H365M75 145H365M75 195H365" stroke="#97bbda" stroke-opacity=".16" />
      <path
        d="M80 205 137 173 194 188 251 139 308 115 360 78 360 220H80Z"
        fill="#41dca0"
        opacity=".12"
      />
      <path
        d="M80 205 137 173 194 188 251 139 308 115 360 78"
        fill="none"
        stroke="#63edb3"
        stroke-width="5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <circle cx="360" cy="78" r="8" fill="#63edb3" stroke="#e0fff4" stroke-width="3" />
      <text x="78" y="239" fill="#b8d2e8" font-size="12">Planejar</text>
      <text x="194" y="239" fill="#b8d2e8" font-size="12">Acompanhar</text>
      <text x="310" y="239" fill="#b8d2e8" font-size="12">Evoluir</text>
    </svg>`;
  }

  /* BLOCO — Cancela a transição quando a tela é substituída ou o usuário pula a animação. */
  function cancelLogoAnimation() {
    clearTimeout(logoTimer);
    logoTimer = null;
  }

  /* BLOCO — Anima a logo oficial antes das etapas, respeitando a preferência por menos movimento. */
  function playLogoAnimation() {
    cancelLogoAnimation();
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
      afterLogo();
      return;
    }
    container.innerHTML = /* HTML */ `<section
      class="apk-logo-splash"
      aria-label="Abertura do Optimus Finance"
    >
      <div class="apk-logo-splash-content" role="status" aria-live="polite">
        <div class="apk-logo-splash-halo" aria-hidden="true"></div>
        <img
          class="apk-logo-splash-mark optimus-logo"
          src="${location.protocol === 'file:' ? './icons/' : '/static/icons/'}app-icon-512.png?v=20261118-dragon"
          width="192"
          height="192"
          alt="Logo do Optimus Finance: dragão dourado"
        />
        <h1 class="apk-logo-splash-title">Optimus <strong>Finance</strong></h1>
        <p class="apk-logo-splash-tagline">
          Clareza para planejar.<br />Liberdade para conquistar.
        </p>
      </div>
      <button type="button" class="apk-logo-splash-skip" data-apk-intro="start">
        Pular animação
      </button>
    </section>`;
    // A abertura é breve; as etapas seguintes continuam sem avanço automático.
    logoTimer = setTimeout(() => {
      logoTimer = null;
      if (container?.isConnected && document.body.classList.contains('onboarding-mode'))
        afterLogo();
    }, 1800);
  }

  /* BLOCO — Cada etapa tem navegação explícita; nada avança sem ação do usuário. */
  function renderStep(focus = false) {
    cancelLogoAnimation();
    const slide = slides[currentStep];
    container.innerHTML = /* HTML */ `<section
      class="apk-intro"
      aria-label="Apresentação do Optimus Finance"
    >
      <div class="apk-intro-header">
        <div class="apk-intro-brand">
          <img
            class="optimus-logo"
            src="${location.protocol === 'file:' ? './icons/' : '/static/icons/'}app-icon-192.png?v=20261118-dragon"
            width="44"
            height="44"
            alt=""
          />
          <span>Optimus<strong>Finance</strong></span>
        </div>
        <button type="button" class="apk-intro-skip" data-apk-intro="finish">
          Pular apresentação
        </button>
      </div>
      <div class="apk-intro-stage" aria-live="polite" aria-atomic="true">
        <div class="apk-intro-art">${illustration(slide.visual)}</div>
        <p class="apk-intro-example">
          ${slide.visual === 'reserve' ? 'Exemplo de depósitos acumulados, sem rendimentos.' : 'Ilustração — não representa seus dados financeiros.'}
        </p>
        <p class="apk-intro-eyebrow">${slide.eyebrow}</p>
        <h1 id="apk-intro-title" tabindex="-1">${slide.title}</h1>
        <p class="apk-intro-description">${slide.description}</p>
        <p class="apk-intro-highlight">${slide.highlight}</p>
      </div>
      <div class="apk-intro-controls">
        <div class="apk-intro-pagination" aria-label="Etapas da apresentação">
          ${slides.map((_, index) => /* HTML */ `<button type="button" data-apk-intro-step="${index}" aria-label="Ir para etapa ${index + 1}" ${index === currentStep ? 'aria-current="step"' : ''}><span></span></button>`).join('')}<span
            class="apk-intro-count"
            >${currentStep + 1} de ${slides.length}</span
          >
        </div>
        <div class="apk-intro-actions">
          ${currentStep > 0 ? '<button type="button" class="apk-intro-back" data-apk-intro="back">Voltar</button>' : ''}<button
            type="button"
            class="apk-intro-next"
            data-apk-intro="${currentStep === slides.length - 1 ? 'finish' : 'next'}"
          >
            ${currentStep === slides.length - 1 ? 'Ir para o login' : 'Continuar'}
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </div>
    </section>`;
    if (focus) container.querySelector('#apk-intro-title').focus({ preventScroll: true });
  }

  /* BLOCO — Exibe o conteúdo no espaço de login, sem ler ou solicitar dados bancários. */
  function show(target, callback) {
    container = target;
    onComplete = callback;
    currentStep = 0;
    document.body.classList.add('onboarding-mode');
    playLogoAnimation();
  }

  /* BLOCO — Pular e concluir salvam somente que a apresentação já foi vista neste aparelho. */
  function finish() {
    cancelLogoAnimation();
    completed = true;
    try {
      localStorage.setItem(STORAGE_KEY, 'complete');
    } catch {
      // A preferência em memória evita repetição mesmo se o armazenamento estiver bloqueado.
    }
    document.body.classList.remove('onboarding-mode');
    const callback = onComplete;
    container = null;
    onComplete = null;
    callback?.();
  }

  document.addEventListener('click', (event) => {
    if (!container?.isConnected || !document.body.classList.contains('onboarding-mode')) return;
    const action = event.target.closest('[data-apk-intro]');
    const step = event.target.closest('[data-apk-intro-step]');
    if (action?.dataset.apkIntro === 'finish') return finish();
    if (action?.dataset.apkIntro === 'start') return afterLogo();
    if (step)
      currentStep = Math.max(
        0,
        Math.min(slides.length - 1, Number(step.dataset.apkIntroStep) || 0),
      );
    else if (action) currentStep += action.dataset.apkIntro === 'next' ? 1 : -1;
    else return;
    currentStep = Math.max(0, Math.min(slides.length - 1, currentStep));
    renderStep(true);
  });

  window.ApkIntro = { shouldShow, show };
})();
