"""Web Push 구독/발송(push_router.py) 시나리오.

conftest.py의 app_context 픽스처가 VAPID 키를 테스트 전용 값으로 고정해두므로
_push_enabled()는 항상 True. 실제 발송(webpush())은 진짜 푸시 서비스로 나가는
네트워크 호출이라 테스트에서는 항상 monkeypatch로 대체한다 - 여기서 검증하는
것은 "누구를 건너뛰고 누구에게 보낼지 고르는 로직"이지 실제 전송 성공 여부가 아니다.

주의: routers.push_router는 매 테스트마다 conftest._reset_app_modules()가
sys.modules에서 지우고 새로 import한다(라우터 분리 검증 때 겪었던 것과 같은
이유) - 그래서 이 모듈을 파일 최상단에서 import해 두면 그 참조는 첫 테스트
이전 시점의 오래된 모듈 객체를 가리키게 되어, 그 객체에 monkeypatch해도 실제
요청을 처리하는(main.py가 참조하는) 최신 모듈에는 반영되지 않는다. 반드시
각 테스트 함수 "안에서"(client/app_context 픽스처가 이미 재로드를 끝낸 뒤)
import해야 한다.
"""

from datetime import date

from conftest import signup, valid_record_payload


def _make_admin(app_context, username):
    client, database_module, models_module = app_context
    db = database_module.SessionLocal()
    try:
        user = db.query(models_module.User).filter(models_module.User.username == username).first()
        user.role = "admin"
        db.commit()
    finally:
        db.close()


def _subscribe_payload(endpoint_suffix: str) -> dict:
    return {
        "endpoint": f"https://push.example.com/ep/{endpoint_suffix}",
        "keys": {"p256dh": "fake-p256dh-key", "auth": "fake-auth-secret"},
    }


def test_vapid_public_key_enabled_with_test_keys(client):
    signup(client, "push_vapid_user")
    res = client.get("/push/vapid-public-key")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["enabled"] is True
    assert len(body["public_key"]) > 20


def test_vapid_public_key_requires_auth(client):
    res = client.get("/push/vapid-public-key")
    assert res.status_code == 401


def test_subscribe_requires_auth(client):
    res = client.post("/push/subscribe", json=_subscribe_payload("noauth"))
    assert res.status_code == 401


def test_subscribe_and_unsubscribe(app_context):
    client, database_module, models_module = app_context
    signup(client, "push_sub_user")

    res = client.post("/push/subscribe", json=_subscribe_payload("sub1"))
    assert res.status_code == 200, res.text

    db = database_module.SessionLocal()
    try:
        subs = db.query(models_module.PushSubscription).all()
        assert len(subs) == 1
        assert subs[0].endpoint == "https://push.example.com/ep/sub1"
    finally:
        db.close()

    res = client.post("/push/unsubscribe", json={"endpoint": "https://push.example.com/ep/sub1"})
    assert res.status_code == 200

    db = database_module.SessionLocal()
    try:
        assert db.query(models_module.PushSubscription).count() == 0
    finally:
        db.close()


def test_subscribe_upsert_on_same_endpoint(app_context):
    """같은 endpoint로 다시 구독하면(예: 브라우저 알림 권한 재설정) 새 행이 늘어나지
    않고 기존 행을 갱신해야 한다 (endpoint에 unique 제약이 걸려 있음)."""
    client, database_module, models_module = app_context
    signup(client, "push_upsert_user")

    res1 = client.post("/push/subscribe", json=_subscribe_payload("upsert"))
    assert res1.status_code == 200
    res2 = client.post("/push/subscribe", json=_subscribe_payload("upsert"))
    assert res2.status_code == 200

    db = database_module.SessionLocal()
    try:
        assert db.query(models_module.PushSubscription).count() == 1
    finally:
        db.close()


def test_send_reminder_requires_admin(client):
    signup(client, "push_reminder_regular")
    res = client.post("/push/send-reminder")
    assert res.status_code == 403


def test_send_reminder_skips_active_and_sends_to_inactive(app_context, monkeypatch):
    import routers.push_router as push_router  # 재로드 이후 최신 모듈이어야 함 - 위 주의사항 참고

    client, database_module, models_module = app_context

    sent_calls = []

    def fake_webpush(subscription_info, data, vapid_private_key, vapid_claims):
        sent_calls.append(subscription_info["endpoint"])
        return "ok"

    monkeypatch.setattr(push_router, "webpush", fake_webpush)

    # 관리자 계정
    signup(client, "push_reminder_admin", password="AdminPass123!")
    _make_admin(app_context, "push_reminder_admin")

    # user_active: 오늘 기록 있음 + 구독 -> 리마인더 건너뛰어야 함
    signup(client, "push_active_user")
    client.post("/records", json=valid_record_payload(date=date.today().isoformat()))
    client.post("/push/subscribe", json=_subscribe_payload("active"))

    # user_inactive: 오늘 기록 없음 + 구독 -> 리마인더 발송 대상
    signup(client, "push_inactive_user")
    client.post("/push/subscribe", json=_subscribe_payload("inactive"))

    client.post("/auth/login", json={"username": "push_reminder_admin", "password": "AdminPass123!"})
    res = client.post("/push/send-reminder")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sent"] == 1
    assert body["skipped_already_active"] == 1
    assert body["skipped_already_sent"] == 0
    assert body["failed"] == 0
    assert sent_calls == ["https://push.example.com/ep/inactive"]

    # 같은 날 다시 호출하면 이미 보낸 구독은 skipped_already_sent로 잡혀야 함
    res2 = client.post("/push/send-reminder")
    body2 = res2.json()
    assert body2["sent"] == 0
    assert body2["skipped_already_sent"] == 1
    assert body2["skipped_already_active"] == 1


def test_send_reminder_removes_expired_subscription_on_410(app_context, monkeypatch):
    import routers.push_router as push_router  # 재로드 이후 최신 모듈이어야 함 - 위 주의사항 참고
    from pywebpush import WebPushException

    client, database_module, models_module = app_context

    class FakeResponse:
        status_code = 410

    def fake_webpush_expired(subscription_info, data, vapid_private_key, vapid_claims):
        raise WebPushException("gone", response=FakeResponse())

    monkeypatch.setattr(push_router, "webpush", fake_webpush_expired)

    signup(client, "push_expired_admin", password="AdminPass123!")
    _make_admin(app_context, "push_expired_admin")

    signup(client, "push_expired_user")
    client.post("/push/subscribe", json=_subscribe_payload("expired"))

    client.post("/auth/login", json={"username": "push_expired_admin", "password": "AdminPass123!"})
    res = client.post("/push/send-reminder")
    body = res.json()
    assert body["failed"] == 1
    assert body["sent"] == 0

    db = database_module.SessionLocal()
    try:
        assert db.query(models_module.PushSubscription).filter(
            models_module.PushSubscription.endpoint == "https://push.example.com/ep/expired"
        ).count() == 0
    finally:
        db.close()
