// index.html/admin.html 양쪽에서 쓰는 공통 프론트 로직.
// 두 페이지는 완전히 분리된 화면(일반 사용자용 / 관리자용)이라 인증 흐름 자체는
// 다르지만, API 호출 방식(fetch 래퍼)·토스트 알림·HTML 이스케이프는 동일하게
// 동작해야 하므로 여기 한 곳에서만 관리한다.

// 신뢰할 수 없는 문자열(이름 등 자유 입력 필드)을 innerHTML로 렌더링해야 할 때
// 저장형 XSS를 막기 위해 항상 이 함수를 거친다.
function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = String(s);
  return div.innerHTML;
}

function toast(message, type) {
  const box = document.getElementById('toast-box');
  const el = document.createElement('div');
  el.className = 'toast' + (type ? ' ' + type : '');
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}

// 세션 만료(401) 시 로그인 화면으로 되돌리는 방식은 index.html(showAuthScreen)과
// admin.html(showAdminLogin)이 서로 다르므로, 각 페이지가 자신의 처리 함수를
// window.onSessionExpired에 등록해두면 apiGet/apiSend가 그 함수를 호출한다.
async function apiGet(path) {
  const res = await fetch(path, { credentials: 'same-origin' });
  if (res.status === 401) {
    if (typeof window.onSessionExpired === 'function') window.onSessionExpired();
    throw new Error('세션이 만료되었습니다. 다시 로그인해주세요.');
  }
  if (!res.ok) { throw new Error((await res.json()).detail || res.statusText); }
  return res.json();
}

async function apiSend(path, method, body) {
  const res = await fetch(path, {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.status === 401) {
    if (typeof window.onSessionExpired === 'function') window.onSessionExpired();
    throw new Error('세션이 만료되었습니다. 다시 로그인해주세요.');
  }
  if (!res.ok) { throw new Error((await res.json()).detail || res.statusText); }
  return res.json();
}
