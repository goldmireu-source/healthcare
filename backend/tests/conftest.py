"""pytest 공용 픽스처.

이 프로젝트의 database.py/main.py는 DB 경로를 "모듈을 처음 import하는 시점"에
환경변수(DB_DIR)로부터 계산해 전역 engine/SessionLocal을 만든다(설정 주입 구조가
아님). 테스트마다 완전히 격리된 SQLite DB를 쓰려면, 매 테스트 전에 DB_DIR을
새 임시 폴더로 바꾸고 관련 모듈을 sys.modules에서 지운 뒤 다시 import해야 한다 —
운영 코드를 테스트 편의를 위해 리팩터링하지 않고도 격리를 확보하는 방법이다.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

# backend/ 를 항상 import 경로에 포함 (pytest를 리포 루트에서 실행해도 동작하도록)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# 테스트 대상 애플리케이션이 새로 import될 때마다 함께 새로 로드되어야 하는 모듈들
# (전부 모듈 최상단에서 DB나 다른 전역 상태를 참조하는 모듈).
_RELOAD_MODULE_PREFIXES = (
    "database", "main", "models", "schemas", "auth", "rate_limit",
    "health_", "goal_", "report_", "admin_", "risk_detection",
    "badges", "integrations",
)


def _reset_app_modules():
    for name in list(sys.modules):
        if name in _RELOAD_MODULE_PREFIXES or name.startswith(_RELOAD_MODULE_PREFIXES):
            del sys.modules[name]


@pytest.fixture
def app_context(monkeypatch, tmp_path):
    """테스트 하나당 완전히 새로운 SQLite DB + FastAPI 앱 인스턴스를 만든다.

    Returns:
        (TestClient, database 모듈, models 모듈) 튜플 — 테스트에서 API 호출과
        DB 직접 조회(cascade 삭제 확인 등)를 모두 할 수 있게 한다.
    """
    monkeypatch.setenv("DB_DIR", str(tmp_path))
    monkeypatch.setenv("ALLOWED_ORIGINS", "")
    _reset_app_modules()

    import database as database_module
    import models as models_module

    # main.py는 import되는 순간(모듈 최상단) 만료 세션 정리 쿼리를 실행하므로,
    # 테이블이 이미 존재해야 한다 — main을 import하기 전에 먼저 스키마를 만든다.
    # (운영 DB는 여전히 Alembic으로만 관리되고, 테스트 DB만 create_all로 직접 생성)
    database_module.Base.metadata.create_all(bind=database_module.engine)

    import main as main_module

    with TestClient(main_module.app) as client:
        yield client, database_module, models_module

    database_module.Base.metadata.drop_all(bind=database_module.engine)
    database_module.engine.dispose()


@pytest.fixture
def client(app_context):
    """API 호출만 필요한 테스트를 위한 간단한 별칭."""
    c, _, _ = app_context
    return c


# ---------- 공용 테스트 데이터 헬퍼 ----------

def signup(client, username: str, password: str = "TestPass123!", name: str = "테스트유저") -> dict:
    res = client.post("/auth/signup", json={
        "username": username,
        "name": name,
        "password": password,
        "security_question": "가장 좋아하는 색은?",
        "security_answer": "blue",
    })
    assert res.status_code == 200, res.text
    return res.json()


def valid_record_payload(**overrides) -> dict:
    payload = {
        "date": "2026-07-01",
        "weight": 65.0,
        "height": 165.0,
        "systolic": 118,
        "diastolic": 76,
        "blood_sugar": 90,
        "steps": 8000,
        "sleep_hours": 7.0,
        "memo": "",
    }
    payload.update(overrides)
    return payload
