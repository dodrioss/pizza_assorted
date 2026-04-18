"""
Экстрактор текста из изображений (OCR).

Поддерживаемые форматы:
    ``.jpg``, ``.jpeg``, ``.png``, ``.tif``, ``.tiff``, ``.gif``

Стратегия OCR:
    1. **Tesseract** (основной бэкенд) — быстрый, работает офлайн,
       поддерживает русский + английский языки.
    2. **EasyOCR** (опциональный резервный бэкенд) — более точный на
       низкокачественных сканах, но значительно медленнее и требует
       дополнительной установки.  Включается параметром
       ``use_easyocr=True`` или автоматически, если Tesseract вернул
       пустой результат.

Предобработка изображений:
    Перед OCR выполняется лёгкая предобработка для улучшения качества:
    конвертация в градации серого, повышение контраста (CLAHE),
    пороговая бинаризация (Otsu).  Предобработка отключается параметром
    ``preprocess=False``.

Зависимости:
    - ``pytesseract`` + системный ``tesseract-ocr``
    - ``Pillow``
    - ``easyocr`` (опционально)

Example::

    from extractors.image_extractor import ImageExtractor

    result = ImageExtractor("scan.png").extract()
    print(result.metadata["ocr_backend"])
    print(result.text)
"""

from __future__ import annotations

import logging
from typing import Iterator

from extractors.base import BaseExtractor, ExtractionResult, ExtractionError

logger = logging.getLogger(__name__)

# Языки Tesseract по умолчанию (rus + eng)
_DEFAULT_TESSERACT_LANG = "rus+eng"

# Конфигурация Tesseract: страничная сегментация (PSM 3 — авто)
_TESSERACT_CONFIG = "--oem 3 --psm 3"


