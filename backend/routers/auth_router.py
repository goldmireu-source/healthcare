"""인증 라우터 (회원가입/로그인/로그아웃/보안질문/비밀번호·이름 변경/탈퇴).

main.py에 있던 라우트 함수를 로직 변경 없이 그대로 옮긴 것 — main.py를 40개
라우트를 한 파일에 담는 대신 도메인별로 분리하기 위함 (main.py는 이제 앱
초기화/미들웨어/정적 파일 서빙만 담당).
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Response, Request
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
import rate_limit

router = APIRouter(tags=["Auth"])


def _client_ip(request: Request) -> str:
    # 리버스 프록시 뒤에 배포할 경우 X-Forwarded-For를 신뢰할 수 있는 범위에서
    # 확인해야 하지만, 이 프로젝트는 그 앞단이 없어 request.client만 사용한다.
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(key: str, max_attempts: int, window_seconds: int, message: str) -> None:
    if rate_limit.is_rate_limited(key, max_attempts, window_seconds):
        raise HTTPException(status_code=429, detail=message)


@router.post("/auth/signup", response_model=schemas.UserOut)
def signup(
    payload: schemas.UserSignup,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    _enforce_rate_limit(
        f"signup:{_client_ip(request)}",
        max_attempts=5,
        window_seconds=600,
        message="회원가입 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
    )

    existing = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")

    password_hash, salt = auth.hash_password(payload.password)
    answer_hash, answer_salt = auth.hash_password(
        auth.normalize_security_answer(payload.security_answer)
    )
    user = models.User(
        username=payload.username,
        name=payload.name,
        password_hash=password_hash,
        password_salt=salt,
        security_question=payload.security_question,
        security_answer_hash=answer_hash,
        security_answer_salt=answer_salt,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    session = auth.create_session(db, user)
    response.set_cookie(
        key=auth.SESSION_COOKIE_NAME,
        value=session.token,
        httponly=True,
        samesite="lax",
        secure=auth.COOKIE_SECURE,
        max_age=auth.SESSION_TTL_DAYS * 24 * 3600,
    )
    return user


@router.post("/auth/login", response_model=schemas.UserOut)
def login(
    payload: schemas.UserLogin,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    # IP 기준 속도 제한 — 서로 다른 아이디를 대량으로 시도하는 무차별 대입을 막음
    _enforce_rate_limit(
        f"login:{_client_ip(request)}",
        max_attempts=15,
        window_seconds=300,
        message="로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
    )

    user = db.query(models.User).filter(models.User.username == payload.username).first()

    # 계정 단위 잠금 — 같은 계정에 대한 반복 실패를 막음 (IP를 바꿔가며 시도해도 방어됨)
    if user and auth.is_account_locked(user):
        raise HTTPException(
            status_code=423,
            detail=f"로그인 실패 횟수가 많아 계정이 잠겼습니다. {auth.LOGIN_LOCKOUT_MINUTES}분 후 다시 시도해주세요.",
        )

    if not user or not auth.verify_password(payload.password, user.password_hash, user.password_salt):
        if user:
            auth.register_failed_login(db, user)
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")

    auth.reset_login_failures(db, user)
    session = auth.create_session(db, user)
    response.set_cookie(
        key=auth.SESSION_COOKIE_NAME,
        value=session.token,
        httponly=True,
        samesite="lax",
        secure=auth.COOKIE_SECURE,
        max_age=auth.SESSION_TTL_DAYS * 24 * 3600,
    )
    return user


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(auth.SESSION_COOKIE_NAME)
    if token:
        auth.delete_session(db, token)
    response.delete_cookie(auth.SESSION_COOKIE_NAME)
    return {"message": "로그아웃되었습니다."}


@router.get("/auth/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@router.get("/auth/security-question", response_model=schemas.SecurityQuestionOut)
def get_security_question(request: Request, username: str = Query(...), db: Session = Depends(get_db)):
    _enforce_rate_limit(
        f"secq:{_client_ip(request)}:{username}",
        max_attempts=10,
        window_seconds=600,
        message="요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
    )
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return schemas.SecurityQuestionOut(security_question=user.security_question)


@router.post("/auth/reset-password")
def reset_password(payload: schemas.PasswordResetIn, request: Request, db: Session = Depends(get_db)):
    # 보안질문 답은 추측 가능한 값이 많아(생일, 색깔 등) 무차별 대입에 특히 취약 -> 엄격하게 제한
    _enforce_rate_limit(
        f"resetpw:{_client_ip(request)}:{payload.username}",
        max_attempts=5,
        window_seconds=900,
        message="비밀번호 재설정 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
    )
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if not auth.verify_password(
        auth.normalize_security_answer(payload.security_answer),
        user.security_answer_hash,
        user.security_answer_salt,
    ):
        raise HTTPException(status_code=401, detail="보안질문 답이 올바르지 않습니다.")

    password_hash, salt = auth.hash_password(payload.new_password)
    user.password_hash = password_hash
    user.password_salt = salt
    # 재설정 후에는 기존에 로그인돼 있던 모든 세션을 무효화 (탈취된 세션 방지)
    db.query(models.Session).filter(models.Session.user_id == user.id).delete()
    db.commit()
    return {"message": "비밀번호가 재설정되었습니다. 새 비밀번호로 다시 로그인해주세요."}


@router.post("/auth/change-password")
def change_password(
    payload: schemas.PasswordChangeIn,
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    _enforce_rate_limit(
        f"changepw:{_client_ip(request)}:{current_user.id}",
        max_attempts=10,
        window_seconds=600,
        message="시도가 너무 많습니다. 잠시 후 다시 시도해주세요.",
    )
    if not auth.verify_password(
        payload.current_password, current_user.password_hash, current_user.password_salt
    ):
        raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다.")

    password_hash, salt = auth.hash_password(payload.new_password)
    current_user.password_hash = password_hash
    current_user.password_salt = salt
    # 지금 이 세션은 유지하고, 다른 기기/브라우저의 세션만 무효화
    current_token = request.cookies.get(auth.SESSION_COOKIE_NAME)
    db.query(models.Session).filter(
        models.Session.user_id == current_user.id,
        models.Session.token != current_token,
    ).delete()
    db.commit()
    return {"message": "비밀번호가 변경되었습니다."}


@router.post("/auth/change-name", response_model=schemas.UserOut)
def change_name(
    payload: schemas.NameChangeIn,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """기존 계정에는 이름이 없을 수 있어(회원가입에 이름 항목이 없던 시절 가입) 언제든
    직접 설정/수정할 수 있게 별도 엔드포인트로 분리했다 (관리자 사용자 관리 화면에서
    이름으로 검색/식별할 수 있게 하기 위함)."""
    current_user.name = payload.name
    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/auth/me")
def delete_my_account(
    payload: schemas.AccountDeleteIn,
    response: Response,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    if not auth.verify_password(
        payload.password, current_user.password_hash, current_user.password_salt
    ):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    db.delete(current_user)
    db.commit()
    response.delete_cookie(auth.SESSION_COOKIE_NAME)
    return {"message": "계정이 삭제되었습니다."}
