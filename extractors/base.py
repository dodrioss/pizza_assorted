"""
Абстрактный базовый класс для всех экстракторов текста.

Определяет общий контракт (интерфейс), которому должны следовать
все конкретные реализации экстракторов.  Содержит также общие
вспомогательные методы и датаклассы для передачи результатов.
"""

from __future__ import annotations

import os
import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Исключение, возникающее при ошибке извлечения текста из файла.

    Attributes:
        file_path: Путь к файлу, при обработке которого возникла ошибка.
        reason: Человекочитаемое описание причины ошибки.
    """

    def __init__(self, file_path: str, reason: str) -> None:
        self.file_path = file_path
        self.reason = reason
        super().__init__(f"Ошибка извлечения из '{file_path}': {reason}")


@dataclass
class ExtractionResult:
    """Результат извлечения текста из одного файла.

    Attributes:
        file_path: Абсолютный путь к исходному файлу.
        text: Извлечённый текст (один или несколько чанков объединены).
        chunks: Список текстовых фрагментов (чанков), если файл был
            разбит на части при извлечении.  Для небольших файлов
            содержит один элемент.
        metadata: Словарь с метаданными файла (формат-зависимые поля,
            например количество страниц для PDF или число строк для CSV).
        extraction_time_sec: Время извлечения в секундах.
        error: Сообщение об ошибке, если извлечение завершилось
            частично или с предупреждением.  ``None`` при успехе.

    Example::

        result = PDFExtractor("doc.pdf").extract()
        if result.error:
            print("Предупреждение:", result.error)
        print(result.text[:200])
    """

    file_path: str
    text: str = ""
    chunks: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    extraction_time_sec: float = 0.0
    error: str | None = None

    @property
    def is_empty(self) -> bool:
        """Возвращает ``True``, если извлечённый текст пуст."""
        return not self.text.strip()

    @property
    def char_count(self) -> int:
        """Количество символов в извлечённом тексте."""
        return len(self.text)

    @property
    def word_count(self) -> int:
        """Приблизительное количество слов в извлечённом тексте."""
        return len(self.text.split())


class BaseExtractor(ABC):
    """Абстрактный базовый класс для всех экстракторов текста.

    Подклассы обязаны реализовать метод :meth:`extract`.
    Опционально — :meth:`extract_chunks` для потоковой обработки больших файлов.

    Attributes:
        file_path: Абсолютный путь к файлу.
        file_size_bytes: Размер файла в байтах (заполняется при инициализации).

    Args:
        file_path: Путь к файлу для извлечения текста.

    Raises:
        FileNotFoundError: Если файл не найден по указанному пути.
        ExtractionError: При любой ошибке извлечения.

    Example::

        class MyExtractor(BaseExtractor):
            def extract(self) -> ExtractionResult:
                text = open(self.file_path).read()
                return self._make_result(text=text)

        result = MyExtractor("file.txt").extract()
    """

    CHUNK_THRESHOLD_BYTES: int = 10 * 1024 * 1024  # 10 MB

    def __init__(self, file_path: str) -> None:
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Файл не найден: '{file_path}'")
        self.file_path: str = os.path.abspath(file_path)
        self.file_size_bytes: int = os.path.getsize(self.file_path)
        self._logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )


    @abstractmethod
    def extract(self) -> ExtractionResult:
        """Извлекает весь текст из файла и возвращает результат.

        Этот метод должен быть реализован в каждом подклассе.
        Для больших файлов реализация может внутри использовать
        :meth:`extract_chunks` и объединять результаты.

        Returns:
            :class:`ExtractionResult` с полным текстом и метаданными.

        Raises:
            ExtractionError: При критической ошибке, когда извлечение
                невозможно (повреждённый файл, неподдерживаемый кодек и т.п.).
        """

    def extract_chunks(self) -> Iterator[str]:
        """Генератор текстовых чанков для потоковой обработки.

        Базовая реализация извлекает весь текст и возвращает его
        одним куском.  Переопределите в подклассе для реальной
        потоковой обработки больших файлов.

        Yields:
            Текстовые фрагменты (чанки) по мере их извлечения.

        Example::

            for chunk in extractor.extract_chunks():
                detector.process(chunk)
        """
        result = self.extract()
        if result.text:
            yield result.text

    @property
    def needs_chunking(self) -> bool:
        """Возвращает ``True``, если файл превышает порог чанкинга."""
        return self.file_size_bytes > self.CHUNK_THRESHOLD_BYTES

   #Доп методы 

    def _make_result(
        self,
        text: str = "",
        chunks: list[str] | None = None,
        metadata: dict | None = None,
        error: str | None = None,
        start_time: float | None = None,
    ) -> ExtractionResult:
        """Фабричный метод для создания :class:`ExtractionResult`.

        Автоматически заполняет ``file_path`` и ``extraction_time_sec``.

        Args:
            text: Извлечённый текст.
            chunks: Список чанков.  Если ``None`` — будет создан из ``text``.
            metadata: Метаданные файла.
            error: Сообщение об ошибке (или ``None``).
            start_time: Время начала извлечения (``time.monotonic()``).
                Если ``None`` — время не вычисляется.

        Returns:
            Заполненный :class:`ExtractionResult`.
        """
        elapsed = (
            round(time.monotonic() - start_time, 4) if start_time is not None else 0.0
        )
        return ExtractionResult(
            file_path=self.file_path,
            text=text,
            chunks=chunks if chunks is not None else ([text] if text else []),
            metadata=metadata or {},
            extraction_time_sec=elapsed,
            error=error,
        )

    def _log_start(self) -> float:
        """Логирует начало обработки и возвращает монотонное время старта.

        Returns:
            Время начала обработки (``time.monotonic()``).
        """
        self._logger.debug(
            "Начало извлечения: '%s' (%.1f KB)",
            self.file_path,
            self.file_size_bytes / 1024,
        )
        return time.monotonic()

    def _log_done(self, result: ExtractionResult) -> None:
        """Логирует завершение обработки с итоговой статистикой.

        Args:
            result: Результат извлечения.
        """
        if result.error:
            self._logger.warning(
                "Извлечение завершено с ошибкой: '%s' — %s",
                self.file_path,
                result.error,
            )
        else:
            self._logger.debug(
                "Извлечение завершено: '%s' — %d символов за %.3f с",
                self.file_path,
                result.char_count,
                result.extraction_time_sec,
            )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"file_path={self.file_path!r}, "
            f"size={self.file_size_bytes} bytes)"
        )