"""이상 징후 감지 (Risk Detection).

health_trends.py가 "지표가 오르는지/내리는지/유지되는지"를 판단하는 모듈이라면,
이 모듈은 한 단계 더 나아가 "그 변화가 위험할 만큼 급격한지"를 판단한다.

예를 들어 체중이 최근 0.4kg 줄어드는 것은 health_trends 기준으로는 DOWN(추세)
이지만, 이 모듈 기준으로는 "위험 신호(anomaly)"가 아니다. 반면 체중이 일주일
새 2kg 넘게 늘면 health_trends로도 UP이고, 이 모듈에서도 "체중 급증"으로 잡혀
전체 위험도(RiskLevel)에 반영된다.

주의: 관리자 페이지(main.py의 admin_list_users, `_risk_level` 함수)가 쓰는
"high/moderate/normal/unknown" 위험도는 "가장 최근 기록 1건의 분류(정상/주의/위험
카테고리)"를 보는 것으로, 이 모듈의 RiskLevel(LOW/MEDIUM/HIGH)과는 판단 기준이
다른 별개의 개념이다. 이 모듈은 "최근 며칠간의 변화량"을 본다. 두 값을 섞어
쓰지 않도록 주의할 것.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import List, Optional

import models
from health_trends import average, split_recent_and_prior

MIN_RECORDS_FOR_DETECTION = 2  # 이 미만이면 비교 자체가 불가능하므로 위험 없음(LOW)으로 처리


class RiskLevel(str, Enum):
    """전체 위험도. str을 상속해 API 응답에도 문자열 그대로 직렬화된다."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# 위험도 우선순위 (여러 이상 징후가 동시에 감지되면 가장 심각한 것을 전체 위험도로 채택)
_RISK_LEVEL_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}

# ---------- 이상 징후 판단 기준값 (매직 넘버 제거 목적으로 전부 상수로 분리) ----------
# health_trends.METRIC_THRESHOLDS보다 훨씬 큰 값이다 — "추세" 정도가 아니라
# "위험 신호"로 부를 만큼 급격한 변화만 여기 걸리도록 의도적으로 크게 잡았다.

WEIGHT_SPIKE_KG = 2.0  # 최근 평균 체중이 이전 대비 이 값(kg) 이상 늘면 "체중 급증"
SYSTOLIC_SPIKE_MMHG = 15.0  # 최근 평균 수축기 혈압이 이전 대비 이 값(mmHg) 이상 오르면 "혈압 급상승"
SUGAR_SPIKE_MGDL = 20.0  # 최근 평균 공복혈당이 이전 대비 이 값(mg/dL) 이상 오르면 "혈당 급상승"
SLEEP_DROP_HOURS = 2.0  # 최근 평균 수면시간이 이전 대비 이 값(시간) 이상 줄면 "수면 급감"
STEPS_DROP = 3000  # 최근 평균 걸음 수가 이전 대비 이 값 이상 줄면 "운동량 급감"


@dataclass(frozen=True)
class Anomaly:
    """감지된 이상 징후 하나."""

    metric: str
    label: str  # 사람이 읽는 짧은 이름 ("체중 급증" 등)
    severity: RiskLevel
    detail: str  # 근거 설명 ("최근 평균 체중이 이전 대비 2.4kg 늘었습니다." 등)


@dataclass(frozen=True)
class RiskDetectionResult:
    """이상 징후 감지 결과 전체."""

    risk_level: RiskLevel
    anomalies: List[Anomaly]


# ---------- 개별 이상 징후 판정 (한 함수 = 한 지표) ----------

def _detect_blood_pressure_spike(recent, prior) -> Optional[Anomaly]:
    recent_avg = average([r.systolic for r in recent])
    prior_avg = average([r.systolic for r in prior])
    if recent_avg is None or prior_avg is None:
        return None
    diff = round(recent_avg - prior_avg, 2)
    if diff >= SYSTOLIC_SPIKE_MMHG:
        return Anomaly(
            metric="systolic",
            label="혈압 급상승",
            severity=RiskLevel.HIGH,
            detail=f"최근 평균 수축기 혈압이 이전보다 {diff}mmHg 올랐습니다 (이전 {prior_avg:.1f} → 최근 {recent_avg:.1f}).",
        )
    return None


