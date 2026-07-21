"""데모 시연용 더미 데이터 생성 스크립트 (로컬 전용).

여러 명의 일반 사용자 + 2주치 건강기록을 만들어서, 관리자 페이지의
검색/페이지네이션/통계/사용자별 기록 조회와, 일반 사용자 화면의
주간 리포트(이번 주 vs 지난 주)를 데모에서 바로 보여줄 수 있게 한다.

기존 계정(예: demo 관리자)은 건드리지 않고, 이미 존재하는 아이디는 건너뛴다.
API로는 노출하지 않고 로컬에서 직접 실행하는 스크립트로만 제공한다.

사용법: python seed_demo_data.py
"""

import json
from datetime import date, timedelta

from database import SessionLocal
import models
import auth
from health_logic import evaluate_record

TODAY = date(2026, 7, 21)  # PROJECT_CONTEXT.md 기준 오늘 날짜로 고정 (재실행해도 항상 같은 데이터)

# (username, password, 프로필 설명) — 프로필별로 서로 다른 BMI/혈압/혈당 분포가 나오게 구성
USERS = [
    "yuna", "minho", "jihoon", "sora", "hana", "doyoon",
    "eunji", "taemin", "somin", "wonwoo", "hyerin", "jaeho",
]
DEFAULT_PASSWORD = "demo1234"

# 사용자별 2주치 기록을 만드는 프로필. 각 항목: 기준 체중/키/혈압/혈당/걸음수/수면 + 하루 변화폭 + 추세
PROFILES = {
    "yuna":    dict(weight=58.0, height=163, systolic=112, diastolic=72, sugar=88,  steps=9500,  sleep=7.5, trend=0.0),
    "minho":   dict(weight=82.0, height=175, systolic=124, diastolic=81, sugar=105, steps=4200,  sleep=6.0, trend=0.0),
    "jihoon":  dict(weight=95.0, height=172, systolic=145, diastolic=92, sugar=130, steps=2500,  sleep=5.2, trend=0.0),
    "sora":    dict(weight=64.0, height=160, systolic=118, diastolic=76, sugar=92,  steps=8000,  sleep=7.0, trend=-0.15),  # 개선 추세(체중 감소)
    "hana":    dict(weight=71.0, height=168, systolic=132, diastolic=85, sugar=110, steps=5200,  sleep=6.5, trend=0.1),   # 악화 추세(체중 증가)
    "doyoon":  dict(weight=68.5, height=174, systolic=115, diastolic=75, sugar=94,  steps=11000, sleep=7.8, trend=0.0),
    "eunji":   dict(weight=55.0, height=158, systolic=108, diastolic=68, sugar=85,  steps=6800,  sleep=8.0, trend=0.0),
    "taemin":  dict(weight=88.0, height=180, systolic=128, diastolic=83, sugar=99,  steps=3600,  sleep=5.8, trend=0.05),
    "somin":   dict(weight=61.0, height=165, systolic=121, diastolic=79, sugar=101, steps=7200,  sleep=6.8, trend=0.0),
    "wonwoo":  dict(weight=79.0, height=177, systolic=138, diastolic=88, sugar=118, steps=4000,  sleep=6.2, trend=0.0),
    "hyerin":  dict(weight=52.0, height=155, systolic=105, diastolic=66, sugar=82,  steps=9800,  sleep=7.6, trend=0.0),
    "jaeho":   dict(weight=90.0, height=173, systolic=150, diastolic=95, sugar=135, steps=2100,  sleep=5.0, trend=-0.2),  # 개선 추세지만 여전히 위험군
}

# 목표를 설정해둘 사용자 (목표 관리 기능 데모용)
GOALS = {
    "minho": dict(target_weight=75.0, target_systolic=118, target_diastolic=78, target_blood_sugar=95),
    "hana": dict(target_weight=65.0, target_systolic=120, target_diastolic=80, target_blood_sugar=95),
    "jihoon": dict(target_weight=80.0, target_systolic=125, target_diastolic=80, target_blood_sugar=100),
}


