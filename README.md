# 마이 헬스 로그 API

매일 기록하는 몸무게·혈압·혈당 같은 건강 수치를 던져주면, 서버가 BMI를 계산하고 건강 상태를 분류하고 필요한 경고까지 알려주는 개인용 건강 기록 API입니다. 기록이 쌓이면 통계와 주간 리포트로 변화 추이도 확인할 수 있습니다.

## 기능 목록

### 필수 기능

| 메서드 · 경로 | 설명 |
|---|---|
| `POST /records` | 건강 기록 추가. 저장 후 BMI·분류·경고를 계산해 응답 |
| `GET /records` | 전체 기록 조회 (개수 포함, `username` 쿼리로 필터 가능) |
| `GET /records/{id}` | 기록 하나 조회. 없으면 404 |
| `PUT /records/{id}` | 기록 수정 (수정 시 BMI/분류/경고 재계산) |
| `DELETE /records/{id}` | 기록 삭제 |
| `GET /search?start=&end=` | 날짜 범위로 검색 |
| `GET /stats` | 평균 체중·BMI·혈압·혈당·걸음수·수면 및 분류별 분포 통계 |

### 고도화 기능

| 메서드 · 경로 | 설명 |
|---|---|
| `POST /goals` | 목표 체중/혈압/혈당 설정 |
| `GET /goals` | 최신 기록 기준 목표 달성 여부 조회 |
| `GET /reports/weekly` | 최근 7일 평균 vs 지난주 평균 비교 |

또한 모든 기록 응답에는 걸음 수 기반 **활동량 등급**(`activity_level`: 부족/적정/우수)과 수면 시간 기반 **수면 분석**(`sleep_status`: 부족/적정/과다)이 자동으로 포함됩니다. `username` 필드로 여러 사용자의 기록을 분리해서 관리할 수 있습니다 (미지정 시 `default` 사용자로 처리).

### 분류 기준 (학습용으로 단순화된 값이며 실제 의학적 진단이 아닙니다)

- **BMI**: 18.5 미만 저체중 · 18.5~22.9 정상 · 23~24.9 과체중 · 25 이상 비만
- **혈압**: 수축기<120 & 이완기<80 정상 · 120~139/80~89 주의 · 140↑/90↑ 고혈압
- **공복혈당**: 100 미만 정상 · 100~125 공복혈당장애 · 126 이상 당뇨 의심

## 기술 스택

- **FastAPI** — REST API 프레임워크
- **SQLAlchemy + SQLite** — 파일 기반 DB (컨테이너/서버 재시작해도 데이터 유지)
- **Pydantic v2** — 요청/응답 데이터 검증
- **Docker** — 컨테이너 실행

### DB 테이블 구조

- `users` — 사용자 구분 (`username`)
- `health_records` — 건강 기록 원본 값 + 서버가 계산한 BMI/분류/경고/활동량/수면 상태
- `goals` — 사용자별 목표 체중/혈압/혈당

## 실행 방법

### 로컬 실행

```bash
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

브라우저에서 http://127.0.0.1:8000/docs 접속 후 테스트합니다.

### Docker 실행

```bash
docker build -t health-log-api .
docker run -d -p 8000:8000 -v $(pwd)/data:/app/data --name health-log-api health-log-api
```

http://localhost:8000/docs 접속.

> `-v $(pwd)/data:/app/data` 로 볼륨을 연결하면 컨테이너를 재생성해도 sqlite 데이터가 유지됩니다.

## 배포 접속 URL

(배포 완료 후 추가 예정)

## 참고

수업 자료와 실습 워크북을 참고해 구현했습니다.
