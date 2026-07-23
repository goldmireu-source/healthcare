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
     - **(2026-07-21, 네 번째 후속 수정) 두 페이지 간 연결을 완전히 제거** — "유저 페이지 로그인 상태에서 관리자 주소로 들어가면 유저 페이지가 열린다"는 버그 리포트 반영. 원인: admin.html의 `checkAdmin()`이 role!=admin이면 `location.replace('/app/')`로 보냈는데, 유저 페이지에 로그인된 비관리자 세션 쿠키가 그대로 있으면 이 리다이렉트가 매번 발동했음. 수정: 리다이렉트 대신 그 세션을 로그아웃시키고 admin.html 자체의 로그인 화면을 보여주도록 변경. index.html의 "관리자 페이지" 링크, admin.html의 "유저 페이지로" 링크도 전부 제거해 두 화면이 서로를 참조/이동시키는 코드가 하나도 없게 만듦 (URL을 아는 사람만 각자 접근, 완전 독립).
       - ⚠️ 참고: 브라우저는 쿠키를 origin 단위로 공유하므로, 관리자 페이지 진입 시 기존 비관리자 세션을 로그아웃시키면 같은 브라우저의 다른 탭에 열려 있던 유저 페이지 세션도 함께 끊김 (의도된 동작 — 두 페이지가 세션을 공유하는 한 근본적으로 감수해야 하는 트레이드오프)
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

**(2026-07-21 개편)** 여러 작업자가 백엔드/프론트엔드를 나눠 맡는 협업 상황을 가정해서 실제로 폴더를 분리함 (기존엔 전부 루트에 평평하게 있었음). `backend/`와 `frontend/`는 로컬·Docker 이미지 내부 모두 항상 형제 폴더로 유지되고, `main.py`/`database.py`는 `__file__` 기준 상대경로로 서로를 찾기 때문에 uvicorn을 어디서 실행하든 경로가 깨지지 않음.

