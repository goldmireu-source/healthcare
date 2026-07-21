import json
import logging
from datetime import date as date_cls, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Query, Response, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from database import Base, engine, get_db
import models
import schemas
import auth
from health_logic import evaluate_record

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("healthlog")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="마이 헬스 로그 API",
    description=(
        "매일의 건강 수치(몸무게·키·혈압·혈당 등)를 기록하면 BMI를 자동 계산하고 "
        "건강 상태를 분류하며, 쌓인 기록으로 통계·목표 달성률·주간 리포트를 제공하는 API입니다. "
        "회원가입/로그인 후 본인 기록만 조회·관리할 수 있습니다."
    ),
    version="2.0.0",
)


# 실행 중 어떤 예외가 나도 서버가 죽지 않고 500 응답으로 처리
@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"detail": f"예상치 못한 오류가 발생했습니다: {str(exc)}"},
    )


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
    # 실제 사용자용 화면으로 이동 (API 문서는 /docs 에서 계속 확인 가능)
    return RedirectResponse(url="/app/")


@app.get("/api", tags=["Root"])
def api_info():
    return {"message": "마이 헬스 로그 API", "docs": "/docs", "web_app": "/app/"}


@app.get("/health", tags=["Root"])
def health_check():
    """배포 환경(Lightsail 등)의 헬스체크용 엔드포인트."""
    return {"status": "ok"}


# 사용자용 웹 화면 (정적 HTML/CSS/JS, 별도 빌드 없이 REST API를 그대로 호출)
app.mount("/app", StaticFiles(directory="static", html=True), name="web_app")


# ---------- 인증 ----------

