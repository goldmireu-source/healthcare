"""AI Health Coach 관련 라우터 — 코칭 메시지/추세/이상징후/스코어/캘린더/타임라인/배지.

각 기능의 실제 계산 로직은 health_coach.py/health_trends.py/risk_detection.py/
health_score.py/health_calendar.py/health_timeline.py/badges.py에 있고, 여기서는
그 결과를 조회해 응답 스키마로 변환하는 얇은 라우트만 담당한다.
"""

import json
from datetime import date

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
from health_coach import generate_health_coaching
from health_trends import analyze_trends
from risk_detection import detect_risks
from health_score import compute_health_score
from health_calendar import build_month_calendar
from health_timeline import build_timeline
from badges import BADGE_DEFINITIONS, evaluate_new_badges

router = APIRouter(tags=["AI Coach"])


# ---------- AI Health Coach ----------
# OPENAI_API_KEY 환경변수가 설정되어 있으면 health_coach.OpenAICoachingProvider가
# 실제 OpenAI API를 호출하고, 키가 없거나 호출이 실패/타임아웃되면 자동으로
# RuleBasedCoachingProvider로 폴백한다 (health_coach.build_default_coaching_provider 참고).

@router.get("/health-coaching", response_model=schemas.HealthCoachingOut)
def get_health_coaching(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    # OpenAI 연동 시 매 요청마다 호출하면 비용이 계속 나가므로, 하루에 한 번만
    # 생성하고 같은 날 재요청은 캐시를 그대로 재사용한다 (badges.py의 지연 평가
    # 패턴과 동일 — 배경 스케줄러 없이 이 조회 시점에만 "오늘 이미 만들었는지" 확인).
    today = date.today().isoformat()
    cache = (
        db.query(models.CoachingCache)
        .filter(models.CoachingCache.user_id == current_user.id)
        .first()
    )
    if cache is not None and cache.generated_date == today:
        return schemas.HealthCoachingOut(messages=json.loads(cache.messages_json))

    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    # 목표가 없는 사용자가 대부분이라 404를 그대로 두면 안 되므로, 없으면 None으로 처리
    goal = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).first()

    messages = generate_health_coaching(records, goal)
    messages_json = json.dumps(messages, ensure_ascii=False)

    if cache is None:
        db.add(models.CoachingCache(user_id=current_user.id, generated_date=today, messages_json=messages_json))
    else:
        cache.generated_date = today
        cache.messages_json = messages_json
    db.commit()

    return schemas.HealthCoachingOut(messages=messages)


# ---------- 건강 추세 분석 ----------
# 체중/혈압/혈당/걸음수/수면 각 지표가 최근 상승(UP)/하락(DOWN)/유지(STABLE)인지
# 판단한다. health_coach.py의 코칭 메시지도 내부적으로 이 모듈(health_trends.py)을
# 사용하므로, 여기서 보여주는 결과와 코칭 메시지의 판단 기준은 항상 일치한다.

@router.get("/trends", response_model=schemas.TrendsOut)
def get_health_trends(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    trend_results = analyze_trends(records)
    trends_out = {
        metric: schemas.TrendOut(
            metric=result.metric,
            trend=result.trend.value,
            recent_avg=result.recent_avg,
            prior_avg=result.prior_avg,
            diff=result.diff,
        )
        for metric, result in trend_results.items()
    }
    return schemas.TrendsOut(trends=trends_out)


# ---------- 이상 징후 감지 ----------
# health_trends.py가 "추세"를 본다면, 이 엔드포인트는 그중 "위험할 만큼 급격한
# 변화"만 추려서 위험도(LOW/MEDIUM/HIGH)로 보여준다 (risk_detection.py 참고).

@router.get("/risk-detection", response_model=schemas.RiskDetectionOut)
def get_risk_detection(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    result = detect_risks(records)
    return schemas.RiskDetectionOut(
        risk_level=result.risk_level.value,
        anomalies=[
            schemas.AnomalyOut(
                metric=a.metric, label=a.label, severity=a.severity.value, detail=a.detail
            )
            for a in result.anomalies
        ],
    )


# ---------- Health Score 개선 ----------
# 이전에는 프론트(JS)에서 5개 지표에 균등한 페널티를 매겨 점수를 계산했다. 이제는
# 지표별 가중치(체중20%/혈압25%/혈당25%/운동15%/수면15%) + 추세 보너스/감점을
# 반영해 서버(health_score.py)에서 계산한 값을 그대로 내려준다.

@router.get("/health-score", response_model=schemas.HealthScoreOut)
def get_health_score(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .order_by(models.HealthRecord.date.asc())
        .all()
    )
    if not records:
        raise HTTPException(status_code=404, detail="건강 스코어를 계산할 기록이 없습니다.")

    result = compute_health_score(latest=records[-1], records=records)
    return schemas.HealthScoreOut(
        total_score=result.total_score,
        metrics=[
            schemas.MetricScoreOut(
                metric=m.metric, category=m.category, base_score=m.base_score,
                trend_adjustment=m.trend_adjustment, final_score=m.final_score, weight=m.weight,
            )
            for m in result.metrics
        ],
    )


# ---------- 건강 캘린더 ----------

@router.get("/calendar", response_model=schemas.CalendarOut)
def get_health_calendar(
    year: int = Query(..., ge=1900, le=2100),
    month: int = Query(..., ge=1, le=12),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    days = build_month_calendar(records, year, month)
    return schemas.CalendarOut(
        year=year,
        month=month,
        days=[schemas.CalendarDayOut(date=d.date, level=d.level, score=d.score) for d in days],
    )


# ---------- 건강 타임라인 ----------

@router.get("/timeline", response_model=schemas.TimelineOut)
def get_health_timeline(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    goal = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).first()
    events = build_timeline(records, goal)
    return schemas.TimelineOut(
        events=[schemas.TimelineEventOut(date=e.date, label=e.label, kind=e.kind) for e in events]
    )


# ---------- 건강 배지 ----------
# 배경 작업 스케줄러가 없는 프로젝트라, "조회 시점에 새로 만족한 조건이 있는지
# 평가하고, 있으면 그때 저장"하는 지연 평가 방식을 쓴다 (badges.py 참고).

@router.get("/badges", response_model=schemas.BadgesOut)
def get_badges(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    earned = db.query(models.Badge).filter(models.Badge.user_id == current_user.id).all()
    earned_keys = {b.badge_key for b in earned}

    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .all()
    )
    goal = db.query(models.Goal).filter(models.Goal.user_id == current_user.id).first()

    new_keys = evaluate_new_badges(records, goal, earned_keys)
    if new_keys:
        for key in new_keys:
            db.add(models.Badge(user_id=current_user.id, badge_key=key))
        db.commit()
        earned = db.query(models.Badge).filter(models.Badge.user_id == current_user.id).all()

    earned_map = {b.badge_key: b for b in earned}
    badges_out = [
        schemas.BadgeOut(
            key=defn.key,
            label=defn.label,
            description=defn.description,
            icon=defn.icon,
            earned=defn.key in earned_map,
            earned_at=earned_map[defn.key].earned_at if defn.key in earned_map else None,
        )
        for defn in BADGE_DEFINITIONS
    ]
    return schemas.BadgesOut(badges=badges_out)
