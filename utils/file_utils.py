"""
Утилиты для работы с файлами: MIME-типы, безопасное чтение, проверка расширений.
"""

import os
import mimetypes
from pathlib import Path
from typing import Optional

from config import SUPPORTED_EXTS_SET   


def is_supported_by_extension(file_path: str) -> bool:
    """Проверяет, поддерживается ли файл по расширению."""
    ext = Path(file_path).suffix.lower()
    return ext in SUPPORTED_EXTS_SET


def get_file_mime(file_path: str) -> str:
    """Определяет MIME-тип файла."""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"


def safe_read_text(file_path: str, encodings: tuple = ("utf-8-sig", "cp1251", "utf-8", "latin-1")) -> Optional[str]:
    """
    Безопасно читает текстовый файл, пробуя разные кодировки.
    Порядок важен: сначала utf-8-sig, потом cp1251 (часто используется в русских файлах),
    затем utf-8 и latin-1 как fallback.
    """
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc, errors="strict") as f:
                return f.read()
        except (UnicodeDecodeError, OSError, LookupError):
            continue
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return None


def get_file_size(file_path: str) -> int:
    """Возвращает размер файла в байтах."""
    try:
        return os.path.getsize(file_path)
    except OSError:
        return 0