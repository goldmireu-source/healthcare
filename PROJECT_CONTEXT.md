# 프로젝트 컨텍스트 — 마이 헬스 로그 API

> 이 파일은 Claude(채팅) / Claude Code(VS Code) 등 어떤 세션에서 작업하든
> 프로젝트 요구사항과 현재 진행 상황을 파악할 수 있도록 정리한 문서입니다.
> 새 세션에서 작업을 시작할 때 이 파일을 먼저 읽어주세요.

## 0. 작업 원칙 (사용자 지시사항 — 반드시 준수)

프로젝트 시작 시 사용자가 명시적으로 정한 작업 방침입니다. 이후 어떤 세션에서
작업하든 아래 원칙을 벗어나지 않아야 합니다.

1. **로컬 우선 진행**: 항상 로컬에서 먼저 세팅하고 동작을 완전히 확인한 뒤에만
   서버(AWS Lightsail)에 배포한다. 검증 안 된 상태로 바로 서버에 올리지 않는다.
2. **DB 테이블은 전체 서비스 관점에서 설계**: 과제 명세서의 필수 요건(JSON 파일 저장)에
   머무르지 않고, 서비스 전체 맥락을 고려해 DB 테이블 항목을 판단해서 추가한다.
   → 이 판단에 따라 SQLite 3테이블(users/health_records/goals) 구조로 이미 설계함 (4번 항목 참고).
3. **고도화 기능은 Claude가 자율적으로 추천·구현**: 매번 사용자에게 어떤 기능을 넣을지 묻지 않고
   판단해서 추천하고 구현해나간다.
   - (2026-07-21 갱신) "너무 무겁지 않은 선"이라는 제약은 사용자 지시로 **삭제됨**. 이제는
     첨부 PDF 명세를 넘어서 **실제 서비스와 동일한 수준**으로 화면·기능을 고도화하는 것이 목표.
   - 고도화 로드맵 (우선순위 순):
     1. **인증 시스템** (완료) — 회원가입/로그인, 세션 쿠키(PBKDF2 해시, 표준 라이브러리만 사용,
        추가 의존성 없음), `sessions` 테이블. 더 이상 자유 텍스트 `username`으로 남의 데이터에
        접근 불가. 로그인한 사용자 본인 데이터만 조회/수정. `/records`, `/search`, `/stats`,
        `/goals`, `/reports/weekly` 전부 로그인 필요.
     2. **데이터 시각화** (미착수) — 체중/혈압/혈당 추이를 보여주는 트렌드 차트
     3. **UX 디테일** (부분 완료) — alert/confirm 대신 토스트 알림 적용 완료. 로딩 상태,
        페이지네이션은 아직 미착수
     4. **배포 관점 보강** (부분 완료) — `/health` 헬스체크 엔드포인트 추가 완료. 환경변수 기반
        설정(`COOKIE_SECURE` 등 일부만), 보안 헤더는 미착수
4. **인프라는 이미 준비되어 있음, 처음부터 만들지 않음**:
   - GitHub 계정 + 저장소 이미 생성됨 → https://github.com/goldmireu-source/healthcare (연결 완료, push까지 완료)
   - AWS 계정 + Lightsail 테스트 서버 이미 생성됨 → 배포 단계에서 새로 만들지 말고 기존 서버 사용
   - 즉, "계정 생성"이나 "저장소 최초 생성" 같은 처음 단계는 스킵하고 바로 실제 구현/배포 작업으로 들어간다.

## 1. 과제 개요

**과제명**: 마이 헬스 로그 API (FastAPI & Docker 미니 프로젝트, 개인 과제)

매일의 건강 수치(몸무게·키·혈압·혈당 등)를 기록하면, 서버가 BMI를 자동 계산하고
건강 상태를 분류하며, 쌓인 기록으로 통계를 제공하는 API. Docker로 실행 가능해야 함.

- 진행 기간: 4일 (Day1 세팅&CRUD / Day2 헬스케어 로직 / Day3 검색·통계·저장 / Day4 Docker&제출)
- 제출물: GitHub 저장소 URL + README
- 학습용 프로젝트: 건강 분류 기준은 단순화된 값이며 실제 의학적 진단 아님

