"""건강 지표 추세(Trend) 분석 공용 모듈.

AI Health Coach(health_coach.py), 이상 징후 감지(risk_detection.py, 예정),
Health Score 가중치 보너스/감점(예정), 목표 달성 예측(예정) 등 여러 기능이
전부 "최근 값이 이전보다 올랐는지/내렸는지/그대로인지"를 판단해야 하는데,
그 판단 방식(비교 구간을 어떻게 나누고, 얼마나 변해야 "유의미한 변화"로 볼지)이
제각각이면 지표마다 기준이 달라지는 문제가 생긴다. 그래서 이 판단 로직을
이 모듈 하나로 모았다.

health_coach.py의 Feature 1/2 구현 때 있었던 개별 _avg/_split_recent_and_prior/
임계값 상수들은 이 모듈로 옮기고, health_coach.py는 이 모듈을 사용하도록
리팩터링했다 (중복 코드 제거).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Dict, List, Optional

import models


class Trend(str, Enum):
    """지표 추세. str을 상속해서 API 응답(JSON)에도 "UP"/"DOWN"/"STABLE" 문자열
    그대로 직렬화된다."""

    UP = "UP"
    DOWN = "DOWN"
    STABLE = "STABLE"


# ---------- 지표별 판단 기준 (매직 넘버 제거 목적으로 전부 상수로 분리) ----------

RECENT_WINDOW_DAYS = 7  # "최근" 구간의 길이 — 주간 리포트(reports/weekly)와 동일한 기준

# HealthRecord의 실제 컬럼명을 그대로 키로 사용한다 (getattr로 값을 꺼내기 위함).
# 값은 "이 값 이상 변해야 UP/DOWN으로 판단하고, 그 미만이면 STABLE" 기준.
METRIC_THRESHOLDS: Dict[str, float] = {
    "weight": 0.3,  # kg
    "systolic": 3.0,  # mmHg
    "diastolic": 3.0,  # mmHg
    "blood_sugar": 6.0,  # mg/dL
    "steps": 1500,  # 걸음
    "sleep_hours": 0.5,  # 시간
}

# 지표별로 "낮을수록 좋은지"를 나타낸다. TrendResult.is_improving이 이 값을 보고
# UP/DOWN을 "개선/악화"로 해석한다 (예: 체중=낮을수록 좋음, 걸음수=높을수록 좋음).
LOWER_IS_BETTER: Dict[str, bool] = {
    "weight": True,
    "systolic": True,
    "diastolic": True,
    "blood_sugar": True,
    "steps": False,
    "sleep_hours": False,
}

TRACKED_METRICS: List[str] = list(METRIC_THRESHOLDS.keys())


@dataclass(frozen=True)
class TrendResult:
    """지표 하나에 대한 추세 분석 결과."""

    metric: str
    trend: Trend
    recent_avg: Optional[float]
    prior_avg: Optional[float]
    diff: Optional[float]  # recent_avg - prior_avg (반올림됨)

    @property
    def is_improving(self) -> Optional[bool]:
        """추세가 "좋아지는 방향"인지. STABLE이거나 비교 불가능하면 None."""
        if self.trend == Trend.STABLE or self.diff is None:
            return None
        lower_is_better = LOWER_IS_BETTER.get(self.metric, True)
        went_down = self.trend == Trend.DOWN
        return went_down if lower_is_better else not went_down


def average(values: List[Optional[float]]) -> Optional[float]:
    """None을 제외한 평균. 값이 하나도 없으면 None.

    이 모듈뿐 아니라 risk_detection.py 등 다른 분석 모듈도 "구간 평균"이 필요할 때
    공통으로 재사용하는 유틸이라 공개 함수로 둔다.
    """
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def split_recent_and_prior(
    sorted_records: List[models.HealthRecord],
    today: Optional[date] = None,
    window_days: int = RECENT_WINDOW_DAYS,
):
    """날짜순으로 정렬된 기록을 '최근 N일'과 '그 직전 N일' 두 구간으로 나눈다.

    최근 구간에 기록이 하나도 없으면(예: 최근 며칠간 기록을 안 한 경우) 폴백으로
    기록 리스트를 앞/뒤 절반으로 나눠서라도 비교할 수 있게 한다.
    """
    if today is None:
        today = date.today()
    recent_start = today - timedelta(days=window_days - 1)
    prior_start = recent_start - timedelta(days=window_days)
    prior_end = recent_start - timedelta(days=1)

    recent = [r for r in sorted_records if recent_start.isoformat() <= r.date <= today.isoformat()]
    prior = [r for r in sorted_records if prior_start.isoformat() <= r.date <= prior_end.isoformat()]

    if not recent:
        half = max(1, len(sorted_records) // 2)
        prior, recent = sorted_records[:half], sorted_records[half:]

    return recent, prior


def compute_trend(
    metric: str,
    recent: List[models.HealthRecord],
    prior: List[models.HealthRecord],
) -> TrendResult:
    """지표 하나(metric)에 대해 recent/prior 구간의 평균을 비교해 추세를 계산한다.

    Args:
        metric: HealthRecord의 속성명 ("weight", "systolic", "steps" 등).
        recent / prior: split_recent_and_prior()가 반환한 두 구간.
    """
    recent_avg = average([getattr(r, metric) for r in recent])
    prior_avg = average([getattr(r, metric) for r in prior])

    if recent_avg is None or prior_avg is None:
        return TrendResult(metric=metric, trend=Trend.STABLE, recent_avg=recent_avg, prior_avg=prior_avg, diff=None)

    diff = round(recent_avg - prior_avg, 2)
    threshold = METRIC_THRESHOLDS.get(metric, 0.0)
    if abs(diff) < threshold:
        trend = Trend.STABLE
    elif diff > 0:
        trend = Trend.UP
    else:
        trend = Trend.DOWN

    return TrendResult(metric=metric, trend=trend, recent_avg=round(recent_avg, 2), prior_avg=round(prior_avg, 2), diff=diff)


def classify_diff(metric: str, diff: Optional[float]) -> Trend:
    """이미 계산되어 있는 평균 차이(diff) 하나만으로 지표 임계값 기준 UP/DOWN/STABLE을 판단한다.

    compute_trend()은 recent/prior 레코드 리스트가 있어야 하지만, 호출부에 따라
    (예: main.py의 weekly_report()) 이미 두 구간의 평균 차이를 계산해둔 경우가 있다.
    이때도 같은 임계값 기준(METRIC_THRESHOLDS)을 재사용하도록 diff만 받는 버전을 둔다.
    """
    if diff is None:
        return Trend.STABLE
    threshold = METRIC_THRESHOLDS.get(metric, 0.0)
    if abs(diff) < threshold:
        return Trend.STABLE
    return Trend.UP if diff > 0 else Trend.DOWN


def analyze_trends(
    records: List[models.HealthRecord],
    today: Optional[date] = None,
    metrics: Optional[List[str]] = None,
) -> Dict[str, TrendResult]:
    """기록 리스트를 받아 지표별 TrendResult를 담은 dict를 반환한다.

    Args:
        records: 사용자의 건강기록 (정렬 여부 무관, 내부에서 날짜순 정렬함).
        today: 테스트 등에서 "오늘"을 고정하고 싶을 때만 지정.
        metrics: 분석할 지표 목록 (기본값: TRACKED_METRICS 전체).

    Returns:
        {"weight": TrendResult(...), "systolic": TrendResult(...), ...}
    """
    target_metrics = metrics if metrics is not None else TRACKED_METRICS
    if not records:
        return {m: TrendResult(m, Trend.STABLE, None, None, None) for m in target_metrics}

    sorted_records = sorted(records, key=lambda r: r.date)
    recent, prior = split_recent_and_prior(sorted_records, today=today)
    return {m: compute_trend(m, recent, prior) for m in target_metrics}
