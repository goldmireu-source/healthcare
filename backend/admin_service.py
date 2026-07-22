"""관리자(Admin) 관련 서비스 레이어.

이전에는 main.py 안에 직접 정의되어 있던 헬퍼/쿼리 로직을 그대로(로직 변경
없이) 옮겼다. 라우트 핸들러(main.py)는 이 모듈의 함수를 호출하는 얇은
wrapper 역할만 한다.

주의: 여기서 쓰는 RISK_BAD_CATEGORIES/RISK_WARN_CATEGORIES는 "가장 최근 기록
1건의 분류"만 보는 기존 관리자 위험도(high/moderate/normal/unknown) 기준이다.
health_score.py/health_trends.py 등 사용자 쪽 AI 기능이 쓰는 판단 기준과는
목적이 달라 의도적으로 분리되어 있다 (자세한 설명은 risk_detection.py 참고).
"""

from datetime import date as date_cls, datetime, timedelta
from typing import Dict, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
import schemas
from admin_analytics import compute_admin_analytics

RISK_BAD_CATEGORIES = {"고혈압", "비만", "당뇨 의심"}
RISK_WARN_CATEGORIES = {"주의", "과체중", "공복혈당장애", "부족", "과다", "저체중"}
RISK_LEVEL_ORDER = {"high": 3, "moderate": 2, "normal": 1, "unknown": 0}


def risk_level_for_record(record: Optional[models.HealthRecord]) -> str:
    if record is None:
        return "unknown"
    cats = {record.bmi_category, record.bp_category, record.sugar_category}
    if cats & RISK_BAD_CATEGORIES:
        return "high"
    if cats & RISK_WARN_CATEGORIES:
        return "moderate"
    return "normal"


def log_admin_action(
    db: Session,
    admin_user: models.User,
    action: str,
    target_username: Optional[str] = None,
    detail: str = "",
) -> None:
    db.add(
        models.AuditLog(
            admin_username=admin_user.username,
            action=action,
            target_username=target_username,
            detail=detail,
        )
    )
    db.commit()


def list_users(
    db: Session,
    search: Optional[str],
    role: Optional[str],
    risk: Optional[str],
    sort_by: str,
    sort_dir: str,
    page: int,
    page_size: int,
    signup_days: Optional[int] = None,
    signup_date: Optional[str] = None,
    active_days: Optional[int] = None,
    has_records: Optional[bool] = None,
) -> schemas.AdminUsersOut:
    """검색/역할/위험도 필터 + 정렬 + 페이지네이션을 적용한 사용자 목록을 만든다.

    signup_days/signup_date/active_days/has_records는 관리자 개요 화면의 KPI
    카드(예: "최근 7일 신규가입", "고위험 사용자")를 클릭했을 때 그 수치의 근거가
    되는 사용자 목록으로 바로 드릴다운하기 위한 필터다 — 숫자만 보여주고 상세를
    확인할 방법이 없던 문제를 해결한다.
    """
    query = db.query(models.User)
    if search:
        # 아이디(username)뿐 아니라 이름(name)으로도 찾을 수 있어야 함 - 이름이 없는
        # 기존 계정도 있으므로 username OR name 중 하나만 일치해도 결과에 포함
        query = query.filter(
            or_(
                models.User.username.ilike(f"%{search}%"),
                models.User.name.ilike(f"%{search}%"),
            )
        )
    if role in ("user", "admin"):
        query = query.filter(models.User.role == role)

    users = query.all()

    # user_id별 기록 수를 한 번의 집계 쿼리로 가져와 N+1 쿼리를 피함
    record_counts = dict(
        db.query(models.HealthRecord.user_id, func.count(models.HealthRecord.id))
        .group_by(models.HealthRecord.user_id)
        .all()
    )

    # user_id별 "가장 최근" 기록 1건만 추려서 위험도를 계산 (user_id, date desc 정렬 후
    # 처음 등장하는 것만 채택 -> 사용자 수만큼의 개별 쿼리 없이 한 번의 조회로 해결)
    latest_by_user: Dict[int, models.HealthRecord] = {}
    for r in (
        db.query(models.HealthRecord)
        .order_by(models.HealthRecord.user_id, models.HealthRecord.date.desc())
        .all()
    ):
        latest_by_user.setdefault(r.user_id, r)
    risk_by_user = {uid: risk_level_for_record(rec) for uid, rec in latest_by_user.items()}

    if risk in ("high", "moderate", "normal", "unknown"):
        users = [u for u in users if risk_by_user.get(u.id, "unknown") == risk]

    if signup_days is not None:
        cutoff = date_cls.today() - timedelta(days=signup_days - 1)
        users = [u for u in users if u.created_at and u.created_at.date() >= cutoff]

    if signup_date:
        users = [u for u in users if u.created_at and u.created_at.date().isoformat() == signup_date]

    if has_records is not None:
        users = [u for u in users if (record_counts.get(u.id, 0) > 0) == has_records]

    if active_days is not None:
        cutoff_str = (date_cls.today() - timedelta(days=active_days - 1)).isoformat()
        users = [
            u for u in users
            if u.id in latest_by_user and latest_by_user[u.id].date >= cutoff_str
        ]

    total = len(users)

    def sort_key(u):
        if sort_by == "username":
            return u.username.lower()
        if sort_by == "created_at":
            return u.created_at or datetime.min
        if sort_by == "record_count":
            return record_counts.get(u.id, 0)
        if sort_by == "risk_level":
            return RISK_LEVEL_ORDER.get(risk_by_user.get(u.id, "unknown"), 0)
        return u.id

    users.sort(key=sort_key, reverse=(sort_dir == "desc"))

    start = (page - 1) * page_size
    page_users = users[start : start + page_size]

    items = [
        schemas.AdminUserOut(
            id=u.id,
            username=u.username,
            name=u.name,
            role=u.role,
            created_at=u.created_at,
            record_count=record_counts.get(u.id, 0),
            risk_level=risk_by_user.get(u.id, "unknown"),
        )
        for u in page_users
    ]
    return schemas.AdminUsersOut(count=total, page=page, page_size=page_size, users=items)


