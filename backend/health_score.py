"""건강 스코어(Health Score) 계산.

이전에는 프론트엔드(JS, index.html의 computeHealthScore)에서 5개 지표(BMI/혈압/
혈당/활동량/수면) 상태에 균등한 페널티를 매겨 점수를 계산했다. 이번 개선에서는

1. 지표별 가중치를 다르게 적용 (체중 20% / 혈압 25% / 혈당 25% / 운동 15% / 수면 15%)
2. 최근 추세(health_trends.py)가 좋아지고 있으면 보너스, 나빠지고 있으면 감점

을 반영한다. 계산을 서버(단일 소스)로 옮겨서 프론트/관리자 등 어디서 조회하든
같은 점수가 나오게 하고, 프론트의 computeHealthScore는 이 API 결과로 대체한다.
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

import models
from health_trends import TrendResult, analyze_trends

# ---------- 지표별 가중치 (합 1.0 = 100%) ----------
WEIGHT_WEIGHT = 0.20  # 체중(BMI) 20%
WEIGHT_BP = 0.25  # 혈압 25%
WEIGHT_SUGAR = 0.25  # 혈당 25%
WEIGHT_ACTIVITY = 0.15  # 운동(걸음 수) 15%
WEIGHT_SLEEP = 0.15  # 수면 15%

# ---------- 분류 문자열 → 기본 점수 (100점 만점 기준) ----------
# health_logic.py가 만드는 실제 분류값들을 세 등급으로 묶는다. main.py의 관리자
# 위험도(_risk_level)도 개념적으로 같은 3등급 구분을 쓰지만, 그쪽은 이미 배포되어
# 동작 중인 코드라 이번 기능 때문에 건드리지 않는다(불필요한 회귀 위험 방지).
GOOD_CATEGORIES = {"정상", "적정", "우수"}
WARN_CATEGORIES = {"주의", "과체중", "공복혈당장애", "부족", "과다", "저체중"}
BAD_CATEGORIES = {"고혈압", "비만", "당뇨 의심"}

SCORE_GOOD = 100.0
SCORE_WARN = 60.0
SCORE_BAD = 20.0
SCORE_NEUTRAL = 50.0  # 분류값이 위 세 그룹 어디에도 없을 때(예: 미기록)의 안전한 기본값

# ---------- 추세 보너스/감점 ----------
TREND_BONUS = 5.0  # 지표가 개선 추세면 해당 지표 점수에 더하는 보너스
TREND_PENALTY = 5.0  # 지표가 악화 추세면 해당 지표 점수에서 빼는 감점

# health_score의 지표 키 → health_trends.analyze_trends()가 쓰는 지표 키 매핑.
# ("체중"의 추세는 latest.bmi_category가 아니라 실제 체중(weight) 변화로 판단한다.)
_METRIC_TO_TREND_KEY = {
    "weight": "weight",
    "bp": "systolic",
    "sugar": "blood_sugar",
    "activity": "steps",
    "sleep": "sleep_hours",
}


@dataclass(frozen=True)
class MetricScore:
    """지표 하나의 점수 산정 내역 (설명 가능성을 위해 세부 내역까지 보존)."""

    metric: str  # "weight" | "bp" | "sugar" | "activity" | "sleep"
    category: Optional[str]
    base_score: float
    trend_adjustment: float
    final_score: float  # base_score + trend_adjustment (0~100으로 clamp됨)
    weight: float


@dataclass(frozen=True)
class HealthScoreResult:
    total_score: int  # 0~100, 반올림된 최종 점수
    metrics: List[MetricScore]


def _category_score(category: Optional[str]) -> float:
    if category in GOOD_CATEGORIES:
        return SCORE_GOOD
    if category in WARN_CATEGORIES:
        return SCORE_WARN
    if category in BAD_CATEGORIES:
        return SCORE_BAD
    return SCORE_NEUTRAL


def _trend_adjustment(metric: str, trends: Dict[str, TrendResult]) -> float:
    """해당 지표의 추세가 개선/악화 방향이면 보너스/감점을, 유지면 0을 반환한다."""
    trend_key = _METRIC_TO_TREND_KEY.get(metric)
    trend_result = trends.get(trend_key) if trend_key else None
    if trend_result is None:
        return 0.0
    improving = trend_result.is_improving
    if improving is True:
        return TREND_BONUS
    if improving is False:
        return -TREND_PENALTY
    return 0.0


def compute_health_score(
    latest: models.HealthRecord,
    records: Optional[List[models.HealthRecord]] = None,
    today: Optional[date] = None,
) -> HealthScoreResult:
    """가장 최근 기록의 분류값 + 최근 추세를 반영해 가중치 기반 건강 스코어를 계산한다.

    Args:
        latest: 가장 최근 건강기록 (bmi_category/bp_category/sugar_category/
            activity_level/sleep_status가 채워진 상태여야 함).
        records: 추세(개선/악화) 판단에 쓸 전체 기록. None이거나 비어 있으면
            추세 보너스/감점 없이(0으로) 계산한다.
        today: 테스트에서 "오늘"을 고정하고 싶을 때만 지정.

    Returns:
        HealthScoreResult(total_score=0~100, metrics=[지표별 세부 내역 5개]).
    """
    trends = analyze_trends(records, today=today) if records else {}

    metric_defs = [
        ("weight", latest.bmi_category, WEIGHT_WEIGHT),
        ("bp", latest.bp_category, WEIGHT_BP),
        ("sugar", latest.sugar_category, WEIGHT_SUGAR),
        ("activity", latest.activity_level, WEIGHT_ACTIVITY),
        ("sleep", latest.sleep_status, WEIGHT_SLEEP),
    ]

    metric_scores: List[MetricScore] = []
    weighted_total = 0.0
    for metric, category, weight in metric_defs:
        base = _category_score(category)
        adjustment = _trend_adjustment(metric, trends)
        final = max(0.0, min(100.0, base + adjustment))
        metric_scores.append(
            MetricScore(
                metric=metric, category=category, base_score=base,
                trend_adjustment=adjustment, final_score=final, weight=weight,
            )
        )
        weighted_total += final * weight

    return HealthScoreResult(total_score=round(weighted_total), metrics=metric_scores)
