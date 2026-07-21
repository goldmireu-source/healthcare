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
  5. **관리자 페이지 / 유저 페이지 분리** (2026-07-21 추가, 이후 같은 날 기능 확장) — User에 `role`("user"/"admin", 기본값 "user") 추가. 회원가입으로는 절대 관리자가 될 수 없고, 로컬 스크립트 `promote_admin.py <username>` 실행으로만 기존 계정을 승격 가능 (사용자 확인 결과 화면에서의 승격/강등 UI는 추가하지 않기로 함 — 보안 원칙 유지). 화면은 `static/admin.html`을 index.html과 완전히 별도 파일로 분리 — 로드 시 `/auth/me`로 role 확인 후 관리자가 아니면 즉시 `/app/`로 리다이렉트(클라이언트 사이드 가드; 실제 보안 경계는 서버의 403). index.html 헤더에는 로그인한 사용자가 관리자일 때만 "관리자 페이지" 링크가 보임.
     - 관리자 전용 API: `GET /admin/users`(아이디 검색 `search` + 페이지네이션 `page`/`page_size` 지원), `GET /admin/stats`(전체 사용자 통계), `GET /admin/users/{id}/records`(특정 사용자 기록 읽기 전용 조회), `DELETE /admin/users/{id}`(계정 삭제, cascade로 기록/목표/세션도 함께 삭제, 자기 자신은 삭제 불가 400), `POST /admin/users/{id}/force-logout`(계정은 유지한 채 세션만 전부 무효화, 자기 자신 대상 불가 400) — 전부 `get_current_admin` 의존성(비관리자 403)으로 보호
     - `AuditLog` 테이블 신설 — 관리자의 계정 삭제/강제 로그아웃 조치를 기록(조치자/조치 종류/대상/시각). `GET /admin/audit-log`로 조회, admin.html에 활동 로그 테이블로 표시
     - admin.html에 사용자별 "기록 보기"(모달 없이 하단에 펼침), 검색창, 페이지네이션, `/health` 기반 서버 상태 배지 추가
     - **(2026-07-21, 세 번째 후속 수정) 관리자 페이지 자체 로그인 화면 추가** — 원래는 관리자도 유저 페이지(index.html)에서 로그인한 뒤 "관리자 페이지" 링크로 넘어가는 구조였는데, 사용자 피드백으로 "관리자는 유저 페이지를 거치지 않고 바로 admin.html에서 로그인해야 한다"는 게 명확해져서 admin.html에 독립적인 로그인 폼을 추가함. 로그인 안 된 상태로 `/app/admin.html` 접속 시 더 이상 `/app/`로 리다이렉트하지 않고 이 페이지 안에서 바로 로그인 가능. 로그인 성공했는데 role이 admin이 아니면(일반 유저가 실수로 이 폼에 로그인한 경우) 그 세션은 즉시 로그아웃 처리하고 안내 메시지만 표시. 로그아웃도 더 이상 `/app/`로 이동하지 않고 이 페이지의 로그인 화면으로 돌아옴. 겸사겸사 이 페이지에 남아있던 native `confirm()`(강제 로그아웃/계정 삭제)도 index.html과 동일한 커스텀 모달로 교체함
     - **더미데이터**: `seed_demo_data.py` 신설 — 일반 사용자 12명 + 최근 2주간 건강기록(사용자당 5건, 이번 주/지난 주 걸쳐 분포) + 목표 3건 생성. 프로필별로 정상/과체중/비만, 정상/주의/고혈압, 정상/공복혈당장애/당뇨의심이 고르게 섞이도록 구성해 관리자 통계 분포와 개별 사용자 주간 리포트(개선/악화 추세 포함)를 데모에서 바로 보여줄 수 있음. 기존 계정은 건드리지 않고 없는 아이디만 생성하므로 재실행해도 안전.
  6. **사용자 페이지(index.html) 계정 관리 기능 보강** (2026-07-21, 같은 날 후속 작업) — "사용자 페이지에도 상식적으로 있을 법한 기능이 다 있나?" 질문에 대한 갭 분석 후 구현
     - 비밀번호 변경 (`POST /auth/change-password`, 로그인 필요, 현재 비밀번호 확인 후 변경. 변경 후 현재 세션은 유지하고 다른 기기 세션만 무효화)
     - **비밀번호 찾기 — 보안질문 방식** (이메일/SMS 인프라가 없어 실제 이메일 발송 방식은 불가능하다고 판단, 사용자 확인 후 이 방식으로 결정): 회원가입 시 보안질문(4개 프리셋 중 선택)/답을 필수로 입력받아 PBKDF2로 해시 저장(`User.security_question`, `security_answer_hash`, `security_answer_salt`). `GET /auth/security-question?username=`으로 질문 조회 → `POST /auth/reset-password`로 답 확인 후 재설정. 답은 대소문자/공백 정규화 후 비교. 재설정 시 기존 세션 전부 무효화
     - 계정 탈퇴 (`DELETE /auth/me`, 비밀번호 재확인 필요) — 본인 기록/목표/세션 cascade 삭제, 관리자 계정도 본인 탈퇴는 막지 않음(관리자 패널의 "자기 자신 삭제 방지"는 어드민이 목록에서 남을 지우다 실수하는 걸 막기 위한 것과는 별개의 의도적 셀프서비스 액션)
     - 기록 삭제 확인창을 브라우저 기본 `confirm()`에서 커스텀 모달로 교체 (PROJECT_CONTEXT.md에 "confirm 대신 토스트 적용 완료"라고 돼 있었지만 실제 코드에는 confirm이 남아있던 걸 발견해 수정함)
     - 기록 목록에 페이지네이션 추가 (클라이언트 사이드 — 개인 기록은 규모가 크지 않아 서버 사이드로 안 가고, `/records`는 그대로 전체를 받아 최신 측정값 계산에 계속 사용)
     - 헤더에 "계정 설정" 버튼 추가 (비밀번호 변경 + 계정 탈퇴 모달)
     - 데이터 시각화 차트, 로딩 상태 표시는 여전히 미착수 (기존 로드맵 항목 유지)
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
│   ├── index.html      # 사용자용 웹 화면 (/app 에 마운트됨)
│   └── admin.html      # 관리자 전용 화면 (/app/admin.html, index.html과 완전 분리)
├── promote_admin.py    # 로컬 전용: 기존 계정을 관리자로 승격 (API로는 노출 안 함)
├── seed_demo_data.py   # 로컬 전용: 데모 시연용 사용자 12명 + 2주치 건강기록/목표 생성
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
  - git commit(`c9322b1`) 및 push 완료
