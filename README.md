# 마이 헬스 로그 API

매일 기록하는 몸무게·혈압·혈당 같은 건강 수치를 던져주면, 서버가 BMI를 계산하고 건강 상태를 분류하고 필요한 경고까지 알려주는 개인용 건강 기록 API입니다. 기록이 쌓이면 통계와 주간 리포트로 변화 추이도 확인할 수 있고, AI Health Coach가 추세를 분석해 코칭 메시지·주간 요약을 생성하며, 회원가입/로그인 기반으로 사용자별 데이터가 분리되고, 관리자 전용 대시보드도 별도로 제공됩니다.

## 폴더 구조

여러 사람이 각자 백엔드/프론트엔드를 나눠 맡는 상황을 가정해 폴더를 분리했습니다. **API 로직을 만질 때는 `backend/`만, 화면을 만질 때는 `frontend/`만 보면 됩니다.**

```text
healthcare/
├── backend/                 # FastAPI 서버 (Python) — API 담당자가 보는 영역
│   ├── main.py              #   앱 진입점, 라우트 전체 (엔드포인트 목록은 아래 참고)
│   ├── auth.py              #   비밀번호 해시(PBKDF2), 세션 발급/검증, 관리자 권한 체크
│   ├── models.py             #   SQLAlchemy ORM (User/Session/HealthRecord/Goal/AuditLog/Badge/CoachingCache)
│   ├── schemas.py            #   Pydantic 요청/응답 모델
│   ├── database.py           #   DB 연결 설정 (SQLite, ../data/health_log.db)
│   ├── health_logic.py       #   BMI/혈압/혈당 계산·분류·경고·활동량·수면 로직
│   ├── health_trends.py      #   지표별 추세(UP/DOWN/STABLE) 판단 — 다른 AI 기능들의 공용 기준
│   ├── health_coach.py       #   AI Health Coach 메시지 (규칙 기반 기본, OpenAI 연동 가능) + 주간 AI 요약
│   ├── risk_detection.py     #   급격한 수치 변화 감지 (LOW/MEDIUM/HIGH)
│   ├── health_score.py       #   가중치 기반 종합 건강 스코어 계산
│   ├── goal_prediction.py    #   목표 달성 예상 소요일 계산
│   ├── health_calendar.py    #   월별 날짜별 상태(good/warn/bad) 캘린더
│   ├── health_timeline.py    #   분류 개선/목표 달성 시점 타임라인 이벤트 추출
│   ├── badges.py             #   자동 획득 배지 판정(연속 기록/첫 정상 지표/첫 목표 달성)
│   ├── integrations.py       #   웨어러블/CSV/PDF 가져오기 확장 인터페이스 (CSV는 실제 동작)
│   ├── health_service.py     #   건강 기록 CRUD/BMI 평가 로직 (main.py에서 분리된 서비스 레이어)
│   ├── goal_service.py       #   목표 관리 로직
│   ├── report_service.py     #   주간 리포트 로직
│   ├── admin_service.py      #   관리자 대시보드(목록/통계/상세) 로직
│   ├── admin_analytics.py    #   관리자 대시보드 참여도/평균 지표 KPI 계산
│   ├── rate_limit.py         #   IP/계정 기준 요청 횟수 제한 (프로세스 내 인메모리 카운터)
│   ├── alembic/              #   DB 스키마 마이그레이션 (아래 "DB 스키마 변경" 참고)
│   ├── alembic.ini
│   ├── tests/                #   pytest 테스트 스위트 (아래 "테스트 실행" 참고)
│   ├── promote_admin.py      #   [로컬 전용] 기존 계정을 관리자로 승격하는 CLI 스크립트
│   ├── seed_demo_data.py     #   [로컬 전용] 데모 시연용 사용자/기록 생성 스크립트
│   ├── backup_db.py          #   [로컬 전용] DB 백업(타임스탬프 복사 + 오래된 백업 자동 정리)
│   ├── requirements.txt
│   ├── requirements-dev.txt  #   테스트 실행용 추가 의존성 (pytest, httpx)
│   ├── pytest.ini
│   ├── .env.example          #   환경변수 템플릿 (`.env`로 복사해서 사용, .env는 git에 포함 안 됨)
│   └── venv/                 #   (git에 포함 안 됨, 로컬에서 생성)
├── frontend/
│   └── static/               # 화면 담당자가 보는 영역 — 별도 빌드 없는 순수 HTML/CSS/JS
│       ├── index.html        #   일반 사용자 화면 (/app/)
│       ├── admin.html        #   관리자 대시보드 (/app/admin.html, index.html과 완전 분리)
│       └── theme.css         #   두 화면이 공유하는 라이트/다크 디자인 토큰
├── data/                     # sqlite 파일 저장 위치 (git에 포함 안 됨, 런타임에 생성)
├── Dockerfile                # backend/, frontend/를 그대로 담아 이미지 빌드
├── AUDIT_REPORT.md           # 외부 코드 감사 보고서 (보안/인프라/기능 개선 근거 자료)
├── PROJECT_CONTEXT.md        # 작업 이력/설계 결정 기록 (세션 간 인수인계용)
└── README.md
```