```
healthcare/
├── backend/                # FastAPI 서버 (Python) — API 담당자 영역
│   ├── main.py              #   앱 진입점, 라우트 전체 (인증/관리자 포함)
│   ├── auth.py               #   비밀번호 해시(PBKDF2) + 세션 토큰 + 관리자 권한 체크
│   ├── models.py             #   SQLAlchemy ORM (User/Session/HealthRecord/Goal/AuditLog)
│   ├── schemas.py            #   Pydantic 요청/응답 모델
│   ├── database.py           #   DB 연결/세션 설정 (SQLite, ../data/health_log.db)
│   ├── health_logic.py        #   BMI/혈압/혈당 계산·분류·경고·활동량·수면 로직
│   ├── rate_limit.py          #   인메모리 요청 횟수 제한기 (로그인/가입/재설정 어뷰징 방지)
│   ├── promote_admin.py       #   로컬 전용: 기존 계정을 관리자로 승격 (API로는 노출 안 함)
│   ├── seed_demo_data.py      #   로컬 전용: 데모 시연용 사용자 12명 + 2주치 건강기록/목표 생성
│   ├── requirements.txt
│   └── venv/                  #   (git 미포함)
├── frontend/
│   └── static/               # 화면 담당자 영역 — 별도 빌드 없는 순수 HTML/CSS/JS
│       ├── index.html         #   사용자용 웹 화면 (/app/)
│       └── admin.html         #   관리자 대시보드 (/app/admin.html, index.html과 완전 분리)
├── data/                    # sqlite 파일 저장 위치 (git 미포함, 런타임에 생성)
├── Dockerfile               # backend/·frontend/를 그대로 담아 이미지 빌드 (WORKDIR을 backend/로 맞춰 실행)
├── .dockerignore
├── .gitignore
├── README.md
└── PROJECT_CONTEXT.md
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
- [x] **프로젝트 폴더 구조 개편 + 관리자 대시보드 전면 고도화** (2026-07-21, 같은 날 후속 작업) — "관리자 화면이 회원 상세페이지 수준밖에 안 된다" + "여러 작업자가 협업하는 걸 가정해서 폴더 정리해달라"는 요청 반영
  - **폴더 구조**: 루트에 평평하게 있던 파일들을 `backend/`(FastAPI 전체)와 `frontend/static/`(index.html, admin.html)로 실제로 분리 (`git mv`로 이력 보존). `main.py`의 정적 파일 마운트 경로, `database.py`의 DB 경로를 전부 `__file__` 기준 상대경로로 바꿔서 uvicorn 실행 위치에 관계없이 항상 올바른 `../frontend/static`, `../data`를 찾도록 함. `venv`도 `backend/venv`로 재생성. `Dockerfile`도 `backend/`·`frontend/`를 그대로 담아 컨테이너 내부에서도 동일한 형제 폴더 구조를 유지하도록 재작성 (WORKDIR을 `/app/backend`로 맞춰 `uvicorn main:app` 그대로 실행)
  - **백엔드 확장**: `GET /admin/stats`에 `role_distribution`(관리자/일반 수), `new_users_last_7_days`, `signup_trend`(최근 14일 가입자 수 추이) 추가. `GET /admin/users`에 `role` 필터, `sort_by`(id/username/created_at/record_count)·`sort_dir` 정렬 추가 — 기록 수는 N+1 쿼리 대신 `group_by` 집계 쿼리 한 번으로 가져오도록 개선
  - **관리자 대시보드 전면 재설계** (`admin.html`): 사이드바 네비게이션(개요/사용자 관리/감사 로그)으로 화면을 분리 — 예전처럼 통계/사용자/기록/로그가 한 페이지에 쭉 나열되던 구조에서 벗어남
    - 개요: KPI 카드 4개(총 사용자·총 기록·최근 7일 가입·감사 로그 건수), 최근 14일 가입 추이(직접 그린 SVG 막대그래프, hover 시 날짜/인원 툴팁), 최근 활동 미리보기, BMI/혈압/혈당 분포(정상=teal/주의=amber/위험=brick 상태색 재사용)
    - 사용자 관리: 아이디 검색 + 권한 필터 + 정렬 가능한 테이블 헤더(오름/내림 화살표) + 페이지네이션. "기록 보기"를 페이지 하단에 펼치던 것에서 오른쪽에서 슬라이드되는 드로어 패널로 변경(리스트 스크롤 위치 유지됨)
    - 감사 로그: 조치 유형 필터(전체/계정삭제/강제로그아웃) 추가
    - 차트는 `dataviz` 스킬 가이드를 따름 — 분류 데이터는 이미 정상/주의/위험 의미를 갖고 있어 상태(status) 컬러 잡을 그대로 재사용(새 카테고리 컬러 발명 안 함), 가입 추이는 단일 시계열이라 단색(teal) 처리, 라벨은 `textContent`로 렌더링(툴팁에 신뢰 안 되는 데이터 주입 방지)
  - 로컬에서 fresh 프로세스로 재시작 후 curl로 전체 회귀 테스트: 폴더 이동 후 정적 파일/DB 경로 정상 확인, 확장된 `/admin/stats`·정렬·역할 필터·조합 검색, 강제 로그아웃→감사 로그 기록 확인, 자기 자신 대상 차단 재확인, 일반 사용자 엔드포인트(`/records`,`/goals`,`/reports/weekly`,`/stats`) 회귀 확인. admin.html JS는 Node `--check`로 문법 검증
  - **참고**: 이 세션 중 실제 사용자가 브라우저에서 직접 회원가입한 것으로 보이는 계정(`goldmireu`)이 데이터에 남아있음 — 삭제하지 않고 그대로 둠
- [x] **로그인/회원가입 어뷰징 방지 가드레일 + 데이터 입력값 검증 추가** (2026-07-21, 같은 날 후속 작업) — "실제 서비스 수준의 기본적인 가드레일"을 요청받아 구현
  - **계정 단위 로그인 잠금**: `User`에 `failed_login_attempts`/`locked_until` 추가. 5회 연속 로그인 실패 시 15분 잠금(423), 로그인 성공 시 카운트 초기화. IP를 바꿔가며 시도해도 계정 자체가 잠기므로 방어됨
  - **IP 기준 속도 제한** (`rate_limit.py` 신규 — Redis 없이 프로세스 내 슬라이딩 윈도우 카운터, 재시작하면 초기화되고 다중 워커로 확장 시 카운터가 공유 안 되는 한계는 주석으로 명시): `POST /auth/signup`(IP당 5회/10분), `POST /auth/login`(IP당 15회/5분, 계정 잠금과 별개로 여러 계정을 대상으로 한 분산 시도 방어), `GET /auth/security-question`(IP+아이디 10회/10분), `POST /auth/reset-password`(IP+아이디 5회/15분 — 보안질문 답은 생일·색깔처럼 추측하기 쉬워 특히 엄격하게), `POST /auth/change-password`(IP+사용자 10회/10분). 전부 429 응답
  - **회원가입 시 취약한 비밀번호 차단**: 흔한 비밀번호 목록("123456","password" 등) 차단 + 비밀번호가 아이디와 동일하면 차단 (Pydantic validator, 422)
  - **건강기록/목표 입력값 검증** (`schemas.py`): `RecordIn`/`RecordUpdate`/`GoalIn`에 상식적인 상한선 추가 — 체중 ≤500kg, 키 ≤250cm, 수축기 ≤300, 이완기 ≤200, 혈당 ≤1000, 걸음수 ≤100,000, 수면시간 ≤24시간, 메모 ≤500자. `date` 필드는 단순 문자열 패턴이 아니라 `datetime.strptime`으로 실제 존재하는 날짜인지 확인하고, 1900-01-01~내일 범위를 벗어나면 거부 (기존엔 형식 검증이 아예 없어서 "2026-13-45" 같은 값도 그대로 저장됐음)
  - curl로 전체 테스트 완료: 5회 실패 후 계정 잠금(423) 확인, signup/security-question/reset-password 각각 정확히 설정한 횟수에서 429로 전환 확인, 약한 비밀번호·아이디=비밀번호 거부(422, rate limit보다 먼저 걸림을 확인 — Pydantic 검증은 라우트 함수 진입 전에 일어나서 rate limit 카운터를 소모하지 않음), 비정상 체중/혈압/걸음수/수면시간/미래날짜/존재하지 않는 날짜 전부 422로 거부, 정상 범위 데이터는 그대로 통과. 테스트용으로 만든 계정/기록은 전부 정리해서 데모 데이터셋(13명) 그대로 유지
  - User 테이블에 컬럼이 또 추가되어(`failed_login_attempts`/`locked_until`) DB를 재생성했고, demo 계정 재가입+재승격, `seed_demo_data.py` 재실행으로 복구함
- [x] **새 backend/frontend 구조 기준 Docker 재빌드 & 실행 검증 완료** (2026-07-21)
  - `docker build -t health-log-api .` 리포 루트에서 정상 빌드 (backend/requirements.txt 설치 → backend/·frontend/ 복사 → WORKDIR을 backend/로 설정)
  - `docker run -d -p 8000:8000 -v F:/healthcare/data:/app/data --name health-log-api health-log-api` 로 실행, 로컬 dev와 동일한 `data/` 볼륨을 마운트해서 기존 데모 계정(demo 관리자 포함 14명, 실사용자 `goldmireu` 포함)이 컨테이너에서도 그대로 보이는 것까지 확인
  - 헬스체크·루트 리다이렉트·유저/관리자 정적 페이지 서빙·관리자 통계·사용자 목록·일반 사용자 로그인/기록/주간리포트 전부 컨테이너 기준 200 확인, `docker logs`에 에러 없음
  - 검증 후 컨테이너는 정지해두고(`docker stop health-log-api`, 이미지는 유지) 이어지는 작업 편의를 위해 로컬 uvicorn dev 서버로 다시 전환함 — 필요하면 `docker start health-log-api`로 재기동 가능
- [x] **Playwright 실브라우저 검증 + 사용자 화면 데이터 시각화 차트/로딩 상태 추가** (2026-07-21)
  - **실브라우저 검증**: 이 환경엔 `chromium-cli`가 없어서 scratchpad에 임시 Node 프로젝트(`npm install playwright`, 이미 캐시된 Chromium 재사용)를 만들어 헤드리스 크로미움으로 관리자/유저 화면을 직접 로그인·클릭·hover하며 스크린샷으로 확인함. 관리자 대시보드(사이드바 네비게이션·KPI·가입추이 차트 hover 툴팁·정렬·검색·드로어·감사로그), 유저 화면(로그인·계정설정 모달·기록삭제 커스텀 모달) 전부 실제 렌더링 확인, 콘솔 에러는 인증 체크 과정의 정상적인 401/404뿐이었음
  - **버그 발견 및 수정 1**: 계정 설정 모달의 "탈퇴" 버튼이 flex 컨테이너에서 좁아져 글자가 두 줄로 쪼개지던 문제 → 입력창 `flex:1`, 버튼 `flex-shrink:0;white-space:nowrap` 추가로 수정
  - **사용자 화면에 측정 추이 차트 추가** (`index.html`, 고도화 로드맵 2번) — 체중/혈압/혈당 탭 전환형 SVG 라인 차트. 혈압만 2계열(수축기=teal, 이완기=amber)이라 범례 표시, 단일 계열은 범례 생략(dataviz 스킬 원칙). hover 시 크로스헤어 없이 각 데이터 포인트의 투명 히트밴드로 날짜+수치 툴팁 표시, 라벨은 `textContent`/`createTextNode`로 렌더링
  - **버그 발견 및 수정 2**: 위 차트로 실제 확인해보니 한 사용자의 값이 기간 내내 전부 동일하면(range=0) 선이 그래프 맨 밑 기준선에 딱 붙어 사실상 안 보이는 문제 발견 → 값이 전부 같을 때는 위아래로 여유를 줘서 차트 중앙에 평평한 선으로 보이게 수정
  - **버그 발견 및 수정 3 (더 근본적)**: 새로 만든 차트로 `sora`(개선 추세로 설계된 데모 계정) 그래프를 열어보니 체중이 시간이 갈수록 **증가**하는 것으로 나와, 애초에 `seed_demo_data.py`의 추세 계산식이 방향을 반대로 계산하고 있었음을 발견(`drift = trend * day_offset`이 "오늘로 갈수록 변화 반영"이 아니라 "옛날로 갈수록 변화 반영"이 되고 있었음). `days_elapsed = 13 - day_offset` 기준으로 수정해 sora(체중 감소)/hana(체중 증가)/jaeho(체중 감소) 세 프로필 모두 의도한 방향대로 나오도록 고침. 해당 3명 기록만 삭제 후 `seed_demo_data.py` 재실행으로 재생성, DB에서 직접 날짜순 체중값 조회해 방향 확인 완료
  - **로딩 상태 표시 추가** (고도화 로드맵 3번 잔여) — 로그인 직후 최신측정값/기록목록/통계/목표/주간리포트 전 영역에 "불러오는 중..." 표시, API 응답 실패 시에도 로딩 문구가 그대로 남지 않도록 각 영역에 실패 메시지로 교체. Playwright로 API 응답을 인위적으로 지연시켜 로딩 상태가 실제로 화면에 뜨는 것까지 스크린샷으로 확인
  - 위 세 가지 수정 후 Playwright 전체 시나리오 재실행으로 최종 확인 (콘솔 에러 없음, 관리자/유저 계정 수·기록 수 테스트 전후 동일하게 유지됨 — Playwright 시나리오 자체는 조회/hover/취소만 하고 실제 변경은 하지 않음)
- [x] **데모 데이터 일별 변동폭을 4단계로 다양화** (2026-07-22) — "혈압/혈당/걸음수가 12명 전원 5건 다 동일하다"는 지적을 받고 확인해보니, 애초에 프로필당 값이 고정이라 혈압/혈당은 원래 전혀 안 변했고, 걸음수도 변화를 주려던 계산식(`day_offset % 3`)이 실제 쓰인 day_offset 수열(13,10,7,4,1 — 전부 3으로 나눈 나머지가 1)에서는 우연히 항상 0이 되어버려 사실상 안 변했음
  - `seed_demo_data.py`에 4단계 변동폭(volatility) 체계 추가: `stable`(크게 변화 없음, 3명: doyoon/eunji/somin) / `subtle`(거의 유사하지만 조금씩 다름, 3명: yuna/sora/hyerin) / `moderate`(적당히 변화, 3명: minho/hana/jaeho) / `high`(많이 변화, 3명: jihoon/taemin/wonwoo) — 체중/수축기/이완기/혈당/걸음수/수면 전부 이 등급에 맞는 폭(`VOLATILITY_NOISE`)만큼 `random.uniform`으로 매번 무작위로 흔들리게 함. 기존 체중 장기 추세(trend, sora/hana/jaeho/taemin)는 그대로 유지하고 그 위에 노이즈를 더함. `random.seed(20260721)` 고정으로 빈 DB에 재실행해도 항상 같은 데이터가 나오게 함
  - 12명 전원의 기록 60건을 삭제 후 재생성, DB에서 사용자별 체중/혈압/혈당/걸음수 min-max 범위를 직접 조회해 등급별로 변동폭이 뚜렷이 다르게 나오는 것 확인(stable은 범위 0.2 내외, high는 1.2~2.5 등)
  - 서버 재시작 후 로그인/사용자 수/통계 회귀 확인, 서버 로그 에러 없음
- [x] **측정 추이 차트에 x축 날짜 라벨 + 데이터 포인트 마커 추가** (2026-07-22) — "x축에 날짜가 있어야 하고 각 지점에 마우스 올릴 점이 있어야 hover해볼 걸 알지"라는 피드백 반영. 각 지점에 원형 마커(r=4, 카드 배경색 2px 링) 추가, x축에 날짜 라벨(겹치지 않게 최소 간격을 두고 선택적으로, 처음/끝은 항상 표시) 추가. 처음/끝 라벨을 가운데 정렬하면 차트 밖으로 잘려서 안쪽으로 붙여 정렬하도록 수정. Playwright로 잘림 없이 렌더링되는 것과 hover 툴팁이 여전히 정상 동작하는 것 확인
- [x] **유저 페이지를 사이드바 메뉴 구조로 전면 개편 + 통계/주간리포트 통합** (2026-07-22) — "통계요약이랑 주간리포트를 메뉴로 묶어서 그래프로 보여줘야 하지 않겠냐"는 제안에, 두 가지 재구성 방향(카드 하나로 합치기 vs 관리자처럼 사이드바 메뉴 전환)을 물어봤고 사용자가 사이드바 메뉴 전환을 선택함
  - `static/index.html`을 admin.html과 동일한 셸 구조(사이드바+콘텐츠)로 재작성: **기록**(오늘의 기록 입력 + 최신 측정값 + 전체 기록 검색/조회, 기존처럼 로그인 후 기본으로 열리는 뷰) / **통계 & 리포트**(측정 추이 차트 + 통계 요약 + 주간 리포트를 한 뷰에 통합) / **목표** 3개 뷰로 분리
  - **주간 리포트를 표에서 막대그래프로 전환**: 지표별(체중/수축기/이완기/혈당/걸음수/수면) 미니 카드에 "지난주"(회색, de-emphasis)와 "이번주"(teal, 강조색) 막대를 나란히 표시 — dataviz 스킬의 "emphasis"(한 계열은 강조색, 나머지는 톤다운) 패턴 적용, 값+증감 화살표는 그대로 유지
  - 로그인/회원가입/모달/토스트/측정추이차트/기록CRUD 등 기존 로직은 전부 그대로 유지하고 DOM만 새 뷰 구조 안으로 이동(JS 함수 변경 없음, `switchView()`만 신규 추가)
  - Playwright로 전체 재검증: 로그인 → 기록 뷰(기본) → 통계&리포트 뷰(차트+통계+막대그래프 리포트) → 목표 뷰 전환, 로딩 상태, 계정설정 모달, 기록삭제 확인모달까지 스크린샷으로 확인. 모바일 뷰포트(390px)에서도 사이드바가 상단 탭 형태로 정상 전환되는 것 확인
  - 콘솔 에러 없음(기존과 동일하게 인증 체크 401/404만 존재), 서버 로그 에러 없음
- [x] **디자인 리뉴얼: 디자인 시스템/다크모드/대시보드 히어로/위험도 지표/반응형 3단** (2026-07-22) — Linear/Stripe/Apple Health 등을 참고한 리디자인 제안서(아티팩트)를 먼저 만들어 방향을 잡은 뒤, 유저/관리자 페이지 실제 코드에 그대로 구현
  - **디자인 토큰 + 다크모드**: `index.html`/`admin.html` 양쪽에 라이트/다크 토큰을 `:root` / `@media (prefers-color-scheme: dark)` / `html[data-theme="dark|light"]` 3단으로 정의 (기존 `--teal`/`--amber`/`--brick` 변수명은 유지하되 값만 새 팔레트로 교체해 기존 CSS 전체를 다시 쓰지 않음). 브랜드색(teal)과 "정상" 상태색을 분리(`--status-good` 신규 추가) — 브랜드 버튼이 곧 "정상"을 의미하지 않도록. 각 페이지에 라이트/시스템/다크 3단 토글 추가(`localStorage` 저장)
  - **폰트 교체**: Fraunces 세리프 + IBM Plex Sans KR → Pretendard Variable(jsDelivr) 기반으로 전면 교체, 데이터/수치는 IBM Plex Mono 유지
  - **유저 페이지 대시보드 히어로**: "기록" 뷰 최상단에 건강 스코어 링(BMI/혈압/혈당/활동량/수면 5개 분류등급 기반 참고용 점수, 의학적 진단 아님 명시) + 체중·혈압·혈당 3개 지표 카드 + 활동량/수면 보조 칩 추가(기존 `vitals-strip` 대체). 기록 목록을 표 대신 날짜별 타임라인 카드로 전환(경고 있는 날은 좌측 빨간 스트라이프). 측정 추이 차트에 영역 채움 + 마지막 지점 강조(링 마커+숫자 라벨) 추가
  - **관리자 페이지 위험도 지표**: 사용자별 "가장 최근 기록"의 BMI/혈압/혈당 분류를 판정해 위험도(high/moderate/normal/unknown)를 서버에서 계산(`main.py`의 `_risk_level`, N+1 없이 user_id+date 정렬 1회 조회로 전원 처리) → `AdminUserOut.risk_level` 필드 추가, `/admin/users`에 `risk` 필터+정렬 파라미터 추가, `/admin/stats`에 `high_risk_usernames` 추가해 개요 KPI 카드로 노출
  - **반응형 3단**: 기존엔 900px 기준 데스크톱↔모바일 2단뿐이었는데, 태블릿 구간(721~1024px)에 아이콘 전용 사이드바 레일을 추가하고 모바일(~720px)은 하단 고정 탭바로 전환 — 사이드바 네비게이션 항목에 인라인 SVG 아이콘 추가
  - **Playwright 검증 중 발견/수정한 실제 버그 3건**: (1) 모바일 사이드바가 `position:fixed`인데 데스크톱용 `top:0`이 겹쳐 남아있어 `bottom:0`과 함께 뷰포트 전체 높이를 차지해버림(실사용자 클릭도 막힘) → `top:auto` 명시로 수정, (2) 토스트/툴팁/트렌드탭 active 등 여러 곳이 `background:var(--ink)`+고정 `#fff` 텍스트 조합이라 다크모드에서 `--ink`가 밝은색으로 뒤집히며 흰 배경에 흰 글씨로 안 보이는 버그 다수 → 고정 다크 칩 색상 또는 `--on-accent` 토큰으로 수정, (3) 모바일 폭에서 상단바의 테마토글+버튼들이 통째로 줄바꿈되지 않고 버튼 글자가 중간에서 잘려 두 줄로 쪼개짐 → `.user-switch`에 `flex-wrap:wrap` 추가로 버튼 단위로 줄바꿈되게 수정
  - 라이트/다크 × 데스크톱/태블릿/모바일 전체 조합 + 위험도 필터를 Playwright 스크린샷으로 최종 재검증, 콘솔 에러는 기존과 동일한 401(비로그인)/404(목표 미설정) 뿐