- [x] **관리자 페이지 / 유저 페이지 분리 구현 완료** (2026-07-21)
  - `models.py`: User에 `role` 컬럼 추가(기본값 "user")
  - `schemas.py`: `UserOut.role` 추가, `AdminUserOut`/`AdminUsersOut`/`AdminStatsOut` 신설
  - `auth.py`: `get_current_admin` 의존성 추가 (비관리자 403)
  - `main.py`: 관리자 전용 엔드포인트 4종 추가 — `GET /admin/users`, `GET /admin/stats`, `GET /admin/users/{id}/records`, `DELETE /admin/users/{id}`(cascade 삭제)
  - `promote_admin.py` 신규 — 로컬 전용 관리자 승격 스크립트. 회원가입으로는 role이 항상 "user"로 고정 생성되어 API로는 절대 관리자가 될 수 없음
  - `static/admin.html` 신규 — index.html과 완전 분리된 관리자 화면, 동일 디자인 톤 재사용. 로드 시 `/auth/me`로 role 확인 후 비관리자면 `/app/`로 즉시 리다이렉트
  - `static/index.html` — 헤더에 관리자에게만 보이는 "관리자 페이지" 링크 추가
  - **DB 스키마 변경**(role 컬럼) → 기존 `data/health_log.db` 삭제 후 재생성함
  - 로컬 uvicorn 기준 전체 흐름 curl 테스트 완료: demo 회원가입(role=user) → `/admin/*` 403 확인 → `promote_admin.py demo` 승격 → 재로그인 시 role=admin 확인 → `GET /admin/users`/`GET /admin/stats` 정상 응답 → 임시 테스트 계정으로 기록/목표 생성 후 `DELETE /admin/users/{id}` 호출 → users/health_records/goals/sessions 전부 cascade 삭제됨을 DB에서 직접 확인 (테스트 후 더미 데이터 남기지 않음)
  - **⚠️ 브라우저 리다이렉트는 클라이언트 JS 로직**이라 curl로는 실제 브라우저 동작까지 확인 불가 (코드 리뷰 + `/auth/me` role 응답으로 간접 검증). 실사용 전 브라우저에서 한 번 더 확인 권장
- [x] **관리자 페이지 기능 확장 + 데모 더미데이터 생성 완료** (2026-07-21, 같은 날 후속 작업)
  - 사용자 확인: 관리자 승격/강등은 화면에 노출하지 않고 CLI(`promote_admin.py`)로만 유지하기로 결정
  - 추가 구현: 사용자별 기록 보기 UI, 아이디 검색, 페이지네이션, 강제 로그아웃(세션만 무효화), 관리자 활동 감사 로그(`AuditLog` 테이블 + `GET /admin/audit-log`), 서버 상태 배지, 자기 자신 삭제/강제로그아웃 방지 가드(400)
  - `seed_demo_data.py`로 일반 사용자 12명 + 2주치 기록 60건 + 목표 3건 생성 (기존 계정은 건드리지 않음, 재실행 안전)
  - 로컬 fresh uvicorn 기준 전체 기능 curl 테스트 완료, 서버 로그 에러 없음: 페이지네이션(13명 → 10+3) / 검색(부분일치·미존재 모두 확인) / 관리자 통계 분포 / 특정 사용자 기록 조회 / 강제 로그아웃 후 기존 세션 401 확인 / 자기 자신 대상 삭제·강제로그아웃 400 확인 / 실제 계정(taemin) 삭제로 cascade 확인 후 데모 데이터셋 복구를 위해 시드 스크립트 재실행
  - **⚠️ 로컬 uvicorn `--reload`가 Windows에서 일부 코드 변경을 반영하지 못하고 이전 워커 프로세스를 계속 쓰는 현상을 겪음** (로그에는 "Reloading..."이 찍혔지만 워커 PID가 그대로였음). 코드를 여러 번 수정한 뒤에는 `--reload` 없이 완전히 새 프로세스로 재시작해서 반영 여부를 반드시 재확인할 것
