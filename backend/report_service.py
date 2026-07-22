"""주간 리포트(Weekly Report) 관련 서비스 레이어.

이전에는 main.py의 weekly_report() 엔드포인트 함수 안에 전부 들어있던 로직을
그대로(로직 변경 없이) 옮겼다. 라우트 핸들러(main.py)는 이 모듈의 함수를
호출하는 얇은 wrapper 역할만 한다.
"""

from datetime import date as date_cls, timedelta
from typing import Optional

from sqlalchemy.orm import Session

import models
import schemas
from health_coach import generate_weekly_summary


def _week_stats(db: Session, user_id: int, start: str, end: str) -> dict:
    records = (
        db.query(models.HealthRecord)
        .filter(
            models.HealthRecord.user_id == user_id,
            models.HealthRecord.date >= start,
            models.HealthRecord.date <= end,
        )
        .all()
    )
    if not records:
        return {"record_count": 0}

    def avg(values):
        return round(sum(values) / len(values), 2)

    return {
        "record_count": len(records),
        "avg_weight": avg([r.weight for r in records]),
        "avg_systolic": avg([r.systolic for r in records]),
        "avg_diastolic": avg([r.diastolic for r in records]),
        "avg_blood_sugar": avg([r.blood_sugar for r in records]),
        "avg_steps": avg([r.steps for r in records]),
        "avg_sleep_hours": avg([r.sleep_hours for r in records]),
    }


def build_weekly_report(
    db: Session,
    current_user: models.User,
    today: Optional[date_cls] = None,
) -> schemas.WeeklyReportOut:
    """이번 주 vs 지난 주 평균 비교 + AI 요약(health_coach.generate_weekly_summary)을 계산한다."""
    if today is None:
        today = date_cls.today()

    this_week_start = (today - timedelta(days=6)).isoformat()
    this_week_end = today.isoformat()
    last_week_start = (today - timedelta(days=13)).isoformat()
    last_week_end = (today - timedelta(days=7)).isoformat()

    this_week = _week_stats(db, current_user.id, this_week_start, this_week_end)
    last_week = _week_stats(db, current_user.id, last_week_start, last_week_end)

    change = {}
    for key in ["avg_weight", "avg_systolic", "avg_diastolic", "avg_blood_sugar", "avg_steps", "avg_sleep_hours"]:
        if key in this_week and key in last_week:
            change[key] = round(this_week[key] - last_week[key], 2)

    ai_summary = generate_weekly_summary(this_week, last_week, change)

    return schemas.WeeklyReportOut(
        username=current_user.username,
        this_week=this_week,
        last_week=last_week,
        change=change,
        ai_summary=ai_summary,
    )
