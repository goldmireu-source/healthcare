FROM python:3.12-slim

WORKDIR /app

# 패키지 캐시 활용을 위해 requirements 먼저 복사
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 소스 복사 — 로컬 저장소와 동일하게 backend/, frontend/를 형제 폴더로 유지
# (main.py가 __file__ 기준 상대경로로 frontend/static, ../data를 찾음)
COPY backend/ backend/
COPY frontend/ frontend/

# sqlite 데이터 파일이 저장될 디렉토리
RUN mkdir -p /app/data

EXPOSE 8000

WORKDIR /app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
