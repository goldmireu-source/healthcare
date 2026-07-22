// 마이 헬스 로그 - Web Push 서비스 워커 (최소 구현).
// /app/ 아래에 위치해 이 스코프(/app/) 전체를 제어한다.

self.addEventListener('push', (event) => {
  let payload = { title: '마이 헬스 로그', body: '새 알림이 있어요.' };
  if (event.data) {
    try { payload = event.data.json(); } catch (e) { payload.body = event.data.text(); }
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || '마이 헬스 로그', {
      body: payload.body || '',
      icon: undefined,
    })
  );
});

// 알림을 클릭하면 이미 열려있는 앱 탭이 있으면 포커스, 없으면 새로 연다.
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const c of clientList) {
        if (c.url.includes('/app/') && 'focus' in c) return c.focus();
      }
      if (clients.openWindow) return clients.openWindow('/app/');
    })
  );
});
