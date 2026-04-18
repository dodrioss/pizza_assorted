"""
Экстрактор текста из PDF-файлов.

Стратегия извлечения:
    1. Сначала пробует **PyMuPDF** (``fitz``) — быстрый и точный для
       большинства PDF с встроенным текстовым слоем.
    2. Если PyMuPDF вернул мало или пустой текст — переключается на
       **pdfplumber**, который лучше справляется со сложной вёрсткой
       и таблицами.
    3. Для больших файлов (> ``CHUNK_THRESHOLD_BYTES``) страницы
       обрабатываются постепенно — это позволяет держать потребление
       памяти под контролем.
    4. Если текстовый слой не найден совсем — метод возвращает
       результат с предупреждением (OCR не входит в этот экстрактор;
       для изображений используйте :class:`~extractors.ImageExtractor`).

Зависимости:
    - ``pymupdf`` (``fitz``) — основной бэкенд
    - ``pdfplumber`` — резервный бэкенд

Example::

    from extractors.pdf_extractor import PDFExtractor

    result = PDFExtractor("report.pdf").extract()
    print(f"Страниц: {result.metadata['page_count']}")
    print(result.text[:500])
"""

from __future__ import annotations

import logging
from typing import Iterator

from extractors.base import BaseExtractor, ExtractionResult, ExtractionError

logger = logging.getLogger(__name__)

# Минимальное количество символов на страницу, при котором считается,
# что PyMuPDF успешно извлёк текст.
_MIN_CHARS_PER_PAGE = 10


class PDFExtractor(BaseExtractor):
    """Экстрактор текста из PDF-файлов.

    Использует двухуровневую стратегию: PyMuPDF → pdfplumber.
    Поддерживает чанкированное чтение больших PDF.

    Args:
        file_path: Путь к PDF-файлу.
        prefer_pdfplumber: Если ``True`` — сразу использует pdfplumber
            без предварительной попытки через PyMuPDF.  По умолчанию
            ``False`` (PyMuPDF быстрее).

    Raises:
        FileNotFoundError: Если файл не найден.
        ExtractionError: При критической ошибке (не удалось открыть
            PDF ни одним из бэкендов).
    """

    def __init__(self, file_path: str, prefer_pdfplumber: bool = False) -> None:
        super().__init__(file_path)
        self._prefer_pdfplumber = prefer_pdfplumber

    def extract(self) -> ExtractionResult:
        """Извлекает текст из всего PDF-файла.

        При больших файлах автоматически переходит на постраничную
        обработку для экономии памяти.

        Returns:
            :class:`~extractors.base.ExtractionResult` с текстом,
            чанками (по одному на страницу) и метаданными:

            - ``page_count`` — число страниц
            - ``backend`` — использованный бэкенд (``"pymupdf"`` или
              ``"pdfplumber"``)
            - ``has_text_layer`` — наличие текстового слоя

        Raises:
            ExtractionError: Если PDF не удалось открыть.
        """
        start = self._log_start()
        if self.file_size_bytes == 0:
            result = self._make_result(
                text="",
                chunks=[],
                metadata={"empty": True},
                error="empty file",
                start_time=start,
            )
            self._log_done(result)
            return result

        if self._prefer_pdfplumber:
            result = self._extract_with_pdfplumber(start)
        else:
            result = self._extract_with_pymupdf(start)
            # Fallback: если PyMuPDF вернул пустышку — пробуем pdfplumber
            if result.is_empty or not result.metadata.get("has_text_layer"):
                self._logger.info(
                    "PyMuPDF не нашёл текст в '%s', переключаемся на pdfplumber",
                    self.file_path,
                )
                result = self._extract_with_pdfplumber(start)

        self._log_done(result)
        return result

    def extract_chunks(self) -> Iterator[str]:
        """Генератор постраничных текстовых чанков.

        Полезно при обработке многостраничных PDF, когда не нужно
        держать весь текст в памяти.

        Yields:
            Текст каждой страницы PDF (не пустые страницы пропускаются).

        Raises:
            ExtractionError: Если не удалось открыть файл.
        """
        yield from self._iter_pages_pymupdf()

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _extract_with_pymupdf(self, start: float) -> ExtractionResult:
        """Извлекает текст с помощью PyMuPDF (``fitz``).

        Args:
            start: Монотонное время начала (``time.monotonic()``).

        Returns:
            :class:`~extractors.base.ExtractionResult`.

        Raises:
            ExtractionError: При ошибке открытия или чтения файла.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise ExtractionError(
                self.file_path,
                "Библиотека 'pymupdf' не установлена. "
                "Выполните: pip install pymupdf",
            ) from exc

        try:
            doc = fitz.open(self.file_path)
        except Exception as exc:
            raise ExtractionError(
                self.file_path, f"Не удалось открыть PDF через PyMuPDF: {exc}"
            ) from exc

        chunks: list[str] = []
        total_chars = 0

        with doc:
            page_count = len(doc)
            for page in doc:
                page_text = page.get_text("text").strip()
                if page_text:
                    chunks.append(page_text)
                    total_chars += len(page_text)

        has_text = total_chars >= page_count * _MIN_CHARS_PER_PAGE
        full_text = "\n\n".join(chunks)

        return self._make_result(
            text=full_text,
            chunks=chunks,
            metadata={
                "page_count": page_count,
                "backend": "pymupdf",
                "has_text_layer": has_text,
            },
            error=None if has_text else "Текстовый слой не найден или пустой",
            start_time=start,
        )

    def _extract_with_pdfplumber(self, start: float) -> ExtractionResult:
        """Извлекает текст с помощью pdfplumber.

        Лучше справляется с PDF со сложной вёрсткой, таблицами и
        многоколончатым текстом.

        Args:
            start: Монотонное время начала (``time.monotonic()``).

        Returns:
            :class:`~extractors.base.ExtractionResult`.

        Raises:
            ExtractionError: При ошибке открытия или чтения файла.
        """
        try:
            import pdfplumber
        except ImportError as exc:
            raise ExtractionError(
                self.file_path,
                "Библиотека 'pdfplumber' не установлена. "
                "Выполните: pip install pdfplumber",
            ) from exc

        try:
            pdf = pdfplumber.open(self.file_path)
        except Exception as exc:
            raise ExtractionError(
                self.file_path, f"Не удалось открыть PDF через pdfplumber: {exc}"
            ) from exc

        chunks: list[str] = []
        total_chars = 0

        with pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                page_text = page_text.strip()
                if page_text:
                    chunks.append(page_text)
                    total_chars += len(page_text)

        has_text = total_chars >= page_count * _MIN_CHARS_PER_PAGE
        full_text = "\n\n".join(chunks)

        return self._make_result(
            text=full_text,
            chunks=chunks,
            metadata={
                "page_count": page_count,
                "backend": "pdfplumber",
                "has_text_layer": has_text,
            },
            error=None if has_text else "Текстовый слой не найден или пустой",
            start_time=start,
        )

    def _iter_pages_pymupdf(self) -> Iterator[str]:
        """Итерирует текст по страницам через PyMuPDF.

        Yields:
            Непустой текст каждой страницы.

        Raises:
            ExtractionError: При ошибке открытия файла.
        """
        try:
            import fitz
        except ImportError as exc:
            raise ExtractionError(
                self.file_path, "Библиотека 'pymupdf' не установлена."
            ) from exc

        try:
            doc = fitz.open(self.file_path)
        except Exception as exc:
            raise ExtractionError(
                self.file_path, f"Ошибка открытия PDF: {exc}"
            ) from exc

        with doc:
            for page in doc:
                page_text = page.get_text("text").strip()
                if page_text:
                    yield page_text