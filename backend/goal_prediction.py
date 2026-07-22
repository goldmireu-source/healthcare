"""목표 달성 예측 (Goal Achievement Prediction).

health_trends.py가 계산하는 "최근 7일 평균 - 이전 7일 평균" 변화량을 하루 단위
변화율로 환산해, 지금의 속도가 그대로 유지된다면 목표까지 며칠이 더 필요한지
추정한다. 요구사항에 따라 선형 회귀(linear regression)가 아니라 단순 평균
변화량(average rate of change) 기반으로 계산한다.

이 프로젝트의 목표 달성 판정(main.py의 _goal_to_out)은 모든 지표(체중/수축기/
이완기/혈당)를 "현재 값이 목표(상한) 이하이면 달성"으로 취급한다. 이 모듈도
동일한 규칙을 따른다 — 목표를 "낮출수록 좋은 상한선"으로 일관되게 취급.
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

import models
from health_trends import RECENT_WINDOW_DAYS, TrendResult, analyze_trends

_PREDICTION_METRICS = ["weight", "systolic", "diastolic", "blood_sugar"]


@dataclass(frozen=True)
class GoalPrediction:
    """지표 하나에 대한 목표 달성 예측 결과."""

    metric: str
    current_avg: Optional[float]
    target: float
    daily_rate: Optional[float]  # 하루 평균 변화량 (음수=감소 중, 양수=증가 중)
    estimated_days: Optional[int]  # None=예측 불가, 0=이미 달성, 그 외=예상 소요일
    message: str


def _predict_metric(metric: str, target: Optional[float], trend: Optional[TrendResult]) -> Optional[GoalPrediction]:
    if target is None:
        return None
    if trend is None or trend.recent_avg is None:
        return GoalPrediction(
            metric=metric, current_avg=None, target=target, daily_rate=None,
            estimated_days=None, message="예측에 필요한 기록이 부족합니다.",
        )

    current = trend.recent_avg
    remaining = round(current - target, 2)  # 양수면 아직 목표(상한)보다 높음

    if remaining <= 0:
        return GoalPrediction(
            metric=metric, current_avg=current, target=target, daily_rate=0.0,
            estimated_days=0, message="이미 목표를 달성했습니다.",
        )

    daily_rate = (trend.diff / RECENT_WINDOW_DAYS) if trend.diff is not None else 0.0
    if daily_rate >= 0:
        # 줄어들고 있지 않으면(그대로거나 오히려 늘고 있으면) 남은 일수를 계산할 수 없음
        return GoalPrediction(
            metric=metric, current_avg=current, target=target, daily_rate=daily_rate,
            estimated_days=None, message="현재 추세로는 목표 달성 시점을 예측하기 어렵습니다.",
        )

    estimated_days = max(1, round(remaining / abs(daily_rate)))
    return GoalPrediction(
        metric=metric, current_avg=current, target=target, daily_rate=daily_rate,
        estimated_days=estimated_days, message=f"현재 속도라면 목표까지 약 {estimated_days}일 예상됩니다.",
    )


def predict_goal_achievement(
    records: List[models.HealthRecord],
    goal: models.Goal,
    today: Optional[date] = None,
) -> Dict[str, GoalPrediction]:
    """목표(goal)에 설정된 지표별로 예상 달성 소요일을 계산한다.

    Args:
        records: 사용자의 전체 건강기록 (추세 계산용).
        goal: 사용자가 설정한 목표.
        today: 테스트에서 "오늘"을 고정하고 싶을 때만 지정.

    Returns:
        목표가 설정된 지표만 담은 dict. 예: {"weight": GoalPrediction(...), ...}.
    """
    trends = analyze_trends(records, today=today, metrics=_PREDICTION_METRICS) if records else {}

    targets = {
        "weight": goal.target_weight,
        "systolic": goal.target_systolic,
        "diastolic": goal.target_diastolic,
        "blood_sugar": goal.target_blood_sugar,
    }

    predictions: Dict[str, GoalPrediction] = {}
    for metric in _PREDICTION_METRICS:
        pred = _predict_metric(metric, targets[metric], trends.get(metric))
        if pred is not None:
            predictions[metric] = pred
    return predictions
