"""
utils/parallel.py — утилита параллельной обработки файлов

Авто-определение оптимального числа потоков:
  - I/O-bound задачи (OCR, чтение файлов): min(32, cpu_count * 4)
  - CPU-bound задачи (regex, классификация): cpu_count

Стратегия: ThreadPoolExecutor для всего пайплайна (узкое место — диск/OCR).
ProcessPoolExecutor не нужен: GIL не мешает I/O, а fork-overhead съест выигрыш.
"""

import os
import logging
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_progress_lock = threading.Lock()


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
    return {
        "cpu_count": cpu,
        "io_workers": min(32, cpu * 4),
        "cpu_workers": cpu,
        "balanced_workers": cpu * 2,
        "env_override": int(env_workers) if env_workers and env_workers.isdigit() else None,
        "effective_workers": optimal_workers("io"),
    }