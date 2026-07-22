"""보안질문 기반 비밀번호 찾기 흐름 + rate limiter(실제 429) 시나리오.

conftest.signup()은 security_question="가장 좋아하는 색은?", security_answer="blue"로
가입시킨다. auth.normalize_security_answer()가 대소문자/공백을 정규화하므로
"Blue"/" blue "도 정답으로 인정돼야 한다.
"""

from conftest import signup


def test_security_question_lookup(client):
    signup(client, "secq_user")
    res = client.get("/auth/security-question?username=secq_user")
    assert res.status_code == 200
    assert res.json()["security_question"] == "가장 좋아하는 색은?"

    res = client.get("/auth/security-question?username=no_such_user")
    assert res.status_code == 404


def test_reset_password_wrong_answer_rejected(client):
    signup(client, "resetpw_wrong_user", password="OldPass123!")
    res = client.post("/auth/reset-password", json={
        "username": "resetpw_wrong_user", "security_answer": "green", "new_password": "NewPass123!",
    })
    assert res.status_code == 401

    # 재설정 실패했으니 기존 비밀번호로 여전히 로그인 가능해야 함
    client.post("/auth/logout")
    res = client.post("/auth/login", json={"username": "resetpw_wrong_user", "password": "OldPass123!"})
    assert res.status_code == 200


def test_reset_password_success_normalizes_answer_and_invalidates_sessions(client):
    signup(client, "resetpw_ok_user", password="OldPass123!")

    # 정답은 "blue"지만 대소문자/공백이 달라도 정규화되어 통과해야 함
    res = client.post("/auth/reset-password", json={
        "username": "resetpw_ok_user", "security_answer": "  Blue  ", "new_password": "BrandNewPass123!",
    })
    assert res.status_code == 200, res.text

    # 재설정 전 세션은 무효화됨
    res = client.get("/auth/me")
    assert res.status_code == 401

    # 기존 비밀번호는 더 이상 안 되고, 새 비밀번호로는 로그인 가능
    res = client.post("/auth/login", json={"username": "resetpw_ok_user", "password": "OldPass123!"})
    assert res.status_code == 401
    res = client.post("/auth/login", json={"username": "resetpw_ok_user", "password": "BrandNewPass123!"})
    assert res.status_code == 200


def test_reset_password_rate_limited_after_5_attempts(client):
    signup(client, "resetpw_limit_user")
    client.post("/auth/logout")

    for _ in range(5):
        res = client.post("/auth/reset-password", json={
            "username": "resetpw_limit_user", "security_answer": "wrong", "new_password": "NewPass123!",
        })
        assert res.status_code == 401

    # 6번째는 (username+IP 기준) 429여야 함
    res = client.post("/auth/reset-password", json={
        "username": "resetpw_limit_user", "security_answer": "blue", "new_password": "NewPass123!",
    })
    assert res.status_code == 429


def test_signup_rate_limited_after_5_attempts(client):
    for i in range(5):
        res = client.post("/auth/signup", json={
            "username": f"ratelimit_signup_{i}", "name": "레이트리밋",
            "password": "TestPass123!", "security_question": "색?", "security_answer": "blue",
        })
        assert res.status_code == 200, res.text

    # 6번째 회원가입 시도는 (IP 기준) 429여야 함
    res = client.post("/auth/signup", json={
        "username": "ratelimit_signup_over", "name": "레이트리밋",
        "password": "TestPass123!", "security_question": "색?", "security_answer": "blue",
    })
    assert res.status_code == 429