- [x] **AI Health Coach 플랫폼 고도화 (14개 기능 전체)** (2026-07-22) — "CRUD를 넘어 AI가 데이터를 분석하고 행동을 유도하는 플랫폼"으로 고도화하라는 요청에 따라, 아래 14개 기능을 순서대로 하나씩 완성 → 테스트 → 다음 기능 진행하는 방식으로 전부 구현. 기존 REST API/DB/디자인 시스템은 전혀 건드리지 않고 순수 추가만 함.
  1. **AI Health Coach** (`health_coach.py`, `GET /health-coaching`) — 규칙 기반 코칭 메시지, `CoachingProvider` 인터페이스로 LLM 교체 대비. 대시보드 최상단 카드.
  2. **AI 건강 리포트** (`health_coach.generate_weekly_summary`) — 주간 리포트를 자연어 문단으로 요약(지만/고/으며 연결어를 어간 기반으로 조합해 문법 보장), `/reports/weekly`의 `ai_summary` 필드로 노출.
  3. **건강 추세 분석** (`health_trends.py`) — `Trend` Enum(UP/DOWN/STABLE), `GET /trends`. Feature 1의 임시 로직을 여기로 리팩터링(회귀 없음을 재확인 완료).
  4. **이상 징후 감지** (`risk_detection.py`, `GET /risk-detection`) — 급격한 변화 전용 임계값으로 LOW/MEDIUM/HIGH 판정, 감지된 게 있을 때만 배너 표시.
  5. **Health Score 개선** (`health_score.py`, `GET /health-score`) — 가중치(체중20/혈압25/혈당25/운동15/수면15) + 추세 보너스·감점. 클라이언트 계산 로직 제거, 서버 단일 소스로 교체.
  6. **목표 달성 예측** (`goal_prediction.py`) — 평균 변화량(회귀 아님) 기반 예상 소요일, `/goals`의 `achievement.predictions`로 노출.
  7. **건강 캘린더** (`health_calendar.py`, `GET /calendar`) — 월별 날짜별 good/warn/bad 3색.
  8. **건강 타임라인** (`health_timeline.py`, `GET /timeline`) — 분류가 좋아진 시점 + 목표 최초 달성 시점만 이벤트로 추출.
  9. **건강 배지** (`badges.py`, 신규 테이블 `badges`, `GET /badges`) — 7일/30일 연속 기록, 첫 정상 BMI/혈압, 첫 목표 달성. 배경 스케줄러가 없어 조회 시점에 평가 후 저장하는 지연 평가 방식.
  10. **Export** (`GET /export/csv`, `GET /export/json`) — PDF 제외, JSON은 기존 `record_to_out()` 재사용.
  11. **관리자 Analytics 확장** (`admin_analytics.py`) — 최근 활동률/기록 유지율/평균 BMI·혈압·혈당/위험 사용자 증가율/가입 전환율을 기존 `/admin/stats`에 추가.
  12. **Service Layer 분리** — `health_service.py`/`goal_service.py`/`report_service.py`/`admin_service.py`로 main.py의 로직을 분리(로직은 그대로 복사, 이름만 정리). **분리 전/후 응답을 직접 diff해 완전히 동일함을 확인**(가장 리스크 큰 단계라 별도로 꼼꼼히 검증).
  13. **Dashboard UI 재배치** — Quick Action 툴바 + 목표진행률/최근배지/이번주변화 요약 카드 3종 추가.
  14. **확장성 확보** (`integrations.py`) — `WearableDataSource`(Mock, Apple/Samsung/Google Fit 공통 인터페이스), `HealthDataImporter`(CSV는 실제 파싱 동작, PDF는 Mock), LLM 확장은 1번의 `CoachingProvider`를 재사용. `GET /integrations/status`로 확인 가능.
  - **검증**: 매 기능마다 (1)단위 테스트(합성 데이터로 여러 시나리오) (2)서버 재시작 후 curl로 실제 데모 계정 데이터 검증 (3)기존 엔드포인트 전체 스모크 테스트 순으로 진행. 최종적으로 Playwright로 유저/관리자 페이지 라이트·다크 모드 전체 스크린샷 확인, 서버 로그 전체에 500/Traceback 없음 확인.
  - **버그 1건 발견/수정**: 관리자 개요의 "평균 혈압" KPI 카드가 소수점 값(`124.26/80.4`)이 카드 폭에 안 맞아 숫자 중간에서 줄바꿈되던 문제 → 정수로 반올림해 표시하도록 수정.
  - **신규 DB 테이블**: `badges` (SQLAlchemy `Base.metadata.create_all`로 자동 생성, 별도 마이그레이션 불필요).
  - **신규 파일 12개**: `health_coach.py`, `health_trends.py`, `risk_detection.py`, `health_score.py`, `goal_prediction.py`, `health_calendar.py`, `health_timeline.py`, `badges.py`, `admin_analytics.py`, `health_service.py`, `goal_service.py`, `report_service.py`, `admin_service.py`, `integrations.py` (실제로는 14개).

- [x] **AUDIT_REPORT.md 기반 보안/인프라/기능 고도화 — Phase A (보안)** (2026-07-22) — 외부 감사 보고서(`AUDIT_REPORT.md`)의 취약점 섹션을 우선순위 1로 반영
  1. **CSV 수식 인젝션(Formula Injection) 방어** — `GET /export/csv`가 셀 값을 문자열로 변환할 때 `=`,`+`,`-`,`@`로 시작하면 앞에 작은따옴표(`'`)를 붙여 엑셀/구글시트가 절대 수식으로 해석하지 못하게 함 (`_sanitize_csv_cell`). memo뿐 아니라 내보내는 모든 컬럼에 일괄 적용. 실제로 `=1+1+cmd|' /C calc'!A1` 같은 페이로드를 memo에 넣고 export해서 `'=1+1+...`로 이스케이프되는 것 확인 후 테스트 계정 삭제.
  2. **만료 세션 정리** — `auth.cleanup_expired_sessions()` 신설. (a) 앱 시작 시 1회 일괄 정리 (b) `create_session()`(로그인/회원가입마다 호출됨) 안에서 매번 지연 평가로 정리 — 배경 스케줄러 없이 badges.py와 동일한 패턴. 가짜 만료 세션을 DB에 직접 삽입 후 로그인 1회로 자동 삭제되는 것을 확인.
  3. **CORS + 보안 헤더** — `CORSMiddleware`를 명시적으로 추가하되 `ALLOWED_ORIGINS` 환경변수(기본값 빈 문자열)로 크로스오리진을 전부 차단(같은 origin에서 서빙하는 지금 구조엔 크로스오리진이 필요 없음 — 나중에 별도 도메인 프론트엔드가 생기면 그때 추가). 모든 응답에 `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` 미들웨어 추가. curl로 신뢰되지 않은 Origin 요청 시 `Access-Control-Allow-Origin` 헤더가 응답에 없음을 확인.
  - 세 항목 모두 반영 후 서버 재시작 → curl로 기존 12개+ 엔드포인트 전체 스모크 테스트 + Playwright로 유저 페이지 로그인/대시보드 렌더링 확인, 서버 로그 500/Traceback 0건.

- [x] **AUDIT_REPORT.md 기반 고도화 — Phase B (인프라 보완)** (2026-07-22)
  4. **Alembic 도입** — `backend/alembic/`에 마이그레이션 환경 구성. `env.py`가 `database.py`의 `DATABASE_URL`을 그대로 가져다 쓰도록 해 DB 경로를 두 곳에서 따로 관리하지 않게 함. 초기 마이그레이션(`d3c282e952de_initial_schema_snapshot.py`)은 **빈 임시 DB에 대해 autogenerate로 생성**한 뒤(6개 테이블 전부 감지 확인), **기존 개발 DB(14명 실데이터)는 `alembic stamp head`로 도장만 찍어 데이터 유실 없이** 마이그레이션 이력에 편입시킴. `main.py`의 `Base.metadata.create_all()` 호출 제거 — 이제 신규 셋업/스키마 변경은 전부 `alembic upgrade head`로만 진행 (README에 절차 명시). `Dockerfile`의 `CMD`도 컨테이너 기동 시 `alembic upgrade head`를 먼저 실행하도록 변경.
  5. **pytest 테스트 스위트 신설** (`backend/tests/`) — `conftest.py`가 테스트마다 완전히 격리된 임시 SQLite DB로 앱을 새로 import해서 띄움(database.py/main.py가 "import 시점에 전역 DB 커넥션을 만드는" 구조라, 설정 주입 리팩터링 없이 `sys.modules` 캐시를 지우고 재import하는 방식으로 격리 확보). 요청하신 5개 핵심 시나리오 전부 포함 + 보조 케이스 4개, 총 9개 테스트: 로그인 5회 실패→423 잠금(+ 4회까지는 정상 로그인되는 경계 케이스), IDOR(다른 유저 기록 접근 시 403이 아니라 404로 존재 자체를 숨김 — 방식까지 검증), 회원 탈퇴 시 기록/목표/세션 cascade 삭제(DB 직접 조회로 확인)와 오답 비밀번호로는 탈퇴 안 되는 경계 케이스, 관리자 권한 없이 `/admin/*` 4종 403, 건강기록 CRUD(수정 시 BMI 재계산까지 확인) + 값 검증(422). `pip install -r requirements-dev.txt` 후 `pytest` 한 줄로 전부 실행됨(CI 없음, 로컬 전용). 테스트 실행 후 실제 개발 DB(14명)가 그대로인지 재확인 완료.
  6. **rate limiter 멀티 워커 한계 — 문서화만 진행, 코드는 유지** — 지금 배포 계획이 단일 워커(uvicorn 기본 실행, Lightsail 소규모 인스턴스) 기준이라 Redis 등 외부 저장소 도입은 하지 않기로 결정. 이유: (1) 단일 워커에서는 인메모리 카운터가 프로세스 전체에서 공유되므로 지금 구조로도 완전히 유효함 (2) Redis 도입은 새 의존성 + 배포 복잡도 증가로, 실제로 워커를 늘릴 계획이 생기기 전에는 비용 대비 효과가 낮음. **워커를 2개 이상으로 늘리는 시점이 오면 그때 반드시 재검토** — 그 전까지는 `rate_limit.py` 상단 docstring에 이미 명시된 한계(재시작 시 초기화, 멀티 워커 시 카운터 분리)를 그대로 감수.
  - 세 항목 반영 후 서버 재시작 → 기존 12개+ 엔드포인트 curl 스모크 테스트 + pytest 9개 전체 통과 + Playwright 유저 페이지 렌더링 확인, 서버 로그 500/Traceback 0건.
  - **신규 파일**: `backend/alembic/`(env.py, script.py.mako, versions/), `backend/alembic.ini`, `backend/pytest.ini`, `backend/requirements-dev.txt`, `backend/tests/`(conftest.py, test_auth.py, test_records.py, test_account.py)
  - **`.gitignore` 추가**: `.pytest_cache/`, `alembic/versions/__pycache__/`

- [x] **AUDIT_REPORT.md 기반 고도화 — Phase C (프론트엔드 정리)** (2026-07-22)
  7. **디자인 토큰 `theme.css`로 분리** — `index.html`/`admin.html` 양쪽에 중복 정의되어 있던 `:root`(라이트) / `@media (prefers-color-scheme: dark)` / `html[data-theme="dark"]` / `html[data-theme="light"]` 4개 토큰 블록을 `frontend/static/theme.css` 하나로 통합, 두 HTML 모두 `<link rel="stylesheet" href="theme.css">`로 참조하도록 교체(정적 파일 마운트 경로는 `/app` prefix — `app.mount("/app", StaticFiles(...))`, 루트가 아님).
  - **병합 중 발견한 기존 버그 1건 수정**: `index.html`의 `html[data-theme="dark"]`(수동 다크모드 토글용) 블록에만 `--on-accent` 정의가 누락되어 있었음(`admin.html`의 동일 블록과 `index.html` 자신의 `@media (prefers-color-scheme: dark)` 블록에는 존재). OS가 라이트인 상태에서 사용자가 수동으로 다크모드를 켜면 `--on-accent`가 라이트값(`#FFFFFF`)으로 남아, 로그인 버튼이 흰 글씨/밝은 틸 배경으로 저대비가 되는 문제였음 — 통합 과정에서 두 파일 중 더 완전한(버그 없는) `admin.html` 버전을 정본으로 채택해 자연스럽게 수정됨.
  - **검증**: 통합 전(`git stash`로 원본 복원) / 통합 후 각각 Playwright로 `index.html`/`admin.html` × 라이트/다크(OS 설정 기준) 스크린샷 4쌍을 비교 — 전부 픽셀 단위로 동일(사용자 요구사항인 "시각적 차이 없음" 충족). 추가로 `data-theme="dark"`를 강제 토글한 스크린샷으로 위 버그가 고쳐졌음을(로그인 버튼이 진한 잉크색 글씨로 표시) 별도 확인. 이후 서버 재시작 + curl 엔드포인트 스모크 테스트 + pytest 9개 전체 통과 확인.
  - **신규 파일**: `frontend/static/theme.css`