- [x] **사용자 페이지 계정 관리 기능 구현 완료** (2026-07-21, 같은 날 후속 작업) — 비밀번호 변경/찾기(보안질문)/계정 탈퇴, confirm→커스텀 모달 교체, 기록 목록 페이지네이션
  - `models.py`: User에 `security_question`/`security_answer_hash`/`security_answer_salt` 추가 (필수 컬럼 → DB 재생성 필요했음)
  - `schemas.py`/`auth.py`/`main.py`: `UserSignup`에 보안질문 필드 추가, `normalize_security_answer`(대소문자/공백 정규화) 헬퍼, `GET /auth/security-question`, `POST /auth/reset-password`, `POST /auth/change-password`, `DELETE /auth/me` 추가
  - `seed_demo_data.py`: 시드 계정들도 보안질문("가장 좋아하는 색은?"/"blue") 갖도록 반영
  - `static/index.html`: 계정 설정 모달(비밀번호 변경/탈퇴), 로그인 화면에 비밀번호 찾기 2단계 폼(보안질문 확인 → 재설정), 회원가입 폼에 보안질문 선택(프리셋 4종)+답 입력 추가, 기록 삭제 확인을 커스텀 모달로 교체, 기록 테이블 페이지네이션(클라이언트 사이드, 10건/페이지)
  - DB 삭제 후 재생성 → demo 계정 재가입(보안질문 포함)+재승격, `seed_demo_data.py` 재실행으로 데모 데이터셋 복구
  - curl로 전체 새 기능 테스트 완료: 보안질문 조회(존재/미존재), 재설정 오답 401·정답 200(대소문자·공백 정규화 확인)·재설정 후 구비밀번호 로그인 401·신비밀번호 로그인 200, 비밀번호 변경 오답 401·정답 200(변경 후 현재 세션 유지 확인), 계정 탈퇴 오답 401·정답 200(cascade로 기록/세션 삭제 확인, 탈퇴 후 같은 쿠키 401)
  - 기존 기능 회귀 테스트도 함께 통과: 관리자 페이지네이션/검색/통계, 일반 사용자 기록·주간리포트, 정적 페이지 서빙, 서버 로그 에러 없음
  - JS 문법은 Node `--check`로 두 화면 모두 파싱 오류 없음을 확인했으나, 실제 브라우저 동작(모달 열림/닫힘, 폼 흐름)은 직접 확인 못 함 — 브라우저에서 한 번 더 확인 권장
  - **⚠️ curl `-d`로 한글이 포함된 JSON을 인라인으로 보내면 인코딩이 깨지는 경우가 있었음** ("There was an error parsing the body"). 한글 포함 payload는 UTF-8로 파일에 먼저 쓰고 `--data-binary @file`로 보낼 것

## 7. 다음 작업

1. Docker 빌드 & 실행 확인 (role/관리자 확장 기능이 반영된 최신 코드 기준으로 재빌드 필요)
   - `docker build -t health-log-api .`
   - `docker run -d -p 8000:8000 -v F:/healthcare/data:/app/data --name health-log-api health-log-api`
     (Windows Git Bash에서는 반드시 슬래시 경로 사용 — 백슬래시는 "system cannot find the file specified" 오류 발생)
   - http://localhost:8000 (자동으로 `/app`으로 이동) 에서 컨테이너 기준 재테스트, 관리자 계정으로 `/app/admin.html`도 확인
   - 문제 있으면 `docker logs health-log-api`
2. 이어서 고도화 로드맵 2번(데이터 시각화 차트), 3번 잔여(로딩 상태) 진행

## 8. 이후 계획 (미착수)

- AWS Lightsail 테스트 서버에 배포 (계정/서버는 이미 생성되어 있음, 접속 정보는 작업 시점에 확인 필요)
  - 배포 시 `COOKIE_SECURE=true` 환경변수 설정 권장 (HTTPS 적용 시)
- 배포 후 README.md의 "배포 접속 URL" 항목 채우기
- 최종 git push 및 제출 체크리스트 확인 (venv/data.json 미포함, README 완성 등)

## 9. 유의사항

- 코드 스스로 작성 원칙 — 참고 자료 활용 시 README에 명시
- venv/, data/, __pycache__ 는 .gitignore로 제외되어 있어 커밋되지 않음 (정상)
- 건강 분류 기준은 학습용 단순화 값, 실제 진단 아님
