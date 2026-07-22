"""Web Push 구독/발송 라우터 - 최소 구현(고도화 Phase 7).

이 프로젝트는 배경 스케줄러(APScheduler/Celery 등)를 쓰지 않고 지연 평가로
버텨왔다(badges.py/CoachingCache/auth.cleanup_expired_sessions 참고). 하지만
"오늘 기록 안 남긴 사용자에게 알림 보내기"는 그 사용자가 다시 접속해야만
평가되는 지연 평가로는 애초에 불가능한 일이라(알림의 목적 자체가 "안 돌아온
사람을 부르는 것"), 이 기능만큼은 관리자가 수동으로 누르는
POST /push/send-reminder로 트리거한다. 실제 서비스에서 매일 자동으로 보내고
싶다면 배포 단계에서 이 엔드포인트를 하루 한 번 cron으로 호출하면 된다 -
그 자동 스케줄 등록 자체는 이번 범위 밖(Phase 6 백업 스크립트와 동일한 경계).
"""
import os
from datetime import date

from fastapi import APIRouter, HTTPException, Depends
from pywebpush import webpush, WebPushException
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(tags=["Push"])

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL", "admin@example.com")


def _push_enabled() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


@router.get("/push/vapid-public-key", response_model=schemas.VapidPublicKeyOut)
def get_vapid_public_key(current_user: models.User = Depends(auth.get_current_user)):
    if not _push_enabled():
        return schemas.VapidPublicKeyOut(enabled=False, public_key="")
    return schemas.VapidPublicKeyOut(enabled=True, public_key=VAPID_PUBLIC_KEY)


@router.post("/push/subscribe")
def subscribe(
    payload: schemas.PushSubscriptionIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if not _push_enabled():
        raise HTTPException(status_code=503, detail="서버에 Web Push가 설정되어 있지 않습니다.")

    existing = db.query(models.PushSubscription).filter(
        models.PushSubscription.endpoint == payload.endpoint
    ).first()
    if existing:
        # 같은 endpoint가 다른 계정 소유였을 수도 있음(같은 브라우저에서 로그아웃 후
        # 다른 계정으로 재구독) - 최신 요청 기준으로 소유자/키를 갱신한다.
        existing.user_id = current_user.id
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
    else:
        db.add(models.PushSubscription(
            user_id=current_user.id,
            endpoint=payload.endpoint,
            p256dh=payload.keys.p256dh,
            auth=payload.keys.auth,
        ))
    db.commit()
    return {"message": "알림 구독이 등록되었습니다."}


@router.post("/push/unsubscribe")
def unsubscribe(
    payload: schemas.PushUnsubscribeIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    db.query(models.PushSubscription).filter(
        models.PushSubscription.endpoint == payload.endpoint,
        models.PushSubscription.user_id == current_user.id,
    ).delete()
    db.commit()
    return {"message": "알림 구독이 해제되었습니다."}


@router.post("/push/send-reminder", response_model=schemas.SendReminderOut)
def send_reminder(
    current_admin: models.User = Depends(auth.get_current_admin),
    db: Session = Depends(get_db),
):
    """오늘 기록을 이미 남긴 사용자, 오늘 이미 리마인더를 받은 구독은 건너뛰고
    나머지에게만 발송한다. 만료/무효 구독(410/404)은 이 기회에 정리한다."""
    if not _push_enabled():
        raise HTTPException(status_code=503, detail="서버에 Web Push가 설정되어 있지 않습니다.")

    today = date.today().isoformat()
    users_with_record_today = {
        row[0] for row in
        db.query(models.HealthRecord.user_id).filter(models.HealthRecord.date == today).distinct()
    }
    subscriptions = db.query(models.PushSubscription).all()

    sent = skipped_already_active = skipped_already_sent = failed = 0
    for sub in subscriptions:
        if sub.user_id in users_with_record_today:
            skipped_already_active += 1
            continue
        if sub.last_reminder_sent_date == today:
            skipped_already_sent += 1
            continue
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data='{"title":"마이 헬스 로그","body":"오늘 아직 건강 기록을 남기지 않으셨어요. 잊지 말고 기록해보세요!"}',
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{VAPID_CLAIMS_EMAIL}"},
            )
            sub.last_reminder_sent_date = today
            sent += 1
        except WebPushException as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in (404, 410):
                db.delete(sub)
            failed += 1

    db.commit()
    return schemas.SendReminderOut(
        sent=sent,
        skipped_already_active=skipped_already_active,
        skipped_already_sent=skipped_already_sent,
        failed=failed,
    )