`backend/`와 `frontend/`는 항상 서로 형제 폴더이며(로컬 저장소·Docker 이미지 내부 모두 동일), `main.py`와 `database.py`는 이 배치를 `__file__` 기준 상대경로로 찾으므로 **uvicorn을 어디서 실행하든** (backend 폴더 안에서든, 다른 곳에서든) 같은 정적 파일/DB를 가리킵니다.

## 기능 목록

### 필수 기능

| 메서드 · 경로 | 설명 |
|---|---|
| `POST /records` | 건강 기록 추가. 저장 후 BMI·분류·경고를 계산해 응답 |
| `GET /records` | 로그인한 사용자의 전체 기록 조회 (개수 포함) |
| `GET /records/{id}` | 기록 하나 조회. 없으면 404 |
| `PUT /records/{id}` | 기록 수정 (수정 시 BMI/분류/경고 재계산) |
| `DELETE /records/{id}` | 기록 삭제 |
| `GET /search?start=&end=` | 날짜 범위로 검색 |
| `GET /stats` | 평균 체중·BMI·혈압·혈당·걸음수·수면 및 분류별 분포 통계 |

### 고도화 기능

| 메서드 · 경로 | 설명 |
|---|---|
| `POST /goals` | 목표 체중/혈압/혈당 설정 |
| `GET /goals` | 최신 기록 기준 목표 달성 여부 + 목표 달성 예상 소요일(`achievement.predictions`) 조회 |
| `GET /reports/weekly` | 최근 7일 평균 vs 지난주 평균 비교 + 자연어 AI 요약(`ai_summary`) |
| `GET /export/csv` | 전체 기록 CSV 다운로드 (수식 인젝션 방어 — `=`/`+`/`-`/`@`로 시작하는 셀은 자동 이스케이프) |
| `GET /export/json` | 전체 기록 JSON 다운로드 |

또한 모든 기록 응답에는 걸음 수 기반 **활동량 등급**(`activity_level`: 부족/적정/우수)과 수면 시간 기반 **수면 분석**(`sleep_status`: 부족/적정/과다)이 자동으로 포함됩니다.

기록/목표 입력값에는 상식적인 범위 검증이 있습니다 — 체중 ≤500kg, 키 ≤250cm, 혈압 수축기 ≤300·이완기 ≤200, 혈당 ≤1000, 걸음수 ≤100,000, 수면시간 ≤24시간, 메모 ≤500자. 날짜는 `YYYY-MM-DD` 형식의 실제 존재하는 날짜만 허용하고, 1900-01-01~내일 범위를 벗어나면 거부됩니다.

### AI Health Coach & 확장 기능

CRUD를 넘어 기록을 분석하고 행동을 유도하는 기능들입니다. 전부 로그인이 필요하고 본인 데이터만 대상입니다.