- [x] **AUDIT_REPORT.md 기반 고도화 — Phase D (기능 추가)** (2026-07-22)
  8. **CSV Import를 실제 DB 저장으로 연결** — `POST /integrations/import/csv/commit` 신설. `CsvHealthDataImporter.parse()`가 만드는 원시값을 `POST /records`와 완전히 동일한 `schemas.RecordIn` 검증(범위/필수값)과 `health_service.apply_evaluation()` BMI 계산 로직으로 재검증한 뒤 저장 — 잘못된 값이 검증을 우회해 저장되는 경로 자체가 없음. 한 행이라도 검증에 실패하면 **아무것도 저장하지 않고**(부분 저장으로 인한 혼란 방지) 실패한 행 번호/날짜/사유를 전부 반환. CSV export가 이미 `height` 컬럼을 내보내고 있었는데 기존 import 파서에는 `height` 파싱이 아예 빠져 있던 것을 이번에 발견해 `integrations.ImportedRecord`/`schemas.ImportedRecordOut`에 추가(export↔import 왕복 시 데이터가 온전히 보존되도록). 검증: 정상 CSV 2건 저장 후 `GET /records`로 실제 반영 확인, 값 범위 초과(체중 99999)·`height` 컬럼 누락 케이스 각각 422 + 아무 것도 저장되지 않음을 확인, pytest 9개 전체 통과.
  9. **OpenAI 실연동** — `health_coach.OpenAICoachingProvider`가 표준 라이브러리 `urllib`만으로 실제 OpenAI Chat Completions API를 호출(새 런타임 의존성 추가 안 함 — rate limiter 때 Redis를 안 쓴 것과 같은 이유로 requirements.txt에 HTTP 클라이언트 라이브러리를 넣지 않음). `health_coach.FallbackCoachingProvider`가 1차(OpenAI) 호출의 모든 실패(키 없음/네트워크 오류/타임아웃/응답 형식 이상)를 잡아 2차(규칙 기반)로 자동 대체 — 실제로 유효하지 않은 API 키로 호출해 OpenAI가 401을 반환하는 것까지 확인했고, 그 경우에도 `/health-coaching`이 500이 아니라 200 + 규칙 기반 메시지를 정상 반환함을 검증. `OPENAI_API_KEY` 환경변수가 없으면 지금까지와 100% 동일하게 규칙 기반만 사용(기본 동작 변화 없음), 있으면 자동으로 OpenAI 우선 사용. 모델은 `OPENAI_COACHING_MODEL`(기본 `gpt-4o-mini`)로 조정 가능. `.env`는 이미 `.gitignore`에 포함되어 있음을 재확인.
     - **하루 1회 캐싱** — 새 테이블 `coaching_cache`(사용자당 1행, `user_id` unique) 신설(Alembic 마이그레이션 `5f05c74ee344`). badges.py와 동일한 지연 평가 패턴: `GET /health-coaching` 조회 시점에 "오늘 이미 생성했는지"만 확인하고, 아니면 새로 생성해 저장 — 배경 스케줄러 없음. `User` 삭제 시 `cascade="all, delete-orphan"`으로 함께 삭제되도록 관계 추가(회원 탈퇴 시 cascade 삭제 확인 테스트로 이미 검증되는 3개 테이블과 동일한 패턴).
     - **프론트엔드 안내 문구** — `index.html`의 AI Health Coach 카드 하단에 "코칭 메시지 생성을 위해 건강 기록 요약이 외부 AI API(OpenAI)로 전송될 수 있습니다." 한 줄 추가(연한 구분선 + muted 텍스트로, 기존 디자인 시스템 톤 유지).
  - 두 항목 반영 후 서버 재시작 → 기존 엔드포인트 curl 스모크 테스트 + pytest 9개 전체 통과 + Playwright로 대시보드(코칭 카드 + 안내 문구) 렌더링 확인, 서버 로그 500/Traceback 0건. `alembic upgrade head` 적용 후에도 기존 데이터(14명/62건) 그대로임을 재확인.
  - **신규 파일**: `backend/alembic/versions/5f05c74ee344_add_coaching_cache_table.py`
  - **README.md 추가**: DB 테이블 목록에 `coaching_cache` 추가, 환경변수 표(`ALLOWED_ORIGINS`/`OPENAI_API_KEY`/`OPENAI_COACHING_MODEL`/`COOKIE_SECURE`) 신설

- [x] **Phase A~E 이후 사용자 피드백 기반 개선 6건** (2026-07-22, 커밋 `52c33af`~`5f7c52a`)
  - **`.env` 자동 로드 + 기록 폼 "이전 값 불러오기"** (`52c33af`) — `python-dotenv`로 서버 시작 시 `backend/.env` 자동 로드(`OPENAI_API_KEY` 등을 어디에 입력하는지 불명확했던 문제 해결), `backend/.env.example` 템플릿 추가. `index.html` 기록 폼에 "이전 값 불러오기" 버튼 추가 — 가장 최근 날짜 기록에서 몸무게/키/혈압/혈당/걸음수/수면시간을 자동 입력(측정일/메모는 제외).
  - **관리자 KPI 카드/가입 추이 차트 클릭 가능하게 변경** (`c4afe85`) — 숫자만 보이고 상세를 볼 수 없던 문제 수정. 모든 KPI 클릭 시 그 근거가 되는 사용자 목록으로 드릴다운(`/admin/users`에 `signup_days`/`signup_date`/`active_days`/`has_records` 필터 추가). 가입 추이 차트 막대도 `cursor:pointer`만 있고 실제 클릭 동작이 없던 동일 유형 버그를 발견해 함께 수정. 필터 배너 + 필터 해제 UI 추가.
  - **유저/관리자 페이지 텍스트 크기 전반 확대** (`e0aa73d`) — 전반적으로 글자가 작아 가독성이 떨어지던 문제 수정. 타이포그래피 계층(제목>본문>라벨)은 유지한 채 전체 폰트 크기를 한 단계씩 상향, 카드/버튼/테이블 패딩도 비례 확대.
  - **사용자 이름(실명) 필드 추가** (`f761bd1`) — `users.name` 컬럼 신설(Alembic), 회원가입 시 필수 입력, 기존 계정은 "계정 설정 → 이름 변경"(`POST /auth/change-name`)으로 설정 가능. 관리자 사용자 관리에서 이름 표시 + 이름으로도 검색 가능(`search`가 username OR name 매칭). 자유 텍스트라 저장형 XSS 위험이 있어 `escapeHtml()` 헬퍼로 항상 이스케이프.
  - **회원정보 보기 모달 + 기존 계정 이름 백필** (`f7aa103`) — `GET /admin/users/{id}` 신설, 보안질문/로그인 실패 횟수/계정 잠금 상태까지 포함하는 상세 조회(비밀번호 해시 등은 응답에 포함 안 함). 기존 14개 계정의 빈 이름을 아이디(로마자 표기) 기반으로 백필(데이터 변경이라 별도 커밋 없음 — `data/`는 gitignore 대상).
  - **현재 접속중인 사용자 표시** (`5f7c52a`) — 실시간 접속 추적(하트비트/웹소켓)은 없어 "만료되지 않은 로그인 세션 보유"를 대리 지표로 사용. 개요에 "현재 접속중" KPI, 사용자 목록에 접속 상태 배지/필터, 회원정보 보기에 활성 세션 수/최근 로그인 시각 추가.
  - 각 건마다 pytest 9개 전체 통과 + Playwright로 실제 브라우저 동작 확인, 기존 데이터(14명/62건) 무결성 확인 후 커밋.

- [x] **가입회원 50명 규모로 확대 + 가입일 분산** (2026-07-22, 데이터 변경만 — 코드 커밋 없음)
  - 신규 36개 계정을 실제 회원가입과 동일한 방식(`auth.hash_password`)으로 생성, 아이디에 맞춰 이름도 채움. 기존 14개 계정 포함 전체 50명의 `created_at`을 2026-07-07~07-21 15일 구간에 하루 3~4명씩 고르게 재분배(랜덤 시각 부여). `data/`는 gitignore 대상이라 이 변경은 로컬 DB에만 반영됨.
  - 참고: 관리자 개요의 "가입 추이" 차트는 항상 오늘 기준 최근 14일만 보여주는 롤링 윈도우라, 조회 시점에 따라 구간 앞쪽 며칠이 차트에는 안 보일 수 있음(기존 차트 설계, 버그 아님).

- [x] **README.md 실제 코드 최신 상태로 대폭 갱신** (2026-07-22, 커밋 `2960149`)
  - Phase A~E 이후 여러 커밋이 README에 전혀 반영 안 되어 있던 것을 발견해 전면 갱신 — 백엔드 모듈 15개, 엔드포인트 14개(AI Coach/Export/Integrations/회원정보 보기/이름 변경), DB `users.name` 컬럼, 관리자 KPI 드릴다운/접속 상태, 접근성 개선, Docker의 alembic 자동 실행 등 반영.

- [x] **AUDIT_REPORT.md + CTO_AUDIT_REPORT.md 기반 종합 개선 — Phase 1 (보안, 최우선)** (2026-07-22)
  - 두 감사 보고서를 먼저 검증: main.py 줄 수(1,125)·pytest 경고 수(54)·index.html 줄 수(1,839) 등 구체적 수치는 grep으로 재확인해 정확했으나, CTO_AUDIT_REPORT.md의 "index.html aria 속성 0건" 주장은 **사실이 아니었음**(직전 접근성 패스 커밋 `4d9fa65`로 이미 index.html 14건/admin.html 19건 존재) — 해당 감사 시점에 최신 커밋을 놓친 것으로 보임. Phase 5-11(접근성)은 "신규 추가"가 아니라 "현황 검증/보강"으로 범위를 조정.
  1. **XSS 전수조사** — `index.html`(35건)·`admin.html`(18건)의 모든 `innerHTML` 사용처를 전수 확인(insertAdjacentHTML은 0건). 결론: **현재 코드베이스에 실제 XSS 취약점 없음** — `memo`는 어디에서도 innerHTML로 렌더링되지 않고 항상 `.value`/`textContent`로만 다뤄짐, `name`/`security_question`은 이미 `escapeHtml()`로 이스케이프됨(직전 세션에서 추가), `username`/`date`/분류(BMI·혈압·혈당 카테고리)/역할 등은 Pydantic 정규식·서버 분류 로직으로 애초에 특수문자가 들어올 수 없어 안전. AI Health Coach 메시지·주간 AI 요약(OpenAI 연동 이후 프롬프트 인젝션 경로까지 고려)도 `textContent`로만 렌더링되어 안전함을 코드로 확인. **실제로 `<img src=x onerror=...>`/`<script>`/`<b>` 페이로드를 회원가입 이름·보안질문·기록 메모에 직접 주입 → 관리자 사용자 목록/회원정보 모달/본인 대시보드에서 Playwright로 렌더링 확인** — `window.__xss` 등 플래그 전부 미실행, `alert` 다이얼로그 0건, innerHTML에 원본 태그 잔존 0건으로 실증 검증 완료.
  2. **비밀번호 찾기 복구 불가 시나리오 보완** — 보안질문 답을 잊거나 rate limit(5회/15분)에 걸려 셀프 복구가 막힌 사용자를 위해 `POST /admin/users/{id}/reset-password` 신설. 무작위 임시 비밀번호(`secrets.token_urlsafe(9)`)를 생성해 즉시 해시로만 저장하고 기존 세션은 전부 무효화(비밀번호 찾기 재설정과 동일한 보안 조치). 감사 로그에는 조치 사실만 남기고 **비밀번호 값 자체는 절대 기록하지 않음**(직접 확인: 로그 텍스트에 실제 발급된 비밀번호 문자열이 없음). 자기 자신 대상은 400으로 차단(다른 관리자 기능과 동일한 패턴). 회원정보 보기 모달에 "임시 비밀번호 발급" 버튼 추가 — 결과는 한 번만 보여주는 별도 모달(복사 버튼 포함)로 표시, 이후 다시 조회 불가. 로그인 화면 비밀번호 찾기 폼 하단에 "관리자에게 문의해 계정 복구를 요청하세요" 안내 문구 추가.
  - 검증: 서버 재시작 → pytest 9개 전체 통과 → curl로 자기 자신 재설정 차단(400)/실제 재설정 성공/기존 세션 401/기존 비밀번호 401/새 임시 비밀번호로 로그인 성공까지 확인 → 감사 로그에 비밀번호 미노출 확인(grep) → Playwright로 XSS 무실행 + 임시 비밀번호 발급 UI 플로우(확인 모달→결과 모달) + 로그인 화면 안내 문구까지 렌더링 확인.
  - **신규 파일**: 없음(기존 파일 수정만)

