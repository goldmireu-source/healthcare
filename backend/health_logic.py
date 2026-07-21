"""건강 지표 계산/분류 로직.

이 모듈의 기준값은 학습용으로 단순화된 값이며, 실제 의학적 진단 기준이 아닙니다.
"""

from typing import List, Dict


def calc_bmi(weight_kg: float, height_cm: float) -> float:
    height_m = height_cm / 100
    if height_m <= 0:
        return 0.0
    return round(weight_kg / (height_m ** 2), 2)


def classify_bmi(bmi: float) -> str:
    if bmi < 18.5:
        return "저체중"
    elif bmi < 23:
        return "정상"
    elif bmi < 25:
        return "과체중"
    return "비만"


def classify_bp(systolic: int, diastolic: int) -> str:
    if systolic >= 140 or diastolic >= 90:
        return "고혈압"
    elif systolic >= 120 or diastolic >= 80:
        return "주의"
    return "정상"


def classify_sugar(blood_sugar: int) -> str:
    if blood_sugar >= 126:
        return "당뇨 의심"
    elif blood_sugar >= 100:
        return "공복혈당장애"
    return "정상"


def build_warnings(bmi_category: str, bp_category: str, sugar_category: str) -> List[str]:
    warnings = []
    if bmi_category == "비만":
        warnings.append("BMI가 비만 범위입니다. 체중 관리가 필요합니다.")
    if bp_category == "고혈압":
        warnings.append("혈압이 고혈압 범위입니다. 전문의 상담을 권장합니다.")
    if sugar_category == "당뇨 의심":
        warnings.append("혈당 수치가 당뇨 의심 범위입니다. 검사를 권장합니다.")
    return warnings


def classify_activity(steps: int) -> str:
    """걸음 수 등급 (고도화 기능)."""
    if steps >= 10000:
        return "우수"
    elif steps >= 5000:
        return "적정"
    return "부족"


def classify_sleep(sleep_hours: float) -> str:
    """수면 분석 - 권장 수면시간 7~9시간 기준 (고도화 기능)."""
    if sleep_hours <= 0:
        return "미기록"
    elif sleep_hours < 6:
        return "부족"
    elif sleep_hours <= 9:
        return "적정"
    return "과다"


def evaluate_record(
    weight: float,
    height: float,
    systolic: int,
    diastolic: int,
    blood_sugar: int,
    steps: int,
    sleep_hours: float,
) -> Dict:
    bmi = calc_bmi(weight, height)
    bmi_category = classify_bmi(bmi)
    bp_category = classify_bp(systolic, diastolic)
    sugar_category = classify_sugar(blood_sugar)
    warnings = build_warnings(bmi_category, bp_category, sugar_category)
    return {
        "bmi": bmi,
        "bmi_category": bmi_category,
        "bp_category": bp_category,
        "sugar_category": sugar_category,
        "warnings": warnings,
        "activity_level": classify_activity(steps),
        "sleep_status": classify_sleep(sleep_hours),
    }
