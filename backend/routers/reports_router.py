"""주간 리포트 라우터 — 실제 로직은 report_service.py에 있음."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
import report_service

router = APIRouter(tags=["Reports"])


@router.get("/reports/weekly", response_model=schemas.WeeklyReportOut)
def weekly_report(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    return report_service.build_weekly_report(db, current_user)