- [x] **AUDIT_REPORT.md + CTO_AUDIT_REPORT.md 기반 종합 개선 — Phase 2 (코드 구조/기술부채)** (2026-07-22)
  - **순서 조정 및 사유**: 계획상 2-3(라우터 분리) → 2-4(ConfigDict) → 2-5(shared.js) 순이었으나, 실제로는 **2-4를 가장 먼저** 처리함 — Pydantic `Config`→`ConfigDict` 전환은 `schemas.py` 한 파일만 건드리는 독립적인 변경이라 먼저 끝내 두면 2-3(라우터 분리) 작업 중 발생하는 diff에 이 변경이 섞여 원인 추적이 어려워지는 걸 피할 수 있었음. 이후 2-3 → 2-5 순으로 원래 계획대로 진행.
  1. **Pydantic `class Config` → `ConfigDict` 전환** — `schemas.py`의 `class Config: from_attributes = True` 6곳을 전부 `model_config = ConfigDict(from_attributes=True)`로 교체. `pytest -q` 결과 9 passed, **경고 54건 → 0건**으로 확인.
  2. **`main.py`를 도메인별 `APIRouter`로 분리** — 기존 1,125줄짜리 `main.py`에 있던 40개 라우트를 `backend/routers/` 아래 8개 모듈(auth/records/goals/reports/export/ai_coach/integrations/admin)로 이동, `main.py`는 앱 설정(미들웨어·예외 핸들러·라우터 등록·정적 마운트)만 남아 ~120줄로 축소. 각 라우터는 원본 로직을 그대로 옮기고 `@app.X` → `@router.X`만 변경(경로/동작 100% 동일 유지가 목표).
     - **검증 중 실제 회귀 발견 및 수정**: 분리 직후 `pytest -q`가 9개 중 7개 실패(스푸리어스 429, sqlalchemy 오류) — 원인은 `backend/tests/conftest.py`의 `_RELOAD_MODULE_PREFIXES`에 새로 생긴 `routers` 패키지가 빠져 있어, 테스트마다 새 임시 DB로 격리해야 할 `routers.*` 서브모듈이 `sys.modules`에 캐시된 채 남아있던 것(예: `routers.auth_router`가 첫 테스트 때 import한 `rate_limit` 모듈 인스턴스를 계속 참조 → rate limit 카운터가 테스트 간 누적). `_RELOAD_MODULE_PREFIXES`에 `"routers"` 추가로 해결, 9 passed 재확인.
     - **분리 전/후 응답 diff 검증**: `router_split_snapshot.py`로 읽기 전용 20여 개 + 쓰기 경로(회원가입→기록/목표/CSV 가져오기→이름/비밀번호 변경→삭제) 전체 사이클, 관리자 전용 9개 엔드포인트 등 53개 호출을 분리 전/후 각각 기록해 비교. **`admin_user_detail`의 `last_login_at` 한 필드만 차이**(두 스냅샷 사이에 시드 계정이 실제로 재로그인해 생긴 정상적인 값 변화) 있었고 나머지는 전부 일치 — 라우터 분리로 인한 동작 변화 없음을 확인. 검증에 쓴 임시 계정(`routersplit_before_user`/`routersplit_after_user`/`router_split_admin`)은 전부 삭제해 DB를 50명/62건 기준선으로 복원.
  3. **프론트 JS 공통 로직을 `frontend/static/shared.js`로 분리** — `index.html`에만 있던 `apiGet`/`apiSend`, 양쪽에 중복돼 있던 `toast()`, `admin.html`에만 있던 `escapeHtml()`을 새 `shared.js`로 이동하고 두 HTML 모두 `<script src="shared.js">`로 로드. `apiGet`/`apiSend`는 401 응답 시 `index.html`(`showAuthScreen`)과 `admin.html`(`showAdminLogin`)의 서로 다른 로그인 화면 복귀 로직을 그대로 타도록, 하드코딩 대신 각 페이지가 등록하는 `window.onSessionExpired` 훅을 호출하는 방식으로 설계 — 두 페이지의 인증 흐름 차이를 유지하면서 중복만 제거함. `admin.html`의 기존 raw `fetch()` 호출부(약 30곳)는 이번 스코프에서 건드리지 않음(중복 로직이 아니라 단지 다른 스타일이라 리스크 대비 이득이 낮다고 판단).
     - **검증**: Playwright로 두 페이지 모두 실제 로그인(성공/실패)·대시보드 렌더링·토스트 표시·관리자 사용자 목록의 `escapeHtml` 렌더링·강제 세션 만료(쿠키 삭제 후 `apiGet` 호출) 시 각 페이지의 올바른 로그인 화면 복귀까지 확인 — 콘솔에 남은 401/404는 전부 의도된 네거티브 테스트 결과이며 실제 JS 오류 없음.
  - 회귀: `pytest -q` 9 passed, 0 warnings / curl 스모크(로그인·기록·통계·헬스스코어·배지·미인증 401·관리자 미인증 401·`/docs` 200·`/` 307) 전부 정상 / DB 50명·62건 기준선 유지 확인.
  - **신규 파일**: `backend/routers/__init__.py`, `backend/routers/{auth,records,goals,reports,export,ai_coach,integrations,admin}_router.py`, `frontend/static/shared.js`

- [x] **AUDIT_REPORT.md + CTO_AUDIT_REPORT.md 기반 종합 개선 — Phase 3 (성능/DB)** (2026-07-22)
  1. **`(user_id, date)` 복합 인덱스** — `models.py`의 `HealthRecord`에 `__table_args__ = (Index("ix_health_records_user_id_date", "user_id", "date"),)` 추가. 거의 모든 조회가 "이 user_id의 기록을 date 순으로"라 단일 컬럼 인덱스 2개보다 복합 인덱스가 더 잘 맞음. Alembic `alembic revision --autogenerate`로 마이그레이션 생성(`c1df83b2dad1`) 후 `alembic upgrade head`로 적용, `sa.inspect(engine).get_indexes(...)`로 실제 생성 확인.
  2. **본인 기록 목록(GET /records, GET /search)에 서버사이드 페이지네이션 추가** — admin 사용자 목록과 같은 패턴으로 `page`/`page_size`(선택) 쿼리 파라미터 추가. **opt-in 설계**: 둘 다 안 주면 기존과 100% 동일하게 전체를 반환(응답의 `page`/`page_size`는 `null`) — 대시보드 히어로 카드(최근 기록 비교)와 추세 차트(`renderTrendChart`)는 전체 기간 데이터가 있어야 그릴 수 있어 이 경로는 그대로 둠. 둘 다 주면 DB에서 `.offset()/.limit()`로 실제 슬라이싱하고 전체 개수를 `count`로 반환. `RecordListOut`에 `page`/`page_size`(둘 다 기본값 `None`) 필드 추가 — 기존 호출부(관리자 회원별 기록 조회 등)는 이 값을 안 주므로 동작 변화 없음.
     - 프론트(`index.html`): 기록 목록 테이블(`renderRecordsPage`)만 실제 서버 페이지네이션 호출로 전환 — 페이지 이동(`recordsPrevPage`/`recordsNextPage`)마다 `GET /records?page=&page_size=&sort_dir=desc` (검색 결과 화면이면 `GET /search?...`)를 새로 호출. `allRecordsCache`(히어로/차트가 쓰는 전체 데이터)는 그대로 유지 — 즉 히어로/추세 차트는 지금도 전체 이력을 한 번에 불러오는 게 불가피함(문서화된 한계).
     - 검증: 임시 계정에 15건 기록을 만들어 Playwright로 실제 확인 — 1페이지 카드 10건/2페이지 5건, "다음" 클릭 시 실제로 `GET /records?page=2&page_size=10&sort_dir=desc` 네트워크 요청 발생(클라이언트 슬라이싱 아님), 검색도 동일 패턴으로 페이지네이션 파라미터가 붙음, 콘솔 오류 0건. 테스트 계정/기록 삭제 후 DB 50명/62건 기준선 복귀 확인.
  3. **정적 파일 Cache-Control 헤더** — `main.py`에 `add_static_cache_headers` 미들웨어 추가. 빌드 단계 없이 파일명에 버전/해시가 없는 순수 정적 파일이라 무기한 캐시는 위험(배포 후 변경 미반영 사고 우려) — HTML은 `no-cache`(매번 재검증, ETag/Last-Modified로 304 가능), CSS/JS는 `public, max-age=3600`(1시간)으로 설정. curl로 `index.html`/`admin.html`→`no-cache`, `theme.css`/`shared.js`→`public, max-age=3600`, API 응답에는 이 헤더가 안 붙는 것까지 확인.
  - 회귀: `pytest -q` 9 passed, 0 warnings / curl 스모크(로그인·페이지네이션 응답 형태·Cache-Control 헤더) 전부 정상.
  - **신규 파일**: `backend/alembic/versions/c1df83b2dad1_add_composite_index_on_health_records_.py`

- [x] **AUDIT_REPORT.md + CTO_AUDIT_REPORT.md 기반 종합 개선 — Phase 4 (테스트/CI)** (2026-07-22)
  1. **pytest 커버리지 확장** — 기존 9개(계정/인증/기록 CRUD)에서 **41개**로 확장. 신규 파일 6개:
     - `test_goals_reports.py`(4개) — 목표 미설정 시 404, 목표 설정/부분 갱신, 주간 리포트 응답 형태, 미인증 401.
     - `test_ai_coach.py`(9개) — AI Health Coach 7개 엔드포인트(코칭/추세/이상징후/스코어/캘린더/타임라인/배지) 전부: 코칭 메시지가 같은 날 캐시 재사용되는지, 건강 스코어는 기록이 없으면 404, 배지는 기록 추가 후 최소 1개 이상 획득되는지 확인.
     - `test_export_import.py`(7개) — CSV/JSON 내보내기, CSV 수식 인젝션 방어(`=1+1` → `'=1+1`로 저장되는지), CSV 가져오기 미리보기(저장 안 함)/커밋(저장함)/검증 실패 시 전체 롤백(all-or-nothing), 연동 상태/웨어러블 mock.
     - `test_admin.py`(7개) — 사용자 목록 검색, 통계, 회원 상세/기록 조회, 강제 로그아웃(실제 세션 무효화 확인), 임시 비밀번호 발급(발급된 비밀번호로 실제 로그인까지 확인), 계정 삭제, 감사 로그 기록 확인. 회원가입으로는 admin이 될 수 없어(설계상 의도) 테스트 DB에서 직접 role을 승격시키는 `_make_admin()` 헬퍼로 관리자 계정을 만듦.
     - `test_password_recovery.py`(5개) — 보안질문 조회, 오답 시 401(+기존 비밀번호 유지 확인), 정답 시 재설정 성공(대소문자/공백 정규화 확인 + 기존 세션 전부 무효화 확인), **비밀번호 재설정 rate limit(5회/900초) 실제 429 확인**, **회원가입 rate limit(5회/600초) 실제 429 확인**.
     - 버그 아님, 테스트 작성 중 발견한 API 사실 확인: `TrendDirection`/`RiskLevel` enum 값은 대문자(`"UP"`/`"DOWN"`/`"STABLE"`, `"LOW"`/`"MODERATE"`/`"HIGH"`)로 응답됨 — 소문자로 잘못 가정했던 첫 버전의 테스트를 수정.
     - 테스트 작성 중 발견한 내 테스트 코드의 버그: force-logout 테스트에서 대상 계정을 만든 뒤 `client.post("/auth/logout")`을 호출하면 관리자로 전환되기도 전에 대상의 세션 자체가 사라져 "무효화할 세션이 0개"가 되는 실수 — `test_records.py`의 IDOR 테스트가 이미 쓰던 패턴(로그아웃 없이 다음 계정으로 signup/login만 하면 클라이언트 쿠키만 바뀌고 이전 세션은 서버에 그대로 남음)으로 수정.
  2. **GitHub Actions CI** — `.github/workflows/backend-tests.yml` 신설. `push`/`pull_request` 전부에서 `backend/` 디렉터리 기준으로 `pip install -r requirements-dev.txt` 후 `pytest -q` 실행. 배포(서버에 올리는 작업)가 아니라 GitHub 저장소 자체의 CI 설정이라 이번 작업 범위에 포함됨(사용자가 명시적으로 제외한 것은 AWS Lightsail 배포/HTTPS/COOKIE_SECURE뿐).
  - 회귀: `pytest -q` **41 passed, 0 warnings** / curl 스모크(로그인·`/health`·`/docs`) 정상. 이번 Phase는 테스트/CI 파일만 추가해 런타임 코드 변경이 없음.
  - **신규 파일**: `backend/tests/test_goals_reports.py`, `backend/tests/test_ai_coach.py`, `backend/tests/test_export_import.py`, `backend/tests/test_admin.py`, `backend/tests/test_password_recovery.py`, `.github/workflows/backend-tests.yml`

