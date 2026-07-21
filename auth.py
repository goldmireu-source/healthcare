"""인증 관련 유틸리티.

- 비밀번호: PBKDF2-HMAC-SHA256 (표준 라이브러리 hashlib만 사용, 추가 의존성 없음)
- 세션: 서버 DB에 저장된 랜덤 토큰을 HttpOnly 쿠키로 전달 (JWT 대신 단순하고 즉시 폐기 가능한 방식)
"""

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as DBSession
from fastapi import Request, HTTPException, Depends

import models
from database import get_db

PBKDF2_ITERATIONS = 260_000
SESSION_COOKIE_NAME = "session_token"
SESSION_TTL_DAYS = 7

# 배포 환경(HTTPS)에서는 COOKIE_SECURE=true 로 설정 권장
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    )
    return dk.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    computed, _ = hash_password(password, salt)
    return hmac.compare_digest(computed, password_hash)


def create_session(db: DBSession, user: models.User) -> models.Session:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
    session = models.Session(token=token, user_id=user.id, expires_at=expires_at)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def delete_session(db: DBSession, token: str) -> None:
    db.query(models.Session).filter(models.Session.token == token).delete()
    db.commit()


def get_current_user(request: Request, db: DBSession = Depends(get_db)) -> models.User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    session = db.query(models.Session).filter(models.Session.token == token).first()
    if not session:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해주세요.")

    user = db.query(models.User).filter(models.User.id == session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user
