"""기존 계정을 관리자로 승격시키는 로컬 전용 스크립트.

API로는 절대 노출하지 않음 (회원가입으로는 언제나 role="user"로만 생성됨).
반드시 서버가 접근 가능한 환경(로컬/서버 콘솔)에서 직접 실행해야 함.

사용법: python promote_admin.py <username>
"""

import sys

from database import SessionLocal
import models


def promote(username: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user:
            print(f"'{username}' 계정을 찾을 수 없습니다.")
            return
        if user.role == "admin":
            print(f"'{username}'은(는) 이미 관리자입니다.")
            return
        user.role = "admin"
        db.commit()
        print(f"'{username}' 계정을 관리자로 승격했습니다.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용법: python promote_admin.py <username>")
        sys.exit(1)
    promote(sys.argv[1])
