from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class User(Base):
    """사용자 계정. 회원가입 시 비밀번호는 해시로만 저장."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    password_salt = Column(String(64), nullable=False)
    role = Column(String(10), nullable=False, default="user")  # "user" | "admin"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    records = relationship(
        "HealthRecord", back_populates="user", cascade="all, delete-orphan"
    )
    goals = relationship(
        "Goal", back_populates="user", cascade="all, delete-orphan"
    )
    sessions = relationship(
        "Session", back_populates="user", cascade="all, delete-orphan"
    )


class Session(Base):
    """로그인 세션. 쿠키에는 이 테이블의 token만 저장하고, 실제 정보는 서버에 보관."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    user = relationship("User", back_populates="sessions")


class AuditLog(Base):
    """관리자 조치 이력 (계정 삭제/강제 로그아웃 등). 대상 계정이 삭제돼도 이력은 남아야
    하므로 외래키 대신 username을 문자열로 저장한다."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_username = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)  # "delete_user" | "force_logout"
    target_username = Column(String(50), nullable=True)
    detail = Column(String(500), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class HealthRecord(Base):
    """건강 기록 + 서버가 계산한 분류/경고 결과를 함께 저장."""

    __tablename__ = "health_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    date = Column(String(10), nullable=False, index=True)  # "YYYY-MM-DD"
    weight = Column(Float, nullable=False)
    height = Column(Float, nullable=False)
    systolic = Column(Integer, nullable=False)
    diastolic = Column(Integer, nullable=False)
    blood_sugar = Column(Integer, nullable=False)
    steps = Column(Integer, default=0)
    sleep_hours = Column(Float, default=0.0)
    memo = Column(String(500), default="")

    # 서버 계산 결과
    bmi = Column(Float)
    bmi_category = Column(String(20))
    bp_category = Column(String(20))
    sugar_category = Column(String(20))
    warnings = Column(Text)  # JSON 문자열로 저장된 경고 리스트
    activity_level = Column(String(20))  # 걸음 수 등급 (고도화)
    sleep_status = Column(String(20))  # 수면 분석 (고도화)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="records")


class Goal(Base):
    """사용자별 목표 체중/혈압/혈당 (고도화: 목표 관리)."""

    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    target_weight = Column(Float, nullable=True)
    target_systolic = Column(Integer, nullable=True)
    target_diastolic = Column(Integer, nullable=True)
    target_blood_sugar = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="goals")
