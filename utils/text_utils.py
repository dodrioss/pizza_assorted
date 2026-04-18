"""
Утилиты для очистки и предобработки текста перед детекцией ПДн.
"""

import re
from typing import Optional


def clean_text(text: str) -> str:
    """
    Основная очистка текста:
    - Удаление лишних пробелов и табуляций
    - Нормализация переносов строк
    - Удаление специальных символов, которые мешают regex
    - Приведение к нижнему регистру опционально (лучше не делать здесь)
    """
    if not text:
        return ""

    text = re.sub(r'\s+', ' ', text)

    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

    text = text.replace('«', '"').replace('»', '"').replace('–', '-').replace('—', '-')

    return text.strip()


def quick_skip_text(text: str, min_chars: int = 20) -> bool:
    """
    Быстрая проверка — стоит ли вообще запускать тяжёлый детектор ПДн.
    Возвращает True, если текст слишком короткий или выглядит как мусор.
    """
    if not text or len(text.strip()) < min_chars:
        return True

    letters = sum(1 for c in text if c.isalpha())
    if letters < 5:
        return True

    return False


def normalize_phone_for_detection(text: str) -> str:
    """Нормализует телефоны для лучшего срабатывания regex (убирает скобки, дефисы и т.д.)"""
    return re.sub(r'[\s\-\(\)\+]', '', text)


def remove_html_tags(text: str) -> str:
    """Простое удаление HTML-тегов (если BeautifulSoup не использовался)"""
    return re.sub(r'<[^>]+>', ' ', text)