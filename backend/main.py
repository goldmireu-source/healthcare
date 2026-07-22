import logging
import os

from dotenv import load_dotenv

# database.py(DB_DIR)/health_coach.py(OPENAI_API_KEY) 등 여러 모듈이 import되는
# 시점에 바로 환경변수를 읽으므로, 다른 로컬 모듈을 import하기 전에 .env부터 로드한다.
# 이미 설정된 환경변수(예: pytest의 monkeypatch, Docker의 -e)는 덮어쓰지 않는다
# (load_dotenv 기본값 override=False).
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from database import SessionLocal
import auth
from routers import (
    auth_router,
    records_router,
    goals_router,
    reports_router,
    export_router,
    ai_coach_router,
    integrations_router,
    admin_router,
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


# ---------- 도메인별 라우터 등록 ----------
# 각 라우터의 경로는 이미 완전한 형태(예: "/auth/signup")로 정의돼 있어 별도
# prefix를 주지 않는다 — main.py가 40개 라우트를 전부 담던 것을 도메인별로
# 나눈 것뿐, 실제 경로/동작은 이전과 100% 동일하다(분리 전/후 응답 diff로 확인).
app.include_router(auth_router.router)
app.include_router(records_router.router)
app.include_router(goals_router.router)
app.include_router(reports_router.router)
app.include_router(export_router.router)
app.include_router(ai_coach_router.router)
app.include_router(integrations_router.router)
app.include_router(admin_router.router)


# backend/와 frontend/는 항상 형제 폴더 (로컬 저장소 구조, Dockerfile 모두 이 배치를 유지함).
# __file__ 기준 경로라 uvicorn을 어디서 실행하든 항상 같은 정적 파일을 가리킨다.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BACKEND_DIR, "..", "frontend", "static")

# 사용자용 웹 화면 (정적 HTML/CSS/JS, 별도 빌드 없이 REST API를 그대로 호출)
app.mount("/app", StaticFiles(directory=STATIC_DIR, html=True), name="web_app")
