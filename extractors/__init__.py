"""
extractors — Модуль извлечения текста из файлов различных форматов.
"""

from extractors.base import BaseExtractor, ExtractionResult, ExtractionError
from extractors.pdf_extractor import PDFExtractor
from extractors.docx_extractor import DocxExtractor
from extractors.csv_parquet_extractor import CsvParquetExtractor
from extractors.image_extractor import ImageExtractor
from extractors.html_extractor import HTMLExtractor
from extractors.video_extractor import VideoExtractor

import os
from typing import Optional, Dict, Any


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


def get_extractor(file_path: str, extra_kwargs: Dict[str, Any] = None) -> Optional[BaseExtractor]:
    """Возвращает подходящий экстрактор для файла с поддержкой дополнительных параметров (для ImageExtractor)."""
    ext = os.path.splitext(file_path)[-1].lower()
    extractor_class = _EXTRACTOR_REGISTRY.get(ext)

    if extractor_class is None:
        return None

    if extra_kwargs and extractor_class is ImageExtractor:
        return extractor_class(file_path, **extra_kwargs)

    return extractor_class(file_path)


def is_supported(file_path: str) -> bool:
    """Проверяет, поддерживается ли формат файла для извлечения текста."""
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