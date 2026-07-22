"""AI Health Coach - 규칙 기반(rule-based) 건강 코칭 메시지 생성.

지금 당장은 이 모듈이 LLM을 호출하지 않고, health_trends.py가 계산한 지표별
추세(Trend)를 문장으로 옮기는 규칙만으로 코칭 문장을 만든다. 다만 "추후
OpenAI/Claude/Gemini API로 쉽게 교체"할 수 있어야 한다는 요구사항 때문에,
아래 두 가지를 분리해뒀다.

1. `CoachingProvider` — 코칭 메시지를 생성하는 방법(규칙 기반 vs LLM 기반)의 인터페이스.
2. `generate_health_coaching()` — 실제 호출부(main.py)가 사용하는 공개 함수. 내부적으로
   기본 provider(RuleBasedCoachingProvider)를 사용하지만, provider 인자를 넘기면 다른
   구현(예: 나중에 추가할 LLMCoachingProvider)으로 교체할 수 있다.

나중에 LLM을 붙일 때는 새 클래스만 추가하면 된다:

    class LLMCoachingProvider(CoachingProvider):
        def generate(self, records, goal=None):
            trends = analyze_trends(records)         # 프롬프트에 넣을 요약은
            prompt = _build_prompt(trends, goal)      # health_trends.py를 그대로 재사용 가능
            return call_openai(prompt)

호출부(main.py)나 응답 스키마(HealthCoachingOut)는 전혀 바뀌지 않는다.

참고: 지표별 "추세(오르는지/내리는지/유지되는지)" 판단은 이 모듈이 직접 하지 않고
health_trends.py에 전부 위임한다 (건강 추세 분석 기능과 로직을 이중으로 두지 않기 위함).
"""

from abc import ABC, abstractmethod
from typing import List, Optional

import models
from health_trends import Trend, TrendResult, analyze_trends, classify_diff

# ---------- 코칭 판단 기준값 (매직 넘버 제거 목적으로 전부 상수로 분리) ----------
# 지표 변화 임계값(체중/혈압/혈당/걸음수/수면 변화폭)은 health_trends.METRIC_THRESHOLDS가
# 유일한 기준이다 — 이 모듈에는 그 값에 대응되지 않는, health_coach만의 고유 기준값만 둔다.

MIN_RECORDS_FOR_COACHING = 2  # 이 미만이면 추세 판단이 무의미하므로 안내 문구만 반환
SLEEP_MIN_HOURS = 6.5  # 평균 수면시간이 이 값 미만이면 "수면 부족"으로 판단 (추세가 아닌 절대 기준)
STEPS_RECOMMENDED_GOAL = 7000  # "다음 주 추천 목표" 문구에 쓰는 하루 권장 걸음 수


# ---------- 개별 코칭 규칙 (한 함수 = 한 지표, 실패해도 다른 규칙에 영향 없음) ----------
# 각 함수는 health_trends.analyze_trends()가 계산해준 TrendResult를 받아 문장으로만 옮긴다.

def _coach_blood_pressure(systolic_trend: TrendResult) -> Optional[str]:
    if systolic_trend.trend == Trend.UP:
        return "최근 혈압이 상승하는 추세입니다. 나트륨 섭취를 줄이고 충분히 휴식해보세요."
    if systolic_trend.trend == Trend.DOWN:
        return "최근 혈압이 안정적으로 낮아지고 있습니다. 지금의 습관을 유지해보세요."
    return None


def _coach_blood_sugar(sugar_trend: TrendResult) -> Optional[str]:
    if sugar_trend.recent_avg is None or sugar_trend.prior_avg is None:
        return None  # 비교할 데이터가 없으면 "안정적"이라고 단정하지 않음
    if sugar_trend.trend == Trend.STABLE:
        return "혈당이 최근 안정되고 있습니다."
    if sugar_trend.trend == Trend.UP:
        return "최근 혈당이 상승하는 추세입니다. 식후 혈당 관리에 신경 써보세요."
    return "최근 혈당이 낮아지는 추세입니다. 좋은 흐름이니 계속 유지해보세요."


