# config.py
"""
Глобальные константы проекта
"""

# Поддерживаемые расширения (по ТЗ хакатона)
SUPPORTED_EXTENSIONS = {
    # Структурированные
    ".csv", ".json", ".parquet",
    # Документы
    ".pdf", ".doc", ".docx", ".rtf", ".xls", ".xlsx",
    # Веб
    ".html", ".htm",
    # Изображения
    ".tif", ".tiff", ".jpeg", ".jpg", ".png", ".gif",
    # Видео
    ".mp4",
}

# Директории, которые НЕ нужно сканировать
EXCLUDED_DIRS = {
    "output",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "env",
    "tests",
    ".idea",
    ".vscode",
    "node_modules",
}
"""Минимальный config.py для запуска тестов."""

SUPPORTED_EXTS_SET: frozenset[str] = frozenset({
    ".pdf", ".docx", ".doc", ".csv", ".parquet",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif",
    ".html", ".htm", ".mp4", ".txt"
})

DEFAULT_ROOT_DIR: str = "./test_dataset"