- [x] **AUDIT_REPORT.md + CTO_AUDIT_REPORT.md 기반 종합 개선 — Phase 5 (UX/접근성/디자인 폴리시)** (2026-07-22)
  1. **접근성 현황 검증/보강** — 조사 에이전트로 전수 점검한 결과, 이전 패스가 아이콘 버튼 aria-label(index.html 6건/admin.html 10건)은 이미 잘 채워뒀지만 더 큰 공백이 남아있었음: (a) **폼 label이 전부 `for`/`id`로 연결 안 되어 있었음** — index.html 30개 + admin.html 7개, 총 37개 label을 정규식 스크립트로 일괄 연결(이미 `id`가 있던 `reset-question-label`처럼 예외 케이스도 정확히 처리됨, 놓친 label 0건). (b) **모달/드로어에 dialog 시맨틱 없음** — index.html 2개(계정 설정/확인창) + admin.html 3개(회원상세/임시비밀번호/확인창) + 드로어 1개에 `role="dialog"`/`aria-modal="true"`/`aria-labelledby` 추가, `temp-password-display` 입력창에 aria-label 추가(기존엔 label 자체가 없었음). (c) **키보드로 모달을 닫을 방법이 없었음** — `shared.js`에 전역 Esc 핸들러 추가(페이지마다 다른 닫기 함수 이름을 몰라도 되게 `.modal-overlay`/`.drawer-overlay`를 그냥 숨기는 방식). 드로어 배경(overlay) 자체는 일부러 포커스 가능하게 만들지 않음 — 보이지 않는 배경을 탭 순서에 넣으면 오히려 키보드 사용자가 혼란스러움(Esc 키와 보이는 "닫기" 버튼으로 충분). 아이콘 전용 버튼/이미지 없음, 색상만으로 상태를 표시하는 곳 없음(전부 텍스트 병기) — 이 부분은 이미 양호해 추가 조치 없음.
  2. **온보딩 개선** — 회원가입 직후에만(이번 세션 한정, `justSignedUp` 플래그로 관리 — 새로고침하면 다시 로그인 흐름을 타 자연히 꺼짐) "오늘의 기록" 카드 위에 배너를 보여줌: 무엇을 입력하면 되는지 안내 + "예시 값 채워보기" 버튼(유효 범위 안의 예시 값을 폼에 채워주되 자동 제출은 하지 않음 - 사용자가 확인 후 직접 제출) + "닫기" 버튼. 첫 기록을 실제로 추가하면(예시든 직접 입력이든) 배너가 자동으로 사라짐.
  3. **theme.css spacing/typography 토큰화** — `--space-1`~`--space-8`, `--text-2xs`~`--text-xl` 스케일을 `:root`에 추가(색상과 달리 라이트/다크 분기 불필요). 가장 많이 반복되던 `font-size` 값부터 정규식으로 일괄 치환(14px→93건 중 index.html 61건/admin.html 32건이 `--text-base`/`--text-sm`/`--text-sm-plus`/`--text-xs`로 교체됨) — 나머지(17~36px 사이 제목류, 1~2건씩만 쓰이는 값들)는 이번 패스 범위 밖으로 남겨둠(문서화된 의도적 축소 범위 — "점진적으로 교체"라는 원 지시사항대로 한 번에 전부 바꾸지 않음).
  4. **파비콘/meta description/OG 태그** — 인라인 SVG data URI 파비콘(테두리 둥근 사각형 + 심박선, teal 액센트 색) 추가로 별도 이미지 파일 없이 처리. 두 파일 모두 `<meta name="description">`, `<meta property="og:title/description/type">` 추가.
  - 회귀: `pytest -q` 41 passed, 0 warnings(백엔드 변경 없음, 프론트만 수정) / Playwright로 라벨-인풋 연결 실제 포커스 이동, 모달 role/aria-labelledby, Esc로 모달 닫힘, CSS 변수가 실제 계산값(11px 등)으로 정확히 해석되는지, 온보딩 배너 표시→예시값 채움→첫 기록 제출 후 배너 소멸까지 전부 실제 브라우저로 확인. 라이트/다크 테마 스크린샷 비교로 시각적 회귀 없음 확인. 테스트 계정 삭제 후 DB 50명/62건 기준선 복귀 확인.
  - **신규 파일**: 없음(기존 파일만 수정)

- [x] **AUDIT_REPORT.md + CTO_AUDIT_REPORT.md 기반 종합 개선 — Phase 6 (백업 도구, 로컬 스크립트만)** (2026-07-22)
  1. **DB 백업 스크립트** — `backend/backup_db.py` 신설. `promote_admin.py`/`seed_demo_data.py`와 같은 위치·컨벤션의 로컬 전용 CLI 스크립트. 단순 파일 복사 대신 `sqlite3.Connection.backup()`(온라인 백업 API)을 써서, 서버가 켜져 있어 DB가 쓰기 도중이어도(트랜잭션 중간) 일관된 스냅샷을 뜬다 — 파일을 그대로 복사하면 손상된 백업이 나올 수 있음. `backups/` 디렉토리에 `health_log_YYYYMMDD_HHMMSS.db` 형식으로 저장하고, 파일명이 문자열 정렬 = 시간순 정렬이 성립하는 걸 이용해 개수 기준으로 오래된 백업을 자동 정리(`--keep`, 기본 14개, 0이면 무제한 보관). `backups/`는 `data/`와 마찬가지로 `.gitignore`에 추가(데이터이지 소스가 아님).
     - 실제 개발 DB(50명/62건)를 대상으로 백업을 떠서 새 파일이 생성되고 sqlite3로 열어 users/health_records 개수가 원본과 정확히 일치하는지 확인. 정리 로직은 격리된 임시 디렉토리에서 6개의 가짜 타임스탬프 백업을 만들어 `--keep 3` 실행 시 **가장 최근 3개만 남고 오래된 3개가 정확히 삭제**되는지, `--keep 0`이면 아무것도 안 지워지는지 별도로 검증.
     - 실제 주기적 실행을 위한 cron(리눅스)/작업 스케줄러(Windows) 등록은 사용자 지시대로 **이번 범위에서 제외** — 서버 배포 단계에서 별도로 진행.
     - README.md에 파일 구조 표 + 사용법 한 줄 추가(다른 로컬 전용 스크립트들과 동일한 문서화 패턴).
  - 회귀: `pytest -q` 41 passed, 0 warnings(신규 스크립트는 앱 런타임과 무관해 기존 테스트에 영향 없음). curl 스모크는 이번 Phase에서 서버 동작 자체를 바꾸지 않아 생략.
  - **신규 파일**: `backend/backup_db.py`

- [x] **AUDIT_REPORT.md + CTO_AUDIT_REPORT.md 기반 종합 개선 — Phase 7 (관리자 시각화 확장 + 최소 웹 푸시, 사용자 확인 후 진행)** (2026-07-23)
  1. **코호트/리텐션 분석** — `admin_analytics.py`에 `compute_cohort_retention()` 추가. 가입 주(월요일 시작 기준)로 사용자를 묶어, 그 코호트가 N주차(0~3주차)에 **그 특정 주간에** 실제로 기록을 남긴 비율을 계산(표준적인 코호트 리텐션 정의 — "그 이후 아무때나 활동"이 아니라 "그 주에 활동"). 아직 도래하지 않은 주는 `null`로 구분(0%와 혼동 방지). `AdminStatsOut.cohort_retention`으로 노출.
     - **dataviz 스킬 적용**: "여러 값을 비교하는 그리드"라 히트맵이 정답(choosing-a-form.md). CSS `color-mix(in oklab, var(--teal) N%, var(--card))`로 순차(sequential) 단일 색조 램프를 구현 — 기존 --teal/--card 토큰이 이미 라이트/다크별로 정의돼 있어 다크모드 대응이 별도 작업 없이 자동으로 됨. 값이 몇 개 안 되는 그리드라 히트맵 관례대로 셀마다 숫자를 직접 표기(막대 차트의 "포인트마다 숫자 금지"와는 다른 케이스 - 표 자체가 곧 "테이블 뷰"라 별도 표 보기 불필요).
     - 검증: `models.User`/`HealthRecord`를 세션 없이 메모리에서 구성해 코호트 경계(월요일 기준)·미도래 주 null 처리·복수 코호트 계산을 pytest로 정밀 검증(`test_admin_analytics.py`, 3개). 실제 개발 DB(50명) 대상으로도 실행해 코호트 인원 합계가 총 사용자 수(50)와 정확히 일치함을 확인. Playwright로 라이트/다크 양쪽 스크린샷 확인 — 색상이 테마별로 올바르게 반전됨.
  2. **최소 Web Push 알림/리마인더** — `pywebpush`/`py-vapid` 추가, VAPID 키 쌍을 생성해 `.env`(로컬)/`.env.example`(템플릿)에 반영. `PushSubscription` 모델(엔드포인트당 1행, `last_reminder_sent_date`로 당일 중복 발송 방지) + Alembic 마이그레이션. `routers/push_router.py`: `GET /push/vapid-public-key`, `POST /push/subscribe`(같은 endpoint 재구독 시 upsert), `POST /push/unsubscribe`, `POST /push/send-reminder`(관리자 전용).
     - **설계 결정 — 왜 수동 발송인가**: 이 프로젝트는 배경 스케줄러(APScheduler/Celery 등)를 쓰지 않고 지연 평가로 버텨왔다(`auth.cleanup_expired_sessions`/`badges.py`/`CoachingCache` 참고 — 전부 "그 사용자가 다시 접속했을 때"만 평가). 하지만 리마인더 알림은 정의상 "안 돌아온 사람을 부르는 것"이라 그 사용자 자신의 요청 사이클 안에서는 절대 트리거될 수 없다 - 그래서 이 기능만 예외적으로 관리자가 누르는 수동 트리거로 구현했고, 실제 매일 자동 발송이 필요하면 배포 단계에서 이 엔드포인트를 cron으로 호출하면 된다(Phase 6 백업 스크립트와 동일한 경계 — 스크립트/엔드포인트는 만들어 두고 스케줄 등록은 배포 시로 미룸).
     - 프론트: `frontend/static/sw.js`(서비스 워커, `/app/sw.js`로 서빙 - `/app/` 스코프 전체를 제어) 신설. `index.html` 계정 설정 모달에 "알림 받기/꺼두기" 토글 버튼(Notification 권한 요청 → 서비스 워커 등록 → VAPID 공개키로 구독 → 서버에 등록, 실패해도 toast로만 알리고 앱이 깨지지 않게 처리). `admin.html` 개요 탭에 "오늘 리마인더 발송" 버튼(발송/이미 활동함/이미 발송됨/실패 건수를 결과로 표시).
     - **정적 파일 캐싱 보완**: Phase 3의 "CSS/JS는 1시간 캐시" 규칙이 `sw.js`에도 적용되고 있던 걸 발견해, 서비스 워커는 갱신 시점이 중요하므로 `no-cache`로 예외 처리 추가(`main.py`).
     - 검증: pytest 8개 신규(`test_push.py`) — 구독/구독해제/같은 endpoint 재구독 시 upsert(행 안 늘어남)/관리자 아니면 403/오늘 활동한 사용자 건너뜀/오늘 이미 보낸 구독 건너뜀/410 응답 시 만료 구독 자동 삭제까지 `pywebpush.webpush()`를 monkeypatch로 대체해 실제 네트워크 호출 없이 "누구를 고르는 로직"만 검증. **테스트 작성 중 자체 버그 발견**: 테스트 파일 최상단에서 `routers.push_router`를 import해두면 conftest의 매 테스트 재로드(`_reset_app_modules`) 이후에는 오래된 모듈 참조가 되어 monkeypatch가 실제 요청 처리 경로에 반영되지 않음 — 각 테스트 함수 안에서(픽스처가 재로드를 끝낸 뒤) import하도록 수정(Phase 2-3 라우터 분리 때 겪은 것과 같은 종류의 문제).
     - **Playwright 검증의 한계 (문서화)**: Chromium은 기본(incognito 유사) 컨텍스트에서 Push API 자체를 지원하지 않음(`crbug.com/41124656`) - `launch_persistent_context()`로 우회해봐도 이 샌드박스 환경엔 실제 푸시 서비스(Google/Mozilla)로 나가는 네트워크 경로가 없어 "push service not available"로 끝남. 서비스 워커 등록 성공 + 알림 권한 플로우 + 실패 시 정상적으로 toast만 뜨고 앱이 안 깨지는 것까지는 실제 브라우저로 확인했고, 실제 푸시 전송 자체는 HTTPS로 배포된 진짜 브라우저 환경에서만 검증 가능(문서화된 한계 — 회피 없이 있는 그대로 기록).
  - 회귀: `pytest -q` **52 passed, 0 warnings** / curl 스모크(로그인·`/admin/stats`·`/push/vapid-public-key`·`/app/sw.js`·`/docs`) 전부 정상 / Playwright로 코호트 히트맵 라이트·다크, 관리자 리마인더 발송 버튼(확인 모달→발송→결과 렌더링) 확인. 테스트 계정 삭제 후 DB 50명/62건 기준선 복귀 확인.
  - **신규 파일**: `backend/routers/push_router.py`, `backend/tests/test_admin_analytics.py`, `backend/tests/test_push.py`, `backend/alembic/versions/3fcbd6117404_add_push_subscriptions_table.py`, `frontend/static/sw.js`