@app.post("/auth/signup", response_model=schemas.UserOut, tags=["Auth"])
def signup(payload: schemas.UserSignup, response: Response, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")

    password_hash, salt = auth.hash_password(payload.password)
    user = models.User(username=payload.username, password_hash=password_hash, password_salt=salt)
    db.add(user)
    db.commit()
    db.refresh(user)

    session = auth.create_session(db, user)
    response.set_cookie(
        key=auth.SESSION_COOKIE_NAME,
        value=session.token,
        httponly=True,
        samesite="lax",
        secure=auth.COOKIE_SECURE,
        max_age=auth.SESSION_TTL_DAYS * 24 * 3600,
    )
    return user


@app.post("/auth/login", response_model=schemas.UserOut, tags=["Auth"])
def login(payload: schemas.UserLogin, response: Response, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not auth.verify_password(payload.password, user.password_hash, user.password_salt):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    session = auth.create_session(db, user)
    response.set_cookie(
        key=auth.SESSION_COOKIE_NAME,
        value=session.token,
        httponly=True,
        samesite="lax",
        secure=auth.COOKIE_SECURE,
        max_age=auth.SESSION_TTL_DAYS * 24 * 3600,
    )
    return user


@app.post("/auth/logout", tags=["Auth"])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(auth.SESSION_COOKIE_NAME)
    if token:
        auth.delete_session(db, token)
    response.delete_cookie(auth.SESSION_COOKIE_NAME)
    return {"message": "로그아웃되었습니다."}


@app.get("/auth/me", response_model=schemas.UserOut, tags=["Auth"])
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


# ---------- 필수 엔드포인트 (모두 로그인 필요, 본인 기록만 대상) ----------

@app.post("/records", response_model=schemas.RecordOut, tags=["Records"])
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
    apply_evaluation(record)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record_to_out(record)


@app.get("/records", response_model=schemas.RecordListOut, tags=["Records"])
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
    return schemas.RecordListOut(count=len(records), records=[record_to_out(r) for r in records])


def _get_owned_record(db: Session, record_id: int, current_user: models.User) -> models.HealthRecord:
    record = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.id == record_id, models.HealthRecord.user_id == current_user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다.")
    return record


@app.get("/records/{record_id}", response_model=schemas.RecordOut, tags=["Records"])
def get_record(
    record_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    record = _get_owned_record(db, record_id, current_user)
    return record_to_out(record)


@app.put("/records/{record_id}", response_model=schemas.RecordOut, tags=["Records"])
def update_record(
    record_id: int,
    payload: schemas.RecordUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    record = _get_owned_record(db, record_id, current_user)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)

    apply_evaluation(record)
    db.commit()
    db.refresh(record)
    return record_to_out(record)


@app.delete("/records/{record_id}", tags=["Records"])
def delete_record(
    record_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    record = _get_owned_record(db, record_id, current_user)
    db.delete(record)
    db.commit()
    return {"message": f"{record_id}번 기록이 삭제되었습니다."}


@app.get("/search", response_model=schemas.RecordListOut, tags=["Records"])
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
    return schemas.RecordListOut(count=len(records), records=[record_to_out(r) for r in records])


@app.get("/stats", response_model=schemas.StatsOut, tags=["Records"])
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
def set_goal(
    payload: schemas.GoalIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).first()
    if not goal:
        goal = models.Goal(user_id=current_user.id)
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
    return _goal_to_out(db, goal, current_user.username)


@app.get("/goals", response_model=schemas.GoalOut, tags=["Goals"])
def get_goal(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="설정된 목표가 없습니다.")
    return _goal_to_out(db, goal, current_user.username)


# ---------- 고도화 기능: 주간 리포트 ----------

@app.get("/reports/weekly", response_model=schemas.WeeklyReportOut, tags=["Reports"])
def weekly_report(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    today = date_cls.today()
    this_week_start = (today - timedelta(days=6)).isoformat()
    this_week_end = today.isoformat()
    last_week_start = (today - timedelta(days=13)).isoformat()
    last_week_end = (today - timedelta(days=7)).isoformat()

    def week_stats(start: str, end: str) -> dict:
        records = (
            db.query(models.HealthRecord)
            .filter(
                models.HealthRecord.user_id == current_user.id,
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
        username=current_user.username, this_week=this_week, last_week=last_week, change=change
    )


# ---------- 관리자 전용 기능 ----------
# 회원가입으로는 절대 admin이 될 수 없음 (role은 항상 "user"로 생성됨).
# 계정을 관리자로 승격하려면 로컬에서 promote_admin.py를 직접 실행해야 함.

def _log_admin_action(
    db: Session,
    admin_user: models.User,
    action: str,
    target_username: Optional[str] = None,
    detail: str = "",
) -> None:
    db.add(
        models.AuditLog(
            admin_username=admin_user.username,
            action=action,
            target_username=target_username,
            detail=detail,
        )
    )
    db.commit()


@app.get("/admin/users", response_model=schemas.AdminUsersOut, tags=["Admin"])
def admin_list_users(
    search: Optional[str] = Query(None, description="아이디 부분 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(models.User)
    if search:
        query = query.filter(models.User.username.ilike(f"%{search}%"))

    total = query.count()
    users = (
        query.order_by(models.User.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for u in users:
        record_count = (
            db.query(models.HealthRecord)
            .filter(models.HealthRecord.user_id == u.id)
            .count()
        )
        items.append(
            schemas.AdminUserOut(
                id=u.id,
                username=u.username,
                role=u.role,
                created_at=u.created_at,
                record_count=record_count,
            )
        )
    return schemas.AdminUsersOut(count=total, page=page, page_size=page_size, users=items)


@app.get("/admin/stats", response_model=schemas.AdminStatsOut, tags=["Admin"])
def admin_stats(
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    total_users = db.query(models.User).count()
    records = db.query(models.HealthRecord).all()

    def distribution(values):
        dist: dict = {}
        for v in values:
            dist[v] = dist.get(v, 0) + 1
        return dist

    return schemas.AdminStatsOut(
        total_users=total_users,
        total_records=len(records),
        bmi_category_distribution=distribution([r.bmi_category for r in records]),
        bp_category_distribution=distribution([r.bp_category for r in records]),
        sugar_category_distribution=distribution([r.sugar_category for r in records]),
    )


@app.get("/admin/users/{user_id}/records", response_model=schemas.RecordListOut, tags=["Admin"])
def admin_get_user_records(
    user_id: int,
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == user_id)
        .order_by(models.HealthRecord.date.asc())
        .all()
    )
    return schemas.RecordListOut(count=len(records), records=[record_to_out(r) for r in records])


@app.delete("/admin/users/{user_id}", tags=["Admin"])
def admin_delete_user(
    user_id: int,
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="자기 자신의 계정은 삭제할 수 없습니다.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    username = user.username
    db.delete(user)
    db.commit()
    _log_admin_action(db, current_admin, "delete_user", target_username=username)
    return {"message": f"'{username}' 계정이 삭제되었습니다."}


@app.post("/admin/users/{user_id}/force-logout", tags=["Admin"])
def admin_force_logout(
    user_id: int,
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="자기 자신의 세션은 이 기능으로 무효화할 수 없습니다. 로그아웃 버튼을 이용하세요.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    invalidated = (
        db.query(models.Session).filter(models.Session.user_id == user_id).delete()
    )
    db.commit()
    _log_admin_action(
        db, current_admin, "force_logout", target_username=user.username,
        detail=f"세션 {invalidated}개 무효화",
    )
    return {
        "message": f"'{user.username}'의 모든 세션을 무효화했습니다.",
        "sessions_invalidated": invalidated,
    }


@app.get("/admin/audit-log", response_model=schemas.AuditLogsOut, tags=["Admin"])
def admin_audit_log(
    limit: int = Query(50, ge=1, le=200),
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return schemas.AuditLogsOut(count=len(logs), logs=logs)
