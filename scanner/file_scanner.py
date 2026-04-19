"""
Сканер файловой структуры корпоративного хранилища (обновленная версия).

Теперь поддерживает все форматы, указанные в кейсе хакатона 152-ФЗ:
    Структурированные: CSV, JSON, Parquet
    Документы: PDF, DOC, DOCX, RTF, XLS, XLSX
    Веб-контент: HTML, HTM
    Изображения: TIF, TIFF, JPEG, JPG, PNG, GIF, BMP
    Видео: MP4

Дополнительные улучшения:
    Пропускает пустые файлы (0 байт)
    Полный список расширений определен прямо в сканнере
    Исправлен баг в if __name__ == "__main__"
"""

from __future__ import annotations

import logging
import sys
import os
from pathlib import Path
from typing import Iterator, List

# Добавляем корень проекта в sys.path (для импорта config)
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from config import DEFAULT_ROOT_DIR

logger = logging.getLogger(__name__)

# ==================== ПОЛНЫЙ СПИСОК ПОДДЕРЖИВАЕМЫХ ФОРМАТОВ ====================
SUPPORTED_EXTS_SET: frozenset[str] = frozenset({
    # Структурированные данные
    ".csv", ".json", ".parquet",
    # Документы
    ".pdf", ".doc", ".docx", ".rtf", ".xls", ".xlsx",
    # Веб-контент
    ".html", ".htm",
    # Изображения
    ".tif", ".tiff", ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    # Видео
    ".mp4",
})

# Системные/скрытые директории, которые всегда пропускаем
_IGNORED_DIRNAMES: frozenset[str] = frozenset({
    "__pycache__", ".git", ".svn", ".hg", "node_modules",
    ".idea", ".vscode", "venv", "env", ".env", "build", "dist",
})


class FileScanner:
    """Сканер файловой структуры (Этап 1 хакатона)."""

    def __init__(self, root_dir: str | None = None) -> None:
        self.root_dir = Path(root_dir or DEFAULT_ROOT_DIR).resolve()
        if not self.root_dir.exists():
            raise FileNotFoundError(f"Директория не найдена: {self.root_dir}")
        if not self.root_dir.is_dir():
            raise NotADirectoryError(f"Путь не является директорией: {self.root_dir}")

        logger.info("Инициализация FileScanner: root_dir=%s", self.root_dir)
        logger.info("Поддерживаемые расширения: %d типов", len(SUPPORTED_EXTS_SET))

    def scan(self) -> List[str]:
        """Полное сканирование → список абсолютных путей."""
        start = self._log_start()
        files: List[str] = [str(p) for p in self.iter_files()]
        self._log_done(len(files))
        return files

    def iter_files(self) -> Iterator[Path]:
        """Генератор — рекомендуется для больших датасетов (3 ГБ+)."""
        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            # Убираем скрытые и системные папки
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in _IGNORED_DIRNAMES
            ]

            for filename in filenames:
                path = Path(dirpath) / filename
                ext = path.suffix.lower()

                if ext in SUPPORTED_EXTS_SET:
                    # НОВАЯ ЗАЩИТА: пропускаем пустые файлы (0 байт)
                    try:
                        if path.stat().st_size == 0:
                            logger.debug("Пропущен пустой файл (0 байт): %s", path)
                            continue
                    except OSError:
                        logger.warning("Не удалось проверить размер файла: %s", path)
                        continue

                    yield path

    def _log_start(self) -> float:
        """Логирует начало сканирования."""
        import time
        start = time.perf_counter()
        logger.info("Начало сканирования директории: %s", self.root_dir)
        return start

    def _log_done(self, total_files: int) -> None:
        """Логирует завершение."""
        logger.info(
            "Сканирование завершено. Найдено поддерживаемых файлов: %d",
            total_files,
        )


if __name__ == "__main__":
    # Поддержка передачи пути через аргумент командной строки
    root_dir = sys.argv[1] if len(sys.argv) > 1 else None
    scanner = FileScanner(root_dir)

    files = scanner.scan()
    print(f"\nНайдено файлов: {len(files)}")
    for i, f in enumerate(files[:15]):
        print(f"   {i + 1:2d}. {f}")
    if len(files) > 15:
        print(f"   ... и еще {len(files) - 15} файлов")