def _coach_activity(steps_trend: TrendResult) -> Optional[str]:
    if steps_trend.trend == Trend.DOWN:
        return "최근 운동량(걸음 수)이 감소했습니다. 가벼운 산책부터 다시 시작해보세요."
    if steps_trend.trend == Trend.UP:
        return "최근 활동량이 늘었습니다! 좋은 흐름을 계속 이어가보세요."
    return None


def _coach_sleep(sleep_trend: TrendResult) -> Optional[str]:
    """수면은 "변화량"이 아니라 절대 기준(SLEEP_MIN_HOURS) 미달 여부로 판단한다."""
    if sleep_trend.recent_avg is None:
        return None
    if sleep_trend.recent_avg < SLEEP_MIN_HOURS:
        return "평균 수면시간이 부족합니다. 하루 7시간 이상 수면을 목표로 해보세요."
    return None


def _coach_weight_progress(
    weight_trend: TrendResult,
    goal: Optional[models.Goal],
) -> Optional[str]:
    """목표 체중이 설정되어 있을 때만 "목표 방향으로 가고 있는지"를 판단한다."""
    if goal is None or goal.target_weight is None:
        return None
    if weight_trend.recent_avg is None or weight_trend.prior_avg is None:
        return None
    if weight_trend.trend == Trend.STABLE:
        return None

    # 목표가 현재보다 낮으면(감량 목표) 체중이 줄어야 "목표 방향".
    # 목표가 현재보다 높으면(증량 목표) 체중이 늘어야 "목표 방향".
    target_is_lower = goal.target_weight < weight_trend.prior_avg
    diff = weight_trend.diff
    moving_toward_goal = (target_is_lower and diff < 0) or (not target_is_lower and diff > 0)

    direction = "감소" if diff < 0 else "증가"
    if moving_toward_goal:
        return f"체중은 목표 방향으로 잘 {direction}하고 있습니다."
    return "체중이 목표와 반대 방향으로 움직이고 있어요. 식단과 활동량을 점검해보세요."


def _generate_rule_based_messages(
    records: List[models.HealthRecord],
    goal: Optional[models.Goal],
) -> List[str]:
    if len(records) < MIN_RECORDS_FOR_COACHING:
        return ["기록을 조금 더 쌓으면 AI 코칭 메시지를 받아보실 수 있어요."]

    # 지표별 추세를 한 번에 계산 (모든 규칙이 동일한 최근/직전 구간 기준을 공유)
    trends = analyze_trends(records, metrics=["systolic", "blood_sugar", "steps", "sleep_hours", "weight"])

    # 규칙은 각각 독립적으로 판단하고, 해당 사항이 없으면 조용히 None을 반환한다
    # (한 규칙의 조건 미충족이 다른 규칙 실행에 영향을 주지 않음).
    candidate_messages = [
        _coach_blood_pressure(trends["systolic"]),
        _coach_blood_sugar(trends["blood_sugar"]),
        _coach_activity(trends["steps"]),
        _coach_sleep(trends["sleep_hours"]),
        _coach_weight_progress(trends["weight"], goal),
    ]
    messages = [m for m in candidate_messages if m]

    if not messages:
        messages.append("최근 지표가 전반적으로 안정적입니다. 지금의 좋은 습관을 유지해보세요.")
    return messages


# ---------- Provider 인터페이스 (LLM으로 교체하기 쉬운 구조) ----------

class CoachingProvider(ABC):
    """건강 코칭 메시지 생성기의 공통 인터페이스.

    지금은 RuleBasedCoachingProvider만 존재하지만, 추후 OpenAI/Claude/Gemini API를
    호출하는 provider를 추가할 때 이 인터페이스만 구현하면 나머지 코드(엔드포인트,
    프론트 렌더링)는 전혀 바뀌지 않는다.
    """

    @abstractmethod
    def generate(
        self,
        records: List[models.HealthRecord],
        goal: Optional[models.Goal] = None,
    ) -> List[str]:
        raise NotImplementedError


