"""건강기록(HealthRecord) CRUD 관련 서비스 레이어.

이전에는 main.py 안에 직접 정의되어 있던 헬퍼들을 그대로(로직 변경 없이) 옮겼다.
라우트 핸들러(main.py)는 이 모듈의 함수를 호출하는 얇은 wrapper 역할만 한다.
"""

import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from health_logic import evaluate_record


def record_to_out(r: models.HealthRecord) -> schemas.RecordOut:
    """HealthRecord ORM 객체를 API 응답 스키마로 변환한다."""
    return schemas.RecordOut(
        id=r.id,
        username=r.user.username,
        date=r.date,
        weight=r.weight,
        height=r.height,
        systolic=r.systolic,
        diastolic=r.diastolic,
        blood_sugar=r.blood_sugar,
        steps=r.steps,
        sleep_hours=r.sleep_hours,
        memo=r.memo or "",
        bmi=r.bmi,
        bmi_category=r.bmi_category,
        bp_category=r.bp_category,
        sugar_category=r.sugar_category,
        warnings=json.loads(r.warnings) if r.warnings else [],
        activity_level=r.activity_level,
        sleep_status=r.sleep_status,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def apply_evaluation(record: models.HealthRecord) -> None:
    """건강 지표(BMI/혈압/혈당 분류, 경고, 활동/수면 등급)를 계산해 record에 채운다."""
    result = evaluate_record(
        record.weight,
        record.height,
        record.systolic,
        record.diastolic,
        record.blood_sugar,
        record.steps,
        record.sleep_hours,
    )
    record.bmi = result["bmi"]
    record.bmi_category = result["bmi_category"]
    record.bp_category = result["bp_category"]
    record.sugar_category = result["sugar_category"]
    record.warnings = json.dumps(result["warnings"], ensure_ascii=False)
    record.activity_level = result["activity_level"]
    record.sleep_status = result["sleep_status"]


def get_owned_record(db: Session, record_id: int, current_user: models.User) -> models.HealthRecord:
    """record_id가 current_user 소유의 기록인지 확인하고 반환한다 (아니면 404)."""
    record = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.id == record_id, models.HealthRecord.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
    return record
