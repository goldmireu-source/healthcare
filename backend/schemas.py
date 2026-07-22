from datetime import datetime, date as _date, timedelta
from typing import Optional, List, Dict

from pydantic import BaseModel, Field, field_validator, model_validator

_MIN_RECORD_DATE = _date(1900, 1, 1)


def _validate_record_date(value: str) -> str:
    """건강 기록 날짜가 실제 존재하는 날짜이고, 상식적인 범위 안에 있는지 확인.

    형식 검증만으로는 "2026-13-45" 같은 값을 걸러내지 못하고, 범위 없이는
    100년 전이나 수십 년 뒤 같은 값도 그대로 저장돼버리므로 둘 다 확인한다.
    """
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("날짜는 YYYY-MM-DD 형식의 실제 날짜여야 합니다.")
    if parsed < _MIN_RECORD_DATE or parsed > _date.today() + timedelta(days=1):
        raise ValueError("날짜가 유효한 범위를 벗어났습니다 (1900-01-01 ~ 내일까지).")
    return value


# ---------- Auth ----------

_COMMON_WEAK_PASSWORDS = {
    "123456", "12345678", "123456789", "1234567890", "password",
    "qwerty", "111111", "000000", "abc123", "1q2w3e4r", "iloveyou",
    "admin123", "letmein", "monkey", "welcome",
}


class UserSignup(BaseModel):
    username: str = Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    name: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    security_question: str = Field(..., min_length=2, max_length=200)
    security_answer: str = Field(..., min_length=1, max_length=200)

    @field_validator("password")
    @classmethod
    def _check_weak_password(cls, v):
        if v.lower() in _COMMON_WEAK_PASSWORDS:
            raise ValueError("너무 흔하게 사용되는 비밀번호입니다. 다른 비밀번호를 사용해주세요.")
        return v

    @model_validator(mode="after")
    def _check_password_not_username(self):
        if self.password.lower() == self.username.lower():
            raise ValueError("비밀번호는 아이디와 같을 수 없습니다.")
        return self


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    name: Optional[str] = None
    role: str

    class Config:
        from_attributes = True


class NameChangeIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class SecurityQuestionOut(BaseModel):
    security_question: str


class PasswordResetIn(BaseModel):
    username: str
    security_answer: str
    new_password: str = Field(..., min_length=6, max_length=100)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6, max_length=100)


class AccountDeleteIn(BaseModel):
    password: str


# ---------- Admin ----------

class AdminUserOut(BaseModel):
    id: int
    username: str
    name: Optional[str] = None
    role: str
    created_at: Optional[datetime] = None
    record_count: int
    # 가장 최근 건강기록의 BMI/혈압/혈당 분류 중 하나라도 "위험" 등급이면 high,
    # "주의" 등급이 있으면 moderate, 전부 정상이면 normal, 기록이 없으면 unknown.
    risk_level: str = "unknown"
    # 만료되지 않은(sessions.expires_at > 지금) 세션이 하나라도 있으면 True.
    # 실시간 접속 여부(하트비트/웹소켓)가 아니라 "유효한 로그인 세션 보유" 기준.
    is_online: bool = False

    class Config:
        from_attributes = True


class AdminUserDetailOut(BaseModel):
    """관리자의 "회원정보 보기" 상세 화면용. 목록(AdminUserOut)에는 없는 계정 상태
    정보(보안질문/로그인 실패 횟수/잠금 상태)까지 포함한다. 비밀번호 해시나 보안질문
    답 해시는 절대 포함하지 않는다(운영상 필요 없고, 굳이 응답에 실을 이유가 없음)."""

    id: int
    username: str
    name: Optional[str] = None
    role: str
    created_at: Optional[datetime] = None
    security_question: str
    failed_login_attempts: int
    locked_until: Optional[datetime] = None
    record_count: int
    risk_level: str = "unknown"
    is_online: bool = False
    active_session_count: int = 0
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminUsersOut(BaseModel):
    count: int  # 검색 조건에 맞는 전체 사용자 수 (페이지네이션 기준)
    page: int
    page_size: int
    users: List[AdminUserOut]


class SignupTrendPoint(BaseModel):
    date: str
    count: int


