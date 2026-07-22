"""건강 캘린더 (월간, GitHub Contribution 그래프 느낌).

날짜별로 그날 기록의 상태를 good(초록)/warn(노랑)/bad(빨강) 중 하나로 요약해
돌려준다. 기록이 없는 날은 결과에 포함하지 않는다(프론트에서 빈 칸으로 처리).

카테고리를 3단계로 묶는 기준은 health_score.py의 GOOD/WARN/BAD_CATEGORIES를
그대로 재사용한다 (여러 모듈이 각자 다른 기준으로 "정상/주의/위험"을 나누지
않도록 하나로 통일).
"""

from dataclasses import dataclass
from typing import Dict, List

import models
from health_score import BAD_CATEGORIES, WARN_CATEGORIES

_LEVEL_ORDER = {"good": 0, "warn": 1, "bad": 2}
_LEVEL_SCORE = {"good": 100, "warn": 60, "bad": 20}


@dataclass(frozen=True)
class CalendarDay:
    date: str
    level: str  # "good" | "warn" | "bad"
    score: int  # 캘린더 색상용 단순 점수 (health_score.py의 가중치 점수와는 다른, 그날 하루만의 값)


def _day_level(record: models.HealthRecord) -> str:
    cats = {record.bmi_category, record.bp_category, record.sugar_category}
    if cats & BAD_CATEGORIES:
        return "bad"
    if cats & WARN_CATEGORIES:
        return "warn"
    return "good"


def build_month_calendar(records: List[models.HealthRecord], year: int, month: int) -> List[CalendarDay]:
    """해당 연/월에 속한 기록만 걸러 날짜별 상태를 계산한다.

    같은 날짜에 기록이 여러 건이면(원칙적으로는 1건/일이지만 방어적으로) 그중
    가장 나쁜 상태를 그 날의 대표값으로 사용한다.
    """
    prefix = f"{year:04d}-{month:02d}-"
    by_date: Dict[str, str] = {}
    for r in records:
        if not r.date.startswith(prefix):
            continue
        level = _day_level(r)
        existing = by_date.get(r.date)
        if existing is None or _LEVEL_ORDER[level] > _LEVEL_ORDER[existing]:
            by_date[r.date] = level

    return [
        CalendarDay(date=d, level=level, score=_LEVEL_SCORE[level])
        for d, level in sorted(by_date.items())
    ]
