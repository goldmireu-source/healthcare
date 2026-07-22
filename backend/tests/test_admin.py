"""관리자 전용 엔드포인트 시나리오 (사용자 목록/상세/기록/통계/강제 로그아웃/
비밀번호 재설정/삭제/감사 로그). 회원가입으로는 admin이 될 수 없으므로, 테스트
DB에서 직접 role을 승격시켜 관리자 계정을 만든다(운영에서는 promote_admin.py로만 가능)."""

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


def test_admin_list_users_and_search(app_context):
    client, _, _ = app_context
    signup(client, "admin_lister", password="AdminPass123!")
    _make_admin(app_context, "admin_lister")
    client.post("/auth/logout")
    client.post("/auth/login", json={"username": "admin_lister", "password": "AdminPass123!"})

    signup_res = signup(client, "plain_member")
    client.post("/auth/logout")
    client.post("/auth/login", json={"username": "admin_lister", "password": "AdminPass123!"})

    res = client.get("/admin/users?page=1&page_size=50")
    assert res.status_code == 200, res.text
    body = res.json()
    usernames = [u["username"] for u in body["users"]]
    assert "admin_lister" in usernames
    assert "plain_member" in usernames

    res = client.get("/admin/users?search=plain_mem")
    assert res.status_code == 200
    assert [u["username"] for u in res.json()["users"]] == ["plain_member"]


def test_admin_stats_shape(app_context):
    client, _, _ = app_context
    signup(client, "admin_stats_user", password="AdminPass123!")
    _make_admin(app_context, "admin_stats_user")
    client.post("/auth/logout")
    client.post("/auth/login", json={"username": "admin_stats_user", "password": "AdminPass123!"})

    res = client.get("/admin/stats")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total_users"] >= 1
    assert "signup_trend" in body
    assert "retention_rate" in body


def test_admin_user_detail_and_records(app_context):
    client, _, _ = app_context
    signup(client, "admin_detail_admin", password="AdminPass123!")
    _make_admin(app_context, "admin_detail_admin")
    client.post("/auth/logout")

    signup(client, "admin_detail_target")
    client.post("/records", json=valid_record_payload())
    target_id_res = client.get("/auth/me")
    target_id = target_id_res.json()["id"]
    client.post("/auth/logout")

    client.post("/auth/login", json={"username": "admin_detail_admin", "password": "AdminPass123!"})

    res = client.get(f"/admin/users/{target_id}")
    assert res.status_code == 200, res.text
    assert res.json()["username"] == "admin_detail_target"
    assert res.json()["record_count"] == 1

    res = client.get(f"/admin/users/{target_id}/records")
    assert res.status_code == 200
    assert res.json()["count"] == 1

    res = client.get("/admin/users/999999")
    assert res.status_code == 404


def test_admin_force_logout_invalidates_target_session(app_context):
    client, _, _ = app_context
    signup(client, "admin_logout_admin", password="AdminPass123!")
    _make_admin(app_context, "admin_logout_admin")
    client.post("/auth/logout")

    signup(client, "admin_logout_target")
    target_id = client.get("/auth/me").json()["id"]
    # 여기서 로그아웃하면 target의 세션이 사라져 force-logout이 무효화할 대상이
    # 없어진다 - 로그인만 새로 하면(로그아웃 없이) 클라이언트 쿠키만 admin 것으로
    # 바뀌고 target의 세션은 서버에 그대로 남아있다 (test_records.py의 IDOR
    # 테스트가 계정을 전환할 때 쓰는 것과 같은 패턴).
    client.post("/auth/login", json={"username": "admin_logout_admin", "password": "AdminPass123!"})
    res = client.post(f"/admin/users/{target_id}/force-logout")
    assert res.status_code == 200, res.text
    assert res.json()["sessions_invalidated"] >= 1

    # 자기 자신은 이 기능으로 무효화할 수 없음
    admin_id = client.get("/auth/me").json()["id"]
    res = client.post(f"/admin/users/{admin_id}/force-logout")
    assert res.status_code == 400


def test_admin_reset_password_issues_working_temp_password(app_context):
    client, _, _ = app_context
    signup(client, "admin_reset_admin", password="AdminPass123!")
    _make_admin(app_context, "admin_reset_admin")
    client.post("/auth/logout")

    signup(client, "admin_reset_target", password="OldPass123!")
    target_id = client.get("/auth/me").json()["id"]
    client.post("/auth/logout")

    client.post("/auth/login", json={"username": "admin_reset_admin", "password": "AdminPass123!"})
    res = client.post(f"/admin/users/{target_id}/reset-password")
    assert res.status_code == 200, res.text
    temp_password = res.json()["temporary_password"]
    assert temp_password

    # 자기 자신 대상은 차단
    admin_id = client.get("/auth/me").json()["id"]
    res = client.post(f"/admin/users/{admin_id}/reset-password")
    assert res.status_code == 400

    client.post("/auth/logout")

    # 기존 비밀번호로는 더 이상 로그인 불가, 새 임시 비밀번호로는 가능
    res = client.post("/auth/login", json={"username": "admin_reset_target", "password": "OldPass123!"})
    assert res.status_code == 401
    res = client.post("/auth/login", json={"username": "admin_reset_target", "password": temp_password})
    assert res.status_code == 200


def test_admin_delete_user(app_context):
    client, database_module, models_module = app_context
    signup(client, "admin_delete_admin", password="AdminPass123!")
    _make_admin(app_context, "admin_delete_admin")
    client.post("/auth/logout")

    signup(client, "admin_delete_target")
    target_id = client.get("/auth/me").json()["id"]
    client.post("/auth/logout")

    client.post("/auth/login", json={"username": "admin_delete_admin", "password": "AdminPass123!"})

    admin_id = client.get("/auth/me").json()["id"]
    res = client.delete(f"/admin/users/{admin_id}")
    assert res.status_code == 400

    res = client.delete(f"/admin/users/{target_id}")
    assert res.status_code == 200, res.text

    db = database_module.SessionLocal()
    try:
        assert db.query(models_module.User).filter(models_module.User.id == target_id).first() is None
    finally:
        db.close()


def test_admin_audit_log_records_actions(app_context):
    client, _, _ = app_context
    signup(client, "admin_audit_admin", password="AdminPass123!")
    _make_admin(app_context, "admin_audit_admin")
    client.post("/auth/logout")

    signup(client, "admin_audit_target")
    target_id = client.get("/auth/me").json()["id"]
    client.post("/auth/logout")

    client.post("/auth/login", json={"username": "admin_audit_admin", "password": "AdminPass123!"})
    client.post(f"/admin/users/{target_id}/force-logout")

    res = client.get("/admin/audit-log")
    assert res.status_code == 200, res.text
    actions = [log["action"] for log in res.json()["logs"]]
    assert "force_logout" in actions
