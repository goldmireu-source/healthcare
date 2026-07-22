"""목표(Goal) CRUD 및 주간 리포트(report_service.py) 시나리오."""

from conftest import signup, valid_record_payload


def test_goal_not_set_returns_404(client):
    signup(client, "goal_none_user")
    res = client.get("/goals")
    assert res.status_code == 404


def test_goal_set_and_get(client):
    signup(client, "goal_user")

    res = client.post("/goals", json={"target_weight": 60.0, "target_systolic": 120})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["target_weight"] == 60.0
    assert body["target_systolic"] == 120
    assert body["target_diastolic"] is None

    # 이미 목표가 있으면 새로 만들지 않고 갱신 - 조회로 확인
    res = client.get("/goals")
    assert res.status_code == 200
    assert res.json()["target_weight"] == 60.0

    # 부분 갱신 - target_diastolic만 추가해도 target_weight는 유지돼야 함
    res = client.post("/goals", json={"target_diastolic": 80})
    assert res.status_code == 200
    body = res.json()
    assert body["target_diastolic"] == 80
    assert body["target_weight"] == 60.0


def test_weekly_report_shape(client):
    signup(client, "report_user")
    client.post("/records", json=valid_record_payload(date="2026-07-01"))
    client.post("/records", json=valid_record_payload(date="2026-07-03", weight=64.0))

    res = client.get("/reports/weekly")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["username"] == "report_user"
    assert "this_week" in body
    assert "last_week" in body
    assert "change" in body
    assert "ai_summary" in body


def test_weekly_report_requires_auth(client):
    res = client.get("/reports/weekly")
    assert res.status_code == 401
