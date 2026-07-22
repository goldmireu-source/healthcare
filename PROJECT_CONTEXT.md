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

## 7. 다음 작업

1. (제안) 관리자 대시보드에도 사용자 화면처럼 시각화가 있으니, 향후 필요시 이 Playwright 스크린샷 검증 방식을 `/run-skill-generator`로 프로젝트 스킬화하는 것을 고려 — 매번 임시 Node 프로젝트를 새로 만들 필요 없어짐
2. AWS Lightsail 배포 단계로 진행 (8번 섹션 참고) — **AUDIT_REPORT.md 기반 Phase A~D 작업 완료 후 진행 예정**
3. Phase D(CSV Import 저장 연결, OpenAI 실연동) 진행 중

## 8. 이후 계획 (미착수)

- AWS Lightsail 테스트 서버에 배포 (계정/서버는 이미 생성되어 있음, 접속 정보는 작업 시점에 확인 필요)
  - 배포 시 `COOKIE_SECURE=true` 환경변수 설정 권장 (HTTPS 적용 시)
- 배포 후 README.md의 "배포 접속 URL" 항목 채우기
- 최종 git push 및 제출 체크리스트 확인 (venv/data.json 미포함, README 완성 등)

## 9. 유의사항

- 코드 스스로 작성 원칙 — 참고 자료 활용 시 README에 명시
- venv/, data/, __pycache__ 는 .gitignore로 제외되어 있어 커밋되지 않음 (정상)
- 건강 분류 기준은 학습용 단순화 값, 실제 진단 아님
