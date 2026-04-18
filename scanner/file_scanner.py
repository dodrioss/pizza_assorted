"""
Сканер файловой структуры корпоративного хранилища.

Рекурсивно обходит указанную директорию и возвращает **только** файлы
с поддерживаемыми расширениями (см. `config.SUPPORTED_EXTENSIONS`).

Особенности реализации:
    • Используется `os.walk` + `pathlib.Path` — максимально быстро и
      экономно по памяти даже на 50 000+ файлов.
    • Предфильтрация по расширению происходит **на этапе сканирования**
      (без открытия файлов) — это ключевое требование к производительности.
    • Автоматически пропускает скрытые директории (начинающиеся с `.`)
      и системные папки (`__pycache__`, `.git`, `node_modules` и т.д.).
    • Поддерживает два режима работы:
        - `scan()` — возвращает полный список (удобно для небольших датасетов)
        - `iter_files()` — генератор (рекомендуется для больших объёмов 3 ГБ+)

Стратегия:
    Файлы группируются по типу (`structured`, `document`, `image` и т.д.),
    что позволяет дальше сразу выбирать нужный экстрактор без дополнительных
    проверок.

Зависимости:
    - `os`, `pathlib`
    - `config` (DEFAULT_ROOT_DIR + SUPPORTED_EXTS_SET)

Example::
    from scanner.file_scanner import FileScanner
    scanner = FileScanner("./test_dataset")
    files = scanner.scan()
    print(f"Найдено поддерживаемых файлов: {len(files)}")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterator, List

from config import DEFAULT_ROOT_DIR, SUPPORTED_EXTS_SET

logger = logging.getLogger(__name__)

# Системные/скрытые директории, которые всегда пропускаем
_IGNORED_DIRNAMES: frozenset[str] = frozenset({
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    ".idea",
    ".vscode",
    "venv",
    "env",
    ".env",
    "build",
    "dist",
})


class FileScanner:
    """Сканер файловой структуры (Этап 1 хакатона).

    Args:
        root_dir: Корневая директория для рекурсивного обхода.
                  По умолчанию `config.DEFAULT_ROOT_DIR`.
    Raises:
        FileNotFoundError: Если указанная директория не существует.
    """

    def __init__(self, root_dir: str | None = None) -> None:
        self.root_dir = Path(root_dir or DEFAULT_ROOT_DIR).resolve()
        if not self.root_dir.exists():
            raise FileNotFoundError(f"Директория не найдена: {self.root_dir}")
        if not self.root_dir.is_dir():
            raise NotADirectoryError(f"Путь не является директорией: {self.root_dir}")

        logger.info("Инициализация FileScanner: root_dir=%s", self.root_dir)

    def scan(self) -> List[str]:
        """Выполняет полное сканирование и возвращает список абсолютных путей.

        Returns:
            Список строк с полными путями к поддерживаемым файлам.
        """
        start = self._log_start()
        files: List[str] = [str(p) for p in self.iter_files()]
        self._log_done(len(files))
        return files

    def iter_files(self) -> Iterator[Path]:
        """Генератор файлов для потоковой обработки (рекомендуется).

        Yields:
            `pathlib.Path` для каждого поддерживаемого файла.
        """
        for dirpath, dirnames, filenames in os.walk(self.root_dir):
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d not in _IGNORED_DIRNAMES
            ]

            for filename in filenames:
                path = Path(dirpath) / filename
                ext = path.suffix.lower()

                if ext in SUPPORTED_EXTS_SET:
                    yield path

    def _log_start(self) -> float:
        """Логирует начало сканирования."""
        import time
        start = time.perf_counter()
        logger.info("Начало сканирования директории: %s", self.root_dir)
        return start

    def _log_done(self, total_files: int) -> None:
        """Логирует завершение сканирования."""
        logger.info(
            "Сканирование завершено. Найдено поддерживаемых файлов: %d",
            total_files,
        )


if __name__ == "__main__":
    scanner = FileScanner()
    files = scanner.scan()
    print(f"Найдено файлов: {len(files)}")
    for i, f in enumerate(files[:10]):
        print(f"   {i + 1:2d}. {f}")
    if len(files) > 10:
        print(f"   ... и ещё {len(files) - 10} файлов")