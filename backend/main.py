import csv
import io
import json
import logging
import os
from datetime import date
from typing import Optional

from dotenv import load_dotenv

# database.py(DB_DIR)/health_coach.py(OPENAI_API_KEY) 등 여러 모듈이 import되는
# 시점에 바로 환경변수를 읽으므로, 다른 로컬 모듈을 import하기 전에 .env부터 로드한다.
# 이미 설정된 환경변수(예: pytest의 monkeypatch, Docker의 -e)는 덮어쓰지 않는다
# (load_dotenv 기본값 override=False).
load_dotenv()

from fastapi import FastAPI, HTTPException, Depends, Query, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy.orm import Session

from database import get_db, SessionLocal
import models
import schemas
import auth
import rate_limit
from health_coach import generate_health_coaching
from health_trends import analyze_trends
from risk_detection import detect_risks
from health_score import compute_health_score
from health_calendar import build_month_calendar
from health_timeline import build_timeline
from badges import BADGE_DEFINITIONS, evaluate_new_badges
import health_service
import goal_service
import report_service
import admin_service
from integrations import (
    WearableProvider,
    MockWearableDataSource,
    CsvHealthDataImporter,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("healthlog")

# 스키마 생성/변경은 이제 Alembic 마이그레이션이 전담한다 (Base.metadata.create_all
# 직접 호출 제거). 새로 셋업할 때는 서버 실행 전에 `alembic upgrade head`를 먼저
# 실행해야 한다 — README.md "DB 스키마 변경" 절 참고.

# 앱 시작 시 1회, 그동안 쌓였을 수 있는 만료 세션을 정리 (배경 스케줄러 없이 가볍게).
# 이후에는 auth.create_session()이 로그인/회원가입마다 지연 평가로 계속 정리한다.
with SessionLocal() as _startup_db:
    _cleaned = auth.cleanup_expired_sessions(_startup_db)
    if _cleaned:
        logger.info(f"앱 시작 시 만료된 세션 {_cleaned}개 정리 완료")

app = FastAPI(
    title="마이 헬스 로그 API",
    description=(
        "매일의 건강 수치(몸무게·키·혈압·혈당 등)를 기록하면 BMI를 자동 계산하고 "
        "건강 상태를 분류하며, 쌓인 기록으로 통계·목표 달성률·주간 리포트를 제공하는 API입니다. "
        "회원가입/로그인 후 본인 기록만 조회·관리할 수 있습니다."
    ),
    version="2.0.0",
)

# ---------- CORS: 지금은 프론트엔드를 이 서버가 같은 origin(/app)으로 직접 서빙하므로
# 크로스오리진 요청이 필요 없다. ALLOWED_ORIGINS를 비워두면(기본값) 어떤 외부 origin도
# 허용하지 않는 가장 보수적인 설정이 된다 — 나중에 별도 도메인의 프론트엔드가 생기면
# 그때 ALLOWED_ORIGINS 환경변수(콤마로 구분)에 그 도메인만 추가하면 된다.
_allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


# 응답마다 기본 보안 헤더 추가 (MIME 스니핑 방지 / 클릭재킹 방지 / referrer 최소 노출)
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# 실행 중 어떤 예외가 나도 서버가 죽지 않고 500 응답으로 처리
@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"detail": f"예상치 못한 오류가 발생했습니다: {str(exc)}"},
    )


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


# backend/와 frontend/는 항상 형제 폴더 (로컬 저장소 구조, Dockerfile 모두 이 배치를 유지함).
# __file__ 기준 경로라 uvicorn을 어디서 실행하든 항상 같은 정적 파일을 가리킨다.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BACKEND_DIR, "..", "frontend", "static")

# 사용자용 웹 화면 (정적 HTML/CSS/JS, 별도 빌드 없이 REST API를 그대로 호출)
app.mount("/app", StaticFiles(directory=STATIC_DIR, html=True), name="web_app")