class AdminStatsOut(BaseModel):
    total_users: int
    total_records: int
    role_distribution: Dict[str, int] = {}
    new_users_last_7_days: int = 0
    signup_trend: List[SignupTrendPoint] = []
    bmi_category_distribution: Dict[str, int] = {}
    bp_category_distribution: Dict[str, int] = {}
    sugar_category_distribution: Dict[str, int] = {}
    high_risk_usernames: List[str] = []

    # ---------- 고도화: 관리자 Analytics 확장 (admin_analytics.py) ----------
    recent_activity_rate: float = 0.0  # 최근 7일 내 기록을 남긴 사용자 비율(%)
    retention_rate: float = 0.0  # 기록을 1건이라도 남긴 사용자 비율(%)
    avg_bmi: Optional[float] = None
    avg_systolic: Optional[float] = None
    avg_diastolic: Optional[float] = None
    avg_blood_sugar: Optional[float] = None
    high_risk_growth_rate: Optional[float] = None  # 7일 전 대비 고위험 사용자 증가율(%)
    signup_to_record_rate: float = 0.0  # 최근 30일 가입자 중 기록 작성 비율(%)
    online_users_count: int = 0  # 만료되지 않은 세션을 보유한(로그인 상태인) 사용자 수


class AuditLogOut(BaseModel):
    id: int
    admin_username: str
    action: str
    target_username: Optional[str] = None
    detail: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AuditLogsOut(BaseModel):
    count: int
    logs: List[AuditLogOut]


class AdminPasswordResetOut(BaseModel):
    """보안질문 답을 잊어(또는 rate limit에 걸려) 셀프 복구가 불가능한 사용자를 위한
    관리자 개입 경로. 임시 비밀번호는 이 응답에 딱 한 번만 노출되고 해시로만 저장되므로,
    관리자가 이 화면을 벗어나면 다시 조회할 방법이 없다 — 안전하게 전달했는지 확인 필요."""

    temporary_password: str
    message: str = "임시 비밀번호가 발급되었습니다. 이 화면을 벗어나면 다시 볼 수 없으니 안전한 방법으로 사용자에게 전달하고, 로그인 후 비밀번호를 변경하도록 안내하세요."


# ---------- Records ----------

class RecordIn(BaseModel):
    date: str = Field(..., examples=["2026-07-20"], description="측정일 YYYY-MM-DD")
    weight: float = Field(..., gt=0, le=500, description="몸무게(kg)")
    height: float = Field(..., gt=0, le=250, description="키(cm)")
    systolic: int = Field(..., gt=0, le=300, description="수축기 혈압")
    diastolic: int = Field(..., gt=0, le=200, description="이완기 혈압")
    blood_sugar: int = Field(..., gt=0, le=1000, description="공복 혈당(mg/dL)")
    steps: int = Field(0, ge=0, le=100_000, description="걸음 수")
    sleep_hours: float = Field(0.0, ge=0, le=24, description="수면 시간")
    memo: str = Field("", max_length=500)

    @field_validator("date")
    @classmethod
    def _check_date(cls, v):
        return _validate_record_date(v)


class RecordUpdate(BaseModel):
    date: Optional[str] = None
    weight: Optional[float] = Field(None, gt=0, le=500)
    height: Optional[float] = Field(None, gt=0, le=250)
    systolic: Optional[int] = Field(None, gt=0, le=300)
    diastolic: Optional[int] = Field(None, gt=0, le=200)
    blood_sugar: Optional[int] = Field(None, gt=0, le=1000)
    steps: Optional[int] = Field(None, ge=0, le=100_000)
    sleep_hours: Optional[float] = Field(None, ge=0, le=24)
    memo: Optional[str] = Field(None, max_length=500)

    @field_validator("date")
    @classmethod
    def _check_date(cls, v):
        if v is None:
            return v
        return _validate_record_date(v)


class RecordOut(BaseModel):
    id: int
    username: str
    date: str
    weight: float
    height: float
    systolic: int
    diastolic: int
    blood_sugar: int
    steps: int
    sleep_hours: float
    memo: str
    bmi: float
    bmi_category: str
    bp_category: str
    sugar_category: str
    warnings: List[str]
    activity_level: str
    sleep_status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RecordListOut(BaseModel):
    count: int
    records: List[RecordOut]


class StatsOut(BaseModel):
    count: int
    avg_weight: Optional[float] = None
    avg_bmi: Optional[float] = None
    avg_systolic: Optional[float] = None
    avg_diastolic: Optional[float] = None
    avg_blood_sugar: Optional[float] = None
    avg_steps: Optional[float] = None
    avg_sleep_hours: Optional[float] = None
    bmi_category_distribution: Dict[str, int] = {}
    bp_category_distribution: Dict[str, int] = {}
    sugar_category_distribution: Dict[str, int] = {}


# ---------- Goals (고도화) ----------

