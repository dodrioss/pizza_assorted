"""
utils/parallel.py — утилита параллельной обработки файлов

Авто-определение оптимального числа потоков:
  - I/O-bound задачи (OCR, чтение файлов): min(32, cpu_count * 4)
  - CPU-bound задачи (regex, классификация): cpu_count
  - OCR-задачи: настраиваемый лимит (по умолчанию 2) через семафор

Стратегия: ThreadPoolExecutor для всего пайплайна (узкое место — диск/OCR).
ProcessPoolExecutor не нужен: GIL не мешает I/O, а fork-overhead съест выигрыш.
"""

import os
import logging
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_progress_lock = threading.Lock()

# Глобальный менеджер слотов для OCR (инициализируется при первом импорте)
_ocr_manager: Optional["OCRSlotManager"] = None


class OCRSlotManager:
    """
    Управляет пулом слотов для ресурсоёмких OCR-операций.

    Зачем: Tesseract/EasyOCR/PaddleOCR потребляют много памяти и CPU.
    Если запустить 20 потоков с OCR одновременно — система уйдёт в своп.
    Решение: семафор на 2-4 слота независимо от общего числа потоков.
    """

    def __init__(self, max_concurrent: int | None = None):
        if max_concurrent is None:
            # Читаем из env или дефолт 2
            env_val = os.environ.get("PDN_OCR_WORKERS")
            max_concurrent = int(env_val) if env_val and env_val.isdigit() else 2
        
        self.max_concurrent = max(1, max_concurrent)
        self._semaphore = threading.Semaphore(self.max_concurrent)
        self._lock = threading.Lock()
        self._active = 0

    @contextmanager
    def acquire(self):
        """Контекстный менеджер для захвата слота."""
        with self._semaphore:
            with self._lock:
                self._active += 1
                logger.debug(f"OCR слот: {self._active}/{self.max_concurrent}")
            try:
                yield
            finally:
                with self._lock:
                    self._active -= 1

    @property
    def active_count(self) -> int:
        with self._lock:
            return self._active


def get_ocr_manager(max_concurrent: int | None = None) -> OCRSlotManager:
    """
    Возвращает глобальный экземпляр OCRSlotManager (singleton).
    При первом вызове можно задать лимит, далее он фиксируется.
    """
    global _ocr_manager
    if _ocr_manager is None:
        _ocr_manager = OCRSlotManager(max_concurrent)
    return _ocr_manager


@contextmanager
def acquire_ocr_slot(max_concurrent: int | None = None):
    """
    Контекстный менеджер для ограничения параллельных OCR-запросов.

    Пример использования в image_extractor.py:
        with acquire_ocr_slot():
            result = pytesseract.image_to_string(img)

    Args:
        max_concurrent: Лимит одновременных OCR (по умолчанию из env или 2).
                       Можно переопределить через PDN_OCR_WORKERS.
    """
    manager = get_ocr_manager(max_concurrent)
    with manager.acquire():
        yield


def optimal_workers(mode: str = "io") -> int:
    """
    Возвращает оптимальное число потоков.

    mode="io"  → min(32, cpu_count * 4)  — для OCR, чтения файлов, сети
    mode="cpu" → cpu_count               — для regex, numpy, чистых вычислений
    mode="balanced" → cpu_count * 2      — компромисс

    Значение можно переопределить через переменную окружения PDN_WORKERS.
    """
    env_override = os.environ.get("PDN_WORKERS")
    if env_override:
        try:
            return max(1, int(env_override))
        except ValueError:
            logger.warning(f"PDN_WORKERS='{env_override}' не число, используем авто")

    cpu = os.cpu_count() or 2

    if mode == "io":
        return min(32, cpu * 4)
    elif mode == "cpu":
        return cpu
    else:  # balanced
        return cpu * 2


def process_files_parallel(
    file_paths: list[str],
    process_fn: Callable[[str], dict],
    *,
    workers: int | None = None,
    progress=None,       # rich.Progress instance (опционально)
    task_id=None,        # TaskID для progress.advance()
    console=None,        # rich.Console для вывода ошибок
) -> tuple[list[dict], int]:
    """
    Обрабатывает список файлов параллельно.

    Args:
        file_paths:  список путей к файлам
        process_fn:  функция (path_str) -> dict с результатом
                     Должна быть потокобезопасной (не писать в общие структуры).
        workers:     число потоков; None = авто (io-режим)
        progress:    rich.Progress для обновления прогресс-бара
        task_id:     ID задачи в progress
        console:     rich.Console для inline-сообщений об ошибках

    Returns:
        (results, errors_count)
        results — список dict в порядке завершения (не гарантирован порядок файлов!)
    """
    n_workers = workers if workers is not None else optimal_workers("io")
    results: list[dict] = []
    errors_count = 0

    logger.info(f"Запуск параллельной обработки: {len(file_paths)} файлов, {n_workers} потоков")

    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        future_to_path = {
            executor.submit(process_fn, path): path
            for path in file_paths
        }

        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception as exc:
                errors_count += 1
                logger.error(f"Необработанное исключение в потоке для {path}: {exc}", exc_info=True)
                if console:
                    console.print(f"[bold red]Thread-level ошибка[/bold red] → {Path(path).name}: {exc}")
                results.append({
                    "path": path,
                    "file_format": Path(path).suffix[1:].lower(),
                    "pii_categories": {},
                    "total_findings": 0,
                    "uz_level": "УЗ-4",
                    "error": f"Thread error: {str(exc)[:200]}",
                })
            finally:
                if progress is not None and task_id is not None:
                    with _progress_lock:
                        progress.advance(task_id)

    return results, errors_count


def get_worker_info() -> dict:
    """
    Возвращает информацию о доступных ресурсах — для логирования и отладки.
    """
    cpu = os.cpu_count() or 2
    env_workers = os.environ.get("PDN_WORKERS")
    env_ocr = os.environ.get("PDN_OCR_WORKERS")
    return {
        "cpu_count": cpu,
        "io_workers": min(32, cpu * 4),
        "cpu_workers": cpu,
        "balanced_workers": cpu * 2,
        "ocr_workers": int(env_ocr) if env_ocr and env_ocr.isdigit() else 2,
        "env_override": int(env_workers) if env_workers and env_workers.isdigit() else None,
        "effective_workers": optimal_workers("io"),
    }