class RuleBasedCoachingProvider(CoachingProvider):
    """지금 실제로 사용하는 규칙 기반 구현."""

    def generate(
        self,
        records: List[models.HealthRecord],
        goal: Optional[models.Goal] = None,
    ) -> List[str]:
        return _generate_rule_based_messages(records, goal)


_default_provider: CoachingProvider = RuleBasedCoachingProvider()


def generate_health_coaching(
    records: List[models.HealthRecord],
    goal: Optional[models.Goal] = None,
    provider: Optional[CoachingProvider] = None,
) -> List[str]:
    """AI Health Coach 메시지 목록을 생성한다.

    Args:
        records: 사용자의 건강기록 (정렬 여부 무관, 내부에서 날짜순 정렬함).
        goal: 사용자가 설정한 목표 (없으면 목표 관련 코칭은 생략).
        provider: 메시지 생성 방식을 교체하고 싶을 때만 지정 (기본값: 규칙 기반).

    Returns:
        코칭 메시지 문자열 리스트. 항상 최소 1개 이상을 반환한다.
    """
    active_provider = provider if provider is not None else _default_provider
    return active_provider.generate(records, goal)


# ================================================================
# AI 건강 리포트 (주간 요약 문단 생성)
# ================================================================
# generate_health_coaching()이 "지표별 짧은 문장"의 목록이라면, 이 함수는
# 주간 리포트(main.py의 weekly_report()가 만드는 this_week/last_week/change와
# 동일한 구조)를 하나의 자연스러운 한국어 문단으로 요약한다.
#
# 예) "이번 주는 체중은 감소했지만 혈압이 조금 증가했습니다. 운동량은 감소하고
#      있으며 평균 수면시간도 줄었습니다. 다음 주에는 하루 7000보 이상 걷기를
#      추천합니다."
#
# 문장을 이어붙일 때 지만/고/으며 같은 연결어는 아무 문자열에나 붙일 수 없어서
# (문법이 깨짐), 아래 _*_change_stem() 함수들은 전부 "-았/었/였"으로 끝나는
# 어간만 반환하도록 맞춰뒀다. 이 어간 뒤에는 "습니다"/"지만"/"고"/"으며"를
# 그대로 이어붙여도 항상 문법적으로 성립한다 (예: "감소했"+"지만"="감소했지만").
#
# 여기서 받는 diff는 main.py가 이미 계산해둔 this_week/last_week 평균 차이라
# health_trends.analyze_trends()(레코드 리스트가 필요함)를 쓸 수 없다. 대신
# 같은 임계값 기준을 쓰기 위해 health_trends.classify_diff()로 분류한다
# (임계값이 중복 정의되지 않도록 health_trends.METRIC_THRESHOLDS가 유일한 기준).

def _weight_change_stem(diff: Optional[float]):
    """체중 변화 → (문장 어간, 개선 여부). 이 프로젝트에서는 체중 감소를 개선으로 본다
    (기존 주간 리포트 delta 표시 로직과 동일한 가정, index.html의 weeklyBarCard 참고)."""
    trend = classify_diff("weight", diff)
    if trend == Trend.STABLE:
        return "체중은 큰 변화가 없었", None
    if trend == Trend.DOWN:
        return "체중은 감소했", True
    return "체중은 증가했", False


def _bp_change_stem(diff: Optional[float]):
    trend = classify_diff("systolic", diff)
    if trend == Trend.STABLE:
        return "혈압은 큰 변화가 없었", None
    if trend == Trend.UP:
        return "혈압이 조금 증가했", False
    return "혈압은 안정적으로 낮아졌", True


def _activity_change_stem(diff: Optional[float]):
    trend = classify_diff("steps", diff)
    if trend == Trend.STABLE:
        return "운동량은 비슷한 수준이었", None
    if trend == Trend.DOWN:
        return "운동량은 감소하고 있", False
    return "운동량은 늘었", True


