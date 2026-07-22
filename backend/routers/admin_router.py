"""관리자 전용 라우터 — 회원가입으로는 절대 admin이 될 수 없음(role은 항상 "user"로
생성됨). 계정을 관리자로 승격하려면 로컬에서 promote_admin.py를 직접 실행해야 함.
실제 쿼리/집계 로직은 admin_service.py로 분리됨.
"""

import secrets
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
import health_service
import admin_service

router = APIRouter(tags=["Admin"])


@router.get("/admin/users", response_model=schemas.AdminUsersOut)
def admin_list_users(
    search: Optional[str] = Query(None, description="아이디 부분 검색"),
    role: Optional[str] = Query(None, description="user 또는 admin으로 필터링"),
    risk: Optional[str] = Query(None, description="high | moderate | normal | unknown 위험도 필터"),
    signup_days: Optional[int] = Query(None, ge=1, description="최근 N일 이내 가입한 사용자만 필터링 (개요 KPI 드릴다운용)"),
    signup_date: Optional[str] = Query(None, description="특정 날짜(YYYY-MM-DD)에 가입한 사용자만 필터링 (가입 추이 차트 드릴다운용)"),
    active_days: Optional[int] = Query(None, ge=1, description="최근 N일 이내 기록을 남긴 사용자만 필터링"),
    has_records: Optional[bool] = Query(None, description="true=기록 1건 이상 보유, false=기록 0건"),
    online: Optional[bool] = Query(None, description="true=현재 로그인 상태(유효한 세션 보유), false=오프라인"),
    sort_by: str = Query("id", description="id | username | created_at | record_count | risk_level"),
    sort_dir: str = Query("asc", description="asc | desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    return admin_service.list_users(
        db, search, role, risk, sort_by, sort_dir, page, page_size,
        signup_days=signup_days, signup_date=signup_date, active_days=active_days,
        has_records=has_records, online=online,
    )


@router.get("/admin/stats", response_model=schemas.AdminStatsOut)
def admin_stats(
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    return admin_service.compute_admin_stats(db)


@router.get("/admin/users/{user_id}", response_model=schemas.AdminUserDetailOut)
def admin_get_user_detail(
    user_id: int,
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    detail = admin_service.get_user_detail(db, user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return detail


@router.get("/admin/users/{user_id}/records", response_model=schemas.RecordListOut)
def admin_get_user_records(
    user_id: int,
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == user_id)
        .order_by(models.HealthRecord.date.asc())
        .all()
    )
    return schemas.RecordListOut(count=len(records), records=[health_service.record_to_out(r) for r in records])


@router.delete("/admin/users/{user_id}")
def admin_delete_user(
    user_id: int,
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="자기 자신의 계정은 삭제할 수 없습니다.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    username = user.username
    db.delete(user)
    db.commit()
    admin_service.log_admin_action(db, current_admin, "delete_user", target_username=username)
    return {"message": f"'{username}' 계정이 삭제되었습니다."}


@router.post("/admin/users/{user_id}/force-logout")
def admin_force_logout(
    user_id: int,
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="자기 자신의 세션은 이 기능으로 무효화할 수 없습니다. 로그아웃 버튼을 이용하세요.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    invalidated = (
        db.query(models.Session).filter(models.Session.user_id == user_id).delete()
    )
    db.commit()
    admin_service.log_admin_action(
        db, current_admin, "force_logout", target_username=user.username,
        detail=f"세션 {invalidated}개 무효화",
    )
    return {
        "message": f"'{user.username}'의 모든 세션을 무효화했습니다.",
        "sessions_invalidated": invalidated,
    }


@router.post("/admin/users/{user_id}/reset-password", response_model=schemas.AdminPasswordResetOut)
def admin_reset_password(
    user_id: int,
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    """보안질문 답을 잊거나(또는 그 rate limit에 걸려) 셀프 복구가 막힌 사용자를 위한
    최소한의 관리자 개입 경로 — 이메일 인증 인프라가 없어 다른 대안이 없는 상황을
    보완한다. 무작위 임시 비밀번호를 생성해 즉시 해시로만 저장하고, 탈취 우려가 있는
    기존 세션은 비밀번호 찾기 재설정과 동일하게 전부 무효화한다."""
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="자기 자신의 비밀번호는 이 기능으로 재설정할 수 없습니다.")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    temporary_password = secrets.token_urlsafe(9)
    password_hash, salt = auth.hash_password(temporary_password)
    user.password_hash = password_hash
    user.password_salt = salt
    db.query(models.Session).filter(models.Session.user_id == user_id).delete()
    db.commit()

    # 감사 로그에는 절대 비밀번호 값 자체를 남기지 않는다 (누가/언제/누구에게 했는지만 기록)
    admin_service.log_admin_action(
        db, current_admin, "admin_password_reset", target_username=user.username,
        detail="관리자가 임시 비밀번호 발급 (기존 세션 전부 무효화됨)",
    )
    return schemas.AdminPasswordResetOut(temporary_password=temporary_password)


@router.get("/admin/audit-log", response_model=schemas.AuditLogsOut)
def admin_audit_log(
    limit: int = Query(50, ge=1, le=200),
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return schemas.AuditLogsOut(count=len(logs), logs=logs)