def get_user_detail(db: Session, user_id: int) -> Optional[schemas.AdminUserDetailOut]:
    """"회원정보 보기" 상세 조회 - 목록에는 없는 보안질문/로그인 실패·잠금 상태까지 포함.

    사용자가 없으면 None을 반환하고, 404 처리는 호출부(main.py)가 담당한다
    (다른 admin_service 함수들과 마찬가지로 HTTP 관심사는 라우트 핸들러에 남겨둠).
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        return None

    record_count = (
        db.query(func.count(models.HealthRecord.id))
        .filter(models.HealthRecord.user_id == user_id)
        .scalar()
    ) or 0

    latest = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == user_id)
        .order_by(models.HealthRecord.date.desc())
        .first()
    )

    return schemas.AdminUserDetailOut(
        id=user.id,
        username=user.username,
        name=user.name,
        role=user.role,
        created_at=user.created_at,
        security_question=user.security_question,
        failed_login_attempts=user.failed_login_attempts,
        locked_until=user.locked_until,
        record_count=record_count,
        risk_level=risk_level_for_record(latest),
    )


def _distribution(values) -> Dict:
    dist: dict = {}
    for v in values:
        dist[v] = dist.get(v, 0) + 1
    return dist


def compute_admin_stats(db: Session) -> schemas.AdminStatsOut:
    """관리자 개요 대시보드에 필요한 통계 전체(기존 통계 + admin_analytics.py의 신규 KPI)를 계산한다."""
    users = db.query(models.User).all()
    records = db.query(models.HealthRecord).all()

    role_distribution = _distribution([u.role for u in users])

    today = date_cls.today()
    new_users_last_7_days = sum(
        1 for u in users if u.created_at and u.created_at.date() >= today - timedelta(days=6)
    )

    signups_by_day: dict = {}
    for u in users:
        if u.created_at:
            day = u.created_at.date().isoformat()
            signups_by_day[day] = signups_by_day.get(day, 0) + 1
    signup_trend = [
        schemas.SignupTrendPoint(
            date=(today - timedelta(days=i)).isoformat(),
            count=signups_by_day.get((today - timedelta(days=i)).isoformat(), 0),
        )
        for i in range(13, -1, -1)
    ]

    latest_by_user: Dict[int, models.HealthRecord] = {}
    for r in sorted(records, key=lambda r: r.date, reverse=True):
        latest_by_user.setdefault(r.user_id, r)
    users_by_id = {u.id: u for u in users}
    high_risk_usernames = sorted(
        users_by_id[uid].username
        for uid, rec in latest_by_user.items()
        if uid in users_by_id and risk_level_for_record(rec) == "high"
    )

    analytics = compute_admin_analytics(users, records, today=today)

    return schemas.AdminStatsOut(
        total_users=len(users),
        total_records=len(records),
        role_distribution=role_distribution,
        new_users_last_7_days=new_users_last_7_days,
        signup_trend=signup_trend,
        bmi_category_distribution=_distribution([r.bmi_category for r in records]),
        bp_category_distribution=_distribution([r.bp_category for r in records]),
        sugar_category_distribution=_distribution([r.sugar_category for r in records]),
        high_risk_usernames=high_risk_usernames,
        recent_activity_rate=analytics.recent_activity_rate,
        retention_rate=analytics.retention_rate,
        avg_bmi=analytics.avg_bmi,
        avg_systolic=analytics.avg_systolic,
        avg_diastolic=analytics.avg_diastolic,
        avg_blood_sugar=analytics.avg_blood_sugar,
        high_risk_growth_rate=analytics.high_risk_growth_rate,
        signup_to_record_rate=analytics.signup_to_record_rate,
    )