| 메서드 · 경로 | 설명 |
|---|---|
| `GET /health-coaching` | AI 코칭 메시지 목록. `OPENAI_API_KEY`가 설정되어 있으면 실제 OpenAI API로 생성하고, 키가 없거나 호출이 실패/타임아웃되면 자동으로 규칙 기반 메시지로 폴백. 비용 절감을 위해 **하루 1회만 생성**하고 그 뒤로는 캐시(`coaching_cache` 테이블) 재사용 |
| `GET /trends` | 체중/혈압/혈당/걸음수/수면 지표별 추세(UP/DOWN/STABLE) |
| `GET /risk-detection` | 급격한 수치 변화 감지 (LOW/MEDIUM/HIGH) |
| `GET /health-score` | 가중치 + 추세 보너스 기반 종합 건강 스코어(0~100) |
| `GET /calendar?year=&month=` | 월별 날짜별 상태(good/warn/bad) |
| `GET /timeline` | 분류가 좋아진 시점·목표 최초 달성 시점 타임라인 |
| `GET /badges` | 자동 획득 배지 목록(7일/30일 연속 기록, 첫 정상 BMI/혈압, 첫 목표 달성) — 조회 시점에 새로 만족한 조건이 있으면 그때 지급(배경 스케줄러 없음) |
| `GET /integrations/status` | 웨어러블/LLM/가져오기 연동 현황 (Mock 상태 vs 실제 연동 상태 표시) |
| `GET /integrations/wearable/mock?provider=&start=&end=` | 웨어러블 걸음수/수면 데이터 목(mock) 조회 |
| `POST /integrations/import/csv/preview` | CSV 내용을 저장 없이 파싱만 해서 미리보기 |
| `POST /integrations/import/csv/commit` | CSV를 실제로 저장. `POST /records`와 동일한 검증/BMI 계산을 재사용하며, 한 행이라도 검증에 실패하면 아무것도 저장하지 않고 실패 행 목록을 반환 |

> **AI Health Coach 관련 안내**: `OPENAI_API_KEY`를 설정하면 코칭 메시지 생성을 위해 건강 기록 요약이 OpenAI API로 전송됩니다(`/app/` 화면에도 이 안내 문구가 표시됨). 키를 설정하지 않으면 외부로 아무 데이터도 전송되지 않고 규칙 기반 코칭만 사용됩니다.

### 인증 (회원가입/로그인/비밀번호 관리)

세션은 서버 DB에 저장되는 랜덤 토큰을 HttpOnly 쿠키로 전달하는 방식이며(JWT 아님, 로그아웃 시 서버에서 즉시 폐기됨), 비밀번호는 PBKDF2-HMAC-SHA256으로 해시하여 저장합니다(평문 저장 없음).

**어뷰징 방지 가드레일**: 로그인 5회 연속 실패 시 해당 계정이 15분간 잠깁니다(423). 회원가입/로그인/비밀번호 찾기/비밀번호 변경은 IP(및 계정) 기준 요청 횟수 제한이 걸려 있어 짧은 시간에 과도하게 반복하면 429가 반환됩니다(`backend/rate_limit.py`, 외부 저장소 없는 프로세스 내 카운터). 회원가입 시 흔한 비밀번호("123456" 등)나 아이디와 동일한 비밀번호는 거부됩니다.

| 메서드·경로 | 설명 |
|---|---|
| `POST /auth/signup` | 회원가입 (아이디 3자 이상 영문/숫자/`_`, **이름 필수**, 비밀번호 6자 이상, 보안질문/답 필수) 후 자동 로그인. **role은 항상 "user"로 고정 생성** — API로는 절대 관리자가 될 수 없음 |
| `POST /auth/login` | 로그인 |
| `POST /auth/logout` | 로그아웃 (서버 세션 폐기) |
| `GET /auth/me` | 현재 로그인 사용자 정보 (`role`/`name` 포함) |
| `GET /auth/security-question?username=` | 비밀번호 찾기 1단계 — 등록된 보안질문 조회 |
| `POST /auth/reset-password` | 비밀번호 찾기 2단계 — 보안질문 답 확인 후 재설정 (기존 세션 전부 무효화) |
| `POST /auth/change-password` | 로그인 상태에서 비밀번호 변경 (현재 세션은 유지, 다른 기기 세션만 무효화) |
| `POST /auth/change-name` | 이름 변경/설정 (이름 필드가 회원가입에 추가되기 전 가입한 기존 계정도 이걸로 나중에 설정 가능) |
| `DELETE /auth/me` | 본인 계정 탈퇴 (비밀번호 재확인 필요, 기록/목표/세션 cascade 삭제) |

위 필수/고도화/AI 기능 엔드포인트는 전부 로그인이 필요하며, **로그인한 사용자 본인의 데이터만** 조회·수정·삭제할 수 있습니다.