class GoalIn(BaseModel):
    target_weight: Optional[float] = Field(None, gt=0, le=500)
    target_systolic: Optional[int] = Field(None, gt=0, le=300)
    target_diastolic: Optional[int] = Field(None, gt=0, le=200)
    target_blood_sugar: Optional[int] = Field(None, gt=0, le=1000)


class GoalOut(BaseModel):
    id: int
    username: str
    target_weight: Optional[float]
    target_systolic: Optional[int]
    target_diastolic: Optional[int]
    target_blood_sugar: Optional[int]
    achievement: Dict = {}

    class Config:
        from_attributes = True


# ---------- Weekly report (고도화) ----------

class WeeklyReportOut(BaseModel):
    username: str
    this_week: Dict
    last_week: Dict
    change: Dict
    ai_summary: str = ""  # AI 건강 리포트 요약 문단 (health_coach.generate_weekly_summary)


# ---------- AI Health Coach ----------

class HealthCoachingOut(BaseModel):
    messages: List[str]


# ---------- 건강 추세 분석 (health_trends.py) ----------

class TrendOut(BaseModel):
    metric: str
    trend: str  # "UP" | "DOWN" | "STABLE" (health_trends.Trend)
    recent_avg: Optional[float] = None
    prior_avg: Optional[float] = None
    diff: Optional[float] = None


class TrendsOut(BaseModel):
    trends: Dict[str, TrendOut]


# ---------- 이상 징후 감지 (risk_detection.py) ----------
# 주의: 아래 risk_level("LOW"/"MEDIUM"/"HIGH")은 "최근 며칠간의 급격한 변화"를 보는
# 값으로, 관리자 페이지의 AdminUserOut.risk_level("high"/"moderate"/"normal"/"unknown",
# 가장 최근 기록 1건의 카테고리 기준)과는 판단 기준이 다른 별개의 개념이다.

class AnomalyOut(BaseModel):
    metric: str
    label: str
    severity: str  # "LOW" | "MEDIUM" | "HIGH"
    detail: str


class RiskDetectionOut(BaseModel):
    risk_level: str  # "LOW" | "MEDIUM" | "HIGH"
    anomalies: List[AnomalyOut]


# ---------- Health Score 개선 (health_score.py) ----------

class MetricScoreOut(BaseModel):
    metric: str
    category: Optional[str] = None
    base_score: float
    trend_adjustment: float
    final_score: float
    weight: float


class HealthScoreOut(BaseModel):
    total_score: int
    metrics: List[MetricScoreOut]


# ---------- 건강 캘린더 (health_calendar.py) ----------

class CalendarDayOut(BaseModel):
    date: str
    level: str  # "good" | "warn" | "bad"
    score: int


class CalendarOut(BaseModel):
    year: int
    month: int
    days: List[CalendarDayOut]


# ---------- 건강 타임라인 (health_timeline.py) ----------

class TimelineEventOut(BaseModel):
    date: str
    label: str
    kind: str


class TimelineOut(BaseModel):
    events: List[TimelineEventOut]


# ---------- 건강 배지 (badges.py) ----------

class BadgeOut(BaseModel):
    key: str
    label: str
    description: str
    icon: str
    earned: bool
    earned_at: Optional[datetime] = None


class BadgesOut(BaseModel):
    badges: List[BadgeOut]


# ---------- 확장성 확보 (integrations.py) ----------

class IntegrationStatusOut(BaseModel):
    name: str
    category: str  # "llm" | "wearable" | "import"
    status: str  # "mock" | "available"
    description: str


class IntegrationsStatusOut(BaseModel):
    integrations: List[IntegrationStatusOut]


class WearableActivityOut(BaseModel):
    date: str
    steps: Optional[int] = None
    sleep_hours: Optional[float] = None


class WearableMockOut(BaseModel):
    provider: str
    days: List[WearableActivityOut]


class ImportedRecordOut(BaseModel):
    date: str
    weight: Optional[float] = None
    height: Optional[float] = None
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    blood_sugar: Optional[int] = None
    steps: Optional[int] = None
    sleep_hours: Optional[float] = None


class CsvImportIn(BaseModel):
    csv_content: str = Field(..., max_length=200_000)


class ImportPreviewOut(BaseModel):
    count: int
    records: List[ImportedRecordOut]


class ImportRowError(BaseModel):
    row: int = Field(..., description="CSV 데이터 행 번호(헤더 제외, 1부터 시작)")
    date: str
    error: str


class ImportCommitOut(BaseModel):
    count: int
    records: List[RecordOut]
