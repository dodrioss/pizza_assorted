"""
detectors — Модуль обнаружения персональных данных (ПДн) по 152-ФЗ.

Структура модуля:
    - :mod:`~detectors.regex_patterns` — скомпилированные regex-паттерны
      и реестр ``PII_PATTERNS`` со всеми категориями ПДн.
    - :mod:`~detectors.validators` — математические валидаторы
      (алгоритм Луна, контрольные суммы СНИЛС/ИНН/паспорт/MRZ).
    - :mod:`~detectors.pii_detector` — основной класс :class:`PIIDetector`
      с методами :meth:`~PIIDetector.detect_all_pii` и
      :meth:`~PIIDetector.detect_from_chunks`.

Быстрый старт::

    from detectors import PIIDetector

    detector = PIIDetector()
    result = detector.detect_all_pii(text=some_text, file_path="file.pdf")

    print(result.has_pii)
    print(result.categories_found)
    for finding in result.findings:
        print(finding.pattern_name, finding.masked_value, finding.count)
"""

from detectors.pii_detector import PIIDetector, PIIDetectionResult, PIIFinding
from detectors.validators import (
    validate_card_luhn,
    validate_snils,
    validate_inn,
    validate_passport_rf,
    validate_mrz_check_digit,
    validate,
)
from detectors.regex_patterns import PII_PATTERNS, PatternMeta

__all__ = [
    "PIIDetector",
    "PIIDetectionResult",
    "PIIFinding",
    "PII_PATTERNS",
    "PatternMeta",
    "validate_card_luhn",
    "validate_snils",
    "validate_inn",
    "validate_passport_rf",
    "validate_mrz_check_digit",
    "validate",
]