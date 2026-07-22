"""건강 기록 CRUD + 검색 + 통계 라우터. 로직은 main.py에서 그대로 옮김."""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
import health_service

router = APIRouter(tags=["Records"])


@router.post("/records", response_model=schemas.RecordOut)
def create_record(
    payload: schemas.RecordIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    record = models.HealthRecord(
        user_id=current_user.id,
        date=payload.date,
        weight=payload.weight,
        height=payload.height,
        systolic=payload.systolic,
        diastolic=payload.diastolic,
        blood_sugar=payload.blood_sugar,
        steps=payload.steps,
        sleep_hours=payload.sleep_hours,
        memo=payload.memo,
    )
    health_service.apply_evaluation(record)
    db.add(record)
    db.commit()
    db.refresh(record)
    return health_service.record_to_out(record)


@router.get("/records", response_model=schemas.RecordListOut)
def list_records(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .order_by(models.HealthRecord.date.asc())
        .all()
    )
    return schemas.RecordListOut(count=len(records), records=[health_service.record_to_out(r) for r in records])


@router.get("/records/{record_id}", response_model=schemas.RecordOut)
def get_record(
    record_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    record = health_service.get_owned_record(db, record_id, current_user)
    return health_service.record_to_out(record)


@router.put("/records/{record_id}", response_model=schemas.RecordOut)
def update_record(
    record_id: int,
    payload: schemas.RecordUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    record = health_service.get_owned_record(db, record_id, current_user)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)

    health_service.apply_evaluation(record)
    db.commit()
    db.refresh(record)
    return health_service.record_to_out(record)


@router.delete("/records/{record_id}")
def delete_record(
    record_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    record = health_service.get_owned_record(db, record_id, current_user)
    db.delete(record)
    db.commit()
    return {"message": f"{record_id}번 기록이 삭제되었습니다."}


@router.get("/search", response_model=schemas.RecordListOut)
def search_records(
    start: str = Query(..., description="검색 시작일 YYYY-MM-DD"),
    end: str = Query(..., description="검색 종료일 YYYY-MM-DD"),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if start > end:
        raise HTTPException(status_code=400, detail="start는 end보다 이전이거나 같아야 합니다.")
    records = (
        db.query(models.HealthRecord)
        .filter(
            models.HealthRecord.user_id == current_user.id,
            models.HealthRecord.date >= start,
            models.HealthRecord.date <= end,
        )
        .order_by(models.HealthRecord.date.asc())
        .all()
    )
    return schemas.RecordListOut(count=len(records), records=[health_service.record_to_out(r) for r in records])


@router.get("/stats", response_model=schemas.StatsOut)
def get_stats(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )

    if not records:
        return schemas.StatsOut(count=0)

    def avg(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 2) if values else None

    def distribution(values):
        dist: dict = {}
        for v in values:
            dist[v] = dist.get(v, 0) + 1
        return dist

    return schemas.StatsOut(
        count=len(records),
        avg_weight=avg([r.weight for r in records]),
        avg_bmi=avg([r.bmi for r in records]),
        avg_systolic=avg([r.systolic for r in records]),
        avg_diastolic=avg([r.diastolic for r in records]),
        avg_blood_sugar=avg([r.blood_sugar for r in records]),
        avg_steps=avg([r.steps for r in records]),
        avg_sleep_hours=avg([r.sleep_hours for r in records]),
        bmi_category_distribution=distribution([r.bmi_category for r in records]),
        bp_category_distribution=distribution([r.bp_category for r in records]),
        sugar_category_distribution=distribution([r.sugar_category for r in records]),
    )
