"""
Основной детектор персональных данных (ПДн).

Является центральным компонентом Этапа 3.  Принимает извлечённый текст
(или итерируемый поток чанков) и возвращает структурированный результат
обнаружения ПДн с привязкой к исходному файлу.

Взаимодействие с другими модулями::

    scanner.FileScanner
        ↓  file_path
    extractors.get_extractor(file_path).extract()
        ↓  ExtractionResult.text / .chunks
    detectors.PIIDetector.detect_all_pii(text, file_path)
        ↓  PIIDetectionResult
    classifiers.UZClassifier.classify(pii_result)
        ↓  УЗ-1…УЗ-4
    report.generators.*

Архитектурные решения:
    - ``detect_all_pii`` принимает **текст целиком** — для небольших файлов
      это удобно и быстро.
    - ``detect_from_chunks`` принимает **генератор чанков** — для больших
      файлов (CSV, большие PDF) позволяет не держать всё в памяти.
    - Результаты дедуплицируются: одно и то же значение, найденное
      несколько раз, считается одним экземпляром (но счётчик растёт).
    - Валидация вызывается только для паттернов из ``VALIDATION_REQUIRED``.

Example::

    from detectors.pii_detector import PIIDetector

    detector = PIIDetector()
    result = detector.detect_all_pii(text="Иванов Иван +79161234567", file_path="doc.pdf")

    print(result.uz_level)              # "УЗ-4" или "УЗ-3" и т.п.
    for finding in result.findings:
        print(finding.pattern_name, finding.value, finding.count)
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from detectors.regex_patterns import (
    PII_PATTERNS,
    PatternMeta,
    VALIDATION_REQUIRED,
    UZ1_PATTERN_NAMES,
)
from detectors.validators import validate

logger = logging.getLogger(__name__)


@dataclass
class PIIFinding:
    """Одна запись об обнаруженном персональном данном.

    Attributes:
        pattern_name: Имя паттерна из ``regex_patterns.PII_PATTERNS``
            (например ``"snils"``, ``"phone"``).
        category: Категория ПДн (``"government_id"``, ``"contact"`` и т.д.).
        description: Человекочитаемое описание типа ПДн.
        value: Найденное значение (маскированное если ``mask=True``).
        count: Сколько раз значение встретилось в тексте.
        validated: ``True`` если прошло математическую валидацию,
            ``None`` если валидация не применялась.
        is_special_category: Относится ли к специальным категориям (ст. 10 152-ФЗ).
        is_biometric: Является ли биометрическими данными.
        context_snippet: Фрагмент текста вокруг найденного значения
            (для отладки; не сохраняется в итоговый отчёт).
    """

    pattern_name: str
    category: str
    description: str
    value: str
    count: int = 1
    validated: bool | None = None
    is_special_category: bool = False
    is_biometric: bool = False
    context_snippet: str = ""

    @property
    def masked_value(self) -> str:
        """Маскированное значение: первые 2 и последние 2 символа видны.

        Example::

            PIIFinding(..., value="79161234567").masked_value
            # "79*********67"
        """
        v = self.value
        if len(v) <= 4:
            return "*" * len(v)
        return v[:2] + "*" * (len(v) - 4) + v[-2:]


@dataclass
class PIIDetectionResult:
    """Итоговый результат обнаружения ПДн в одном файле.

    Attributes:
        file_path: Абсолютный путь к файлу.
        findings: Список уникальных :class:`PIIFinding`.
        categories_found: Множество обнаруженных категорий ПДн
            (``"contact"``, ``"government_id"`` и т.п.).
        has_special_categories: Есть ли данные специальных категорий.
        has_biometrics: Есть ли биометрические данные.
        total_matches: Суммарное число всех совпадений (с повторами).
        detection_time_sec: Время работы детектора.
        error: Сообщение об ошибке (``None`` при успехе).
    """

    file_path: str
    findings: list[PIIFinding] = field(default_factory=list)
    categories_found: set[str] = field(default_factory=set)
    has_special_categories: bool = False
    has_biometrics: bool = False
    total_matches: int = 0
    detection_time_sec: float = 0.0
    error: str | None = None

    @property
    def has_pii(self) -> bool:
        """``True`` если найдены хоть какие-то ПДн."""
        return bool(self.findings)

    @property
    def pattern_names_found(self) -> set[str]:
        """Множество имён паттернов, давших находки."""
        return {f.pattern_name for f in self.findings}

    def findings_by_category(self) -> dict[str, list[PIIFinding]]:
        """Группирует находки по категории.

        Returns:
            Словарь ``{category: [PIIFinding, ...]}``.
        """
        result: dict[str, list[PIIFinding]] = defaultdict(list)
        for f in self.findings:
            result[f.category].append(f)
        return dict(result)

    def to_dict(self, mask_values: bool = True) -> dict:
        """Сериализует результат в словарь (для JSON/CSV отчётов).

        Args:
            mask_values: Маскировать ли найденные значения.

        Returns:
            Словарь с ключами, совместимыми с форматом отчёта.
        """
        return {
            "file_path": self.file_path,
            "has_pii": self.has_pii,
            "categories_found": sorted(self.categories_found),
            "has_special_categories": self.has_special_categories,
            "has_biometrics": self.has_biometrics,
            "total_matches": self.total_matches,
            "detection_time_sec": round(self.detection_time_sec, 4),
            "error": self.error,
            "findings": [
                {
                    "pattern_name": f.pattern_name,
                    "category": f.category,
                    "description": f.description,
                    "value": f.masked_value if mask_values else f.value,
                    "count": f.count,
                    "validated": f.validated,
                    "is_special_category": f.is_special_category,
                    "is_biometric": f.is_biometric,
                }
                for f in self.findings
            ],
        }


class PIIDetector:
    """Детектор персональных данных на основе регулярных выражений.

    Применяет все паттерны из :mod:`detectors.regex_patterns` к переданному
    тексту.  Для паттернов, требующих математической валидации
    (номера карт, СНИЛС, ИНН), дополнительно вызывает соответствующий
    валидатор из :mod:`detectors.validators`.

    Args:
        context_window: Количество символов вокруг совпадения, включаемых
            в ``context_snippet`` для отладки.  По умолчанию 60.
        deduplicate: Если ``True`` (по умолчанию) — одинаковые значения
            в одном файле считаются одним экземпляром, ``count`` растёт.
        min_text_length: Если текст короче этого значения — не запускать
            детектор (пустые / мусорные файлы).  По умолчанию 10.

    Example::

        detector = PIIDetector()

        # Из строки
        result = detector.detect_all_pii("Иванов Иван +79161234567", "doc.txt")

        # Из генератора чанков (большой CSV)
        extractor = CsvParquetExtractor("big.csv")
        result = detector.detect_from_chunks(extractor.extract_chunks(), "big.csv")
    """

    def __init__(
        self,
        context_window: int = 60,
        deduplicate: bool = True,
        min_text_length: int = 10,
    ) -> None:
        self._context_window = context_window
        self._deduplicate = deduplicate
        self._min_text_length = min_text_length
        self._logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )

    def detect_all_pii(self, text: str, file_path: str = "") -> PIIDetectionResult:
        """Обнаруживает все ПДн в переданном тексте.

        Главный метод модуля.  Проходит по всем паттернам,
        собирает находки, запускает валидацию, дедуплицирует.

        Args:
            text: Извлечённый текст файла (один блок).
            file_path: Путь к исходному файлу (для метаданных результата).

        Returns:
            :class:`PIIDetectionResult` с полным списком находок.
        """
        start = time.monotonic()
        self._logger.debug("Детектор запущен для '%s'", file_path)

        if len(text) < self._min_text_length:
            self._logger.debug(
                "Текст слишком короткий (%d симв.) — пропускаем '%s'",
                len(text),
                file_path,
            )
            return PIIDetectionResult(
                file_path=file_path,
                detection_time_sec=round(time.monotonic() - start, 4),
            )

        # Счётчик: (pattern_name, normalized_value) → PIIFinding
        accumulator: dict[tuple[str, str], PIIFinding] = {}

        for name, meta in PII_PATTERNS.items():
            self._apply_pattern(name, meta, text, accumulator)

        findings = list(accumulator.values())
        result = self._build_result(file_path, findings, time.monotonic() - start)
        self._logger.debug(
            "Детектор завершён для '%s': %d уникальных находок, %d совпадений",
            file_path,
            len(findings),
            result.total_matches,
        )
        return result

    def detect_from_chunks(
        self,
        chunks: Iterable[str],
        file_path: str = "",
    ) -> PIIDetectionResult:
        """Обнаруживает ПДн в потоке текстовых чанков.

        Удобно для больших файлов (CSV, большие PDF), когда текст
        не помещается в память целиком.  Результаты по всем чанкам
        объединяются в один :class:`PIIDetectionResult`.

        Args:
            chunks: Итерируемый источник строк-чанков.
            file_path: Путь к исходному файлу.

        Returns:
            :class:`PIIDetectionResult` — агрегированный по всем чанкам.

        Example::

            extractor = PDFExtractor("big.pdf")
            result = detector.detect_from_chunks(
                extractor.extract_chunks(), "big.pdf"
            )
        """
        start = time.monotonic()
        accumulator: dict[tuple[str, str], PIIFinding] = {}

        for chunk in chunks:
            if not chunk or len(chunk) < self._min_text_length:
                continue
            for name, meta in PII_PATTERNS.items():
                self._apply_pattern(name, meta, chunk, accumulator)

        findings = list(accumulator.values())
        result = self._build_result(file_path, findings, time.monotonic() - start)
        return result


    def _apply_pattern(
        self,
        name: str,
        meta: PatternMeta,
        text: str,
        accumulator: dict[tuple[str, str], PIIFinding],
    ) -> None:
        """Применяет один паттерн к тексту и обновляет аккумулятор.

        Args:
            name: Имя паттерна.
            meta: Метаданные паттерна.
            text: Текст для поиска.
            accumulator: Словарь ``{(name, value): PIIFinding}`` —
                изменяется in-place.
        """
        try:
            matches = list(meta.pattern.finditer(text))
        except re.error as exc:
            self._logger.warning("Ошибка regex '%s': %s", name, exc)
            return

        for match in matches:
            raw_value = match.group(0).strip()
            if not raw_value:
                continue

            # Математическая валидация (только если требуется)
            validated: bool | None = None
            if name in VALIDATION_REQUIRED:
                validated = validate(name, raw_value)
                if not validated:
                    continue   # отбрасываем невалидные совпадения

            # Нормализованный ключ для дедупликации
            norm_value = self._normalize(raw_value)
            key = (name, norm_value)

            if key in accumulator:
                accumulator[key].count += 1
            else:
                context = self._get_context(text, match.start(), match.end())
                accumulator[key] = PIIFinding(
                    pattern_name=name,
                    category=meta.category,
                    description=meta.description,
                    value=norm_value,
                    count=1,
                    validated=validated,
                    is_special_category=meta.is_special_category,
                    is_biometric=meta.is_biometric,
                    context_snippet=context,
                )

    def _get_context(self, text: str, start: int, end: int) -> str:
        """Извлекает фрагмент текста вокруг совпадения.

        Args:
            text: Полный текст.
            start: Начало совпадения.
            end: Конец совпадения.

        Returns:
            Строка с «…» по краям если текст обрезан.
        """
        w = self._context_window
        left = max(0, start - w)
        right = min(len(text), end + w)
        snippet = text[left:right].replace("\n", " ")
        prefix = "…" if left > 0 else ""
        suffix = "…" if right < len(text) else ""
        return prefix + snippet + suffix

    @staticmethod
    def _normalize(value: str) -> str:
        """Нормализует найденное значение для дедупликации.

        Убирает лишние пробелы, дефисы и приводит к нижнему регистру.

        Args:
            value: Исходная строка совпадения.

        Returns:
            Нормализованная строка.
        """
        return re.sub(r"[\s\-]+", "", value).lower()

    @staticmethod
    def _build_result(
        file_path: str,
        findings: list[PIIFinding],
        elapsed: float,
    ) -> PIIDetectionResult:
        """Собирает итоговый :class:`PIIDetectionResult` из списка находок.

        Args:
            file_path: Путь к файлу.
            findings: Список уникальных находок.
            elapsed: Время детектора в секундах.

        Returns:
            Заполненный :class:`PIIDetectionResult`.
        """
        categories: set[str] = set()
        has_special = False
        has_bio = False
        total = 0

        for f in findings:
            categories.add(f.category)
            if f.is_special_category:
                has_special = True
            if f.is_biometric:
                has_bio = True
            total += f.count

        return PIIDetectionResult(
            file_path=file_path,
            findings=findings,
            categories_found=categories,
            has_special_categories=has_special,
            has_biometrics=has_bio,
            total_matches=total,
            detection_time_sec=round(elapsed, 4),
        )