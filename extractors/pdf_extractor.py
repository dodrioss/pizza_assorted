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
import os
import tempfile
from typing import Iterator
from pathlib import Path

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

    def _is_valid_pdf(self, path: str) -> bool:
        """Проверяет, что файл — валидный PDF по заголовку и размеру."""
        try:
            if os.path.getsize(path) < 100:  # Минимальный осмысленный PDF
                return False
            with open(path, 'rb') as f:
                header = f.read(8)
            return header.startswith(b'%PDF-')
        except Exception:
            return False

    def _extract_ocr_fallback(self, pdf_path: str, start: float) -> ExtractionResult:
        """
        Резервный метод: рендерит страницы PDF в изображения и извлекает текст через ImageExtractor.
        Вызывается, когда текстовый слой не найден.
        """
        try:
            from pdf2image import convert_from_path
        except ImportError:
            self._logger.warning("pdf2image не установлен: pip install pdf2image — пропуск OCR-фоллбэка")
            return self._make_result(
                text="", chunks=[],
                metadata={"page_count": 0, "backend": "none", "has_text_layer": False, "ocr_fallback": False},
                error="pdf2image не установлен",
                start_time=start,
            )

        # Импортируем ваш ImageExtractor локально, чтобы избежать циклических импортов
        from extractors.image_extractor import ImageExtractor

        chunks: list[str] = []
        total_chars = 0
        page_count = 0

        try:
            images = convert_from_path(pdf_path, dpi=200, thread_count=2)
            page_count = len(images)
            self._logger.info("OCR-фоллбэк: обработаем %d страниц через ImageExtractor", page_count)

            with tempfile.TemporaryDirectory() as tmpdir:
                for idx, img in enumerate(images):
                    tmp_path = os.path.join(tmpdir, f"page_{idx}.png")
                    img.save(tmp_path, "PNG")
                    img_result = ImageExtractor(tmp_path).extract()
                    if img_result.text.strip():
                        chunks.append(img_result.text.strip())
                        total_chars += len(img_result.text)
        except Exception as exc:
            self._logger.error("OCR-фоллбэк упал для %s: %s", pdf_path, exc)
            return self._make_result(
                text="", chunks=[],
                metadata={"page_count": 0, "backend": "ocr_fallback", "has_text_layer": False},
                error=f"OCR fallback failed: {exc}",
                start_time=start,
            )

        has_text = total_chars >= page_count * _MIN_CHARS_PER_PAGE if page_count > 0 else False
        return self._make_result(
            text="\n\n--- PAGE BREAK ---\n\n".join(chunks),
            chunks=chunks,
            metadata={
                "page_count": page_count,
                "backend": "ocr_fallback",
                "has_text_layer": False,
                "ocr_fallback": True,
            },
            error=None if has_text else "OCR не смог извлечь текст из скана",
            start_time=start,
        )

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
            # Fallback на pdfplumber ТОЛЬКО если это не OCR-результат и текст пустой
            if (result.is_empty 
                and not result.metadata.get("has_text_layer") 
                and result.metadata.get("backend") != "ocr_fallback"
                and not result.metadata.get("invalid_pdf")):  # <--- Добавлена проверка
                self._logger.info(
                    "PyMuPDF + OCR не дали результата для '%s', пробуем pdfplumber",
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

    def _extract_with_pymupdf(self, start: float) -> ExtractionResult:
        """Извлекает текст с помощью PyMuPDF (``fitz``) с безопасным открытием."""
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise ExtractionError(
                self.file_path,
                "Библиотека 'pymupdf' не установлена. Выполните: pip install pymupdf",
            ) from exc

        if not self._is_valid_pdf(self.file_path):
            self._logger.warning("Файл не похож на валидный PDF: %s", self.file_path)
            return self._make_result(
                text="", chunks=[],
                metadata={
                    "page_count": 0, 
                    "backend": "pymupdf", 
                    "has_text_layer": False,
                    "invalid_pdf": True  
                },
                error="Файл не является валидным PDF (повреждён или не PDF)",
                start_time=start,
            )
        
        # Если валидация прошла — открываем как обычно
        try:
            doc = fitz.open(self.file_path)
        except Exception as exc:
            err_msg = str(exc).lower()
            if "no objects found" in err_msg or "fzerrorformat" in err_msg:
                self._logger.warning("PDF повреждён или пуст: %s", self.file_path)
                return self._make_result(
                    text="", chunks=[],
                    metadata={"page_count": 0, "backend": "pymupdf", "has_text_layer": False},
                    error="PDF повреждён или не содержит объектов",
                    start_time=start,
                )
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

        has_text = total_chars >= page_count * _MIN_CHARS_PER_PAGE if page_count > 0 else False
        full_text = "\n\n".join(chunks)

        # === НОВОЕ: если текст не найден — не сразу fallback на pdfplumber, а сначала пробуем OCR ===
        if not has_text and page_count > 0:
            self._logger.info(
                "PyMuPDF не нашёл текст в '%s' (%d стр.), пробуем OCR-фоллбэк",
                self.file_path, page_count
            )
            ocr_result = self._extract_ocr_fallback(self.file_path, start)
            if ocr_result.text.strip():
                self._logger.info("OCR-фоллбэк успешен для %s: %d символов", self.file_path, len(ocr_result.text))
                return ocr_result

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

        has_text = total_chars >= page_count * _MIN_CHARS_PER_PAGE if page_count > 0 else False
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