class ImageExtractor(BaseExtractor):
    """Экстрактор текста из изображений с поддержкой OCR.

    Args:
        file_path: Путь к файлу изображения.
        use_easyocr: Если ``True`` — использовать EasyOCR как основной
            бэкенд (медленнее, но точнее).  По умолчанию ``False``.
        easyocr_fallback: Если ``True`` (по умолчанию) — при пустом
            результате Tesseract автоматически пробует EasyOCR.
        preprocess: Выполнять ли предобработку изображения перед OCR.
            По умолчанию ``True``.
        tesseract_lang: Строка языков Tesseract.
            По умолчанию ``"rus+eng"``.

    Raises:
        FileNotFoundError: Если файл не найден.
    """

    def __init__(
        self,
        file_path: str,
        use_easyocr: bool = False,
        easyocr_fallback: bool = True,
        preprocess: bool = True,
        tesseract_lang: str = _DEFAULT_TESSERACT_LANG,
    ) -> None:
        super().__init__(file_path)
        self._use_easyocr = use_easyocr
        self._easyocr_fallback = easyocr_fallback
        self._preprocess = preprocess
        self._tesseract_lang = tesseract_lang


    def extract(self) -> ExtractionResult:
        """Извлекает текст из изображения через OCR.

        Returns:
            :class:`~extractors.base.ExtractionResult` с текстом и
            метаданными:

            - ``ocr_backend`` — использованный бэкенд (``"tesseract"``
              или ``"easyocr"``)
            - ``image_size`` — размер изображения ``(ширина, высота)``
            - ``image_mode`` — режим изображения (``"RGB"``, ``"L"`` и т.п.)
            - ``preprocessed`` — выполнялась ли предобработка

        Raises:
            ExtractionError: Если не удалось открыть изображение или
                OCR полностью недоступен.
        """
        start = self._log_start()

        image = self._load_image()
        image_meta = {
            "image_size": image.size,
            "image_mode": image.mode,
            "preprocessed": self._preprocess,
        }

        if self._preprocess:
            image = self._preprocess_image(image)

        if self._use_easyocr:
            text, backend = self._run_easyocr(image)
        else:
            text, backend = self._run_tesseract(image)
            if not text.strip() and self._easyocr_fallback:
                self._logger.info(
                    "Tesseract вернул пустой результат для '%s', пробуем EasyOCR",
                    self.file_path,
                )
                text, backend = self._run_easyocr(image)

        image_meta["ocr_backend"] = backend

        result = self._make_result(
            text=text,
            chunks=[text] if text else [],
            metadata=image_meta,
            error=None if text.strip() else "OCR не смог извлечь текст",
            start_time=start,
        )
        self._log_done(result)
        return result

    def extract_chunks(self) -> Iterator[str]:
        """Возвращает один чанк — весь текст изображения.

        Изображение не разбивается на части (один файл — один чанк).

        Yields:
            Текст, извлечённый из изображения (если не пустой).
        """
        result = self.extract()
        if result.text.strip():
            yield result.text


    def _load_image(self) -> object:
        """Загружает изображение с помощью Pillow.

        Returns:
            Объект ``PIL.Image.Image``.

        Raises:
            ExtractionError: Если Pillow не установлен или файл
                не является изображением.
        """
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:
            raise ExtractionError(
                self.file_path,
                "Библиотека 'Pillow' не установлена. "
                "Выполните: pip install Pillow",
            ) from exc

        try:
            image = Image.open(self.file_path)
            image.load()  # принудительная загрузка (для GIF и TIFF)
            if hasattr(image, "n_frames") and image.n_frames > 1:
                image.seek(0)
            return image.convert("RGB")
        except Exception as exc:
            raise ExtractionError(
                self.file_path, f"Не удалось открыть изображение: {exc}"
            ) from exc

    @staticmethod
    def _preprocess_image(image: object) -> object:
        """Предобрабатывает изображение для улучшения качества OCR.

        Шаги предобработки:
        1. Конвертация в градации серого (``L``).
        2. Повышение контраста через ``ImageOps.autocontrast``.
        3. Пороговая бинаризация (адаптивный метод через ``ImageFilter``).

        Args:
            image: ``PIL.Image.Image`` в режиме ``RGB``.

        Returns:
            Предобработанное изображение ``PIL.Image.Image``.
        """
        from PIL import ImageOps, ImageFilter

        # Градации серого
        gray = image.convert("L")
        # Автоконтраст
        enhanced = ImageOps.autocontrast(gray, cutoff=2)
        # Сглаживание шума
        enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
        return enhanced

    def _run_tesseract(self, image: object) -> tuple[str, str]:
        """Выполняет OCR через Tesseract.

        Args:
            image: ``PIL.Image.Image`` для распознавания.

        Returns:
            Кортеж ``(extracted_text, "tesseract")``.
            При ошибке возвращает ``("", "tesseract")``.
        """
        try:
            import pytesseract
        except ImportError:
            self._logger.warning("pytesseract не установлен, пропускаем Tesseract OCR")
            return "", "tesseract_unavailable"

        try:
            text = pytesseract.image_to_string(
                image,
                lang=self._tesseract_lang,
                config=_TESSERACT_CONFIG,
            )
            return text.strip(), "tesseract"
        except Exception as exc:
            self._logger.warning(
                "Ошибка Tesseract OCR для '%s': %s", self.file_path, exc
            )
            return "", "tesseract"

    def _run_easyocr(self, image: object) -> tuple[str, str]:
        """Выполняет OCR через EasyOCR.

        EasyOCR загружает нейронные модели при первом вызове —
        это занимает несколько секунд.

        Args:
            image: ``PIL.Image.Image`` для распознавания.

        Returns:
            Кортеж ``(extracted_text, "easyocr")``.
            При ошибке возвращает ``("", "easyocr_unavailable")``.
        """
        try:
            import easyocr
            import numpy as np
        except ImportError:
            self._logger.warning(
                "easyocr не установлен. Выполните: pip install easyocr"
            )
            return "", "easyocr_unavailable"

        try:
            import numpy as np

            img_array = np.array(image)
            reader = easyocr.Reader(["ru", "en"], gpu=False, verbose=False)
            results = reader.readtext(img_array, detail=0, paragraph=True)
            text = "\n".join(str(r) for r in results if r)
            return text.strip(), "easyocr"
        except Exception as exc:
            self._logger.warning(
                "Ошибка EasyOCR для '%s': %s", self.file_path, exc
            )
            return "", "easyocr"