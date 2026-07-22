"""목표 관리(Goal) 관련 서비스 레이어.

이전에는 main.py 안에 직접 정의되어 있던 _goal_to_out()을 그대로(로직 변경
없이) 옮겼다. 라우트 핸들러(main.py)는 이 모듈의 함수를 호출하는 얇은
wrapper 역할만 한다.
"""

from sqlalchemy.orm import Session

import models
import schemas
from goal_prediction import predict_goal_achievement


def goal_to_out(db: Session, goal: models.Goal, username: str) -> schemas.GoalOut:
    """목표 + 최신 기록 기준 달성 여부 + 달성 예측(goal_prediction.py)을 합쳐 응답을 만든다."""
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == goal.user_id)
        .order_by(models.HealthRecord.date.asc())
        .all()
    )
    latest = records[-1] if records else None

    achievement: dict = {}
    if latest:
        if goal.target_weight is not None:
            achievement["weight_diff"] = round(latest.weight - goal.target_weight, 2)
            achievement["weight_achieved"] = latest.weight <= goal.target_weight
        if goal.target_systolic is not None:
            achievement["systolic_achieved"] = latest.systolic <= goal.target_systolic
        if goal.target_diastolic is not None:
            achievement["diastolic_achieved"] = latest.diastolic <= goal.target_diastolic
        if goal.target_blood_sugar is not None:
            achievement["blood_sugar_achieved"] = latest.blood_sugar <= goal.target_blood_sugar

        # 목표 달성 예측: 평균 변화량 기준으로 목표까지 예상 소요일 계산
        predictions = predict_goal_achievement(records, goal)
        if predictions:
            achievement["predictions"] = {
                metric: {"estimated_days": pred.estimated_days, "message": pred.message}
                for metric, pred in predictions.items()
            }
    else:
        achievement["message"] = "아직 기록이 없어 달성률을 계산할 수 없습니다."

    return schemas.GoalOut(
        id=goal.id,
        username=username,
        target_weight=goal.target_weight,
        target_systolic=goal.target_systolic,
        target_diastolic=goal.target_diastolic,
        target_blood_sugar=goal.target_blood_sugar,
        achievement=achievement,
    )