DEMO_SECURITY_QUESTION = "가장 좋아하는 색은?"
DEMO_SECURITY_ANSWER = "blue"


def get_or_create_user(db, username: str, password: str) -> models.User:
    user = db.query(models.User).filter(models.User.username == username).first()
    if user:
        return user
    password_hash, salt = auth.hash_password(password)
    answer_hash, answer_salt = auth.hash_password(
        auth.normalize_security_answer(DEMO_SECURITY_ANSWER)
    )
    user = models.User(
        username=username,
        password_hash=password_hash,
        password_salt=salt,
        security_question=DEMO_SECURITY_QUESTION,
        security_answer_hash=answer_hash,
        security_answer_salt=answer_salt,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def add_record(db, user: models.User, day: date, profile: dict, day_offset: int) -> None:
    # day_offset은 "며칠 전"(13=가장 오래된 기록, 0=오늘)이므로, trend가 오늘 쪽으로
    # 갈수록(day_offset이 작아질수록) 더 크게 반영되도록 (13 - day_offset)을 곱한다.
    # 그래야 trend<0(예: sora)일 때 실제로 "오늘로 갈수록 체중 감소" 그래프가 나온다
    # (day_offset을 그대로 곱하면 방향이 반대로 나오는 버그가 있었음).
    days_elapsed = 13 - day_offset
    drift = profile["trend"] * days_elapsed
    weight = round(profile["weight"] + drift, 1)
    steps = max(0, profile["steps"] + (day_offset % 3 - 1) * 400)
    sleep_hours = max(0.0, round(profile["sleep"] + (day_offset % 2) * 0.3 - 0.15, 1))

    result = evaluate_record(
        weight, profile["height"], profile["systolic"], profile["diastolic"],
        profile["sugar"], steps, sleep_hours,
    )
    record = models.HealthRecord(
        user_id=user.id,
        date=day.isoformat(),
        weight=weight,
        height=profile["height"],
        systolic=profile["systolic"],
        diastolic=profile["diastolic"],
        blood_sugar=profile["sugar"],
        steps=steps,
        sleep_hours=sleep_hours,
        memo="",
        bmi=result["bmi"],
        bmi_category=result["bmi_category"],
        bp_category=result["bp_category"],
        sugar_category=result["sugar_category"],
        warnings=json.dumps(result["warnings"], ensure_ascii=False),
        activity_level=result["activity_level"],
        sleep_status=result["sleep_status"],
    )
    db.add(record)


def seed() -> None:
    db = SessionLocal()
    try:
        created_users = 0
        created_records = 0
        created_goals = 0

        for username in USERS:
            existing = db.query(models.User).filter(models.User.username == username).first()
            already_existed = existing is not None
            user = get_or_create_user(db, username, DEFAULT_PASSWORD)
            if not already_existed:
                created_users += 1

            has_records = (
                db.query(models.HealthRecord)
                .filter(models.HealthRecord.user_id == user.id)
                .first()
            )
            if not has_records:
                profile = PROFILES[username]
                # 최근 14일 중 3일에 한 번꼴로 기록 (이번 주 3~4건 + 지난 주 3~4건 -> 주간 리포트 비교 가능)
                for day_offset in range(13, -1, -3):
                    day = TODAY - timedelta(days=day_offset)
                    add_record(db, user, day, profile, day_offset)
                    created_records += 1
                db.commit()

            if username in GOALS:
                existing_goal = (
                    db.query(models.Goal).filter(models.Goal.user_id == user.id).first()
                )
                if not existing_goal:
                    db.add(models.Goal(user_id=user.id, **GOALS[username]))
                    db.commit()
                    created_goals += 1

        print(f"완료: 신규 사용자 {created_users}명, 신규 기록 {created_records}건, 신규 목표 {created_goals}건")
        print(f"모든 데모 계정 비밀번호: {DEFAULT_PASSWORD}")
        print(f"모든 데모 계정 보안질문: {DEMO_SECURITY_QUESTION} / 답: {DEMO_SECURITY_ANSWER}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
