"""건강 타임라인 (이벤트 기반 뷰).

기록을 단순 나열하는 대신, "지표 분류가 더 좋은 방향으로 바뀐 시점"과 "목표를
처음 달성한 시점"만 뽑아 이벤트로 보여준다. (예: "BMI 정상 진입", "목표 체중 달성")

분류를 3단계로 묶는 기준은 health_score.py의 GOOD/WARN/BAD_CATEGORIES를 그대로
재사용한다 (여러 모듈이 각자 다른 기준으로 "정상/주의/위험"을 나누지 않도록).
"""

from dataclasses import dataclass
from typing import List, Optional

import models
from health_score import BAD_CATEGORIES, GOOD_CATEGORIES, WARN_CATEGORIES

_TIER_ORDER = {"bad": 0, "warn": 1, "good": 2}  # 숫자가 클수록 좋은 상태
_METRIC_LABELS = {"bmi": "BMI", "bp": "혈압", "sugar": "혈당"}


def _tier(category: Optional[str]) -> str:
    if category in GOOD_CATEGORIES:
        return "good"
    if category in WARN_CATEGORIES:
        return "warn"
    if category in BAD_CATEGORIES:
        return "bad"
    return "warn"  # 알 수 없는 분류값은 중립적으로 취급 (good으로 오인해 이벤트가 남발되지 않도록)


@dataclass(frozen=True)
class TimelineEvent:
    date: str
    label: str
    kind: str  # "bmi" | "bp" | "sugar" | "goal_weight" | "goal_systolic" | "goal_diastolic" | "goal_blood_sugar"


def _category_transition_events(sorted_records: List[models.HealthRecord]) -> List[TimelineEvent]:
    """분류가 "이전 기록보다 좋아진 방향"으로 바뀐 날짜마다 이벤트를 하나씩 만든다."""
    events: List[TimelineEvent] = []
    metric_fields = [("bmi", "bmi_category"), ("bp", "bp_category"), ("sugar", "sugar_category")]

    for metric_key, field in metric_fields:
        prev_tier = None
        prev_category = None
        for r in sorted_records:
            category = getattr(r, field)
            tier = _tier(category)
            if prev_tier is not None and _TIER_ORDER[tier] > _TIER_ORDER[prev_tier] and category != prev_category:
                events.append(TimelineEvent(date=r.date, label=f"{_METRIC_LABELS[metric_key]} {category} 진입", kind=metric_key))
            prev_tier = tier
            prev_category = category
    return events


def _goal_achievement_events(sorted_records: List[models.HealthRecord], goal: Optional[models.Goal]) -> List[TimelineEvent]:
    """목표를 "처음" 달성한 날짜에만 이벤트를 만든다 (계속 달성 상태여도 반복 생성 안 함)."""
    if goal is None:
        return []

    events: List[TimelineEvent] = []
    targets = [
        ("goal_weight", goal.target_weight, lambda r: r.weight, "체중"),
        ("goal_systolic", goal.target_systolic, lambda r: r.systolic, "수축기 혈압"),
        ("goal_diastolic", goal.target_diastolic, lambda r: r.diastolic, "이완기 혈압"),
        ("goal_blood_sugar", goal.target_blood_sugar, lambda r: r.blood_sugar, "혈당"),
    ]
    for kind, target, getter, label_name in targets:
        if target is None:
            continue
        was_achieved = False
        for r in sorted_records:
            achieved_now = getter(r) <= target
            if achieved_now and not was_achieved:
                events.append(TimelineEvent(date=r.date, label=f"목표 {label_name} 달성", kind=kind))
            was_achieved = achieved_now
    return events


def build_timeline(
    records: List[models.HealthRecord],
    goal: Optional[models.Goal] = None,
) -> List[TimelineEvent]:
    """건강기록에서 "의미 있는 변화 시점"만 뽑아 최신순으로 정렬해 반환한다."""
    sorted_records = sorted(records, key=lambda r: r.date)
    events = _category_transition_events(sorted_records) + _goal_achievement_events(sorted_records, goal)
    events.sort(key=lambda e: e.date, reverse=True)
    return events
