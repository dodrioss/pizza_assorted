"""
utils/__init__.py — Публичный API пакета утилит.

Позволяет импортировать функции напрямую:
    from utils import clean_text, setup_logging, process_files_parallel
"""

from .text_utils import clean_text, quick_skip_text
from .file_utils import is_supported_by_extension, get_file_mime, safe_read_text
from .logging_utils import setup_logging, get_progress_bar
from .performance import timer, memory_usage
from .parallel import process_files_parallel, get_worker_info, optimal_workers

__all__ = [
    "clean_text",
    "quick_skip_text",
    "is_supported_by_extension",
    "get_file_mime",
    "safe_read_text",
    "setup_logging",
    "get_progress_bar",
    "timer",
    "memory_usage",
    "process_files_parallel",
    "get_worker_info",
    "optimal_workers",
]