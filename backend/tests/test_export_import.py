"""CSV/JSON 내보내기(export_router.py) + CSV 가져오기 미리보기/커밋(integrations_router.py) 시나리오."""

from conftest import signup, valid_record_payload

VALID_CSV = (
    "date,weight,height,systolic,diastolic,blood_sugar,steps,sleep_hours\n"
    "2026-06-01,60,160,110,70,90,5000,7\n"
    "2026-06-02,60.5,160,112,72,88,6000,7.5\n"
)

INVALID_CSV = (
    "date,weight,height,systolic,diastolic,blood_sugar,steps,sleep_hours\n"
    "2026-06-01,99999,160,110,70,90,5000,7\n"  # weight 범위 초과 -> 검증 실패
)


def test_export_csv_requires_auth(client):
    res = client.get("/export/csv")
    assert res.status_code == 401


def test_export_csv_and_json(client):
    signup(client, "export_user")
    client.post("/records", json=valid_record_payload())

    res = client.get("/export/csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    body = res.text
    assert "date,weight,height" in body
    assert "65.0" in body

    res = client.get("/export/json")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    records = res.json()
    assert len(records) == 1
    assert records[0]["weight"] == 65.0


def test_export_csv_sanitizes_formula_injection(client):
    signup(client, "export_csv_injection_user")
    client.post("/records", json=valid_record_payload(memo="=1+1"))

    res = client.get("/export/csv")
    assert res.status_code == 200
    # 수식으로 해석되지 않도록 앞에 작은따옴표가 붙어야 함
    assert "'=1+1" in res.text


def test_csv_import_preview_does_not_save(client):
    signup(client, "import_preview_user")
    res = client.post("/integrations/import/csv/preview", json={"csv_content": VALID_CSV})
    assert res.status_code == 200, res.text
    assert res.json()["count"] == 2

    # 미리보기는 저장하지 않아야 함
    res = client.get("/records")
    assert res.json()["count"] == 0


def test_csv_import_commit_saves_all_valid_rows(client):
    signup(client, "import_commit_user")
    res = client.post("/integrations/import/csv/commit", json={"csv_content": VALID_CSV})
    assert res.status_code == 200, res.text
    assert res.json()["count"] == 2

    res = client.get("/records")
    assert res.json()["count"] == 2


def test_csv_import_commit_is_all_or_nothing_on_invalid_row(client):
    signup(client, "import_invalid_user")
    res = client.post("/integrations/import/csv/commit", json={"csv_content": INVALID_CSV})
    assert res.status_code == 422, res.text
    assert "errors" in res.json()["detail"]

    # 검증 실패한 행이 하나라도 있으면 아무것도 저장되지 않아야 함
    res = client.get("/records")
    assert res.json()["count"] == 0


def test_integrations_status_and_wearable_mock(client):
    signup(client, "integrations_user")

    res = client.get("/integrations/status")
    assert res.status_code == 200
    names = [i["name"] for i in res.json()["integrations"]]
    assert "OpenAI" in names
    assert "CSV Import" in names

    res = client.get("/integrations/wearable/mock?provider=apple_health&start=2026-06-01&end=2026-06-03")
    assert res.status_code == 200
    assert len(res.json()["days"]) > 0

    res = client.get("/integrations/wearable/mock?provider=invalid_provider&start=2026-06-01&end=2026-06-03")
    assert res.status_code == 400
