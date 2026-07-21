import json
import logging
from datetime import date as date_cls, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import Base, engine, get_db
import models
import schemas
from health_logic import evaluate_record

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("healthlog")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="마이 헬스 로그 API",
    description=(
        "매일의 건강 수치(몸무게·키·혈압·혈당 등)를 기록하면 BMI를 자동 계산하고 "
        "건강 상태를 분류하며, 쌓인 기록으로 통계·목표 달성률·주간 리포트를 제공하는 API입니다."
    ),
    version="1.0.0",
)


# 실행 중 어떤 예외가 나도 서버가 죽지 않고 500 응답으로 처리
@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"detail": f"예상치 못한 오류가 발생했습니다: {str(exc)}"},
    )


def get_or_create_user(db: Session, username: str) -> models.User:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        user = models.User(username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def record_to_out(r: models.HealthRecord) -> schemas.RecordOut:
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


@app.get("/", tags=["Root"])
def read_root():
    return {"message": "마이 헬스 로그 API", "docs": "/docs"}


# ---------- 필수 엔드포인트 ----------

@app.post("/records", response_model=schemas.RecordOut, tags=["Records"])
def create_record(payload: schemas.RecordIn, db: Session = Depends(get_db)):
    user = get_or_create_user(db, payload.username)
    record = models.HealthRecord(
        user_id=user.id,
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
    apply_evaluation(record)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record_to_out(record)


@app.get("/records", response_model=schemas.RecordListOut, tags=["Records"])
def list_records(
    username: Optional[str] = Query(None, description="지정 시 해당 사용자 기록만 조회"),
    db: Session = Depends(get_db),
):
    q = db.query(models.HealthRecord)
    if username:
        q = q.join(models.User).filter(models.User.username == username)
    records = q.order_by(models.HealthRecord.date.asc()).all()
    return schemas.RecordListOut(count=len(records), records=[record_to_out(r) for r in records])


@app.get("/records/{record_id}", response_model=schemas.RecordOut, tags=["Records"])
def get_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(models.HealthRecord).filter(models.HealthRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
    return record_to_out(record)


@app.put("/records/{record_id}", response_model=schemas.RecordOut, tags=["Records"])
def update_record(record_id: int, payload: schemas.RecordUpdate, db: Session = Depends(get_db)):
    record = db.query(models.HealthRecord).filter(models.HealthRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)

    apply_evaluation(record)
    db.commit()
    db.refresh(record)
    return record_to_out(record)


@app.delete("/records/{record_id}", tags=["Records"])
def delete_record(record_id: int, db: Session = Depends(get_db)):
    record = db.query(models.HealthRecord).filter(models.HealthRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
    db.delete(record)
    db.commit()
    return {"message": f"{record_id}번 기록이 삭제되었습니다."}


@app.get("/search", response_model=schemas.RecordListOut, tags=["Records"])
def search_records(
    start: str = Query(..., description="검색 시작일 YYYY-MM-DD"),
    end: str = Query(..., description="검색 종료일 YYYY-MM-DD"),
    username: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    if start > end:
        raise HTTPException(status_code=400, detail="start는 end보다 이전이거나 같아야 합니다.")
    q = db.query(models.HealthRecord).filter(
        models.HealthRecord.date >= start, models.HealthRecord.date <= end
    )
    if username:
        q = q.join(models.User).filter(models.User.username == username)
    records = q.order_by(models.HealthRecord.date.asc()).all()
    return schemas.RecordListOut(count=len(records), records=[record_to_out(r) for r in records])


@app.get("/stats", response_model=schemas.StatsOut, tags=["Records"])
def get_stats(username: Optional[str] = Query(None), db: Session = Depends(get_db)):
    q = db.query(models.HealthRecord)
    if username:
        q = q.join(models.User).filter(models.User.username == username)
    records = q.all()

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


# ---------- 고도화 기능: 목표 관리 ----------

def _goal_to_out(db: Session, goal: models.Goal, username: str) -> schemas.GoalOut:
    latest = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == goal.user_id)
        .order_by(models.HealthRecord.date.desc())
        .first()
    )
    achievement: dict = {}
    if latest:
        if goal.target_weight is not None:
            achievement["weight_diff"] = round(latest.weight - goal.target_weight, 2)
            achievement["weight_achieved"] = latest.weight <= goal.target_weight
        if goal.target_systolic is not None:
            achievement["systolic_achieved"] = latest.systolic <= goal.target_systolic
        if goal.target_diastolic is not None:
            achievement["diastolic_achieved"] = latest.diastolic <= goal.target_diastolic
        if goal.target_blood_sugar is not None:
            achievement["blood_sugar_achieved"] = latest.blood_sugar <= goal.target_blood_sugar
    else:
        achievement["message"] = "아직 기록이 없어 달성률을 계산할 수 없습니다."

    return schemas.GoalOut(
        id=goal.id,
        username=username,
        target_weight=goal.target_weight,
        target_systolic=goal.target_systolic,
        target_diastolic=goal.target_diastolic,
        target_blood_sugar=goal.target_blood_sugar,
        achievement=achievement,
    )


@app.post("/goals", response_model=schemas.GoalOut, tags=["Goals"])
def set_goal(payload: schemas.GoalIn, db: Session = Depends(get_db)):
    user = get_or_create_user(db, payload.username)
    goal = db.query(models.Goal).filter(models.Goal.user_id == user.id).first()
    if not goal:
        goal = models.Goal(user_id=user.id)
        db.add(goal)

    if payload.target_weight is not None:
        goal.target_weight = payload.target_weight
    if payload.target_systolic is not None:
        goal.target_systolic = payload.target_systolic
    if payload.target_diastolic is not None:
        goal.target_diastolic = payload.target_diastolic
    if payload.target_blood_sugar is not None:
        goal.target_blood_sugar = payload.target_blood_sugar

    db.commit()
    db.refresh(goal)
    return _goal_to_out(db, goal, user.username)


@app.get("/goals", response_model=schemas.GoalOut, tags=["Goals"])
def get_goal(username: str = Query("default"), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    goal = db.query(models.Goal).filter(models.Goal.user_id == user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="설정된 목표가 없습니다.")
    return _goal_to_out(db, goal, username)


# ---------- 고도화 기능: 주간 리포트 ----------

@app.get("/reports/weekly", response_model=schemas.WeeklyReportOut, tags=["Reports"])
def weekly_report(username: str = Query("default"), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    today = date_cls.today()
    this_week_start = (today - timedelta(days=6)).isoformat()
    this_week_end = today.isoformat()
    last_week_start = (today - timedelta(days=13)).isoformat()
    last_week_end = (today - timedelta(days=7)).isoformat()

    def week_stats(start: str, end: str) -> dict:
        records = (
            db.query(models.HealthRecord)
            .filter(
                models.HealthRecord.user_id == user.id,
                models.HealthRecord.date >= start,
                models.HealthRecord.date <= end,
            )
            .all()
        )
        if not records:
            return {"record_count": 0}

        def avg(values):
            return round(sum(values) / len(values), 2)

        return {
            "record_count": len(records),
            "avg_weight": avg([r.weight for r in records]),
            "avg_systolic": avg([r.systolic for r in records]),
            "avg_diastolic": avg([r.diastolic for r in records]),
            "avg_blood_sugar": avg([r.blood_sugar for r in records]),
            "avg_steps": avg([r.steps for r in records]),
            "avg_sleep_hours": avg([r.sleep_hours for r in records]),
        }

    this_week = week_stats(this_week_start, this_week_end)
    last_week = week_stats(last_week_start, last_week_end)

    change = {}
    for key in ["avg_weight", "avg_systolic", "avg_diastolic", "avg_blood_sugar", "avg_steps", "avg_sleep_hours"]:
        if key in this_week and key in last_week:
            change[key] = round(this_week[key] - last_week[key], 2)

    return schemas.WeeklyReportOut(
        username=username, this_week=this_week, last_week=last_week, change=change
    )
