"""
Экстрактор метаданных и субтитров из видеофайлов.

Поддерживаемые форматы:
    ``.mp4`` (основной формат по условию задачи)

Что извлекается:
    1. **Метаданные контейнера** — продолжительность, разрешение,
       кодек, битрейт, количество потоков.  Используется
       ``ffprobe`` (часть FFmpeg).
    2. **Встроенные субтитры** — если видеофайл содержит дорожку
       субтитров, они извлекаются как текст через ``ffmpeg``.
    3. **Внешние субтитры** — если рядом с файлом лежит ``.srt`` /
       ``.vtt`` с тем же именем, они читаются напрямую.

Важно:
    OCR видеодорожки (распознавание текста с экрана) в данной
    реализации **не выполняется** — это выходит за рамки задачи.
    Если субтитры отсутствуют, результат содержит только метаданные.

Зависимости:
    - ``ffprobe`` / ``ffmpeg`` (системные утилиты) — для метаданных
      и извлечения субтитров.
    - ``json`` (стандартная библиотека)

Example::

    from extractors.video_extractor import VideoExtractor

    result = VideoExtractor("interview.mp4").extract()
    print(result.metadata["duration_sec"])
    print(result.text[:200])  # субтитры, если есть
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from typing import Iterator

from extractors.base import BaseExtractor, ExtractionResult, ExtractionError

logger = logging.getLogger(__name__)

_SUBTITLE_EXTENSIONS: tuple[str, ...] = (".srt", ".vtt", ".ass", ".ssa")


class VideoExtractor(BaseExtractor):
    """Экстрактор метаданных и субтитров из видеофайлов.

    Args:
        file_path: Путь к видеофайлу (``.mp4``).
        extract_subtitles: Если ``True`` — извлекать встроенные
            субтитры через ``ffmpeg``.  По умолчанию ``True``.
        ffprobe_path: Путь к исполняемому файлу ``ffprobe``.
            По умолчанию ищется в ``PATH``.
        ffmpeg_path: Путь к исполняемому файлу ``ffmpeg``.
            По умолчанию ищется в ``PATH``.

    Raises:
        FileNotFoundError: Если файл не найден.
    """

    def __init__(
        self,
        file_path: str,
        extract_subtitles: bool = True,
        ffprobe_path: str = "ffprobe",
        ffmpeg_path: str = "ffmpeg",
    ) -> None:
        super().__init__(file_path)
        self._extract_subtitles = extract_subtitles
        self._ffprobe = ffprobe_path
        self._ffmpeg = ffmpeg_path


    def extract(self) -> ExtractionResult:
        """Извлекает метаданные и субтитры из видеофайла.

        Returns:
            :class:`~extractors.base.ExtractionResult` с текстом
            субтитров (или пустой строкой) и метаданными:

            - ``duration_sec`` — длительность в секундах (``float``)
            - ``width``, ``height`` — разрешение видео
            - ``video_codec`` — кодек видеодорожки
            - ``audio_codec`` — кодек аудиодорожки
            - ``bit_rate`` — битрейт контейнера (бит/с)
            - ``has_embedded_subtitles`` — есть ли встроенные субтитры
            - ``subtitle_source`` — откуда взяты субтитры
              (``"embedded"``, ``"external"``, ``"none"``)
            - ``ffprobe_available`` — доступен ли ffprobe
        """
        start = self._log_start()

        # Метаданные через ffprobe
        metadata, ffprobe_ok = self._probe_metadata()
        metadata["ffprobe_available"] = ffprobe_ok

        text = ""
        subtitle_source = "none"

        if self._extract_subtitles:
            # Внешние субтитры (быстрее)
            external_text = self._read_external_subtitles()
            if external_text:
                text = external_text
                subtitle_source = "external"
            # Встроенные субтитры через ffmpeg
            elif ffprobe_ok and metadata.get("has_embedded_subtitles"):
                embedded_text = self._extract_embedded_subtitles()
                if embedded_text:
                    text = embedded_text
                    subtitle_source = "embedded"

        metadata["subtitle_source"] = subtitle_source

        result = self._make_result(
            text=text,
            chunks=[text] if text else [],
            metadata=metadata,
            error=(
                None
                if text or not self._extract_subtitles
                else "Субтитры не найдены"
            ),
            start_time=start,
        )
        self._log_done(result)
        return result

    def extract_chunks(self) -> Iterator[str]:
        """Возвращает текст субтитров как один чанк.

        Yields:
            Текст субтитров (если не пустой).
        """
        result = self.extract()
        if result.text.strip():
            yield result.text


    def _probe_metadata(self) -> tuple[dict, bool]:
        """Запускает ``ffprobe`` и парсит метаданные файла.

        Returns:
            Кортеж ``(metadata_dict, ffprobe_available_bool)``.
            Если ``ffprobe`` недоступен — возвращает базовые метаданные
            (размер файла) и ``False``.
        """
        if not shutil.which(self._ffprobe):
            self._logger.warning(
                "ffprobe не найден в PATH. Только базовые метаданные доступны."
            )
            return {"file_size_bytes": self.file_size_bytes}, False

        cmd = [
            self._ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            self.file_path,
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            data = json.loads(proc.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
            self._logger.warning("Ошибка ffprobe для '%s': %s", self.file_path, exc)
            return {"file_size_bytes": self.file_size_bytes}, False

        return self._parse_ffprobe_output(data), True

    @staticmethod
    def _parse_ffprobe_output(data: dict) -> dict:
        """Извлекает нужные поля из вывода ffprobe.

        Args:
            data: Словарь, распарсенный из JSON-вывода ``ffprobe``.

        Returns:
            Нормализованный словарь метаданных.
        """
        meta: dict = {}

        fmt = data.get("format", {})
        meta["duration_sec"] = float(fmt.get("duration", 0) or 0)
        meta["bit_rate"] = int(fmt.get("bit_rate", 0) or 0)
        meta["format_name"] = fmt.get("format_name", "unknown")

        has_subtitles = False
        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type", "")
            if codec_type == "video":
                meta["width"] = stream.get("width")
                meta["height"] = stream.get("height")
                meta["video_codec"] = stream.get("codec_name")
                meta["fps"] = stream.get("r_frame_rate", "")
            elif codec_type == "audio":
                meta["audio_codec"] = stream.get("codec_name")
                meta["audio_channels"] = stream.get("channels")
                meta["audio_sample_rate"] = stream.get("sample_rate")
            elif codec_type == "subtitle":
                has_subtitles = True

        meta["has_embedded_subtitles"] = has_subtitles
        return meta

    def _read_external_subtitles(self) -> str:
        """Ищет и читает внешний файл субтитров.

        Проверяет наличие файла с тем же именем, но с расширениями
        ``.srt``, ``.vtt``, ``.ass``, ``.ssa``.

        Returns:
            Очищенный текст субтитров или пустая строка.
        """
        base = os.path.splitext(self.file_path)[0]
        for ext in _SUBTITLE_EXTENSIONS:
            sub_path = base + ext
            if os.path.isfile(sub_path):
                self._logger.debug("Найден внешний файл субтитров: %s", sub_path)
                try:
                    with open(sub_path, encoding="utf-8", errors="replace") as f:
                        raw = f.read()
                    return self._clean_subtitle_text(raw, ext)
                except OSError as exc:
                    self._logger.warning(
                        "Не удалось прочитать субтитры '%s': %s", sub_path, exc
                    )
        return ""

    def _extract_embedded_subtitles(self) -> str:
        """Извлекает встроенные субтитры через ``ffmpeg``.

        Использует ``ffmpeg`` для экспорта первой дорожки субтитров
        в формат SRT во временный буфер.

        Returns:
            Очищенный текст субтитров или пустая строка.
        """
        if not shutil.which(self._ffmpeg):
            self._logger.warning("ffmpeg не найден в PATH, пропускаем субтитры")
            return ""

        cmd = [
            self._ffmpeg,
            "-v", "quiet",
            "-i", self.file_path,
            "-map", "0:s:0",    # первая дорожка субтитров
            "-f", "srt",
            "pipe:1",            # вывод в stdout
        ]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                timeout=60,
            )
            raw = proc.stdout.decode("utf-8", errors="replace")
            return self._clean_subtitle_text(raw, ".srt")
        except (subprocess.TimeoutExpired, OSError) as exc:
            self._logger.warning(
                "Ошибка извлечения субтитров из '%s': %s", self.file_path, exc
            )
            return ""

    @staticmethod
    def _clean_subtitle_text(raw: str, ext: str) -> str:
        """Очищает текст субтитров от тайм-кодов и тегов.

        Удаляет:
        - Тайм-коды SRT/VTT (``00:00:01,000 --> 00:00:03,000``)
        - Порядковые номера строк SRT
        - HTML-теги (``<i>``, ``<b>`` и т.п.)
        - Пустые строки

        Args:
            raw: Сырой текст субтитров.
            ext: Расширение формата субтитров (для специфичной обработки).

        Returns:
            Чистый текст без разметки.
        """
        raw = re.sub(
            r"\d{1,2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[,\.]\d{3}",
            "",
            raw,
        )
        # Порядковые номера (строки, содержащие только цифры)
        raw = re.sub(r"^\d+\s*$", "", raw, flags=re.MULTILINE)
        # HTML-теги
        raw = re.sub(r"<[^>]+>", "", raw)
        # VTT-заголовок
        raw = re.sub(r"^WEBVTT.*$", "", raw, flags=re.MULTILINE)
        # Множественные пустые строки → одна
        raw = re.sub(r"\n{3,}", "\n\n", raw)

        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        return "\n".join(lines)