### 관리자 기능

계정에는 `role`("user" 기본값 / "admin")이 있습니다. **회원가입으로는 절대 관리자가 될 수 없고**, 기존 계정을 관리자로 승격하려면 서버에 접근 가능한 사람이 로컬에서 `promote_admin.py <username>`을 직접 실행해야 합니다 (API로 노출되지 않음).

| 메서드·경로 | 설명 |
|---|---|
| `GET /admin/users` | 전체 사용자 목록. `search`(아이디 **또는 이름** 부분검색), `role`(user/admin), `risk`(high/moderate/normal/unknown), `online`(true=현재 로그인 상태), `signup_days`/`signup_date`/`active_days`/`has_records`(개요 KPI 드릴다운용 필터), `sort_by`/`sort_dir`(id·username·created_at·record_count·risk_level), `page`/`page_size` 지원 |
| `GET /admin/stats` | 시스템 전체 통계 — 총 사용자/기록 수, role 분포, 최근 7일 신규가입, 최근 14일 가입 추이, 현재 접속중인 사용자 수, 전체 사용자 BMI/혈압/혈당 분포, 최근 활동률/기록 유지율/가입 전환율/고위험 사용자 증가율 등 참여도 지표 |
| `GET /admin/users/{id}` | 사용자 상세 정보(회원정보 보기) — 이름/권한/가입일/보안질문/로그인 실패 횟수/계정 잠금 상태/접속 상태/활성 세션 수/최근 로그인 시각/기록 수/위험도 (비밀번호 해시 등 민감정보는 응답에 포함 안 함) |
| `GET /admin/users/{id}/records` | 특정 사용자의 건강기록 조회 (읽기 전용, 고객지원용) |
| `POST /admin/users/{id}/force-logout` | 계정은 유지한 채 해당 사용자의 모든 세션만 무효화 |
| `DELETE /admin/users/{id}` | 계정 삭제 (기록/목표/세션 cascade 삭제) |
| `GET /admin/audit-log` | 관리자 조치 이력 (계정 삭제·강제 로그아웃 — 누가/언제/누구에게) |

위 엔드포인트는 전부 관리자 권한이 없으면 403을 반환합니다. 자기 자신을 대상으로 한 강제 로그아웃/계정 삭제는 실수 방지를 위해 400으로 막혀 있습니다.

"현재 접속중"(`is_online`)은 실시간 접속 추적(하트비트/웹소켓)이 아니라 **만료되지 않은 로그인 세션 보유 여부**를 대리 지표로 씁니다 — 로그아웃하지 않고 창만 닫아도 세션 만료(7일) 전까지는 온라인으로 표시됩니다.

### 화면 (별도 빌드 없는 순수 HTML/CSS/JS)

`/docs`는 개발자용 API 테스트 도구이고, 실제 화면은 두 개로 **완전히 분리**되어 있습니다 — 서로를 리다이렉트하거나 링크하지 않으며, 각자 독립적으로 로그인 상태를 확인합니다.

- **`/app/`** — 일반 사용자 화면. 대시보드 히어로(건강 스코어 링 + 체중/혈압/혈당 카드 + 활동량/수면), AI Health Coach 카드, 이상 징후 감지 배너, 기록 입력(+"이전 값 불러오기")/조회/검색/수정/삭제, 목표 진행률·최근 배지·이번주 변화 요약, 통계(측정 추이 차트, 건강 캘린더, 타임라인), 목표(달성 예측 포함), 주간 리포트(+AI 요약), CSV/JSON 내보내기, CSV 가져오기(미리보기 후 저장), 계정 설정(이름 변경/비밀번호 변경/탈퇴), 비밀번호 찾기
- **`/app/admin.html`** — 관리자 대시보드. 사이드바 네비게이션(개요 / 사용자 관리 / 감사 로그), 클릭 가능한 KPI 카드(각 수치의 근거가 되는 사용자 목록으로 드릴다운), 가입 추이 차트(막대 클릭 시 해당 날짜 가입자 필터링), 분류별 분포, 검색(아이디/이름)·정렬·필터(권한/위험도/접속 상태)가 되는 사용자 테이블, 사용자별 기록 조회 드로어, 회원정보 보기(계정 상세), 강제 로그아웃/계정 삭제, 감사 로그. **이 화면 자체에 독립적인 로그인 폼이 있어** 유저 화면을 거치지 않고 바로 접속·로그인합니다.

