from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class User(Base):
    """사용자 구분용 테이블. username 미지정 시 'default' 사용자로 자동 생성."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    records = relationship(
        "HealthRecord", back_populates="user", cascade="all, delete-orphan"
    )
    goals = relationship(
        "Goal", back_populates="user", cascade="all, delete-orphan"
    )


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
