"""
Экстрактор текстового содержимого из HTML-файлов.

Использует **BeautifulSoup4** для парсинга HTML и извлечения
читаемого текста.  Нечитаемые теги (``<script>``, ``<style>``,
``<meta>``, ``<link>``) удаляются перед извлечением.

Что извлекается:
    - Заголовок страницы (``<title>``)
    - Мета-описание (``<meta name="description">``)
    - Весь видимый текст (``body``)
    - Альтернативный текст изображений (``alt``)
    - Текст ссылок (``<a>``)

Кодировка:
    Определяется автоматически: сначала из ``<meta charset>``,
    затем через ``chardet`` / ``charset-normalizer``, в крайнем
    случае — ``utf-8`` с заменой ошибочных байт.

Зависимости:
    - ``beautifulsoup4``
    - ``lxml`` (опционально, быстрый парсер) или встроенный ``html.parser``

Example::

    from extractors.html_extractor import HTMLExtractor

    result = HTMLExtractor("page.html").extract()
    print(result.metadata["title"])
    print(result.text[:500])
"""

from __future__ import annotations

import logging
from typing import Iterator

from extractors.base import BaseExtractor, ExtractionResult, ExtractionError


logger = logging.getLogger(__name__)

# Теги, содержимое которых не является читаемым контентом
_TAGS_TO_REMOVE: tuple[str, ...] = (
    "script", "style", "noscript", "meta", "link",
    "head", "svg", "canvas", "iframe",
)

# Предпочтительный парсер BeautifulSoup
_PREFERRED_PARSER = "lxml"
_FALLBACK_PARSER = "html.parser"