두 화면은 `theme.css`(라이트/다크 디자인 토큰)를 공유하고, 라이트/시스템/다크 3단 테마 토글을 제공합니다. 아이콘 전용 네비게이션에는 `aria-label`을, 목록의 반복 액션 버튼에는 대상을 식별할 수 있는 구체적인 `aria-label`을 붙여뒀습니다(스크린 리더 접근성 1차 개선).

루트(`/`)로 접속하면 자동으로 `/app/`으로 이동합니다.

### 분류 기준 (학습용으로 단순화된 값이며 실제 의학적 진단이 아닙니다)

- **BMI**: 18.5 미만 저체중 · 18.5~22.9 정상 · 23~24.9 과체중 · 25 이상 비만
- **혈압**: 수축기<120 & 이완기<80 정상 · 120~139/80~89 주의 · 140↑/90↑ 고혈압
- **공복혈당**: 100 미만 정상 · 100~125 공복혈당장애 · 126 이상 당뇨 의심

## 기술 스택

- **FastAPI** — REST API 프레임워크
- **SQLAlchemy + SQLite** — 파일 기반 DB (컨테이너/서버 재시작해도 데이터 유지)
- **Pydantic v2** — 요청/응답 데이터 검증
- **Docker** — 컨테이너 실행
- **HTML/CSS/JS (Vanilla)** — 사용자/관리자 화면, 별도 빌드 불필요

### DB 테이블 구조

- `users` — 계정 (`username`, `name`(실명, nullable — 회원가입에 이름 항목이 추가되기 전 계정은 비어있을 수 있음), `password_hash`/`password_salt`, `role`, `security_question`/`security_answer_hash`/`security_answer_salt`, `failed_login_attempts`, `locked_until`)
- `sessions` — 로그인 세션 토큰 (쿠키에는 토큰만 저장, 실제 정보는 서버 DB에)
- `health_records` — 건강 기록 원본 값 + 서버가 계산한 BMI/분류/경고/활동량/수면 상태
- `goals` — 사용자별 목표 체중/혈압/혈당
- `audit_logs` — 관리자 조치 이력 (대상 계정이 삭제돼도 이력은 남도록 username을 문자열로 저장)
- `badges` — 자동 획득 배지(연속 기록/첫 정상 지표/첫 목표 달성)
- `coaching_cache` — AI Health Coach 메시지 캐시 (사용자당 1건, 하루 1회만 재생성)

### 환경변수

로컬 개발 시 `backend/.env.example`을 `backend/.env`로 복사한 뒤 값을 채우면
`main.py`가 (python-dotenv로) 서버 시작 시 자동으로 읽어들입니다 (`.env`는
`.gitignore`에 포함되어 커밋되지 않음). Docker/서버 배포 시에는 `.env` 대신
`docker run -e OPENAI_API_KEY=...` 등으로 직접 주입하세요.

```bash
cd backend
cp .env.example .env
# .env 파일을 열어 OPENAI_API_KEY 등 실제 값 입력
```

| 변수 | 기본값 | 설명 |
|---|---|---|
| `ALLOWED_ORIGINS` | (빈 값 = 전부 차단) | CORS 허용 origin, 콤마로 구분. 지금처럼 프론트를 같은 origin에서 서빙하면 필요 없음 |
| `OPENAI_API_KEY` | (없음) | 설정하면 AI Health Coach가 규칙 기반 대신 실제 OpenAI API를 사용 (키가 없거나 호출 실패/타임아웃 시 자동으로 규칙 기반 폴백) |
| `OPENAI_COACHING_MODEL` | `gpt-4o-mini` | `OPENAI_API_KEY` 설정 시 사용할 모델 |
| `COOKIE_SECURE` | `false` | HTTPS 배포 시 `true`로 설정 권장 |

### DB 스키마 변경 (Alembic)

**(2026-07-22부터) 스키마가 바뀔 때 더 이상 `data/health_log.db`를 지우고 재생성하지 않습니다.**
`backend/`에 Alembic 마이그레이션 환경이 구성되어 있고, `models.py`를 고치면
아래 순서로 반영합니다.

