"""
Тесты для модуля detectors (Этап 3 — обнаружение ПДн)
"""

import pytest
import re
from detectors import (
    PIIDetector,
    PIIDetectionResult,
    PIIFinding,
    PII_PATTERNS,
    validate_card_luhn,
    validate_snils,
    validate_inn,
    validate_passport_rf,
    validate_mrz_check_digit,
    validate,
)
from detectors.validators import _digits
from detectors.regex_patterns import VALIDATION_REQUIRED, UZ1_PATTERN_NAMES


# ====================== Вспомогательные утилиты ======================
def test_digits_cleaner():
    assert _digits("123-456 789 01") == "12345678901"
    assert _digits("4111 1111 1111 1111") == "4111111111111111"


# ====================== Валидаторы ======================
def test_validate_card_luhn():
    assert validate_card_luhn("4111 1111 1111 1111") is True
    assert validate_card_luhn("5555 5555 5555 4444") is True
    assert validate_card_luhn("1234 5678 9012 3456") is False


def test_validate_snils():
    assert validate_snils("112-233-445 95") is True
    assert validate_snils("123-456-789 01") is False
    assert validate_snils("000-000-000 00") is False


def test_validate_inn():
    assert validate_inn("7707083893") is True
    assert validate_inn("500100732259") is True
    assert validate_inn("123456789012") is False


def test_validate_passport_rf():
    assert validate_passport_rf("4510", "123456") is True
    assert validate_passport_rf("4510", "000000") is False


def test_validate_mrz_check_digit():
    assert validate_mrz_check_digit("520727", "3") is True
    # Правильный пример (контрольная цифра = 6)
    assert validate_mrz_check_digit("D231458907<<<<<<<<<<<<<<<", "6") is True
    assert validate_mrz_check_digit("ABC123", "9") is False


def test_dispatch_validate():
    assert validate("card_number", "4111 1111 1111 1111") is True
    assert validate("snils", "112-233-445 95") is True
    assert validate("inn", "7707083893") is True
    assert validate("passport_rf", "4510123456") is True
    assert validate("passport_rf_context", "Паспорт 4510123456") is True
    assert validate("email", "test@example.com") is True


# ====================== Структура паттернов ======================
def test_pii_patterns_structure():
    assert len(PII_PATTERNS) >= 25
    for name, meta in PII_PATTERNS.items():
        assert isinstance(meta.pattern, re.Pattern)


def test_validation_required_set():
    expected = {"card_number", "snils", "inn", "inn_context", "passport_rf", "passport_rf_context"}
    assert VALIDATION_REQUIRED == expected


def test_uz1_patterns():
    assert len(UZ1_PATTERN_NAMES) > 0


# ====================== Проверка паттернов ======================
@pytest.mark.parametrize("pattern_name, sample_text, expected_count", [
    ("phone", "Мой телефон +7 (916) 123-45-67", 1),
    ("email", "Связаться по test.user@example.com", 1),
    ("full_name", "Иванов Иван Иванович проживает", 1),
    ("snils", "СНИЛС 112-233-445 95", 1),
    ("card_number", "Карта 4111 1111 1111 1111", 1),
    ("passport_rf", "4510 123456", 1),
    ("passport_rf_context", "Паспорт 45 10 123456", 1),
    ("inn", "ИНН 7707083893", 1),
    ("inn_context", "ИНН: 500100732259", 1),
])
def test_basic_pattern_matching(pattern_name, sample_text, expected_count):
    meta = PII_PATTERNS[pattern_name]
    matches = list(meta.pattern.finditer(sample_text))
    assert len(matches) == expected_count


# ====================== Основной детектор ======================
@pytest.fixture
def detector():
    return PIIDetector(context_window=40, deduplicate=True)


def test_detector_basic_detection(detector):
    text = """
    Иванов Иван Иванович
    Телефон: +7 (916) 123-45-67
    Email: test@example.com
    СНИЛС 112-233-445 95
    ИНН 7707083893
    Паспорт 4510 123456
    Карта: 4111 1111 1111 1111
    """

    result: PIIDetectionResult = detector.detect_all_pii(text, "test_doc.pdf")

    assert result.has_pii is True
    assert len(result.findings) >= 6
    assert "full_name" in result.pattern_names_found
    assert "contact" in result.categories_found
    assert "government_id" in result.categories_found
    assert "payment" in result.categories_found


def test_detector_deduplication(detector):
    text = "СНИЛС 112-233-445 95 и ещё раз СНИЛС 112-233-445 95"
    result = detector.detect_all_pii(text, "dup.pdf")
    snils_findings = [f for f in result.findings if f.pattern_name.startswith("snils")]
    assert len(snils_findings) == 1
    assert snils_findings[0].count == 2


def test_detector_masked_value():
    finding = PIIFinding(
        pattern_name="phone",
        category="contact",
        description="Телефон",
        value="79161234567",
        count=1
    )
    assert finding.masked_value == "79*******67"


def test_to_dict_serialization(detector):
    text = "Иванов Иван +79161234567 СНИЛС 112-233-445 95"
    result = detector.detect_all_pii(text, "test.pdf")
    data = result.to_dict(mask_values=True)
    assert data["has_pii"] is True
    assert len(data["findings"]) > 0


def test_detect_from_chunks(detector):
    chunks = [
        "Иванов Иван Иванович ",
        "+7 (916) 123-45-67 СНИЛС 112-233-445 95",
        "ИНН 7707083893 Паспорт 4510123456"
    ]
    result = detector.detect_from_chunks(chunks, "chunked.pdf")
    assert result.has_pii is True
    assert len(result.findings) >= 4


def test_detector_handles_bad_regex_gracefully(detector):
    result = detector.detect_all_pii("normal text", "ok.txt")
    assert result.error is None