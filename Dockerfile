FROM python:3.12-slim

WORKDIR /app

# 패키지 캐시 활용을 위해 requirements 먼저 복사
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# sqlite 데이터 파일이 저장될 디렉토리
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
