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
    role: str

    class Config:
        from_attributes = True


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
    role: str
    created_at: Optional[datetime] = None
    record_count: int

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
