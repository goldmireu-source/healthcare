"""Export(CSV/JSON) 라우터 — PDF는 요구사항에서 제외됨. 사용자 본인의 건강기록만 내보낸다."""

import csv
import io
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
import models
import auth
import health_service

router = APIRouter(tags=["Export"])

_EXPORT_CSV_HEADER = [
    "date", "weight", "height", "systolic", "diastolic", "blood_sugar",
    "steps", "sleep_hours", "bmi", "bmi_category", "bp_category",
    "sugar_category", "activity_level", "sleep_status", "memo",
]

# CSV 수식 인젝션(Formula Injection) 방어 기준값 — 이 문자로 시작하는 셀은
# 엑셀/구글시트가 수식으로 해석해 실행할 수 있음 (예: memo에 "=1+1" 저장 후
# export한 파일을 열면 수식으로 계산됨). 표준 방어는 앞에 작은따옴표를 붙여
# 스프레드시트가 무조건 텍스트로 취급하게 만드는 것.
_CSV_DANGEROUS_PREFIXES = ("=", "+", "-", "@")


def _sanitize_csv_cell(value) -> str:
    """셀 값을 문자열로 변환하면서 수식 인젝션 위험이 있으면 무력화한다.

    memo 같은 자유 입력 필드뿐 아니라, 나중에 컬럼이 늘어나도 안전하도록
    문자열로 나가는 모든 셀에 동일하게 적용한다 (지금 값 중에는 음수가 없어
    "-"로 시작하는 정상 데이터는 없지만, 혹시 모를 경우에도 스프레드시트에서
    텍스트로만 보일 뿐 데이터 유실은 없음).
    """
    text = "" if value is None else str(value)
    if text.startswith(_CSV_DANGEROUS_PREFIXES):
        return "'" + text
    return text


def _export_filename(username: str, extension: str) -> str:
    # username은 회원가입 시 ^[a-zA-Z0-9_]+$ 로만 검증되어 헤더 인젝션 위험이 없음
    return f"health_records_{username}.{extension}"


@router.get("/export/csv")
def export_records_csv(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .order_by(models.HealthRecord.date.asc())
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_EXPORT_CSV_HEADER)
    for r in records:
        row = [
            r.date, r.weight, r.height, r.systolic, r.diastolic, r.blood_sugar,
            r.steps, r.sleep_hours, r.bmi, r.bmi_category, r.bp_category,
            r.sugar_category, r.activity_level, r.sleep_status, r.memo,
        ]
        writer.writerow([_sanitize_csv_cell(v) for v in row])

    filename = _export_filename(current_user.username, "csv")
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/json")
def export_records_json(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    records = (
        db.query(models.HealthRecord)
        .filter(models.HealthRecord.user_id == current_user.id)
        .order_by(models.HealthRecord.date.asc())
        .all()
    )
    # health_service.record_to_out()은 이미 /records 엔드포인트가 쓰는 것과 동일한 직렬화 로직 (중복 방지)
    payload = [health_service.record_to_out(r).model_dump(mode="json") for r in records]

    filename = _export_filename(current_user.username, "json")
    return StreamingResponse(
        iter([json.dumps(payload, ensure_ascii=False, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