- [x] **디자인 기본기 + 시각적 위계 강화 (Phase 7 이후 추가 요청, CTO_AUDIT_REPORT.md 범위 밖의 사용자 후속 요청)** (2026-07-23)
  - 사용자가 "웹디자인 암묵적 룰/공식이 잘 지켜져 있지 않은 것 같다"고 지적 — grep으로 실제 확인해보니 사실이었음(추측이 아니라 수치로 확인):
    - 타이포그래피: `--text-*` 토큰이 Phase 5에 만들어졌지만 본문급(11~14px)에만 적용되고, 제목류는 17/18/19/20/21/22/25/28/36px 등 9개 값이 전부 하드코딩(스케일 없음). 게다가 정수 검색(`[0-9]+px`)에 안 걸리는 **소수점 값**(11.5/12.5/13.5/14.5px)이 20건 추가로 숨어있었음 — 기존 정수 스텝 사이를 임의로 반씩 쪼갠 값들.
    - 간격: Phase 5-13에서 만든 `--space-*` 토큰이 **실사용 0건**이었음(정의만 해두고 안 씀) — 105개 padding/margin/gap 선언이 전부 9px/7px/5px/3px 같은 4의 배수가 아닌 임의값.
    - border-radius: 7/6/5/20/8/1/16/10/9/4px 등이 뒤섞여 있었고, 이미 만들어둔 `--radius-sm/md/lg` 토큰은 정의만 되고 거의 안 쓰이는 상태.
    - 시각적 위계: 건강 스코어("99")가 대시보드에서 가장 중요한 숫자인데도 인라인 스타일로 22px만 지정되어 있어, 부수적인 통계값(28px)보다도 작게 표시되고 있었음 — "가장 먼저 봐야 할 숫자"가 눈에 안 띄는 실질적 결함.
  - **범위 협의**: AskUserQuestion으로 "기본기만" / "기본기+위계 강화" / "일단 보고만 판단" 중 선택받음 → **"기본기 + 시각적 위계 강화"** 선택.
  1. **타이포그래피 스케일 확장** — `theme.css`에 `--text-md(16)/--text-lg(18)/--text-xl(20)/--text-2xl(24)/--text-3xl(28)/--text-4xl(36)/--text-hero(48)` 추가(기존 11~14px 스텝에 이어짐). 9개 제목 하드코딩 값 + 20건의 소수점 값을 전부 역할별로 토큰에 매핑(예: 카드 h2와 모달 h3처럼 같은 "구성요소 제목" 역할은 하나의 토큰으로 통일). `.score-card .score-num`은 `--text-hero(48px)`로 대폭 키우고, 기존에 이 크기를 덮어쓰던 인라인 `style="font-size:22px"`를 JS 템플릿에서 제거.
  2. **간격을 4pt 그리드로 스냅** — 정규식 스크립트로 index.html 212건 + admin.html 114건의 padding/margin/gap 리터럴을 전부 `--space-*` 토큰으로 치환(0이 아닌 값 기준, 이미 토큰인 것은 건드리지 않음). 60/80/84px 같은 큰 값이 40px로 뭉개지는 초기 버그를 발견해 `--space-12(48)/--space-14(56)/--space-16(64)/--space-20(80)`을 추가로 정의해 해결(스케일이 40에서 끊겨 있던 게 원인).
  3. **border-radius 3단계 스케일 + pill 정리** — `--radius-xs(4)` / `--radius-pill(999px)`를 신규 추가해 기존 `--radius-sm(8)/--radius-md(12)/--radius-lg(16)`과 합쳐 5단계로 완성. 폼 컨트롤/버튼류(7·6·5·9px)는 전부 `--radius-sm`, 카드/모달류(12·10px)는 `--radius-md`, 뱃지/칩/토글 파일류(20·16px)는 `--radius-pill`, 얇은 진행바(4px)는 `--radius-xs`로 통일.
  4. **시각적 위계 강화** — (a) 건강 스코어 카드에 `linear-gradient(180deg, var(--teal-soft), var(--card) 70%)` 배경 워시 + `border-color:var(--teal)` + `box-shadow:var(--shadow-md)`를 추가해 나머지 흰 배경 히어로 카드들과 확실히 구분되게 함(라이트/다크 전부 기존 테마 토큰만 사용해 별도 다크 대응 불필요 — 자동으로 반전됨). (b) `.hero-row` 아래쪽 여백을 카드 간 기본 간격(20px)보다 넓게(24px) 둬서 "오늘의 상태" 블록이 그 아래 "오늘의 기록" 입력 폼과 시각적으로 분리된 하나의 장(chapter)처럼 읽히게 함(근접성 게슈탈트 원칙).
  - 검증: 매 단계(타이포→간격→radius→위계강화)마다 Playwright로 라이트/다크 스크린샷 확인, 최종적으로 `grep`으로 font-size/border-radius/padding·margin·gap 전부에 하드코딩 리터럴이 **0건**임을 재확인. `pytest -q` 52 passed(백엔드 무변경). 임시 관리자 계정으로 admin.html도 확인, 테스트 계정 삭제 후 DB 50명/62건 기준선 복귀 확인.
  - **신규 파일**: 없음(theme.css/index.html/admin.html만 수정)

- [x] **레이아웃 여백/영역 크기 정합성 보강 (디자인 후속 요청 2)** (2026-07-23)
  - 사용자가 토큰화 작업 이후에도 "관리자/사용자 페이지 모두 영역별 크기가 제각각이고, 영역 안 내용에 비해 영역이 너무 커서 빈 공간이 많고, 시각화 자료 내부 간격도 엉망"이라고 재지적. 이번엔 눈대중이 아니라 Playwright `getBoundingClientRect()`로 실제 렌더링 크기를 측정해 확인:
    - index.html 히어로 카드 4개가 전부 grid stretch로 248px 높이로 강제되는데, 체중/혈압/혈당 카드는 내용이 3줄뿐이라 실제로는 ~130px만 있으면 충분 — 나머지 절반 가까이가 빈 공간이었음(수치로 확인).
    - `.summary-grid`(목표 진행률/최근 배지/이번주 변화) 3개 카드도 124px로 강제되는데 "설정된 목표가 없습니다" 한 줄짜리 카드는 절반이 빔.
    - admin.html `#kpi-row-2`의 평균 BMI/혈압/혈당 카드는 보조 설명(`.d`)이 없어 다른 카드보다 내용이 짧은데도 같은 높이로 강제됨.
    - **가장 심각한 사례**: "가입 추이" 차트 카드가 옆의 "최근 활동"(로그 5줄+버튼) 카드와 같은 높이(393px)로 늘어나는데, 차트 SVG는 고정 `height:130px`라 카드 안에 150px 이상의 순수 빈 공간이 육안으로도 뚜렷하게 보였음.
    - **버그 발견**: index.html "측정 추이" 라인 차트의 마지막 값 라벨("58.1")이 최고점 근처에서 SVG 상단 밖으로 잘려나가고 있었음(`padTop:16px`인데 라벨을 점 위 11px에 그리는 로직이라 여유 공간 부족) — dataviz 스킬의 anti-pattern("라벨이 컨테이너 밖으로 잘림")에 정확히 해당하는 실제 버그.
  - 1. **내용이 적은 카드는 세로 가운데 정렬** — `.metric-card`/`.kpi-card`에 `justify-content:center` 추가. `.summary-card`는 제목(`sc-title`)은 위에 고정하고 나머지 내용만 `.sc-body`로 감싸 그 안에서 가운데 정렬(3장의 JS 렌더 함수 수정) — 제목 줄은 카드 3개가 나란히 정렬된 채로, 내용이 적은 카드만 자연스럽게 여백을 흡수.
  - 2. **차트가 카드 높이를 실제로 채우도록 전환** — admin.html "가입 추이" 차트를 감싸는 카드에 `trend-card` 클래스를 부여해 flex-column으로 만들고, `.trend-chart-wrap`을 `flex:1`로 전환. `renderTrendChart()` JS를 index.html의 "측정 추이" 차트와 같은 패턴으로 바꿔 `getBoundingClientRect()`로 실제 렌더링된 너비/높이를 매 호출마다 측정해 viewBox에 반영(고정 560×130 하드코딩 제거) — 옆 카드가 더 길어지면 차트도 그만큼 커져서 빈 공간이 생기지 않음. 막대 클릭/hover 툴팁은 좌표 그대로(마우스 좌표 기반)라 영향 없음(Playwright로 hover 시 툴팁 정상 동작 재확인).
  - 3. **차트 라벨 잘림 버그 수정** — index.html 라인 차트의 `padTop`을 16px→28px로 늘려, 마지막 값 라벨이 최고점 근처에 와도 SVG 위쪽 경계 안에 완전히 들어가도록 함.
  - 검증: Playwright로 실제 카드 높이를 다시 측정해 빈 공간이 줄었는지 확인, 라이트/다크 스크린샷으로 "가입 추이" 차트가 카드를 꽉 채우는지 육안 확인, 라벨 잘림이 해소됐는지 확인. `pytest -q` 52 passed(백엔드 무변경). 임시 관리자 계정 3개를 순차로 만들어 확인 후 전부 삭제, DB 50명/62건 기준선 복귀 확인.
  - **신규 파일**: 없음(index.html/admin.html만 수정)

- [x] **AWS Lightsail 실배포** (2026-07-23) — https://healthcare.kro.kr/ (서울 리전, Ubuntu 22.04, 4.16Gi 스왑 추가 후 416Mi RAM에서 안정 운영)
  1. **접속/사전 조사**: SSH(3.36.92.148, ubuntu, .pem 키)로 접속 확인. 기존에 이 프로젝트와 무관한 `my-web` 컨테이너(포트 8080)가 이미 떠 있는 것을 발견 — 건드리지 않고 별도 포트/설정으로 배포 진행.
  2. **트러블슈팅 — apt 잠금**: `apt.systemd.daily`(우분투 자동 일일 업데이트)가 `apt-get check`에서 멈춰(9분+ 경과, R 상태로 실제 행) `/var/lib/dpkg/lock-frontend`를 계속 붙잡고 있어 `nginx`/`certbot` 설치가 막힘. 해당 프로세스를 강제 종료하고 락 파일 정리, 이후 재발 방지를 위해 `apt-daily.timer`/`apt-daily-upgrade.timer`를 mask 처리.
  3. **트러블슈팅 — 방화벽**: 사용자가 Lightsail 콘솔에서 HTTPS(443) 규칙을 추가하는 과정에서 순간적으로 SSH(22)/HTTP(80)까지 같이 막힌 것으로 추정되는 전체 접속 불가 상태 발생 → 콘솔에서 규칙 재확인 후 복구.
  4. **트러블슈팅 — 메모리 부족**: 인스턴스가 최소 사양(총 416Mi RAM, 스왑 0)이라 서버에서 직접 `docker build`(python 패키지 컴파일 포함)를 시도하니 메모리 고갈로 SSH 접속 자체가 간헐적으로 끊기고 빌드가 사실상 멈춤(load average 22+). **로컬(개발 환경)에서 이미지를 빌드해 `docker save | gzip`(105MB→77MB) → `scp` → 서버에서 `docker load`** 하는 방식으로 전환해 해결 — 로컬 빌드는 30초 만에 끝남. 서버에는 이후 안정성을 위해 스왑 1GB도 추가.
  5. **트러블슈팅 — 시크릿 유출(중요)**: 로컬에서 빌드한 첫 이미지에 로컬 `backend/.env`(개인 OpenAI API 키 포함)와 `venv/` 전체가 그대로 들어가 있는 것을 배포 직전에 발견 — 원인은 `.dockerignore`의 `.env`/`venv/` 같은 bare 패턴이 Docker에서는 **컨텍스트 루트에서만 매치되고 `backend/.env`처럼 중첩된 경로는 매치하지 않는(.gitignore와 다른 동작) 것**이었음. `.dockerignore`에 `**/.env`, `**/venv/`, `**/*.pem` 등 이중 패턴을 추가해 실제로 제외되는지 이미지 안을 직접 열어(`docker run ... ls`) 재확인 후, 유출됐던 이미지/tar.gz는 로컬·서버 양쪽에서 즉시 삭제. 이미지 크기도 475MB→327MB로 줄어듦(venv 제외 효과). *(개인 API 키가 사설 인프라 밖으로 나간 적은 없지만, 만에 하나를 위해 로테이션을 고려할 만함 — 사용자에게 안내함.)*
  6. **배포 구성**: `nginx`(80/443) → 컨테이너(`127.0.0.1:8001`, `--restart unless-stopped`) 리버스 프록시. SQLite 데이터는 `~/healthcare-data`를 `/app/data`로 바인드 마운트해 컨테이너 재생성에도 유지. 운영용 VAPID 키를 로컬 개발용과 별도로 새로 생성해 `.env`에 반영, `COOKIE_SECURE=true` 설정. `healthcare.kro.kr` 도메인은 사용자가 DNS A 레코드를 직접 설정.
  7. **HTTPS**: DNS/방화벽 확인 후 `certbot --nginx`로 Let's Encrypt 인증서 발급 성공(2026-10-21 만료, 자동 갱신 등록됨), HTTP→HTTPS 리다이렉트 자동 구성.
  8. **검증**: 실제 도메인으로 회원가입→로그인→기록 생성/조회 curl 검증 — 응답의 `Set-Cookie`에 `Secure` 속성이 실제로 붙는 것 확인(COOKIE_SECURE=true 반영 확인). `/app/admin.html` 로드 확인. 테스트 계정은 탈퇴로 정리. 기존 `my-web` 컨테이너가 배포 작업 내내 영향받지 않고 정상 응답하는지 재확인.
  9. **백업 cron 등록**: `backup_db.py`(표준 라이브러리만 사용해 컨테이너 밖에서도 실행 가능)를 매일 새벽 3시 cron으로 등록, `~/healthcare-backups`에 최근 14개 보관.
  - **신규 파일**: 없음(로컬 `.dockerignore`만 수정). 서버 쪽 산출물(nginx 설정, 인증서, cron, systemd mask)은 저장소 밖의 인프라 상태라 이 문서에 정리만 하고 별도 코드로 커밋하지 않음.