def _detect_blood_sugar_spike(recent, prior) -> Optional[Anomaly]:
    recent_avg = average([r.blood_sugar for r in recent])
    prior_avg = average([r.blood_sugar for r in prior])
    if recent_avg is None or prior_avg is None:
        return None
    diff = round(recent_avg - prior_avg, 2)
    if diff >= SUGAR_SPIKE_MGDL:
        return Anomaly(
            metric="blood_sugar",
            label="혈당 급상승",
            severity=RiskLevel.HIGH,
            detail=f"최근 평균 공복혈당이 이전보다 {diff}mg/dL 올랐습니다 (이전 {prior_avg:.1f} → 최근 {recent_avg:.1f}).",
        )
    return None


def _detect_weight_spike(recent, prior) -> Optional[Anomaly]:
    recent_avg = average([r.weight for r in recent])
    prior_avg = average([r.weight for r in prior])
    if recent_avg is None or prior_avg is None:
        return None
    diff = round(recent_avg - prior_avg, 2)
    if diff >= WEIGHT_SPIKE_KG:
        return Anomaly(
            metric="weight",
            label="체중 급증",
            severity=RiskLevel.MEDIUM,
            detail=f"최근 평균 체중이 이전보다 {diff}kg 늘었습니다 (이전 {prior_avg:.1f}kg → 최근 {recent_avg:.1f}kg).",
        )
    return None


def _detect_sleep_drop(recent, prior) -> Optional[Anomaly]:
    recent_avg = average([r.sleep_hours for r in recent])
    prior_avg = average([r.sleep_hours for r in prior])
    if recent_avg is None or prior_avg is None:
        return None
    diff = round(recent_avg - prior_avg, 2)
    if diff <= -SLEEP_DROP_HOURS:
        return Anomaly(
            metric="sleep_hours",
            label="수면 급감",
            severity=RiskLevel.MEDIUM,
            detail=f"최근 평균 수면시간이 이전보다 {abs(diff)}시간 줄었습니다 (이전 {prior_avg:.1f}h → 최근 {recent_avg:.1f}h).",
        )
    return None


def _detect_activity_drop(recent, prior) -> Optional[Anomaly]:
    recent_avg = average([r.steps for r in recent])
    prior_avg = average([r.steps for r in prior])
    if recent_avg is None or prior_avg is None:
        return None
    diff = round(recent_avg - prior_avg, 2)
    if diff <= -STEPS_DROP:
        return Anomaly(
            metric="steps",
            label="운동량 급감",
            severity=RiskLevel.LOW,
            detail=f"최근 평균 걸음 수가 이전보다 {abs(int(diff))}보 줄었습니다 (이전 {prior_avg:.0f}보 → 최근 {recent_avg:.0f}보).",
        )
    return None


def detect_risks(
    records: List[models.HealthRecord],
    today: Optional[date] = None,
) -> RiskDetectionResult:
    """건강기록에서 이상 징후를 감지하고 전체 위험도를 계산한다.

    Args:
        records: 사용자의 건강기록 (정렬 여부 무관, 내부에서 날짜순 정렬함).
        today: 테스트 등에서 "오늘"을 고정하고 싶을 때만 지정.

    Returns:
        RiskDetectionResult(risk_level=..., anomalies=[...]).
        감지된 이상 징후가 없으면 risk_level=LOW, anomalies=[].
    """
    if len(records) < MIN_RECORDS_FOR_DETECTION:
        return RiskDetectionResult(risk_level=RiskLevel.LOW, anomalies=[])

    sorted_records = sorted(records, key=lambda r: r.date)
    recent, prior = split_recent_and_prior(sorted_records, today=today)

    # 규칙은 각각 독립적으로 판단하고, 해당 사항이 없으면 조용히 None을 반환한다
    # (한 규칙의 조건 미충족이 다른 규칙 실행에 영향을 주지 않음).
    candidates = [
        _detect_blood_pressure_spike(recent, prior),
        _detect_blood_sugar_spike(recent, prior),
        _detect_weight_spike(recent, prior),
        _detect_sleep_drop(recent, prior),
        _detect_activity_drop(recent, prior),
    ]
    anomalies = [a for a in candidates if a]

    if not anomalies:
        risk_level = RiskLevel.LOW
    else:
        risk_level = max(anomalies, key=lambda a: _RISK_LEVEL_ORDER[a.severity]).severity

    return RiskDetectionResult(risk_level=risk_level, anomalies=anomalies)
