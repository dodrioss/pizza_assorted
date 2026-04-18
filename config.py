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