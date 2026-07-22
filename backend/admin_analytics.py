"""관리자 Analytics 확장 — 신규 KPI 계산.

기존 /admin/stats가 이미 총 사용자 수/총 기록 수/역할 분포/가입 추이/카테고리
분포를 제공한다. 여기서는 그 위에 참여도(활동률/유지율/가입 전환율), 평균 지표,
위험 사용자 증가율을 추가로 계산한다.

관리자 페이지의 기존 사용자별 risk_level(main.py의 _risk_level, "high/moderate/
normal/unknown")은 건드리지 않고, 이 모듈은 health_score.py의 카테고리 분류
기준(BAD_CATEGORIES)만 재사용해 "고위험 사용자 수"를 독립적으로 집계한다
(main.py를 이 모듈이 임포트하면 순환 참조가 생기므로 로직을 공유하지 않음).
"""

from dataclasses import dataclass
from datetime import date as date_cls, timedelta
from typing import Dict, List, Optional

import models
from health_score import BAD_CATEGORIES

ACTIVITY_WINDOW_DAYS = 7  # "최근 활동" 판정 기준 일수
SIGNUP_CONVERSION_WINDOW_DAYS = 30  # "최근 가입" 판정 기준 일수
RISK_GROWTH_WINDOW_DAYS = 7  # 위험 사용자 증가율 비교 기준 일수


def _average(values: List[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _is_high_risk(records_for_user: List[models.HealthRecord], cutoff: date_cls) -> bool:
    """cutoff 이전(포함) 기록 중 가장 최근 것을 기준으로 고위험 여부를 판정한다."""
    candidates = [r for r in records_for_user if r.date <= cutoff.isoformat()]
    if not candidates:
        return False
    latest = max(candidates, key=lambda r: r.date)
    cats = {latest.bmi_category, latest.bp_category, latest.sugar_category}
    return bool(cats & BAD_CATEGORIES)


@dataclass(frozen=True)
class AdminAnalytics:
    recent_activity_rate: float  # 최근 N일 내 기록을 남긴 사용자 비율 (%)
    retention_rate: float  # 기록을 1건이라도 남긴 사용자 비율 (%)
    avg_bmi: Optional[float]
    avg_systolic: Optional[float]
    avg_diastolic: Optional[float]
    avg_blood_sugar: Optional[float]
    high_risk_growth_rate: Optional[float]  # 최근 대비 고위험 사용자 증가율(%). 비교 기준이 0명이면 None
    signup_to_record_rate: float  # 최근 가입자 중 기록을 남긴 비율 (%)


def compute_admin_analytics(
    users: List[models.User],
    records: List[models.HealthRecord],
    today: Optional[date_cls] = None,
) -> AdminAnalytics:
    if today is None:
        today = date_cls.today()

    total_users = len(users)
    records_by_user: Dict[int, List[models.HealthRecord]] = {}
    for r in records:
        records_by_user.setdefault(r.user_id, []).append(r)

    activity_cutoff = (today - timedelta(days=ACTIVITY_WINDOW_DAYS - 1)).isoformat()
    active_recently = sum(
        1 for u in users if any(r.date >= activity_cutoff for r in records_by_user.get(u.id, []))
    )
    recent_activity_rate = round(active_recently / total_users * 100, 1) if total_users else 0.0

    has_any_record = sum(1 for u in users if records_by_user.get(u.id))
    retention_rate = round(has_any_record / total_users * 100, 1) if total_users else 0.0

    avg_bmi = _average([r.bmi for r in records])
    avg_systolic = _average([r.systolic for r in records])
    avg_diastolic = _average([r.diastolic for r in records])
    avg_blood_sugar = _average([r.blood_sugar for r in records])

    growth_cutoff = today - timedelta(days=RISK_GROWTH_WINDOW_DAYS)
    current_high_risk = sum(1 for u in users if _is_high_risk(records_by_user.get(u.id, []), today))
    previous_high_risk = sum(1 for u in users if _is_high_risk(records_by_user.get(u.id, []), growth_cutoff))
    high_risk_growth_rate = (
        round((current_high_risk - previous_high_risk) / previous_high_risk * 100, 1)
        if previous_high_risk > 0 else None
    )

    signup_cutoff = today - timedelta(days=SIGNUP_CONVERSION_WINDOW_DAYS)
    recent_signups = [u for u in users if u.created_at and u.created_at.date() >= signup_cutoff]
    if recent_signups:
        wrote_record = sum(1 for u in recent_signups if records_by_user.get(u.id))
        signup_to_record_rate = round(wrote_record / len(recent_signups) * 100, 1)
    else:
        signup_to_record_rate = 0.0

    return AdminAnalytics(
        recent_activity_rate=recent_activity_rate,
        retention_rate=retention_rate,
        avg_bmi=avg_bmi,
        avg_systolic=avg_systolic,
        avg_diastolic=avg_diastolic,
        avg_blood_sugar=avg_blood_sugar,
        high_risk_growth_rate=high_risk_growth_rate,
        signup_to_record_rate=signup_to_record_rate,
    )
