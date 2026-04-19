"""
Экстрактор текста из изображений (OCR) — усиленная версия 2026
Поддерживаемые форматы: .jpg, .jpeg, .png, .tif, .tiff, .gif

Стратегия (от быстрого к мощному):
1. Tesseract + разные PSM + предобработка
2. EasyOCR (с улучшенными параметрами)
3. PaddleOCR (самый точный на сложных скриншотах сайтов)

Предобработка: OpenCV (CLAHE, adaptive threshold, Otsu, sharpening, upscale).
"""

from __future__ import annotations
import logging
from typing import Iterator, Tuple
from pathlib import Path

import numpy as np
from PIL import Image

from extractors.base import BaseExtractor, ExtractionResult, ExtractionError

logger = logging.getLogger(__name__)

_DEFAULT_TESSERACT_LANG = "rus+eng"


class ImageExtractor(BaseExtractor):
    """Улучшенный экстрактор для сложных изображений с сайтов."""

    def __init__(
        self,
        file_path: str,
        use_easyocr: bool = False,
        easyocr_fallback: bool = True,
        paddle_fallback: bool = True,      # Новый параметр
        preprocess: bool = True,
        tesseract_lang: str = _DEFAULT_TESSERACT_LANG,
        max_ocr_attempts: int = 5,         # Максимум попыток предобработки
    ) -> None:
        super().__init__(file_path)
        self._use_easyocr = use_easyocr
        self._easyocr_fallback = easyocr_fallback
        self._paddle_fallback = paddle_fallback
        self._preprocess = preprocess
        self._tesseract_lang = tesseract_lang
        self._max_ocr_attempts = max_ocr_attempts

    def extract(self) -> ExtractionResult:
        start = self._log_start()
        pil_image = self._load_image()

        image_meta = {
            "image_size": pil_image.size,
            "image_mode": pil_image.mode,
            "preprocessed": self._preprocess,
            "attempts_made": 0,
            "ocr_backend": None,
        }

        text = ""
        backend = "none"

        # Первая попытка (быстрая)
        if self._use_easyocr:
            text, backend = self._run_easyocr(pil_image)
        else:
            text, backend = self._run_tesseract(pil_image, attempt=0)

        image_meta["attempts_made"] = 1

        # Если пусто — многоуровневый fallback с предобработкой
        if not text.strip() and self._preprocess:
            logger.info(f"Tesseract/EasyOCR вернул пустой результат → запускаем усиленную предобработку для {Path(self.file_path).name}")

            for attempt in range(self._max_ocr_attempts):
                try:
                    processed = self._preprocess_image_advanced(pil_image, attempt)

                    # Пробуем Tesseract с разными PSM
                    text, backend = self._run_tesseract(processed, attempt=attempt)
                    if text.strip():
                        logger.info(f"Успех на попытке {attempt+1} (Tesseract)")
                        image_meta["attempts_made"] = attempt + 2
                        break

                    # EasyOCR как промежуточный fallback
                    if not text.strip() and self._easyocr_fallback:
                        text, backend = self._run_easyocr(processed)
                        if text.strip():
                            logger.info(f"Успех на попытке {attempt+1} (EasyOCR)")
                            image_meta["attempts_made"] = attempt + 2
                            break

                    # PaddleOCR как последний и самый мощный уровень
                    if not text.strip() and self._paddle_fallback:
                        text, backend = self._run_paddleocr(processed)
                        if text.strip():
                            logger.info(f"Успех на попытке {attempt+1} (PaddleOCR — лучший результат)")
                            image_meta["attempts_made"] = attempt + 2
                            break

                except Exception as e:
                    logger.debug(f"Попытка {attempt+1} упала: {e}")

        image_meta["ocr_backend"] = backend

        error = "OCR не смог извлечь текст" if not text.strip() else None

        result = self._make_result(
            text=text,
            chunks=[text] if text.strip() else [],
            metadata=image_meta,
            error=error,
            start_time=start,
        )
        self._log_done(result)
        return result

    def _load_image(self) -> Image.Image:
        """Загружает изображение. Даже если файл повреждён — бросаем понятную ошибку."""
        try:
            from PIL import Image, UnidentifiedImageError
            image = Image.open(self.file_path)
            image.load() 
            if hasattr(image, "n_frames") and image.n_frames > 1:
                image.seek(0)
            return image.convert("RGB")
        except UnidentifiedImageError as exc:
            raise ExtractionError(
                self.file_path, 
                f"Повреждённое или невалидное изображение: cannot identify image file"
            ) from exc
        except Exception as exc:
            raise ExtractionError(
                self.file_path, f"Не удалось открыть изображение: {exc}"
            ) from exc

    @staticmethod
    def _preprocess_image_advanced(pil_image: Image.Image, attempt: int = 0) -> Image.Image:
        """Улучшенная предобработка через OpenCV."""
        try:
            import cv2
            img = np.array(pil_image)
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

            variants = []

            # Вариант 0: CLAHE + sharpening
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
            sharpened = cv2.filter2D(enhanced, -1, kernel)
            _, bin_img = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(bin_img)

            # Вариант 1: Adaptive Threshold
            adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                             cv2.THRESH_BINARY, 11, 2)
            variants.append(adaptive)

            # Вариант 2: Инверсия + Otsu
            _, otsu_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            variants.append(otsu_inv)

            # Вариант 3+: Upscale для мелкого текста
            if attempt >= 2 or gray.shape[0] < 700:
                scale = 2.0
                scaled = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                _, bin_scaled = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                variants.append(bin_scaled)

            processed = variants[attempt % len(variants)]
            return Image.fromarray(processed)

        except ImportError:
            logger.warning("OpenCV не установлен → используем простую предобработку Pillow")
            return ImageExtractor._preprocess_image(pil_image)
        except Exception:
            return pil_image

    @staticmethod
    def _preprocess_image(image: Image.Image) -> Image.Image:
        """Оригинальная простая предобработка Pillow (fallback)."""
        from PIL import ImageOps, ImageFilter
        gray = image.convert("L")
        enhanced = ImageOps.autocontrast(gray, cutoff=2)
        enhanced = enhanced.filter(ImageFilter.MedianFilter(size=3))
        return enhanced

    def _run_tesseract(self, image: Image.Image, attempt: int = 0) -> Tuple[str, str]:
        try:
            import pytesseract
        except ImportError:
            logger.warning("pytesseract не установлен")
            return "", "tesseract_unavailable"

        psm_list = [6, 3, 11, 12, 7]   # 6 — блок текста, 11/12 — sparse text (идеально для сайтов)
        psm = psm_list[attempt % len(psm_list)]
        config = f"--oem 3 --psm {psm} -l {self._tesseract_lang}"

        try:
            text = pytesseract.image_to_string(image, config=config)
            return text.strip(), "tesseract"
        except Exception as exc:
            logger.warning(f"Tesseract ошибка (attempt {attempt}): {exc}")
            return "", "tesseract"

    def _run_easyocr(self, image: Image.Image) -> Tuple[str, str]:
        try:
            import easyocr
        except ImportError:
            logger.warning("easyocr не установлен. pip install easyocr")
            return "", "easyocr_unavailable"

        try:
            img_array = np.array(image)
            reader = easyocr.Reader(["ru", "en"], gpu=False, verbose=False)
            results = reader.readtext(
                img_array,
                detail=0,
                paragraph=True,
                low_text=0.3,
                text_threshold=0.6,
                width_ths=0.7
            )
            text = "\n".join(str(r) for r in results if r)
            return text.strip(), "easyocr"
        except Exception as exc:
            logger.warning(f"EasyOCR ошибка: {exc}")
            return "", "easyocr"

    def _run_paddleocr(self, image: Image.Image) -> Tuple[str, str]:
        """Самый мощный бэкенд — PaddleOCR (обновлённая версия без use_gpu)."""
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            logger.warning("paddleocr не установлен.")
            return "", "paddleocr_unavailable"

        try:
            ocr = PaddleOCR(
                use_angle_cls=True,
                lang="ru",
                use_gpu=False,   
                show_log=False,
                det_db_thresh=0.3,
                det_db_box_thresh=0.5,
                # device="cpu"
            )

            img_array = np.array(image)
            result = ocr.ocr(img_array, cls=True)

            if not result or not result[0]:
                return "", "paddleocr"

            text_lines = [line[1][0] for line in result[0] if line[1][1] > 0.5]
            text = "\n".join(text_lines)
            return text.strip(), "paddleocr"

        except Exception as exc:
            logger.warning(f"PaddleOCR ошибка для '{self.file_path}': {exc}")
            return "", "paddleocr"

    def extract_chunks(self) -> Iterator[str]:
        result = self.extract()
        if result.text.strip():
            yield result.text