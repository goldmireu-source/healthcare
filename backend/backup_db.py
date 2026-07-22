"""SQLite DB 백업 스크립트 (로컬 전용).

data/health_log.db를 타임스탬프가 붙은 파일로 backups/ 디렉토리에 복사하고,
오래된 백업은 개수 기준으로 자동 정리한다. 단순 파일 복사 대신 sqlite3의
온라인 백업 API(Connection.backup())를 쓴다 - 서버가 켜져 있어 DB가 쓰기
도중이어도(트랜잭션 중간) 일관된 스냅샷을 뜨기 위함이며, 파일을 그대로
복사하면 손상된 백업이 나올 수 있다.

사용법:
    python backup_db.py                # 기본 설정으로 1회 백업 (최근 14개만 보관)
    python backup_db.py --keep 30      # 최근 30개만 보관

이 스크립트는 로컬에서 수동/1회 실행만 확인한다 - 주기적 실행을 위한
cron(리눅스)/작업 스케줄러(Windows) 등록은 실제 배포 단계에서 별도로 진행한다
(AWS Lightsail 배포와 함께 처리될 서버 운영 작업이라 이번 범위에서 제외).
"""
import argparse
import os
import sqlite3
from datetime import datetime, timezone

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_DIR = os.path.join(BACKEND_DIR, "..", "data")
DEFAULT_BACKUP_DIR = os.path.join(BACKEND_DIR, "..", "backups")

_BACKUP_PREFIX = "health_log_"
_BACKUP_SUFFIX = ".db"


def backup_database(db_dir: str, backup_dir: str, keep: int) -> str:
    db_path = os.path.join(db_dir, "health_log.db")
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DB 파일을 찾을 수 없습니다: {db_path}")

    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"{_BACKUP_PREFIX}{timestamp}{_BACKUP_SUFFIX}")

    source = sqlite3.connect(db_path)
    dest = sqlite3.connect(backup_path)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()

    deleted = _cleanup_old_backups(backup_dir, keep)
    return backup_path, deleted


def _cleanup_old_backups(backup_dir: str, keep: int) -> list:
    """파일명이 YYYYMMDD_HHMMSS라 문자열 정렬 = 시간 순 정렬이 성립한다."""
    backups = sorted(
        f for f in os.listdir(backup_dir)
        if f.startswith(_BACKUP_PREFIX) and f.endswith(_BACKUP_SUFFIX)
    )
    to_delete = backups[:-keep] if keep > 0 and len(backups) > keep else []
    for name in to_delete:
        os.remove(os.path.join(backup_dir, name))
    return to_delete


def main():
    parser = argparse.ArgumentParser(description="SQLite DB 백업 (로컬 전용)")
    parser.add_argument("--db-dir", default=os.getenv("DB_DIR", DEFAULT_DB_DIR))
    parser.add_argument("--backup-dir", default=os.getenv("BACKUP_DIR", DEFAULT_BACKUP_DIR))
    parser.add_argument("--keep", type=int, default=14, help="보관할 최근 백업 개수 (기본 14개, 0이면 무제한 보관)")
    args = parser.parse_args()

    backup_path, deleted = backup_database(args.db_dir, args.backup_dir, args.keep)
    print(f"백업 완료: {backup_path}")
    if deleted:
        print(f"오래된 백업 {len(deleted)}개 정리됨: {', '.join(deleted)}")


if __name__ == "__main__":
    main()
