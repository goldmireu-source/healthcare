"""admin_analytics.compute_cohort_retention() 단위 테스트.

API 계층 없이 순수 함수를 직접 호출 - compute_admin_analytics()와 같은 스타일로
설계된 함수라, DB/세션 없이 models.User/HealthRecord를 메모리에서만 구성해서
날짜 산술이 정확한지(특히 "아직 도래하지 않은 주"는 None, 코호트 경계는
월요일 기준인지)를 검증한다.
"""

from datetime import date, datetime, timedelta

import models
from admin_analytics import compute_cohort_retention


def _user(user_id: int, created_at: datetime) -> models.User:
    u = models.User()
    u.id = user_id
    u.created_at = created_at
    return u


def _record(user_id: int, date_str: str) -> models.HealthRecord:
    r = models.HealthRecord()
    r.user_id = user_id
    r.date = date_str
    return r


def test_cohort_buckets_by_monday_and_computes_week0_retention():
    # 코호트 A 시작 = 임의의 월요일. user1은 그 주(week 0)에 기록 있음, user2는 기록 없음.
    cohort_a_monday = date(2026, 1, 5)  # 2026-01-05는 월요일
    assert cohort_a_monday.weekday() == 0

    users = [
        _user(1, datetime(2026, 1, 6, 9, 0)),  # 화요일 가입 -> 코호트 시작은 여전히 월요일(1/5)
        _user(2, datetime(2026, 1, 5, 9, 0)),
    ]
    records = [
        _record(1, "2026-01-07"),  # week 0 안 (1/5~1/11)
    ]

    today = cohort_a_monday + timedelta(days=3)  # week 0만 도래, week1 이후는 미도래
    rows = compute_cohort_retention(users, records, today=today, max_week_offset=3)

    assert len(rows) == 1
    row = rows[0]
    assert row.cohort_start == "2026-01-05"
    assert row.cohort_size == 2
    assert row.retention_by_week[0] == 50.0  # 2명 중 1명만 그 주에 기록
    assert row.retention_by_week[1] is None  # 아직 도래하지 않음
    assert row.retention_by_week[2] is None
    assert row.retention_by_week[3] is None


def test_cohort_retention_across_multiple_weeks_and_cohorts():
    cohort_a_monday = date(2026, 1, 5)
    cohort_b_monday = cohort_a_monday + timedelta(days=7)  # 2026-01-12

    users = [
        _user(1, datetime(2026, 1, 5, 9, 0)),  # 코호트 A
        _user(2, datetime(2026, 1, 6, 9, 0)),  # 코호트 A
        _user(3, datetime(2026, 1, 12, 9, 0)),  # 코호트 B
    ]
    records = [
        _record(1, "2026-01-06"),  # user1: week0
        _record(1, "2026-01-13"),  # user1: week1
        _record(3, "2026-01-13"),  # user3: week0 (코호트 B 기준)
    ]

    # 코호트 A의 week0/week1은 도래, week2/3은 미도래. 코호트 B는 week0만 도래.
    today = cohort_a_monday + timedelta(days=10)
    rows = compute_cohort_retention(users, records, today=today, max_week_offset=3)

    assert [r.cohort_start for r in rows] == ["2026-01-05", "2026-01-12"]

    cohort_a, cohort_b = rows
    assert cohort_a.cohort_size == 2
    assert cohort_a.retention_by_week[0] == 50.0  # user1만 활동 (2명 중 1명)
    assert cohort_a.retention_by_week[1] == 50.0  # user1만 week1에도 활동
    assert cohort_a.retention_by_week[2] is None
    assert cohort_a.retention_by_week[3] is None

    assert cohort_b.cohort_size == 1
    assert cohort_b.retention_by_week[0] == 100.0  # user3 혼자라 100%
    assert cohort_b.retention_by_week[1] is None  # 코호트 B 기준 week1은 아직 미도래


def test_cohort_retention_empty_when_no_users():
    assert compute_cohort_retention([], [], today=date(2026, 1, 1)) == []
