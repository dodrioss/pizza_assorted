"""
Утилиты для замера производительности: таймеры, использование памяти.
"""

import time
from functools import wraps
import psutil   # pip install psutil (добавь в requirements.txt)


def timer(func):
    """Декоратор для замера времени выполнения функции."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"⏱️  {func.__name__} выполнено за {elapsed:.2f} сек")
        return result
    return wrapper


def memory_usage() -> dict:
    """Возвращает текущие показатели использования памяти процесса."""
    process = psutil.Process()
    mem_info = process.memory_info()

    return {
        "rss_mb": mem_info.rss / 1024 / 1024,           # Resident Set Size
        "vms_mb": mem_info.vms / 1024 / 1024,           # Virtual Memory Size
        "percent": process.memory_percent(),
    }


def log_memory_usage(logger=None, message: str = "Memory usage"):
    """Логирует текущее потребление памяти."""
    mem = memory_usage()
    msg = f"{message}: RSS={mem['rss_mb']:.1f} MB, VMS={mem['vms_mb']:.1f} MB ({mem['percent']:.1f}%)"

    if logger:
        logger.info(msg)
    else:
        print(msg)

class Timer:
    def __init__(self, name: str = "Operation"):
        self.name = name
        self.start = None

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        elapsed = time.perf_counter() - self.start
        print(f"⏱️  {self.name} завершено за {elapsed:.2f} секунд")