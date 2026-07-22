"""목표 관리 라우터 — 실제 로직(달성 여부 + 예측 계산)은 goal_service.py에 있음."""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
import goal_service

router = APIRouter(tags=["Goals"])


@router.post("/goals", response_model=schemas.GoalOut)
def set_goal(
    payload: schemas.GoalIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).first()
    if not goal:
        goal = models.Goal(user_id=current_user.id)
        db.add(goal)

    if payload.target_weight is not None:
        goal.target_weight = payload.target_weight
    if payload.target_systolic is not None:
        goal.target_systolic = payload.target_systolic
    if payload.target_diastolic is not None:
        goal.target_diastolic = payload.target_diastolic
    if payload.target_blood_sugar is not None:
        goal.target_blood_sugar = payload.target_blood_sugar

    db.commit()
    db.refresh(goal)
    return goal_service.goal_to_out(db, goal, current_user.username)


@router.get("/goals", response_model=schemas.GoalOut)
def get_goal(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="설정된 목표가 없습니다.")
    return goal_service.goal_to_out(db, goal, current_user.username)