## 2. 필수 요구사항 — 엔드포인트 7개

| 메서드·경로 | 요구 동작 |
|---|---|
| POST /records | 건강 기록 추가. BMI·분류·경고 계산해 응답 |
| GET /records | 전체 기록 조회 (개수 포함) |
| GET /records/{id} | 기록 하나 조회. 없으면 404 |
| PUT /records/{id} | 기록 수정 |
| DELETE /records/{id} | 기록 삭제 |
| GET /search?start=&end= | 날짜 범위 검색 |
| GET /stats | 평균 체중 등 통계 반환 |

공통 요구사항: Pydantic 검증 / 재시작해도 데이터 유지 / `/docs`에서 전체 테스트 가능 / 예외로 서버 죽지 않을 것

## 3. 데이터 구조 & 분류 기준

**필드**: date, weight, height, systolic, diastolic, blood_sugar, steps/sleep_hours/memo(선택)
**응답 추가 필드**: bmi, bmi_category, bp_category, sugar_category, warnings

| 항목 | 구간 | 분류 |
|---|---|---|
| BMI | 18.5 미만 / 18.5~22.9 / 23~24.9 / 25 이상 | 저체중 / 정상 / 과체중 / 비만 |
| 혈압 | 수축기<120&이완기<80 / 120~139 or 80~89 / ≥140 or ≥90 | 정상 / 주의 / 고혈압 |
| 공복혈당 | 100 미만 / 100~125 / 126 이상 | 정상 / 공복혈당장애 / 당뇨 의심 |

경고(warnings): BMI 비만, 혈압 고혈압, 혈당 당뇨의심 시 각각 경고 메시지 추가. 해당 없으면 빈 배열.

## 4. 설계 결정 (기존 명세 + 사용자 요청 반영)

- **DB**: 단순 JSON 파일 대신 **SQLite + SQLAlchemy** 사용 (재시작해도 유지되는 요건은 동일하게 충족, 서비스 전체를 고려한 테이블 구조 요청 반영)
  - `users` — 계정 (username, password_hash, password_salt)
  - `sessions` — 로그인 세션 토큰 (쿠키엔 토큰만, 실제 세션 정보는 서버 DB)
  - `health_records` — 건강 기록 원본 값 + 서버 계산 결과(bmi/분류/경고/활동량등급/수면상태)
  - `goals` — 사용자별 목표 체중/혈압/혈당
- **고도화 기능** (과제 "추가 도전" 목록을 넘어, 실제 서비스 수준으로 확장):
  1. **인증 시스템** — 회원가입/로그인/로그아웃, PBKDF2 비밀번호 해시, DB 기반 세션 토큰(HttpOnly 쿠키). 자유 텍스트 username 대신 실제 계정으로 로그인해야 본인 데이터에 접근 가능
  2. 목표 관리 (`POST/GET /goals` — 목표 대비 최신 기록 달성 여부)
  3. 주간 리포트 (`GET /reports/weekly` — 최근 7일 vs 지난주 평균 비교)
  4. **사용자용 웹 화면** (`/app`) — 순수 HTML/CSS/JS 단일 파일(`static/index.html`), 별도 빌드 없이 기존 REST API 호출. 로그인/회원가입 화면 + 기록 입력/조회/수정/삭제, 검색, 통계, 목표, 주간 리포트, 토스트 알림. 루트(`/`)는 `/app`으로 자동 리다이렉트, API 상태 확인용 JSON은 `/api`로, 헬스체크는 `/health`로 이동.
     (※ 처음엔 "무겁지 않게"라는 기준으로 웹 화면·인증 모두 스킵했으나, 사용자 피드백으로 원칙 0-3번이 갱신되며 순차적으로 추가함)
  - 걸음 수 등급(`activity_level`)·수면 분석(`sleep_status`)은 별도 엔드포인트 없이 모든 기록 응답에 자동 포함

## 5. 파일 구조