def _sleep_change_stem(diff: Optional[float]):
    trend = classify_diff("sleep_hours", diff)
    if trend == Trend.STABLE:
        return "평균 수면시간은 비슷했", None
    if trend == Trend.DOWN:
        return "평균 수면시간도 줄었", False
    return "평균 수면시간도 늘었", True


def _connective(a_improved: Optional[bool], b_improved: Optional[bool]) -> str:
    """두 지표의 방향이 정반대(하나는 개선, 하나는 악화)일 때만 "지만"으로 대비시키고,
    그 외(둘 다 같은 방향이거나 하나라도 변화 없음)에는 "으며"로 담담하게 이어붙인다."""
    if a_improved is True and b_improved is False:
        return "지만"
    if a_improved is False and b_improved is True:
        return "지만"
    return "으며"


def _weekly_recommendation(this_week: dict, change: dict) -> str:
    """이번 주 데이터 기준으로 다음 주에 실천할 행동 하나를 추천한다.

    여러 지표가 동시에 안 좋아 보여도 문단이 조언 나열로 늘어지지 않도록,
    아래 우선순위 중 가장 먼저 걸리는 것 하나만 추천 문장으로 만든다.
    """
    avg_steps = this_week.get("avg_steps")
    if avg_steps is not None and avg_steps < STEPS_RECOMMENDED_GOAL:
        return f"다음 주에는 하루 {STEPS_RECOMMENDED_GOAL}보 이상 걷기를 추천합니다."

    avg_sleep = this_week.get("avg_sleep_hours")
    if avg_sleep is not None and avg_sleep < SLEEP_MIN_HOURS:
        return "다음 주에는 하루 7시간 이상 수면을 목표로 해보세요."

    if classify_diff("systolic", change.get("avg_systolic")) == Trend.UP:
        return "다음 주에는 나트륨 섭취를 줄이고 혈압 관리에 조금 더 신경 써보세요."

    if classify_diff("blood_sugar", change.get("avg_blood_sugar")) == Trend.UP:
        return "다음 주에는 식후 혈당 관리에 조금 더 신경 써보세요."

    return "다음 주에도 지금의 좋은 습관을 유지해보세요."


def generate_weekly_summary(this_week: dict, last_week: dict, change: dict) -> str:
    """주간 리포트 데이터를 AI 요약 문단으로 변환한다.

    Args:
        this_week / last_week / change: main.py의 GET /reports/weekly 가 만드는
            것과 동일한 구조의 딕셔너리 (avg_weight, avg_systolic, avg_diastolic,
            avg_blood_sugar, avg_steps, avg_sleep_hours, record_count).

    Returns:
        2~3문장으로 구성된 한국어 요약 문단.
    """
    if not this_week.get("record_count"):
        return "이번 주는 기록이 없어 리포트를 만들 수 없어요. 기록을 추가하면 다음 주에 AI 요약을 받아보실 수 있어요."
    if not last_week.get("record_count"):
        return "이번 주 기록이 쌓이기 시작했어요. 다음 주부터는 지난주와 비교한 AI 요약을 보여드릴게요."

    weight_stem, weight_improved = _weight_change_stem(change.get("avg_weight"))
    bp_stem, bp_improved = _bp_change_stem(change.get("avg_systolic"))
    sentence_1 = f"이번 주는 {weight_stem}{_connective(weight_improved, bp_improved)} {bp_stem}습니다."

    activity_stem, activity_improved = _activity_change_stem(change.get("avg_steps"))
    sleep_stem, sleep_improved = _sleep_change_stem(change.get("avg_sleep_hours"))
    sentence_2 = f"{activity_stem}{_connective(activity_improved, sleep_improved)} {sleep_stem}습니다."

    sentence_3 = _weekly_recommendation(this_week, change)

    return f"{sentence_1} {sentence_2} {sentence_3}"