# ---------- 인증 ----------

def _client_ip(request: Request) -> str:
    # 리버스 프록시 뒤에 배포할 경우 X-Forwarded-For를 신뢰할 수 있는 범위에서
    # 확인해야 하지만, 이 프로젝트는 그 앞단이 없어 request.client만 사용한다.
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(key: str, max_attempts: int, window_seconds: int, message: str) -> None:
    if rate_limit.is_rate_limited(key, max_attempts, window_seconds):
        raise HTTPException(status_code=429, detail=message)


@app.post("/auth/signup", response_model=schemas.UserOut, tags=["Auth"])
def signup(
    payload: schemas.UserSignup,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _enforce_rate_limit(
        f"signup:{_client_ip(request)}",
        max_attempts=5,
        window_seconds=600,
        message="회원가입 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
    )

    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")

    password_hash, salt = auth.hash_password(payload.password)
    answer_hash, answer_salt = auth.hash_password(
        auth.normalize_security_answer(payload.security_answer)
    )
    user = models.User(
        username=payload.username,
        password_hash=password_hash,
        password_salt=salt,
        security_question=payload.security_question,
        security_answer_hash=answer_hash,
        security_answer_salt=answer_salt,
    )
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
def login(
    payload: schemas.UserLogin,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    # IP 기준 속도 제한 — 서로 다른 아이디를 대량으로 시도하는 무차별 대입을 막음
    _enforce_rate_limit(
        f"login:{_client_ip(request)}",
        max_attempts=15,
        window_seconds=300,
        message="로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
    )

    user = db.query(models.User).filter(models.User.username == payload.username).first()

    # 계정 단위 잠금 — 같은 계정에 대한 반복 실패를 막음 (IP를 바꿔가며 시도해도 방어됨)
    if user and auth.is_account_locked(user):
        raise HTTPException(
            status_code=423,
            detail=f"로그인 실패 횟수가 많아 계정이 잠겼습니다. {auth.LOGIN_LOCKOUT_MINUTES}분 후 다시 시도해주세요.",
        )

    if not user or not auth.verify_password(payload.password, user.password_hash, user.password_salt):
        if user:
            auth.register_failed_login(db, user)
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    auth.reset_login_failures(db, user)
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


@app.get("/auth/security-question", response_model=schemas.SecurityQuestionOut, tags=["Auth"])
def get_security_question(request: Request, username: str = Query(...), db: Session = Depends(get_db)):
    _enforce_rate_limit(
        f"secq:{_client_ip(request)}:{username}",
        max_attempts=10,
        window_seconds=600,
        message="요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
    )
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return schemas.SecurityQuestionOut(security_question=user.security_question)


@app.post("/auth/reset-password", tags=["Auth"])
def reset_password(payload: schemas.PasswordResetIn, request: Request, db: Session = Depends(get_db)):
    # 보안질문 답은 추측 가능한 값이 많아(생일, 색깔 등) 무차별 대입에 특히 취약 -> 엄격하게 제한
    _enforce_rate_limit(
        f"resetpw:{_client_ip(request)}:{payload.username}",
        max_attempts=5,
        window_seconds=900,
        message="비밀번호 재설정 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
    )
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if not auth.verify_password(
        auth.normalize_security_answer(payload.security_answer),
        user.security_answer_hash,
        user.security_answer_salt,
    ):
        raise HTTPException(status_code=401, detail="보안질문 답이 올바르지 않습니다.")

    password_hash, salt = auth.hash_password(payload.new_password)
    user.password_hash = password_hash
    user.password_salt = salt
    # 재설정 후에는 기존에 로그인돼 있던 모든 세션을 무효화 (탈취된 세션 방지)
    db.query(models.Session).filter(models.Session.user_id == user.id).delete()
    db.commit()
    return {"message": "비밀번호가 재설정되었습니다. 새 비밀번호로 다시 로그인해주세요."}


@app.post("/auth/change-password", tags=["Auth"])
def change_password(
    payload: schemas.PasswordChangeIn,
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    _enforce_rate_limit(
        f"changepw:{_client_ip(request)}:{current_user.id}",
        max_attempts=10,
        window_seconds=600,
        message="시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
    )
    if not auth.verify_password(
        payload.current_password, current_user.password_hash, current_user.password_salt
    ):
        raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다.")

    password_hash, salt = auth.hash_password(payload.new_password)
    current_user.password_hash = password_hash
    current_user.password_salt = salt
    # 지금 이 세션은 유지하고, 다른 기기/브라우저의 세션만 무효화
    current_token = request.cookies.get(auth.SESSION_COOKIE_NAME)
    db.query(models.Session).filter(
        models.Session.user_id == current_user.id,
        models.Session.token != current_token,
    ).delete()
    db.commit()
    return {"message": "비밀번호가 변경되었습니다."}


@app.delete("/auth/me", tags=["Auth"])
def delete_my_account(
    payload: schemas.AccountDeleteIn,
    response: Response,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if not auth.verify_password(
        payload.password, current_user.password_hash, current_user.password_salt
    ):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    db.delete(current_user)
    db.commit()
    response.delete_cookie(auth.SESSION_COOKIE_NAME)
    return {"message": "계정이 삭제되었습니다."}


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
    health_service.apply_evaluation(record)
    db.add(record)
    db.commit()
    db.refresh(record)
    return health_service.record_to_out(record)


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
    return schemas.RecordListOut(count=len(records), records=[health_service.record_to_out(r) for r in records])


@app.get("/records/{record_id}", response_model=schemas.RecordOut, tags=["Records"])
def get_record(
    record_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    record = health_service.get_owned_record(db, record_id, current_user)
    return health_service.record_to_out(record)


@app.put("/records/{record_id}", response_model=schemas.RecordOut, tags=["Records"])
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


@app.delete("/records/{record_id}", tags=["Records"])
def delete_record(
    record_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    record = health_service.get_owned_record(db, record_id, current_user)
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
    return schemas.RecordListOut(count=len(records), records=[health_service.record_to_out(r) for r in records])


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
# 실제 로직(달성 여부 + 예측 계산)은 goal_service.py로 분리됨.


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
    return goal_service.goal_to_out(db, goal, current_user.username)


@app.get("/goals", response_model=schemas.GoalOut, tags=["Goals"])
def get_goal(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="설정된 목표가 없습니다.")
    return goal_service.goal_to_out(db, goal, current_user.username)


# ---------- 고도화 기능: 주간 리포트 ----------

@app.get("/reports/weekly", response_model=schemas.WeeklyReportOut, tags=["Reports"])
def weekly_report(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return report_service.build_weekly_report(db, current_user)


# ---------- 고도화 기능: Export (CSV / JSON) ----------
# PDF는 요구사항에서 제외됨. 사용자 본인의 건강기록만 내보낸다.

_EXPORT_CSV_HEADER = [
    "date", "weight", "height", "systolic", "diastolic", "blood_sugar",
    "steps", "sleep_hours", "bmi", "bmi_category", "bp_category",
    "sugar_category", "activity_level", "sleep_status", "memo",
]

# CSV 수식 인젝션(Formula Injection) 방어 기준값 — 이 문자로 시작하는 셀은
# 엑셀/구글시트가 수식으로 해석해 실행할 수 있음 (예: memo에 "=1+1" 저장 후
# export한 파일을 열면 수식으로 계산됨). 표준 방어는 앞에 작은따옴표를 붙여
# 스프레드시트가 무조건 텍스트로 취급하게 만드는 것.
_CSV_DANGEROUS_PREFIXES = ("=", "+", "-", "@")


def _sanitize_csv_cell(value) -> str:
    """셀 값을 문자열로 변환하면서 수식 인젝션 위험이 있으면 무력화한다.

    memo 같은 자유 입력 필드뿐 아니라, 나중에 컬럼이 늘어나도 안전하도록
    문자열로 나가는 모든 셀에 동일하게 적용한다 (지금 값 중에는 음수가 없어
    "-"로 시작하는 정상 데이터는 없지만, 혹시 모를 경우에도 스프레드시트에서
    텍스트로만 보일 뿐 데이터 유실은 없음).
    """
    text = "" if value is None else str(value)
    if text.startswith(_CSV_DANGEROUS_PREFIXES):
        return "'" + text
    return text


def _export_filename(username: str, extension: str) -> str:
    # username은 회원가입 시 ^[a-zA-Z0-9_]+$ 로만 검증되어 헤더 인젝션 위험이 없음
    return f"health_records_{username}.{extension}"


@app.get("/export/csv", tags=["Export"])
def export_records_csv(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .order_by(models.HealthRecord.date.asc())
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_EXPORT_CSV_HEADER)
    for r in records:
        row = [
            r.date, r.weight, r.height, r.systolic, r.diastolic, r.blood_sugar,
            r.steps, r.sleep_hours, r.bmi, r.bmi_category, r.bp_category,
            r.sugar_category, r.activity_level, r.sleep_status, r.memo,
        ]
        writer.writerow([_sanitize_csv_cell(v) for v in row])

    filename = _export_filename(current_user.username, "csv")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/export/json", tags=["Export"])
def export_records_json(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .order_by(models.HealthRecord.date.asc())
        .all()
    )
    # health_service.record_to_out()은 이미 /records 엔드포인트가 쓰는 것과 동일한 직렬화 로직 (중복 방지)
    payload = [health_service.record_to_out(r).model_dump(mode="json") for r in records]

    filename = _export_filename(current_user.username, "json")
    return StreamingResponse(
        iter([json.dumps(payload, ensure_ascii=False, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- 고도화 기능: AI Health Coach ----------
# OPENAI_API_KEY 환경변수가 설정되어 있으면 health_coach.OpenAICoachingProvider가
# 실제 OpenAI API를 호출하고, 키가 없거나 호출이 실패/타임아웃되면 자동으로
# RuleBasedCoachingProvider로 폴백한다 (health_coach.build_default_coaching_provider 참고).

@app.get("/health-coaching", response_model=schemas.HealthCoachingOut, tags=["AI Coach"])
def get_health_coaching(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    # OpenAI 연동 시 매 요청마다 호출하면 비용이 계속 나가므로, 하루에 한 번만
    # 생성하고 같은 날 재요청은 캐시를 그대로 재사용한다 (badges.py의 지연 평가
    # 패턴과 동일 — 배경 스케줄러 없이 이 조회 시점에만 "오늘 이미 만들었는지" 확인).
    today = date.today().isoformat()
    cache = (
        db.query(models.CoachingCache)
        .filter(models.CoachingCache.user_id == current_user.id)
        .first()
    )
    if cache is not None and cache.generated_date == today:
        return schemas.HealthCoachingOut(messages=json.loads(cache.messages_json))

    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    # 목표가 없는 사용자가 대부분이라 404를 그대로 두면 안 되므로, 없으면 None으로 처리
    goal = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).first()

    messages = generate_health_coaching(records, goal)
    messages_json = json.dumps(messages, ensure_ascii=False)

    if cache is None:
        db.add(models.CoachingCache(user_id=current_user.id, generated_date=today, messages_json=messages_json))
    else:
        cache.generated_date = today
        cache.messages_json = messages_json
    db.commit()

    return schemas.HealthCoachingOut(messages=messages)


# ---------- 고도화 기능: 건강 추세 분석 ----------
# 체중/혈압/혈당/걸음수/수면 각 지표가 최근 상승(UP)/하락(DOWN)/유지(STABLE)인지
# 판단한다. health_coach.py의 코칭 메시지도 내부적으로 이 모듈(health_trends.py)을
# 사용하므로, 여기서 보여주는 결과와 코칭 메시지의 판단 기준은 항상 일치한다.

@app.get("/trends", response_model=schemas.TrendsOut, tags=["AI Coach"])
def get_health_trends(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    trend_results = analyze_trends(records)
    trends_out = {
        metric: schemas.TrendOut(
            metric=result.metric,
            trend=result.trend.value,
            recent_avg=result.recent_avg,
            prior_avg=result.prior_avg,
            diff=result.diff,
        )
        for metric, result in trend_results.items()
    }
    return schemas.TrendsOut(trends=trends_out)


# ---------- 고도화 기능: 이상 징후 감지 ----------
# health_trends.py가 "추세"를 본다면, 이 엔드포인트는 그중 "위험할 만큼 급격한
# 변화"만 추려서 위험도(LOW/MEDIUM/HIGH)로 보여준다 (risk_detection.py 참고).

@app.get("/risk-detection", response_model=schemas.RiskDetectionOut, tags=["AI Coach"])
def get_risk_detection(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    result = detect_risks(records)
    return schemas.RiskDetectionOut(
        risk_level=result.risk_level.value,
        anomalies=[
            schemas.AnomalyOut(
                metric=a.metric, label=a.label, severity=a.severity.value, detail=a.detail
            )
            for a in result.anomalies
        ],
    )


# ---------- 고도화 기능: Health Score 개선 ----------
# 이전에는 프론트(JS)에서 5개 지표에 균등한 페널티를 매겨 점수를 계산했다. 이제는
# 지표별 가중치(체중20%/혈압25%/혈당25%/운동15%/수면15%) + 추세 보너스/감점을
# 반영해 서버(health_score.py)에서 계산한 값을 그대로 내려준다.

@app.get("/health-score", response_model=schemas.HealthScoreOut, tags=["AI Coach"])
def get_health_score(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .order_by(models.HealthRecord.date.asc())
        .all()
    )
    if not records:
        raise HTTPException(status_code=404, detail="건강 스코어를 계산할 기록이 없습니다.")

    result = compute_health_score(latest=records[-1], records=records)
    return schemas.HealthScoreOut(
        total_score=result.total_score,
        metrics=[
            schemas.MetricScoreOut(
                metric=m.metric, category=m.category, base_score=m.base_score,
                trend_adjustment=m.trend_adjustment, final_score=m.final_score, weight=m.weight,
            )
            for m in result.metrics
        ],
    )


# ---------- 고도화 기능: 건강 캘린더 ----------

@app.get("/calendar", response_model=schemas.CalendarOut, tags=["AI Coach"])
def get_health_calendar(
    year: int = Query(..., ge=1900, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    days = build_month_calendar(records, year, month)
    return schemas.CalendarOut(
        year=year,
        month=month,
        days=[schemas.CalendarDayOut(date=d.date, level=d.level, score=d.score) for d in days],
    )


# ---------- 고도화 기능: 건강 타임라인 ----------

@app.get("/timeline", response_model=schemas.TimelineOut, tags=["AI Coach"])
def get_health_timeline(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    goal = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).first()
    events = build_timeline(records, goal)
    return schemas.TimelineOut(
        events=[schemas.TimelineEventOut(date=e.date, label=e.label, kind=e.kind) for e in events]
    )


# ---------- 고도화 기능: 건강 배지 ----------
# 배경 작업 스케줄러가 없는 프로젝트라, "조회 시점에 새로 만족한 조건이 있는지
# 평가하고, 있으면 그때 저장"하는 지연 평가 방식을 쓴다 (badges.py 참고).

@app.get("/badges", response_model=schemas.BadgesOut, tags=["AI Coach"])
def get_badges(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    earned = db.query(models.Badge).filter(models.Badge.user_id == current_user.id).all()
    earned_keys = {b.badge_key for b in earned}

    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    goal = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).first()

    new_keys = evaluate_new_badges(records, goal, earned_keys)
    if new_keys:
        for key in new_keys:
            db.add(models.Badge(user_id=current_user.id, badge_key=key))
        db.commit()
        earned = db.query(models.Badge).filter(models.Badge.user_id == current_user.id).all()

    earned_map = {b.badge_key: b for b in earned}
    badges_out = [
        schemas.BadgeOut(
            key=defn.key,
            label=defn.label,
            description=defn.description,
            icon=defn.icon,
            earned=defn.key in earned_map,
            earned_at=earned_map[defn.key].earned_at if defn.key in earned_map else None,
        )
        for defn in BADGE_DEFINITIONS
    ]
    return schemas.BadgesOut(badges=badges_out)


# ---------- 고도화 기능: 확장성 확보 (Integrations) ----------
# 지금은 OpenAI/Claude/Gemini, Apple Health/Samsung Health/Google Fit, 건강검진
# PDF를 실제로 연결하지 않는다. 대신 나중에 붙이기 쉽도록 인터페이스만 설계해
# integrations.py에 두고, 여기서는 그 인터페이스가 실제로 동작하는지 보여주는
# 최소한의 엔드포인트만 노출한다 (CSV 파싱은 진짜로 동작, 나머지는 Mock).

@app.get("/integrations/status", response_model=schemas.IntegrationsStatusOut, tags=["Integrations"])
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


@app.get("/integrations/wearable/mock", response_model=schemas.WearableMockOut, tags=["Integrations"])
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


@app.post("/integrations/import/csv/preview", response_model=schemas.ImportPreviewOut, tags=["Integrations"])
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


@app.post("/integrations/import/csv/commit", response_model=schemas.ImportCommitOut, tags=["Integrations"])
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


# ---------- 관리자 전용 기능 ----------
# 회원가입으로는 절대 admin이 될 수 없음 (role은 항상 "user"로 생성됨).
# 계정을 관리자로 승격하려면 로컬에서 promote_admin.py를 직접 실행해야 함.
# 실제 쿼리/집계 로직은 admin_service.py로 분리됨.

@app.get("/admin/users", response_model=schemas.AdminUsersOut, tags=["Admin"])
def admin_list_users(
    search: Optional[str] = Query(None, description="아이디 부분 검색"),
    role: Optional[str] = Query(None, description="user 또는 admin으로 필터링"),
    risk: Optional[str] = Query(None, description="high | moderate | normal | unknown 위험도 필터"),
    signup_days: Optional[int] = Query(None, ge=1, description="최근 N일 이내 가입한 사용자만 필터링 (개요 KPI 드릴다운용)"),
    signup_date: Optional[str] = Query(None, description="특정 날짜(YYYY-MM-DD)에 가입한 사용자만 필터링 (가입 추이 차트 드릴다운용)"),
    active_days: Optional[int] = Query(None, ge=1, description="최근 N일 이내 기록을 남긴 사용자만 필터링"),
    has_records: Optional[bool] = Query(None, description="true=기록 1건 이상 보유, false=기록 0건"),
    sort_by: str = Query("id", description="id | username | created_at | record_count | risk_level"),
    sort_dir: str = Query("asc", description="asc | desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    return admin_service.list_users(
        db, search, role, risk, sort_by, sort_dir, page, page_size,
        signup_days=signup_days, signup_date=signup_date, active_days=active_days, has_records=has_records,
    )


@app.get("/admin/stats", response_model=schemas.AdminStatsOut, tags=["Admin"])
def admin_stats(
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    return admin_service.compute_admin_stats(db)


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
    return schemas.RecordListOut(count=len(records), records=[health_service.record_to_out(r) for r in records])


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
    admin_service.log_admin_action(db, current_admin, "delete_user", target_username=username)
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
    admin_service.log_admin_action(
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
