"""외부 연동 확장 인터페이스 (Integrations).

이 프로젝트가 지금 당장 실제 외부 API에 연결하지는 않지만, 나중에 아래
항목들을 쉽게 붙일 수 있도록 인터페이스만 미리 설계해둔다. 지금은 전부
Mock(또는 최소한의 실제 파싱만 가능한) 구현만 제공한다.

  1. LLM 기반 AI 코칭 (OpenAI / Claude / Gemini)
     -> health_coach.py의 CoachingProvider(ABC)가 이 역할을 한다.
        OpenAI는 OpenAICoachingProvider로 실제 연동 완료(OPENAI_API_KEY 환경변수
        필요, 없거나 실패 시 FallbackCoachingProvider가 규칙 기반으로 자동 대체).
        Claude/Gemini는 아직 Mock이며, 동일한 CoachingProvider를 구현하면
        똑같은 방식으로 추가할 수 있다 (API 호출 부분만 다름).
  2. 웨어러블 연동 (Apple Health / Samsung Health / Google Fit)
     -> WearableDataSource(ABC) + MockWearableDataSource
  3. 외부 데이터 가져오기 (CSV Import / 건강검진 PDF)
     -> HealthDataImporter(ABC) + CsvHealthDataImporter(파싱 + DB 저장까지 실제 동작,
        main.py의 /integrations/import/csv/preview, /commit 참고) +
        MockHealthCheckupPdfImporter(목)

실제 연동 시에는 각 ABC를 구현하는 새 클래스만 추가하면 되고, 호출부
(main.py)는 provider/importer 객체만 바꿔 끼우면 나머지 로직은 그대로
재사용된다 — 이번 프로젝트 전반에서 쓴 "Provider 인터페이스" 패턴과 동일하다.
"""

import csv
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date as date_cls, timedelta
from enum import Enum
from typing import List, Optional

# ================================================================
# 1. 웨어러블 연동 (Wearable Integration)
# ================================================================

class WearableProvider(str, Enum):
    APPLE_HEALTH = "apple_health"
    SAMSUNG_HEALTH = "samsung_health"
    GOOGLE_FIT = "google_fit"


@dataclass(frozen=True)
class WearableDailyActivity:
    """웨어러블에서 가져온 하루치 활동 데이터 (걸음수/수면시간)."""

    date: str
    steps: Optional[int]
    sleep_hours: Optional[float]


class WearableDataSource(ABC):
    """웨어러블 연동의 공통 인터페이스.

    실제 Apple Health/Samsung Health/Google Fit 연동 시에는 이 클래스를 상속해
    fetch_daily_activity()만 각 사의 SDK/REST API 호출로 구현하면 된다.
    호출부(main.py)는 provider 객체만 바꿔 끼우면 나머지는 그대로 재사용된다.
    """

    @abstractmethod
    def fetch_daily_activity(self, start_date: str, end_date: str) -> List[WearableDailyActivity]:
        raise NotImplementedError


class MockWearableDataSource(WearableDataSource):
    """실제 API 연동 전, UI/흐름을 검증하기 위한 목(mock) 데이터 소스."""

    def __init__(self, provider: WearableProvider = WearableProvider.APPLE_HEALTH):
        self.provider = provider

    def fetch_daily_activity(self, start_date: str, end_date: str) -> List[WearableDailyActivity]:
        start = date_cls.fromisoformat(start_date)
        end = date_cls.fromisoformat(end_date)
        # provider별로 그럴듯하게 다른 패턴의 값이 나오도록 provider 이름으로 시드를 만듦
        seed = sum(ord(c) for c in self.provider.value)

        results: List[WearableDailyActivity] = []
        current = start
        while current <= end:
            day_index = (current - start).days
            results.append(WearableDailyActivity(
                date=current.isoformat(),
                steps=6000 + ((seed + day_index * 137) % 5000),
                sleep_hours=round(6.0 + ((seed + day_index * 53) % 30) / 10, 1),
            ))
            current += timedelta(days=1)
        return results


# ================================================================
# 2. 외부 데이터 가져오기 (Health Data Import)
# ================================================================

@dataclass(frozen=True)
class ImportedRecord:
    """외부 소스(CSV/PDF)에서 가져온, 아직 검증 전인 원시 기록 한 건.

    schemas.RecordIn과 필드가 비슷하지만, 외부 데이터는 값이 없거나(Optional)
    형식이 깨져 있을 수 있어 별도 타입으로 분리했다 (검증은 호출부 책임).
    """

    date: str
    weight: Optional[float] = None
    height: Optional[float] = None
    systolic: Optional[int] = None
    diastolic: Optional[int] = None
    blood_sugar: Optional[int] = None
    steps: Optional[int] = None
    sleep_hours: Optional[float] = None


class HealthDataImporter(ABC):
    """외부 건강 데이터 가져오기의 공통 인터페이스."""

    @abstractmethod
    def parse(self, raw_content: str) -> List[ImportedRecord]:
        raise NotImplementedError


def _to_float(value) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _to_int(value) -> Optional[int]:
    try:
        return int(float(value)) if value not in (None, "") else None
    except ValueError:
        return None


class CsvHealthDataImporter(HealthDataImporter):
    """실제로 동작하는 CSV 가져오기 구현체.

    Export 기능(고도화 10번)이 만드는 CSV와 같은 헤더(date, weight, height,
    systolic, diastolic, blood_sugar, steps, sleep_hours, ...)를 그대로 읽어들인다.
    파싱 결과는 아직 검증 전 원시값이라, 실제 DB 저장은 호출부(main.py의
    /integrations/import/csv/commit)가 schemas.RecordIn으로 재검증한 뒤 수행한다.
    """

    def parse(self, raw_content: str) -> List[ImportedRecord]:
        reader = csv.DictReader(io.StringIO(raw_content))
        records: List[ImportedRecord] = []
        for row in reader:
            records.append(ImportedRecord(
                date=(row.get("date") or "").strip(),
                weight=_to_float(row.get("weight")),
                height=_to_float(row.get("height")),
                systolic=_to_int(row.get("systolic")),
                diastolic=_to_int(row.get("diastolic")),
                blood_sugar=_to_int(row.get("blood_sugar")),
                steps=_to_int(row.get("steps")),
                sleep_hours=_to_float(row.get("sleep_hours")),
            ))
        return records


class MockHealthCheckupPdfImporter(HealthDataImporter):
    """건강검진 PDF 파싱은 실제 OCR/파서가 아직 없어 인터페이스만 목으로 보여준다.

    실제 연동 시에는 parse()를 PDF 텍스트 추출(pdfplumber 등) + 정규식/OCR
    파싱으로 교체하면 된다. raw_content는 지금은 무시되고 항상 같은 예시
    기록 하나를 반환한다.
    """

    def parse(self, raw_content: str) -> List[ImportedRecord]:
        return [ImportedRecord(date="2026-01-01", weight=65.0, systolic=118, diastolic=76, blood_sugar=92)]
