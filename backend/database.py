import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# backend/와 data/는 항상 형제 폴더 (로컬 저장소 구조, Dockerfile 모두 이 배치를 유지함).
# __file__ 기준 경로라 uvicorn을 어느 위치에서 실행하든(backend/ 안에서든, 리포 루트에서든)
# 항상 같은 data/ 디렉토리를 가리킨다.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_DIR = os.path.join(BACKEND_DIR, "..", "data")

# 컨테이너/서버 환경에서도 데이터가 남도록 data/ 디렉토리에 sqlite 파일로 저장
DB_DIR = os.getenv("DB_DIR", DEFAULT_DB_DIR)
os.makedirs(DB_DIR, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_DIR}/health_log.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
