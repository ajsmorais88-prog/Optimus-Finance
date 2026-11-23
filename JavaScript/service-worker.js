/* Somente a página genérica offline é armazenada; nenhuma API ou informação financeira. */
const OFFLINE_CACHE = 'finance-offline-v2';
// BLOCO — Prepara apenas a página genérica usada quando a rede estiver indisponível.
self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(OFFLINE_CACHE).then((cache) => cache.add('/offline.html')));
  self.skipWaiting();
});
// BLOCO — Remove versões antigas do cache e assume o controle das abas abertas.
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith('finance-offline-') && key !== OFFLINE_CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});
// BLOCO — Mantém a navegação online; somente falhas de rede usam a página offline.
self.addEventListener('fetch', (event) => {
  if (
    event.request.mode !== 'navigate' ||
    new URL(event.request.url).origin !== self.location.origin
  )
    return;
  event.respondWith(fetch(event.request).catch(() => caches.match('/offline.html')));
});

/* BLOCO — Vínculo mínimo do dispositivo; não armazena valores ou dados bancários. */
const PUSH_BINDING_CACHE = 'finance-push-binding-v1';
self.addEventListener('message', (event) => {
  if (event.data?.type !== 'push-binding') return;
  event.waitUntil(
    (async () => {
      const cache = await caches.open(PUSH_BINDING_CACHE);
      if (event.data.binding)
        await cache.put('/push-binding', new Response(JSON.stringify(event.data.binding)));
      else {
        await cache.delete('/push-binding');
        const notifications = await self.registration.getNotifications();
        notifications.forEach((notification) => notification.close());
      }
      event.ports[0]?.postMessage({ ok: true });
    })(),
  );
});

/* Um aviso genérico protege informações financeiras na tela bloqueada. */
self.addEventListener('push', (event) => {
  event.waitUntil(
    (async () => {
      let payload;
      try {
        payload = event.data.json();
      } catch {
        return;
      }
      const cache = await caches.open(PUSH_BINDING_CACHE);
      const saved = await cache.match('/push-binding');
      if (!saved) return;
      const binding = await saved.json();
      if (
        binding.user_id !== payload.user_id ||
        binding.session_version !== payload.session_version
      )
        return;
      const route = ['bank_account', 'card_bill', 'fixed_costs'].includes(payload.route)
        ? payload.route
        : 'overview';
      await self.registration.showNotification('Optimus Finance', {
        body:
          payload.kind === 'connection_test'
            ? 'Notificações ativadas neste celular. Este é um teste de entrega.'
            : route === 'fixed_costs'
              ? payload.kind === 'fixed_overdue'
                ? 'Você tem um custo fixo vencido. Confira no aplicativo.'
                : 'Você tem um custo fixo próximo do vencimento.'
              : route === 'card_bill'
                ? 'Novas transações no cartão de crédito.'
                : 'Novas transações na conta bancária.',
        icon: '/static/icons/app-icon-192.png?v=20261118-dragon',
        badge: '/static/icons/notification-badge.png',
        tag: 'finance-' + payload.id,
        renotify: false,
        data: {
          route,
          record_id: payload.record_id,
          period: payload.period,
          user_id: payload.user_id,
        },
      });
    })(),
  );
});

/* A abertura usa sempre o próprio domínio; o login continua obrigatório. */
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    (async () => {
      const data = event.notification.data || {};
      const route = ['bank_account', 'card_bill', 'fixed_costs'].includes(data.route)
        ? data.route
        : 'overview';
      const url = new URL('/', self.location.origin);
      url.hash = route;
      if (/^\d{4}-\d{2}$/.test(data.period || ''))
        url.searchParams.set('notification_month', data.period);
      if (Number.isSafeInteger(data.record_id))
        url.searchParams.set('notification_record', String(data.record_id));
      url.searchParams.set('notification_user', String(data.user_id));
      url.searchParams.set('notification_route', route);
      await self.clients.openWindow(url.href);
    })(),
  );
});
