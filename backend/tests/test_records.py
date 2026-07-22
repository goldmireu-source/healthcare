"""건강기록 CRUD 정상 동작 + IDOR(다른 유저 기록 접근 차단) 시나리오."""

from conftest import signup, valid_record_payload


def test_record_crud(client):
    signup(client, "crud_user")

    # CREATE
    res = client.post("/records", json=valid_record_payload())
    assert res.status_code == 200, res.text
    record = res.json()
    record_id = record["id"]
    assert record["bmi_category"]  # 서버가 분류값을 계산해 채워줬는지

    # READ (단건)
    res = client.get(f"/records/{record_id}")
    assert res.status_code == 200
    assert res.json()["weight"] == 65.0

    # READ (전체)
    res = client.get("/records")
    assert res.status_code == 200
    assert res.json()["count"] == 1

    # UPDATE
    res = client.put(f"/records/{record_id}", json={"weight": 70.0})
    assert res.status_code == 200
    assert res.json()["weight"] == 70.0
    assert res.json()["bmi"] != record["bmi"]  # 체중이 바뀌었으니 BMI도 재계산돼야 함

    # DELETE
    res = client.delete(f"/records/{record_id}")
    assert res.status_code == 200

    # 삭제 후 조회하면 404
    res = client.get(f"/records/{record_id}")
    assert res.status_code == 404


def test_record_validation_rejects_impossible_values(client):
    signup(client, "validation_user")

    res = client.post("/records", json=valid_record_payload(weight=99999))
    assert res.status_code == 422

    res = client.post("/records", json=valid_record_payload(date="2026-13-45"))
    assert res.status_code == 422


def test_idor_cannot_access_other_users_record(client):
    # user1이 기록 생성
    signup(client, "idor_victim")
    res = client.post("/records", json=valid_record_payload())
    victim_record_id = res.json()["id"]

    # user2로 갈아타서 (같은 client의 쿠키가 새 세션으로 교체됨) victim의 기록 ID로 접근 시도
    signup(client, "idor_attacker")
    res = client.get(f"/records/{victim_record_id}")
    assert res.status_code == 404  # 403이 아니라 404로 응답해 존재 자체를 숨김 (IDOR 방지)

    res = client.put(f"/records/{victim_record_id}", json={"weight": 1.0})
    assert res.status_code == 404

    res = client.delete(f"/records/{victim_record_id}")
    assert res.status_code == 404

    # victim의 기록 목록에는 여전히 원본 데이터가 그대로 있어야 함 (attacker가 못 건드렸는지 재확인)
    signup(client, "idor_victim2", password="TestPass123!")  # 그냥 세션 전환용 더미 계정
    client.post("/auth/logout")
    res = client.post("/auth/login", json={"username": "idor_victim", "password": "TestPass123!"})
    assert res.status_code == 200
    res = client.get(f"/records/{victim_record_id}")
    assert res.status_code == 200
    assert res.json()["weight"] == 65.0
