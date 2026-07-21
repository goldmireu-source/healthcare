"""아주 단순한 인메모리 요청 횟수 제한기 (sliding window).

Redis 등 외부 저장소 없이, 이 프로세스가 살아있는 동안만 유지되는 카운터로
로그인/회원가입/비밀번호 재설정 같은 민감한 엔드포인트에 대한 반복 시도를
막는다. 단일 프로세스로 도는 학습/데모 규모에 맞춘 수준의 가드레일이며,
서버를 재시작하면 카운터가 초기화되고 여러 워커/서버로 수평 확장하면
카운터가 프로세스별로 분리된다는 한계가 있다 — 실제 운영 규모에서는
Redis 등 공유 저장소 기반 제한기로 교체가 필요하다.
"""

import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone

_lock = threading.Lock()
_attempts: dict = defaultdict(list)


def is_rate_limited(key: str, max_attempts: int, window_seconds: int) -> bool:
    """True를 반환하면 이번 시도는 한도 초과 — 호출한 쪽에서 막아야 함."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=window_seconds)
    with _lock:
        fresh = [t for t in _attempts[key] if t > window_start]
        if len(fresh) >= max_attempts:
            _attempts[key] = fresh
            return True
        fresh.append(now)
        _attempts[key] = fresh
        return False


def reset(key: str) -> None:
    with _lock:
        _attempts.pop(key, None)
