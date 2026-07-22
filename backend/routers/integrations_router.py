"""확장성 확보(Integrations) 라우터 — 웨어러블/LLM/가져오기 연동 인터페이스.

지금은 OpenAI/Claude/Gemini, Apple Health/Samsung Health/Google Fit, 건강검진
PDF를 실제로 연결하지 않는다. 대신 나중에 붙이기 쉽도록 인터페이스만 설계해
integrations.py에 두고, 여기서는 그 인터페이스가 실제로 동작하는지 보여주는
최소한의 엔드포인트만 노출한다 (CSV 파싱+저장은 진짜로 동작, 나머지는 Mock).
"""

import os

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
import health_service
from integrations import (
    WearableProvider,
    MockWearableDataSource,
    CsvHealthDataImporter,
)

router = APIRouter(tags=["Integrations"])


@router.get("/integrations/status", response_model=schemas.IntegrationsStatusOut)
def integrations_status(current_user: models.User = Depends(auth.get_current_user)):
    openai_configured = bool(os.getenv("OPENAI_API_KEY"))
    return schemas.IntegrationsStatusOut(integrations=[
        schemas.IntegrationStatusOut(
            name="OpenAI", category="llm", status="available" if openai_configured else "mock",
            description=(
                "AI Health Coach가 실제 OpenAI API로 코칭 메시지를 생성 중 (호출 실패 시 규칙 기반 자동 폴백)"
                if openai_configured
                else "OPENAI_API_KEY 환경변수를 설정하면 실제 OpenAI 연동으로 전환됨 (지금은 규칙 기반)"
            ),
        ),
        schemas.IntegrationStatusOut(
            name="Claude", category="llm", status="mock",
            description="OpenAI와 동일한 CoachingProvider 인터페이스로 교체 가능",
        ),
        schemas.IntegrationStatusOut(
            name="Gemini", category="llm", status="mock",
            description="OpenAI와 동일한 CoachingProvider 인터페이스로 교체 가능",
        ),
        schemas.IntegrationStatusOut(
            name="Apple Health", category="wearable", status="mock",
            description="WearableDataSource 구현체를 추가하면 실제 걸음수/수면 데이터 연동 가능",
        ),
        schemas.IntegrationStatusOut(
            name="Samsung Health", category="wearable", status="mock",
            description="Apple Health와 동일한 WearableDataSource 인터페이스로 교체 가능",
        ),
        schemas.IntegrationStatusOut(
            name="Google Fit", category="wearable", status="mock",
            description="Apple Health와 동일한 WearableDataSource 인터페이스로 교체 가능",
        ),
        schemas.IntegrationStatusOut(
            name="CSV Import", category="import", status="available",
            description="CSV 파싱 + 미리보기 + 실제 DB 저장(POST /integrations/import/csv/commit)까지 지원",
        ),
        schemas.IntegrationStatusOut(
            name="건강검진 PDF", category="import", status="mock",
            description="HealthDataImporter 구현체(PDF 파서)를 추가하면 실제 연동 가능",
        ),
    ])


@router.get("/integrations/wearable/mock", response_model=schemas.WearableMockOut)
def integrations_wearable_mock(
    provider: str = Query("apple_health", description="apple_health | samsung_health | google_fit"),
    start: str = Query(..., description="조회 시작일 YYYY-MM-DD"),
    end: str = Query(..., description="조회 종료일 YYYY-MM-DD"),
    current_user: models.User = Depends(auth.get_current_user),
):
    try:
        provider_enum = WearableProvider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail="지원하지 않는 웨어러블 provider입니다.")

    source = MockWearableDataSource(provider_enum)
    days = source.fetch_daily_activity(start, end)
    return schemas.WearableMockOut(
        provider=provider,
        days=[schemas.WearableActivityOut(date=d.date, steps=d.steps, sleep_hours=d.sleep_hours) for d in days],
    )


@router.post("/integrations/import/csv/preview", response_model=schemas.ImportPreviewOut)
def integrations_import_csv_preview(
    payload: schemas.CsvImportIn,
    current_user: models.User = Depends(auth.get_current_user),
):
    importer = CsvHealthDataImporter()
    records = importer.parse(payload.csv_content)
    return schemas.ImportPreviewOut(
        count=len(records),
        records=[
            schemas.ImportedRecordOut(
                date=r.date, weight=r.weight, height=r.height, systolic=r.systolic,
                diastolic=r.diastolic, blood_sugar=r.blood_sugar, steps=r.steps,
                sleep_hours=r.sleep_hours,
            )
            for r in records
        ],
    )


@router.post("/integrations/import/csv/commit", response_model=schemas.ImportCommitOut)
def integrations_import_csv_commit(
    payload: schemas.CsvImportIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """CSV를 실제로 DB에 저장한다.

    POST /records와 완전히 동일한 검증(schemas.RecordIn)과 BMI 계산 로직
    (health_service.apply_evaluation)을 재사용해, 형식이 깨졌거나 범위를
    벗어난 값이 그대로 저장되는 일이 없게 한다. 한 행이라도 검증에 실패하면
    아무것도 저장하지 않고 전체 행의 오류 목록을 반환한다(부분 저장으로 인한
    혼란 방지).
    """
    importer = CsvHealthDataImporter()
    parsed = importer.parse(payload.csv_content)

    validated: list[schemas.RecordIn] = []
    errors: list[schemas.ImportRowError] = []
    for i, r in enumerate(parsed, start=1):
        try:
            validated.append(schemas.RecordIn(
                date=r.date,
                weight=r.weight,
                height=r.height,
                systolic=r.systolic,
                diastolic=r.diastolic,
                blood_sugar=r.blood_sugar,
                steps=r.steps if r.steps is not None else 0,
                sleep_hours=r.sleep_hours if r.sleep_hours is not None else 0.0,
            ))
        except ValidationError as exc:
            first = exc.errors()[0]
            field = first["loc"][-1] if first["loc"] else "값"
            errors.append(schemas.ImportRowError(row=i, date=r.date, error=f"{field}: {first['msg']}"))

    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "CSV 검증에 실패한 행이 있어 아무것도 저장하지 않았습니다.", "errors": [e.model_dump() for e in errors]},
        )

    created: list[models.HealthRecord] = []
    for payload_in in validated:
        record = models.HealthRecord(
            user_id=current_user.id,
            date=payload_in.date,
            weight=payload_in.weight,
            height=payload_in.height,
            systolic=payload_in.systolic,
            diastolic=payload_in.diastolic,
            blood_sugar=payload_in.blood_sugar,
            steps=payload_in.steps,
            sleep_hours=payload_in.sleep_hours,
            memo=payload_in.memo,
        )
        health_service.apply_evaluation(record)
        db.add(record)
        created.append(record)

    db.commit()
    for record in created:
        db.refresh(record)

    return schemas.ImportCommitOut(
        count=len(created),
        records=[health_service.record_to_out(r) for r in created],
    )
