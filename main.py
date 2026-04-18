# main.py
"""
Точка входа (CLI) для решения хакатона
Полный пайплайн: сканирование → извлечение → обнаружение ПДн → классификация УЗ → отчёт
"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from tqdm import tqdm

from scanner import FileScanner
from extractors import get_extractor
from detectors import PIIDetector
from classifiers import UZClassifier
from report import ReportGenerator


def parse_args():
    parser = argparse.ArgumentParser(
        description="Автоматическое обнаружение персональных данных (152-ФЗ)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dir",
        default=".",  # По умолчанию текущая папка (можно указать ../ПДнDataset)
        help="Путь к папке для сканирования",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=["csv", "json", "md"],
        default=["csv", "json", "md"],
        help="Форматы отчётов",
    )
    parser.add_argument(
        "--output-dir",
        default="output/reports",
        help="Папка для сохранения отчётов",
    )
    return parser.parse_args()


def main():
    start_time = time.perf_counter()
    args = parse_args()

    target_dir = Path(args.dir).resolve()
    print("=== ЗАПУСК СКАНИРОВАНИЯ ФАЙЛОВОГО ХРАНИЛИЩА ===")
    print(f"Целевая директория: {target_dir}")

    try:
        scanner = FileScanner(root_dir=str(target_dir))
        file_paths = scanner.scan()
    except Exception as e:
        print(f"❌ Ошибка сканирования: {e}")
        sys.exit(1)

    print(f"Найдено файлов для анализа: {len(file_paths)}")

    detector = PIIDetector()
    classifier = UZClassifier()
    results = []
    errors_count = 0

    print("=== ОБРАБОТКА ФАЙЛОВ ===")

    for path_str in tqdm(file_paths, desc="Обработка", unit="файл"):
        path = Path(path_str)

        try:
            extractor = get_extractor(str(path))
            if extractor is None:
                continue

            extraction = extractor.extract()
            text = getattr(extraction, "text", str(extraction))

            # Основное обнаружение ПДн
            detection = detector.detect_all_pii(text, str(path))

            # Надёжное получение категорий и количества (работает и с set, и с dict, и с findings)
            if hasattr(detection, "findings") and detection.findings:
                findings_counter = Counter(
                    f.pattern_name for f in detection.findings
                    if hasattr(f, "pattern_name")
                )
                pii_categories = dict(findings_counter)
                pii_count = len(detection.findings)
            elif hasattr(detection, "categories_found") and detection.categories_found:
                cats = detection.categories_found
                if isinstance(cats, (set, list)):
                    pii_categories = {cat: 1 for cat in cats}
                elif isinstance(cats, dict):
                    pii_categories = cats
                else:
                    pii_categories = {}
                pii_count = sum(pii_categories.values()) if pii_categories else 0
            else:
                pii_categories = {}
                pii_count = 0

            # Классификация уровня защищённости
            uz_level = (
                classifier.classify(pii_categories)
                if pii_count > 0
                else "УЗ-4"
            )

            results.append({
                "path": str(path),
                "file_format": path.suffix[1:].lower(),
                "pii_categories": pii_categories,
                "total_findings": pii_count,
                "uz_level": uz_level,
            })

        except Exception as e:
            errors_count += 1
            err_str = str(e)
            # Пропускаем ожидаемые «безобидные» ошибки
            if any(skip in err_str for skip in [
                "Текстовый слой не найден", "Package not found",
                "Failed to open", "No text layer", "OCR failed"
            ]):
                continue
            print(f"⚠️  Ошибка обработки {path.name}: {err_str}", file=sys.stderr)
            continue

    # Этап 5: Формирование отчётов
    print(f"\n=== ГЕНЕРАЦИЯ ОТЧЁТОВ ({len(results)} записей, ошибок: {errors_count}) ===")
    saved = ReportGenerator.generate(
        results=results,
        output_dir=args.output_dir,
        formats=args.formats,
    )

    elapsed = time.perf_counter() - start_time
    print("\n=== ГОТОВО ===")
    print(f"Успешно обработано: {len(results)} файлов")
    print(f"Пропущено ошибок: {errors_count}")
    print(f"Время выполнения: {elapsed:.1f} сек ({elapsed/60:.1f} мин)")
    print(f"Отчёты сохранены в: {Path(args.output_dir).resolve()}")
    for fmt, path in saved.items():
        print(f"   • {fmt.upper():4} → {Path(path).name}")


if __name__ == "__main__":
    main()