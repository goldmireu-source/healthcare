"""건강 배지(Badge) — 자동 획득 조건 평가.

사용자가 특정 조건(연속 기록일수, 첫 정상 지표 도달, 첫 목표 달성)을 만족하면
자동으로 배지를 지급한다. 이 모듈은 순수 판정 로직만 담당하고, 실제 DB 저장은
main.py의 GET /badges에서 처리한다(배경 작업 스케줄러가 없는 프로젝트라 "조회
시점에 평가하고, 새로 만족한 조건이 있으면 그때 저장"하는 지연 평가 방식을 쓴다).
"""

from dataclasses import dataclass
from datetime import date as date_cls, datetime
from typing import List, Optional, Set

import models

STREAK_7_DAYS = 7
STREAK_30_DAYS = 30


@dataclass(frozen=True)
class BadgeDefinition:
    key: str
    label: str
    description: str
    icon: str  # 프론트에서 아이콘을 고를 때 참고하는 카테고리명 (streak/goal/bmi/bp)


# 순서 = 프론트에 보여줄 기본 순서
BADGE_DEFINITIONS: List[BadgeDefinition] = [
    BadgeDefinition("streak_7", "7일 연속 기록", "7일 연속으로 건강 기록을 남겼어요.", "streak"),
    BadgeDefinition("streak_30", "30일 연속 기록", "30일 연속으로 건강 기록을 남겼어요.", "streak"),
    BadgeDefinition("first_normal_bmi", "첫 정상 BMI", "BMI가 처음으로 정상 범위에 들어왔어요.", "bmi"),
    BadgeDefinition("first_normal_bp", "첫 정상 혈압", "혈압이 처음으로 정상 범위에 들어왔어요.", "bp"),
    BadgeDefinition("first_goal_achieved", "첫 목표 달성", "설정한 목표 중 하나를 처음으로 달성했어요.", "goal"),
]

_BADGE_BY_KEY = {b.key: b for b in BADGE_DEFINITIONS}


def badge_definition(key: str) -> Optional[BadgeDefinition]:
    return _BADGE_BY_KEY.get(key)


def _longest_consecutive_day_streak(dates: List[date_cls]) -> int:
    """날짜 리스트에서 가장 긴 연속 일수를 구한다 (중복은 하나로 취급)."""
    if not dates:
        return 0
    unique_sorted = sorted(set(dates))
    longest = 1
    current = 1
    for i in range(1, len(unique_sorted)):
        if (unique_sorted[i] - unique_sorted[i - 1]).days == 1:
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def evaluate_new_badges(
    records: List[models.HealthRecord],
    goal: Optional[models.Goal],
    already_earned: Set[str],
) -> List[str]:
    """아직 획득하지 않은 배지 중, 지금 조건을 만족하는 배지 키 목록을 반환한다.

    Args:
        records: 사용자의 전체 건강기록.
        goal: 사용자가 설정한 목표 (없으면 목표 관련 배지는 평가하지 않음).
        already_earned: 이미 DB에 저장된 badge_key 집합 (중복 지급 방지).
    """
    newly_earned: List[str] = []
    if not records:
        return newly_earned

    sorted_records = sorted(records, key=lambda r: r.date)
    record_dates = [datetime.strptime(r.date, "%Y-%m-%d").date() for r in sorted_records]
    longest_streak = _longest_consecutive_day_streak(record_dates)

    if "streak_7" not in already_earned and longest_streak >= STREAK_7_DAYS:
        newly_earned.append("streak_7")
    if "streak_30" not in already_earned and longest_streak >= STREAK_30_DAYS:
        newly_earned.append("streak_30")

    if "first_normal_bmi" not in already_earned and any(r.bmi_category == "정상" for r in sorted_records):
        newly_earned.append("first_normal_bmi")
    if "first_normal_bp" not in already_earned and any(r.bp_category == "정상" for r in sorted_records):
        newly_earned.append("first_normal_bp")

    if "first_goal_achieved" not in already_earned and goal is not None:
        targets = [
            (goal.target_weight, lambda r: r.weight),
            (goal.target_systolic, lambda r: r.systolic),
            (goal.target_diastolic, lambda r: r.diastolic),
            (goal.target_blood_sugar, lambda r: r.blood_sugar),
        ]
        achieved_any = any(
            target is not None and any(getter(r) <= target for r in sorted_records)
            for target, getter in targets
        )
        if achieved_any:
            newly_earned.append("first_goal_achieved")

    return newly_earned