```
healthcare/
├── main.py           # FastAPI 앱, 라우트 전체 (인증 포함)
├── auth.py            # 비밀번호 해시(PBKDF2) + 세션 토큰 관리
├── models.py          # SQLAlchemy ORM (User, Session, HealthRecord, Goal)
├── schemas.py         # Pydantic 요청/응답 모델 (UserSignup/UserLogin 포함)
├── database.py        # DB 연결/세션 설정 (SQLite, data/health_log.db)
├── health_logic.py     # BMI/혈압/혈당 계산·분류·경고·활동량·수면 로직
├── static/
│   └── index.html      # 사용자용 웹 화면 (/app 에 마운트됨)
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .gitignore
└── README.md
```

## 6. 진행 상황 (지금까지 완료된 것)

- [x] Day1~3: 핵심 로직 + DB 설계 + 필수 엔드포인트 7개 구현 완료
- [x] 로컬 uvicorn 실행 테스트 완료 — `/docs`에서 정상 동작 확인
  - 비만/고혈압/당뇨의심 케이스 경고 메시지까지 정확히 계산됨을 확인
  - 서버 재시작 후 데이터 유지 확인 (SQLite 파일 기반)
  - 404, 422 검증 오류 정상 처리 확인
- [x] GitHub 저장소 연결 및 push 완료 — repo: https://github.com/goldmireu-source/healthcare (main 브랜치)
- [x] VS Code + Claude Code 확장 설치 완료, 가상환경(venv) 활성화됨
- [x] 사용자용 웹 화면(`/app`) 추가 완료 — 순수 HTML/CSS/JS, 기록 CRUD/검색/통계/목표/주간리포트 UI로 사용 가능, 로컬 테스트 완료
- [x] **인증 시스템 구현 완료** (2026-07-21) — `auth.py` 신설, `models.py`(User에 password_hash/salt 추가, Session 테이블 신설), `schemas.py`(UserSignup/UserLogin/UserOut 추가), `main.py`(모든 데이터 엔드포인트에 `Depends(auth.get_current_user)` 적용, username 쿼리 파라미터 전부 제거), `static/index.html`(로그인/회원가입 화면, 로그아웃 버튼, 토스트 알림 추가)
  - curl로 전체 흐름 검증 완료: 미인증 401 / 회원가입·로그인 성공 / 사용자간 데이터 완전 분리 / 중복 아이디 409 / 오답 비밀번호 401 / 로그아웃 후 세션 무효화
  - `/health` 헬스체크 엔드포인트 추가
  - **⚠️ DB 스키마가 바뀌어서 기존 `data/health_log.db` 파일은 삭제하고 재생성해야 함** (마이그레이션 아님, 로컬이라 그냥 삭제 후 재시작)

## 7. 다음 작업

1. **(최우선)** 로컬 F:\healthcare에 아래 변경된/신규 파일 반영 후 기존 `data/health_log.db` 삭제, 재실행하여 브라우저로 회원가입→로그인→기록 CRUD 전체 흐름 직접 확인
   - 신규: `auth.py`
   - 수정: `main.py`, `models.py`, `schemas.py`, `static/index.html`, `README.md`
2. 확인되면 git add/commit/push
3. Docker 빌드 & 실행 확인
   - `docker build -t health-log-api .`
   - `docker run -d -p 8000:8000 -v F:\healthcare\data:/app/data --name health-log-api health-log-api`
   - http://localhost:8000 (자동으로 `/app`으로 이동) 에서 컨테이너 기준 재테스트
   - 문제 있으면 `docker logs health-log-api`
4. 이어서 고도화 로드맵 2번(데이터 시각화 차트), 3번 잔여(로딩 상태/페이지네이션) 진행

## 8. 이후 계획 (미착수)

- AWS Lightsail 테스트 서버에 배포 (계정/서버는 이미 생성되어 있음, 접속 정보는 작업 시점에 확인 필요)
  - 배포 시 `COOKIE_SECURE=true` 환경변수 설정 권장 (HTTPS 적용 시)
- 배포 후 README.md의 "배포 접속 URL" 항목 채우기
- 최종 git push 및 제출 체크리스트 확인 (venv/data.json 미포함, README 완성 등)

## 9. 유의사항

- 코드 스스로 작성 원칙 — 참고 자료 활용 시 README에 명시
- venv/, data/, __pycache__ 는 .gitignore로 제외되어 있어 커밋되지 않음 (정상)
- 건강 분류 기준은 학습용 단순화 값, 실제 진단 아님
