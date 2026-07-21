from datetime import datetime
from typing import Optional, List, Dict

from pydantic import BaseModel, Field


# ---------- Auth ----------

class UserSignup(BaseModel):
    username: str = Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=6, max_length=100)


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        from_attributes = True


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


class AdminStatsOut(BaseModel):
    total_users: int
    total_records: int
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
    weight: float = Field(..., gt=0, description="몸무게(kg)")
    height: float = Field(..., gt=0, description="키(cm)")
    systolic: int = Field(..., gt=0, description="수축기 혈압")
    diastolic: int = Field(..., gt=0, description="이완기 혈압")
    blood_sugar: int = Field(..., gt=0, description="공복 혈당(mg/dL)")
    steps: int = Field(0, ge=0, description="걸음 수")
    sleep_hours: float = Field(0.0, ge=0, description="수면 시간")
    memo: str = ""


class RecordUpdate(BaseModel):
    date: Optional[str] = None
    weight: Optional[float] = Field(None, gt=0)
    height: Optional[float] = Field(None, gt=0)
    systolic: Optional[int] = Field(None, gt=0)
    diastolic: Optional[int] = Field(None, gt=0)
    blood_sugar: Optional[int] = Field(None, gt=0)
    steps: Optional[int] = Field(None, ge=0)
    sleep_hours: Optional[float] = Field(None, ge=0)
    memo: Optional[str] = None


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
    target_weight: Optional[float] = Field(None, gt=0)
    target_systolic: Optional[int] = Field(None, gt=0)
    target_diastolic: Optional[int] = Field(None, gt=0)
    target_blood_sugar: Optional[int] = Field(None, gt=0)


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
