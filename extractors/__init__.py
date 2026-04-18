"""
extractors — Модуль извлечения текста из файлов различных форматов.

Поддерживаемые форматы:
    - PDF (.pdf)           — PyMuPDF + pdfplumber с чанкингом для больших файлов
    - Word (.docx, .doc)   — python-docx
    - Таблицы (.csv, .parquet) — pandas / pyarrow с чанкированным чтением
    - Изображения (.jpg, .png, .tif, .gif) — Tesseract OCR + EasyOCR (опционально)
    - Веб-страницы (.html) — BeautifulSoup
    - Видео (.mp4)         — метаданные + субтитры (если доступны)

Пример использования::

    from extractors import get_extractor

    extractor = get_extractor("/path/to/file.pdf")
    result = extractor.extract()
    print(result.text)
    print(result.metadata)
"""

from extractors.base import BaseExtractor, ExtractionResult, ExtractionError
from extractors.pdf_extractor import PDFExtractor
from extractors.docx_extractor import DocxExtractor
from extractors.csv_parquet_extractor import CsvParquetExtractor
from extractors.image_extractor import ImageExtractor
from extractors.html_extractor import HTMLExtractor
from extractors.video_extractor import VideoExtractor

import os
from typing import Optional


# Реестр экстракторов: расширение -> класс
_EXTRACTOR_REGISTRY: dict[str, type[BaseExtractor]] = {
    ".pdf": PDFExtractor,
    ".docx": DocxExtractor,
    ".doc": DocxExtractor,
    ".csv": CsvParquetExtractor,
    ".parquet": CsvParquetExtractor,
    ".jpg": ImageExtractor,
    ".jpeg": ImageExtractor,
    ".png": ImageExtractor,
    ".tif": ImageExtractor,
    ".tiff": ImageExtractor,
    ".gif": ImageExtractor,
    ".html": HTMLExtractor,
    ".htm": HTMLExtractor,
    ".mp4": VideoExtractor,
}


def get_extractor(file_path: str) -> Optional[BaseExtractor]:
    """Возвращает подходящий экстрактор для переданного файла.

    Выбор экстрактора осуществляется по расширению файла.
    Если расширение не поддерживается — возвращается ``None``.

    Args:
        file_path: Абсолютный или относительный путь к файлу.

    Returns:
        Экземпляр подходящего экстрактора или ``None``,
        если формат файла не поддерживается.

    Example::

        extractor = get_extractor("report.pdf")
        if extractor:
            result = extractor.extract()
    """
    ext = os.path.splitext(file_path)[-1].lower()
    extractor_class = _EXTRACTOR_REGISTRY.get(ext)
    if extractor_class is None:
        return None
    return extractor_class(file_path)


def is_supported(file_path: str) -> bool:
    """Проверяет, поддерживается ли формат файла для извлечения текста.

    Args:
        file_path: Путь к файлу.

    Returns:
        ``True`` если формат поддерживается, иначе ``False``.
    """
    ext = os.path.splitext(file_path)[-1].lower()
    return ext in _EXTRACTOR_REGISTRY


__all__ = [
    "BaseExtractor",
    "ExtractionResult",
    "ExtractionError",
    "PDFExtractor",
    "DocxExtractor",
    "CsvParquetExtractor",
    "ImageExtractor",
    "HTMLExtractor",
    "VideoExtractor",
    "get_extractor",
    "is_supported",
]