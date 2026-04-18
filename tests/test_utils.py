"""
Полные тесты для модуля utils/
"""

import time
import logging
from pathlib import Path

import pytest

from utils.text_utils import clean_text, quick_skip_text
from utils.file_utils import is_supported_by_extension, get_file_mime, safe_read_text
from utils.logging_utils import setup_logging, get_progress_bar
from utils.performance import timer, memory_usage, Timer, log_memory_usage


# ====================== text_utils.py ======================

def test_clean_text():
    assert clean_text("  Hello   World!  \n\n") == "Hello World!"
    assert clean_text("Тест   с   пробелами   и\nпереносами") == "Тест с пробелами и переносами"
    assert clean_text("") == ""
    assert clean_text("   ") == ""


def test_clean_text_multiple_spaces_and_newlines():
    assert clean_text("   Много    пробелов   и\n\n\nпереносов   ") == "Много пробелов и переносов"


def test_clean_text_special_symbols():
    assert clean_text("Текст с «кавычками» и — длинным тире!") == 'Текст с "кавычками" и - длинным тире!'


def test_quick_skip_text():
    assert quick_skip_text("") is True
    assert quick_skip_text(" ") is True
    assert quick_skip_text("abc") is True
    assert quick_skip_text("Это нормальный текст для проверки ПДн") is False


def test_quick_skip_text_edge_cases():
    assert quick_skip_text(None) is True
    assert quick_skip_text("1234567890") is True
    assert quick_skip_text("!@#$%^&*()") is True
    assert quick_skip_text("ПДн тест СНИЛС 123-456-789 01") is False


def test_normalize_phone_for_detection():
    from utils.text_utils import normalize_phone_for_detection
    assert normalize_phone_for_detection("+7 (999) 123-45-67") == "79991234567"
    assert normalize_phone_for_detection("8-916-555-44-33") == "89165554433"


# ====================== file_utils.py ======================

def test_is_supported_by_extension():
    assert is_supported_by_extension("document.pdf") is True
    assert is_supported_by_extension("report.docx") is True
    assert is_supported_by_extension("data.csv") is True
    assert is_supported_by_extension("photo.jpg") is True
    assert is_supported_by_extension("virus.exe") is False
    assert is_supported_by_extension("unknown.abc") is False


def test_is_supported_by_extension_uppercase():
    assert is_supported_by_extension("DOCUMENT.PDF") is True
    assert is_supported_by_extension("REPORT.DOCX") is True


def test_get_file_mime():
    assert get_file_mime("test.pdf").startswith("application/")
    assert get_file_mime("image.jpg").startswith("image/")
    mime = get_file_mime("unknown.xyz")
    assert mime is not None
    assert "/" in mime


def test_get_file_mime_common_formats():
    assert get_file_mime("file.pdf").startswith("application/pdf")
    assert get_file_mime("file.jpg").startswith("image/jpeg")
    assert get_file_mime("file.png").startswith("image/png")
    assert get_file_mime("file.csv").startswith("text/")


def test_safe_read_text(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("Привет, это тестовый текст!", encoding="utf-8")
    content = safe_read_text(str(test_file))
    assert content == "Привет, это тестовый текст!"
    assert safe_read_text("non_existent_file_123456.txt") is None


def test_safe_read_text_different_encodings(tmp_path):
    test_file = tmp_path / "cp1251.txt"
    original = "Привет, мир! Текст с русскими буквами."
    test_file.write_text(original, encoding="cp1251")

    content = safe_read_text(str(test_file))
    assert content is not None
    assert "Привет, мир!" in content


def test_safe_read_text_with_errors(tmp_path):
    test_file = tmp_path / "broken.txt"
    test_file.write_bytes(b"Valid text \xff\xfe invalid bytes")
    content = safe_read_text(str(test_file))
    assert content is not None


def test_get_file_size(tmp_path):
    from utils.file_utils import get_file_size
    test_file = tmp_path / "size_test.txt"
    test_file.write_text("12345")
    assert get_file_size(str(test_file)) == 5
    assert get_file_size("nonexistent_file_987654.txt") == 0


# ====================== performance.py ======================

def test_memory_usage():
    mem = memory_usage()
    assert isinstance(mem, dict)
    assert "rss_mb" in mem
    assert mem["rss_mb"] > 0


def test_memory_usage_has_all_keys():
    mem = memory_usage()
    assert set(mem.keys()) >= {"rss_mb", "vms_mb", "percent"}


def test_timer_decorator(capsys):
    @timer
    def slow_function():
        time.sleep(0.1)
        return "done"
    assert slow_function() == "done"
    captured = capsys.readouterr()
    assert "выполнено за" in captured.out


def test_timer_decorator_returns_value():
    @timer
    def return_test():
        return 42
    assert return_test() == 42


def test_timer_context_manager(capsys):
    with Timer("Тест операции"):
        time.sleep(0.1)
    captured = capsys.readouterr()
    assert "Тест операции завершено за" in captured.out


def test_log_memory_usage_does_not_raise(capsys):
    log_memory_usage(message="Тест без логгера")
    captured = capsys.readouterr()
    assert "RSS" in captured.out or "Memory" in captured.out


# ====================== logging_utils.py ======================

def test_setup_logging(tmp_path):
    log_file = tmp_path / "test.log"

    # Сброс конфигурации логирования
    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)
    logging.getLogger().handlers.clear()

    setup_logging(str(log_file), level=logging.INFO)

    logger = logging.getLogger("test_logger")
    logger.info("Это тестовое сообщение из pytest")

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "Это тестовое сообщение из pytest" in content


def test_setup_logging_different_levels(tmp_path):
    log_file = tmp_path / "level_test.log"

    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)
    logging.getLogger().handlers.clear()

    setup_logging(str(log_file), level=logging.DEBUG)

    logger = logging.getLogger("debug_test")
    logger.debug("Debug сообщение")
    logger.info("Info сообщение")

    content = log_file.read_text(encoding="utf-8")
    assert "Debug сообщение" in content
    assert "Info сообщение" in content


def test_logging_after_multiple_setup_calls(tmp_path):
    log_file = tmp_path / "multi_setup.log"

    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)
    logging.getLogger().handlers.clear()

    setup_logging(str(log_file))
    setup_logging(str(log_file))   # повторный вызов

    logger = logging.getLogger("multi_test")
    logger.info("Сообщение после повторной настройки")

    content = log_file.read_text(encoding="utf-8")
    assert "Сообщение после повторной настройки" in content


def test_get_progress_bar():
    items = list(range(5))
    progress = get_progress_bar(items, desc="Тест", disable=True)
    assert list(progress) == items


def test_get_progress_bar_with_custom_params():
    items = [1, 2, 3, 4, 5]
    progress = get_progress_bar(items, desc="Custom", unit="item", disable=True)
    assert list(progress) == items