- [x] **모바일 헤더/하단 내비/푸터 레이아웃 버그 수정** (2026-07-23) — 사용자가 "헤더랑 푸터가 한 줄로 보여야 하는데 줄바꿈된다, 전체적으로 모바일 최적화 필요"라고 지적. 서버는 사용자가 비용 절감을 위해 중지시켜 두어 이번 작업은 로컬 코드만 수정(서버 동기화는 나중에 사용자가 별도 요청 시 진행).
  - Playwright로 375×667(iPhone SE급) 뷰포트를 실제로 로그인 후 캡처·측정(`getBoundingClientRect()`)해 눈대중이 아니라 수치로 원인 확인.
  - **버그 1 — `.topbar` 줄바꿈**: 대시보드 상단 바(뷰 제목 + 테마 토글 3버튼 "라이트/시스템/다크" + 사용자명 + "계정 설정"/"로그아웃")가 `flex-wrap:wrap`인 채로 모바일 전용 오버라이드가 전혀 없어 131px 높이로 2~3줄에 걸쳐 줄바꿈되고 있었음. 모바일(~720px)에서: `flex-wrap:nowrap`으로 전환, 테마 토글 버튼을 텍스트 라벨 대신 아이콘 전용(☀/⚙/🌙, 버튼 자체에 정적 `aria-label`을 둬 스크린리더 접근성 유지)으로 축소, 사용자명(`#whoami-text`)은 저우선순위 정보라 모바일에서 숨김(계정 설정 모달에서 확인 가능), 나머지 버튼도 패딩/폰트 축소. 결과: topbar 높이 131px → 30px, 한 줄로 정리되고 우측 잘림(overflow) 없음을 재확인.
  - **버그 2 — 하단 탭바(`.side-nav`)가 세로로 쌓임**: 데스크톱 규칙 `nav.side-nav{flex-direction:column}` (element+class, 특이도 0,0,1,1)이 모바일 미디어쿼리의 `.side-nav{flex-direction:row}` (class만, 특이도 0,0,1,0)보다 특이도가 높아 미디어쿼리 안에서도 데스크톱 규칙이 계속 이겨서, 기록/통계 & 리포트/목표 3개 탭이 가로 정렬이 아니라 각각 전체 너비(359px)로 세로로 쌓이고 있었음(이 때문에 하단 바 전체 높이가 170px까지 부풀어 있었음). 모바일 선택자를 `nav.side-nav{...}`로 맞춰 특이도를 동일하게 하고 소스 순서로 정상 override되게 수정 → 하단 바 높이 170px → 68px, 3개 탭이 나란히 정렬됨.
  - **버그 3 — `<footer>` 문구가 고정 하단 탭바에 완전히 가려짐**: `<footer>`가 `.shell`/`.content` 바깥의 형제 요소라 `.content`에 이미 있던 하단 여백(고정 탭바를 위한 `padding-bottom`)을 전혀 받지 못했고, 탭바는 `position:fixed;bottom:0`이라 스크롤을 끝까지 내려도 항상 뷰포트 최하단을 덮어 문구 자체가 화면에 전혀 보이지 않는 상태였음(버그 2로 탭바가 170px까지 부풀어 있어 더 심했음). 로그인 시 `body`에 `logged-in` 클래스를 토글하도록 JS(`showApp`/`showAuthScreen`)를 수정하고, 모바일에서 `body.logged-in footer`에만 `padding-bottom:calc(var(--space-20) + env(safe-area-inset-bottom))`을 부여해 하단 탭바 높이만큼 여백을 확보(로그인 전 화면은 탭바가 없으므로 이 여백을 받지 않아 불필요한 빈 공간이 생기지 않음). 첫 시도는 `margin-bottom`으로 처리했으나 `html,body{height:100%}`가 명시적 높이라 마지막 자식의 하단 마진이 시각적으로 반영되지 않는 현상을 실측으로 확인 후 `padding-bottom`(마진 collapse 없음)으로 교체.
  - **부가 개선**: 본문(`body`)에 `word-break:keep-all`을 전역 추가해 한글 문구가 어절 중간에서 어색하게 끊기지 않도록 함(기존에 누락돼 있던 한글 웹 기본기). 푸터는 모바일에서 폰트 크기를 한 단계 줄여(`--text-sm`) 2줄 줄바꿈이 자연스럽게 보이도록 함(문구 자체가 길어 320px 폭에서 완전한 한 줄은 비현실적 — 사용자 원 지적의 핵심이었던 "레이아웃이 깨져 아예 안 보이거나 뒤섞이는" 문제를 해결하는 데 집중).
  - 검증: Playwright로 라이트/다크 테마 모두 재확인(테마 토글은 여전히 `data-theme-choice` 데이터 속성 기반으로 동작해 아이콘/라벨 마크업 변경의 영향 없음). `pytest` 대상 백엔드 변경 없음(프론트엔드 CSS/HTML/JS만 수정).
  - **범위**: 사용자가 "사용자 페이지" 모바일만 명시적으로 지적해 admin.html은 이번 수정 대상에서 제외(관리자 페이지는 데스크톱 전용 사용을 가정).
  - **신규 파일**: 없음(index.html만 수정)

## 7. 다음 작업

1. (제안) 관리자 대시보드에도 사용자 화면처럼 시각화가 있으니, 향후 필요시 이 Playwright 스크린샷 검증 방식을 `/run-skill-generator`로 프로젝트 스킬화하는 것을 고려 — 매번 임시 Node 프로젝트를 새로 만들 필요 없어짐
2. **배포 완료** — https://healthcare.kro.kr/ 에서 실제 운영 중. CTO_AUDIT_REPORT.md 기반 Phase 1~7 + 디자인 보강 + 실배포까지 이 프로젝트의 전체 작업 범위가 전부 완료됨.
3. 남은 선택 사항: (a) 개인 OpenAI API 키가 잠깐 이미지에 들어갔던 사고 이력이 있어 원하면 키 로테이션 고려, (b) `POST /push/send-reminder`(리마인더 알림)를 정말 매일 자동 발송하고 싶다면 관리자 인증을 포함한 별도 cron 스크립트 설계 필요(지금은 관리자가 대시보드에서 수동 발송), (c) 인스턴스가 최소 사양(416Mi RAM)이라 트래픽이 늘면 Lightsail 플랜 업그레이드 검토, (d) 시드 계정 비밀번호(`demo1234` 등)가 코드/문서에 공개돼 있어 실제 서비스로 계속 운영한다면 초기 배포 직후 전부 재설정하거나 삭제하는 걸 권장.
4. **DB 데이터 이관 (2026-07-23 추가)** — 최초 배포 시 Alembic으로 스키마만 만들고 로컬 데이터(가입자 50명/기록 62건)는 옮기지 않아, 배포 직후 기존 로그인 정보로 접속이 안 되는 문제가 있었음. 로컬 `data/health_log.db`를 서버로 전송해 교체(컨테이너 정지 → DB 파일 교체 → 재시작)하는 방식으로 해결. **주의**: 컨테이너가 root로 도니 바인드 마운트된 DB 파일도 host에서 root 소유가 되어 `ubuntu` 사용자가 직접 덮어쓸 수 없었음 — `sudo cp`로 처리. 다음에 로컬 DB를 다시 배포 서버에 반영할 일이 있으면 같은 방식(컨테이너 정지 → `sudo cp` → 소유권 조정 → 재시작) 사용.
5. **서버 동기화 대기 중 (2026-07-23 추가)** — 사용자가 비용 절감을 위해 Lightsail 인스턴스를 의도적으로 중지시켜 둔 상태. 위 "모바일 헤더/하단 내비/푸터 레이아웃 버그 수정"은 로컬(GitHub)에만 반영되어 있고, 실제 운영 서버(`healthcare.kro.kr`)에는 아직 반영되지 않음 — 사용자가 서버를 다시 켜고 동기화를 요청하면 기존 배포 절차(로컬 빌드 → `docker save`/`scp`/`docker load` → 컨테이너 재기동)를 따라 반영할 것.

## 8. 이후 계획 (미착수)

### Phase E — 논의 필요한 다음 후보 (AUDIT_REPORT.md 기반, 지금은 구현하지 않음, 2026-07-22)

아래 5개는 감사 보고서에서 제안됐지만, 지금 당장 구현하지 않고 백로그로만 남겨둔다
(우선순위/범위에 대해 먼저 논의가 필요하다고 판단).

- **웨어러블 실제 연동** — 지금은 `integrations.MockWearableDataSource`만 존재. Apple Health/Samsung Health/Google Fit 각각 OAuth 연동 + 실제 REST/SDK 호출이 필요해 범위가 큼. `WearableDataSource` 인터페이스는 이미 준비되어 있어, 실제 연동 시 새 구현체 클래스 하나만 추가하면 됨.
- **건강검진 PDF 실제 파싱** — 지금은 `integrations.MockHealthCheckupPdfImporter`가 고정된 예시 기록 하나만 반환. 실제로는 병원/기관마다 PDF 레이아웃이 달라 OCR/정규식 파싱 전략을 먼저 정해야 함 (pdfplumber 등 새 의존성 필요).
- **알림/리마인더** — 기록을 안 남긴 날 알림을 보내는 기능. 이메일/푸시/문자 등 어떤 채널을 쓸지, 배경 스케줄러(Celery/APScheduler 등 새 인프라)를 도입할지부터 결정 필요 — 지금까지 이 프로젝트가 지연 평가로 배경 스케줄러를 피해온 것과 방향이 다름.
- **사용자 행동 감사 로그 확장** — 지금 `audit_logs`는 관리자 조치(계정 삭제/강제 로그아웃)만 기록. 사용자 자신의 로그인/기록 수정 등까지 남기려면 로그 테이블 용량 증가와 개인정보 보관 정책을 먼저 정해야 함.
- **i18n(다국어 지원)** — 지금은 한국어 문자열이 프론트/백엔드 전반에 하드코딩되어 있어, 다국어화하려면 문자열 추출부터 시작하는 큰 작업. 실제 다국어 사용자가 필요해지는 시점에 재검토.

## 9. 유의사항

- 코드 스스로 작성 원칙 — 참고 자료 활용 시 README에 명시
- venv/, data/, __pycache__ 는 .gitignore로 제외되어 있어 커밋되지 않음 (정상)
- 건강 분류 기준은 학습용 단순화 값, 실제 진단 아님
