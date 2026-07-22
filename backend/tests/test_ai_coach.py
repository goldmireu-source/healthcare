"""AI Health Coach 7개 엔드포인트(코칭/추세/이상징후/스코어/캘린더/타임라인/배지) 시나리오."""

from conftest import signup, valid_record_payload


def _seed_two_records(client):
    client.post("/records", json=valid_record_payload(date="2026-07-01", weight=65.0))
    client.post("/records", json=valid_record_payload(date="2026-07-08", weight=63.0))


def test_health_coaching_requires_auth(client):
    res = client.get("/health-coaching")
    assert res.status_code == 401


def test_health_coaching_returns_messages_and_is_cached(client):
    signup(client, "coach_user")
    _seed_two_records(client)

    res = client.get("/health-coaching")
    assert res.status_code == 200, res.text
    first = res.json()["messages"]
    assert isinstance(first, list)

    # 같은 날 재요청은 캐시를 그대로 재사용해야 함 (health_coach 재계산이 아니라 동일 응답)
    res2 = client.get("/health-coaching")
    assert res2.status_code == 200
    assert res2.json()["messages"] == first


def test_trends_shape(client):
    signup(client, "trends_user")
    _seed_two_records(client)

    res = client.get("/trends")
    assert res.status_code == 200, res.text
    trends = res.json()["trends"]
    assert "weight" in trends
    assert trends["weight"]["trend"] in ("UP", "DOWN", "STABLE")


def test_risk_detection_shape(client):
    signup(client, "risk_user")
    _seed_two_records(client)

    res = client.get("/risk-detection")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["risk_level"] in ("LOW", "MODERATE", "HIGH")
    assert isinstance(body["anomalies"], list)


def test_health_score_requires_records(client):
    signup(client, "score_empty_user")
    res = client.get("/health-score")
    assert res.status_code == 404


def test_health_score_with_records(client):
    signup(client, "score_user")
    _seed_two_records(client)

    res = client.get("/health-score")
    assert res.status_code == 200, res.text
    body = res.json()
    assert 0 <= body["total_score"] <= 100
    assert len(body["metrics"]) == 5


def test_calendar_shape(client):
    signup(client, "calendar_user")
    _seed_two_records(client)

    res = client.get("/calendar?year=2026&month=7")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["year"] == 2026
    assert body["month"] == 7
    assert isinstance(body["days"], list)


def test_timeline_shape(client):
    signup(client, "timeline_user")
    _seed_two_records(client)

    res = client.get("/timeline")
    assert res.status_code == 200, res.text
    assert isinstance(res.json()["events"], list)


def test_badges_earn_first_record_badge(client):
    signup(client, "badge_user")
    res = client.get("/badges")
    assert res.status_code == 200, res.text
    badges_before = {b["key"]: b["earned"] for b in res.json()["badges"]}
    assert all(v is False for v in badges_before.values())

    client.post("/records", json=valid_record_payload())
    res = client.get("/badges")
    assert res.status_code == 200
    badges_after = {b["key"]: b["earned"] for b in res.json()["badges"]}
    # 기록을 하나라도 남기면 조건을 만족하는 배지가 최소 하나는 생겨야 함
    assert any(badges_after.values())