class HTMLExtractor(BaseExtractor):
    """Экстрактор текста из HTML-файлов.

    Args:
        file_path: Путь к ``.html`` / ``.htm`` файлу.
        extract_alt_text: Если ``True`` — включать ``alt``-тексты
            изображений в извлечённый текст.  По умолчанию ``True``.
        extract_link_text: Если ``True`` — включать тексты ссылок.
            По умолчанию ``True``.

    Raises:
        FileNotFoundError: Если файл не найден.
    """

    def __init__(
        self,
        file_path: str,
        extract_alt_text: bool = True,
        extract_link_text: bool = True,
    ) -> None:
        super().__init__(file_path)
        self._extract_alt_text = extract_alt_text
        self._extract_link_text = extract_link_text

    def extract(self) -> ExtractionResult:
        """Извлекает читаемый текст из HTML-файла.

        Returns:
            :class:`~extractors.base.ExtractionResult` с текстом и
            метаданными:

            - ``title`` — заголовок страницы (или ``None``)
            - ``description`` — мета-описание (или ``None``)
            - ``encoding`` — определённая кодировка файла
            - ``parser`` — использованный парсер (``"lxml"`` или
              ``"html.parser"``)

        Raises:
            ExtractionError: Если файл не удалось прочитать или
                BeautifulSoup не установлен.
        """
        start = self._log_start()

        raw_html, encoding = self._read_file()
        soup, parser = self._parse_html(raw_html)

        title = self._extract_title(soup)
        description = self._extract_meta_description(soup)

        for tag in soup.find_all(_TAGS_TO_REMOVE):
            tag.decompose()

        body_text = self._get_visible_text(soup)

        alt_texts: list[str] = []
        if self._extract_alt_text:
            alt_texts = [
                img.get("alt", "").strip()
                for img in soup.find_all("img")
                if img.get("alt", "").strip()
            ]

        parts: list[str] = []
        if title:
            parts.append(title)
        if description:
            parts.append(description)
        if body_text:
            parts.append(body_text)
        if alt_texts:
            parts.append("\n".join(alt_texts))

        full_text = "\n\n".join(parts)

        result = self._make_result(
            text=full_text,
            chunks=[full_text] if full_text else [],
            metadata={
                "title": title,
                "description": description,
                "encoding": encoding,
                "parser": parser,
            },
            start_time=start,
        )
        self._log_done(result)
        return result

    def extract_chunks(self) -> Iterator[str]:
        """Возвращает текст HTML как один чанк.

        HTML-документы обычно небольшие, поэтому разбиение на чанки
        не требуется.

        Yields:
            Полный извлечённый текст (если не пустой).
        """
        result = self.extract()
        if result.text.strip():
            yield result.text


    def _read_file(self) -> tuple[bytes, str]:
        """Читает HTML-файл и определяет кодировку.

        Сначала пробует ``utf-8``, затем — ``cp1251`` (типично для
        русскоязычных сайтов), затем — ``latin-1`` (никогда не даёт
        ошибки декодирования).

        Returns:
            Кортеж ``(raw_bytes, detected_encoding)``.

        Raises:
            ExtractionError: Если файл не удалось прочитать.
        """
        try:
            with open(self.file_path, "rb") as f:
                raw = f.read()
        except OSError as exc:
            raise ExtractionError(
                self.file_path, f"Не удалось прочитать файл: {exc}"
            ) from exc

        encoding = self._detect_encoding(raw)
        return raw, encoding

    @staticmethod
    def _detect_encoding(raw: bytes) -> str:
        """Определяет кодировку байтовых данных.

        Приоритет:
        1. ``chardet`` / ``charset-normalizer`` (если установлены)
        2. Эвристика по BOM-маркеру
        3. UTF-8 с обработкой ошибок

        Args:
            raw: Сырые байты файла.

        Returns:
            Название кодировки в формате Python (напр. ``"utf-8"``).
        """
        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"
        if raw.startswith(b"\xff\xfe"):
            return "utf-16-le"

        try:
            import chardet
            result = chardet.detect(raw[:8192])
            if result.get("confidence", 0) > 0.7 and result.get("encoding"):
                return result["encoding"]
        except ImportError:
            pass

        for enc in ("utf-8", "cp1251"):
            try:
                raw.decode(enc)
                return enc
            except UnicodeDecodeError:
                continue

        return "latin-1"

    def _parse_html(self, raw: bytes) -> tuple[object, str]:
        """Парсит HTML через BeautifulSoup.

        Сначала пробует ``lxml`` (быстрее), при недоступности — ``html.parser``.

        Args:
            raw: Сырые байты HTML-файла.

        Returns:
            Кортеж ``(BeautifulSoup_object, parser_name)``.

        Raises:
            ExtractionError: Если BeautifulSoup не установлен.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise ExtractionError(
                self.file_path,
                "Библиотека 'beautifulsoup4' не установлена. "
                "Выполните: pip install beautifulsoup4",
            ) from exc

        try:
            soup = BeautifulSoup(raw, _PREFERRED_PARSER)
            return soup, _PREFERRED_PARSER
        except Exception:
            soup = BeautifulSoup(raw, _FALLBACK_PARSER)
            return soup, _FALLBACK_PARSER

    @staticmethod
    def _extract_title(soup: object) -> str | None:
        """Извлекает заголовок страницы из тега ``<title>``.

        Args:
            soup: ``BeautifulSoup`` объект.

        Returns:
            Строка заголовка или ``None``.
        """
        tag = soup.find("title")
        if tag and tag.string:
            return tag.string.strip()
        return None

    @staticmethod
    def _extract_meta_description(soup: object) -> str | None:
        """Извлекает мета-описание из ``<meta name="description">``.

        Args:
            soup: ``BeautifulSoup`` объект.

        Returns:
            Строка описания или ``None``.
        """
        tag = soup.find("meta", attrs={"name": "description"})
        if tag and tag.get("content"):
            return tag["content"].strip()
        return None

    @staticmethod
    def _get_visible_text(soup: object) -> str:
        """Возвращает читаемый текст страницы без HTML-разметки.

        Использует ``get_text`` с разделителем новой строки,
        убирает множественные пустые строки.

        Args:
            soup: ``BeautifulSoup`` объект (после удаления нечитаемых тегов).

        Returns:
            Очищенная строка текста.
        """
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)