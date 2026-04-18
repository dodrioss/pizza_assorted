# pizza_assorted

```
pii_scanner/
├── main.py                          # ← Точка входа (CLI)
├── config.py                        # Константы, пути, параметры, regex-флаги
├── requirements.txt
├── README.md
├── .gitignore
├── run.bat                          # (опционально) для Windows
├── scanner/                         # ← Этап 1
│   ├── __init__.py
│   └── file_scanner.py              # os.walk + предфильтрация (только по расширению)
├── extractors/                      # ← Этап 2
│   ├── __init__.py
│   ├── base.py                      # Абстрактный базовый класс Extractor
│   ├── pdf_extractor.py             # PyMuPDF + pdfplumber (chunk для больших PDF)
│   ├── docx_extractor.py            # python-docx
│   ├── csv_parquet_extractor.py     # pandas / pyarrow (chunked reading для больших файлов)
│   ├── image_extractor.py           # Tesseract OCR + EasyOCR (опционально)
│   ├── html_extractor.py            # BeautifulSoup
│   └── video_extractor.py           # Метаданные + субтитры (если нужно)
├── detectors/                       # ← Этап 3
│   ├── __init__.py
│   ├── regex_patterns.py            # Все regex + ключевые слова
│   ├── validators.py                # Алгоритм Луна, checksum СНИЛС/ИНН/паспорт
│   └── pii_detector.py              # Основной класс: detect_all_pii(text, path)
├── classifiers/                     # ← Этап 4
│   ├── __init__.py
│   └── uz_classifier.py             # Логика УЗ-1…УЗ-4 по правилам 152-ФЗ
├── report/                          # ← Этап 5
│   ├── __init__.py
│   └── generators.py                # CSV, JSON, Markdown + визуализация
├── utils/                           # ← Этап 6 + общие утилиты
│   ├── __init__.py
│   ├── text_utils.py                # quick_skip_after_extraction + очистка текста
│   ├── file_utils.py                # MIME, расширение, безопасное чтение
│   ├── logging_utils.py             # tqdm + logging + ошибки
│   └── performance.py               # таймеры, память, chunking
├── tests/                           # (по желанию, для хакатона можно оставить пустым)
│   └── test_detector.py
└── output/                          # Создаётся автоматически
    └── reports/                     # .csv / .json / .md
```

