"""회원 탈퇴 시 cascade 삭제(기록/목표/세션까지 함께 삭제) 시나리오."""

from conftest import signup, valid_record_payload


def test_account_deletion_cascades_records_and_goals(app_context):
    client, database_module, models_module = app_context

    signup(client, "delete_me", password="TestPass123!")
    client.post("/records", json=valid_record_payload())
    client.post("/goals", json={"target_weight": 60.0})

    db = database_module.SessionLocal()
    try:
        user = db.query(models_module.User).filter(models_module.User.username == "delete_me").first()
        user_id = user.id
        assert db.query(models_module.HealthRecord).filter(models_module.HealthRecord.user_id == user_id).count() == 1
        assert db.query(models_module.Goal).filter(models_module.Goal.user_id == user_id).count() == 1
        assert db.query(models_module.Session).filter(models_module.Session.user_id == user_id).count() >= 1
    finally:
        db.close()

    # 탈퇴
    res = client.request("DELETE", "/auth/me", json={"password": "TestPass123!"})
    assert res.status_code == 200

    db = database_module.SessionLocal()
    try:
        assert db.query(models_module.User).filter(models_module.User.id == user_id).first() is None
        assert db.query(models_module.HealthRecord).filter(models_module.HealthRecord.user_id == user_id).count() == 0
        assert db.query(models_module.Goal).filter(models_module.Goal.user_id == user_id).count() == 0
        assert db.query(models_module.Session).filter(models_module.Session.user_id == user_id).count() == 0
    finally:
        db.close()

    # 탈퇴 후 같은 세션 쿠키로는 더 이상 접근 불가
    res = client.get("/records")
    assert res.status_code == 401


def test_account_deletion_requires_correct_password(client):
    signup(client, "keep_me", password="TestPass123!")
    res = client.request("DELETE", "/auth/me", json={"password": "WrongPassword!"})
    assert res.status_code == 401

    # 틀린 비밀번호로는 탈퇴되지 않았으므로 계정이 여전히 남아있어야 함
    res = client.get("/records")
    assert res.status_code == 200
