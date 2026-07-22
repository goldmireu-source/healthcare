"""인증/권한 핵심 시나리오: 로그인 잠금, 관리자 권한 없이 /admin/* 접근 차단."""

from conftest import signup


def test_login_lockout_after_5_failures(client):
    signup(client, "locktest_user")
    client.post("/auth/logout")

    for _ in range(5):
        res = client.post("/auth/login", json={"username": "locktest_user", "password": "WrongPass!"})
        assert res.status_code == 401

    # 6번째 시도는 (비밀번호가 맞아도) 계정 잠금으로 423이어야 함
    res = client.post("/auth/login", json={"username": "locktest_user", "password": "TestPass123!"})
    assert res.status_code == 423


def test_login_success_before_lockout_threshold(client):
    signup(client, "locktest_user2")
    client.post("/auth/logout")

    for _ in range(4):
        res = client.post("/auth/login", json={"username": "locktest_user2", "password": "WrongPass!"})
        assert res.status_code == 401

    # 4번 실패까지는 잠기지 않으므로 정상 로그인 가능해야 함
    res = client.post("/auth/login", json={"username": "locktest_user2", "password": "TestPass123!"})
    assert res.status_code == 200


def test_admin_endpoints_require_admin_role(client):
    signup(client, "regular_user")

    res = client.get("/admin/users")
    assert res.status_code == 403

    res = client.get("/admin/stats")
    assert res.status_code == 403

    res = client.get("/admin/audit-log")
    assert res.status_code == 403

    res = client.delete("/admin/users/1")
    assert res.status_code == 403


def test_unauthenticated_requests_are_rejected(client):
    res = client.get("/records")
    assert res.status_code == 401
