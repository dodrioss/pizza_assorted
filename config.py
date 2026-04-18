"""Минимальный config.py для запуска тестов."""

SUPPORTED_EXTS_SET: frozenset[str] = frozenset({
    ".pdf", ".docx", ".doc", ".csv", ".parquet",
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif",
    ".html", ".htm", ".mp4", ".txt"
})

DEFAULT_ROOT_DIR: str = "./test_dataset"