```bash
cd backend
# 1) models.py를 원하는 대로 수정
# 2) 변경사항을 자동으로 감지해 마이그레이션 파일 생성
python -m alembic revision --autogenerate -m "간단한 변경 설명"
# 3) alembic/versions/에 생성된 파일을 열어 내용이 의도한 대로인지 확인(자동 생성은
#    항상 검토 필요 — 컬럼 삭제/이름 변경 등은 정확히 잡아내지 못할 수 있음)
# 4) 실제 DB에 적용
python -m alembic upgrade head
```

새로 로컬 환경을 셋업할 때(DB 파일이 아직 없을 때)도 서버를 처음 띄우기 전에
`alembic upgrade head`를 한 번 실행해 테이블을 만들어야 합니다 (`main.py`는 더
이상 `Base.metadata.create_all()`을 호출하지 않습니다).

## 실행 방법

### 로컬 실행

```bash
cd backend
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m alembic upgrade head   # DB 테이블 생성/최신화 (최초 1회 + 스키마 변경 시)
uvicorn main:app --reload
```

브라우저에서 http://127.0.0.1:8000 (자동으로 `/app/`으로 이동) · http://127.0.0.1:8000/app/admin.html (관리자) · http://127.0.0.1:8000/docs (API 테스트) 접속.

첫 관리자 계정 만들기:

```bash
# 1) /app/ 에서 회원가입으로 계정을 하나 만든 뒤
# 2) backend/ 안에서:
python promote_admin.py <username>
```

데모 시연용 더미데이터가 필요하면 `backend/` 안에서 `python seed_demo_data.py` 실행 (일반 사용자 12명 + 2주치 건강기록/목표 생성, 기존 계정은 건드리지 않음).

DB 백업이 필요하면 `backend/` 안에서 `python backup_db.py` 실행 — `data/health_log.db`를 sqlite3의 온라인 백업 API로 `backups/` 디렉토리에 타임스탬프 파일(`health_log_YYYYMMDD_HHMMSS.db`)로 복사하고, 기본적으로 최근 14개만 남기고 오래된 백업은 자동 삭제한다 (`--keep 30`처럼 보관 개수 조정 가능, `--keep 0`은 무제한 보관). 지금은 수동 실행만 지원 - 주기적 자동 실행(cron/작업 스케줄러 등록)은 서버 배포 시 별도로 설정한다.

### 테스트 실행

```bash
cd backend
pip install -r requirements-dev.txt   # pytest, httpx 추가 설치
pytest
```

테스트마다 완전히 독립된 임시 SQLite DB를 사용하므로 `data/health_log.db`(실제
개발/데모 데이터)에는 영향을 주지 않습니다. 핵심 시나리오: 로그인 5회 실패 시
계정 잠금, IDOR(다른 사용자 기록 접근 차단), 회원 탈퇴 시 cascade 삭제, 관리자
권한 없이 `/admin/*` 접근 시 403, 건강기록 CRUD.

### Docker 실행 (리포 루트에서)

```bash
docker build -t health-log-api .
docker run -d -p 8000:8000 -v $(pwd)/data:/app/data --name health-log-api health-log-api
```

http://localhost:8000 (웹 화면) 또는 http://localhost:8000/docs (API 문서) 접속.

> `-v $(pwd)/data:/app/data` 로 볼륨을 연결하면 컨테이너를 재생성해도 sqlite 데이터가 유지됩니다. Windows Git Bash에서는 백슬래시 경로(`F:\...`)가 아니라 슬래시 경로(`F:/...`)를 써야 합니다.
>
> 컨테이너 시작 시 `alembic upgrade head`가 먼저 자동 실행된 뒤 `uvicorn`이 뜹니다(`Dockerfile`의 `CMD`) — `main.py`는 더 이상 스키마를 자동 생성하지 않으므로 별도로 마이그레이션을 실행할 필요가 없습니다. `OPENAI_API_KEY` 등 환경변수가 필요하면 `docker run -e OPENAI_API_KEY=... ...`로 주입하세요.

## 배포 접속 URL

(배포 완료 후 추가 예정)

## 참고

수업 자료와 실습 워크북을 참고해 구현했습니다.
