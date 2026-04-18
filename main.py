"""
Точка входа (CLI) — параллельная обработка файлов + цветной вывод
"""

import argparse
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

from utils.logging_utils import setup_logging
from utils.text_utils import clean_text, quick_skip_text
from utils.performance import log_memory_usage
from utils.parallel import process_files_parallel, get_worker_info, optimal_workers

from scanner import FileScanner
from extractors import get_extractor
from detectors import PIIDetector
from classifiers import UZClassifier
from report import ReportGenerator

import logging
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

console = Console()
logger = logging.getLogger(__name__)

_detector: PIIDetector | None = None
_classifier: UZClassifier | None = None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Автоматическое обнаружение персональных данных (152-ФЗ)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dir", default=".", help="Путь к папке для сканирования")
    parser.add_argument("--formats", nargs="+", choices=["csv", "json", "md"], default=["csv"])
    parser.add_argument("--output-dir", default="output/reports")
    parser.add_argument("--log", default="pdn_scanner.log")

    parser.add_argument("--max-ocr-attempts", type=int, default=5)
    parser.add_argument("--paddle-fallback", action="store_true")
    parser.add_argument("--aggressive-ocr", action="store_true")
    parser.add_argument("--no-skip", action="store_true")

    parser.add_argument(
        "--workers", type=int, default=None,
        help="Число потоков (по умолчанию: авто, cpu*4 для I/O). "
             "Можно задать через PDN_WORKERS."
    )

    return parser.parse_args()


def build_process_fn(args):
    """
    Замыкание: возвращает потокобезопасную функцию обработки одного файла.
    Все объекты внутри — read-only (детектор, классификатор, args).
    """
    detector = _detector
    classifier = _classifier

    def process_file(path_str: str) -> dict | None:
        path = Path(path_str)
        try:
            extractor = get_extractor(
                str(path),
                extra_kwargs={
                    "max_ocr_attempts": args.max_ocr_attempts,
                    "paddle_fallback": args.paddle_fallback,
                }
            )
            if extractor is None:
                return None

            extraction = extractor.extract()
            text = clean_text(getattr(extraction, "text", ""))

            if not args.no_skip and quick_skip_text(text, min_chars=30):
                return None

            detection = detector.detect_all_pii(text, str(path))

            if hasattr(detection, "findings") and detection.findings:
                findings_counter = Counter(
                    f.pattern_name for f in detection.findings if hasattr(f, "pattern_name")
                )
                pii_categories = dict(findings_counter)
                pii_count = len(detection.findings)
            else:
                pii_categories = {}
                pii_count = 0

            uz_level = classifier.classify(pii_categories) if pii_count > 0 else "УЗ-4"

            return {
                "path": str(path),
                "file_format": path.suffix[1:].lower(),
                "pii_categories": pii_categories,
                "total_findings": pii_count,
                "uz_level": uz_level,
            }

        except Exception as e:
            err_str = str(e).lower()
            err_full = str(e)

            if any(kw in err_str for kw in [
                "не удалось открыть изображение",
                "unidentifiedimageerror",
                "cannot identify image file"
            ]):
                console.print(f"[yellow]Повреждённое изображение[/yellow] → {path.name}")
                return {
                    "path": str(path),
                    "file_format": path.suffix[1:].lower(),
                    "pii_categories": {},
                    "total_findings": 0,
                    "uz_level": "УЗ-4",
                    "ocr_failed": True,
                    "error": "Повреждённое изображение"
                }

            elif any(kw in err_str for kw in [
                "ocr не смог", "ocr failed", "tesseract вернул пустой",
                "easyocr", "paddleocr"
            ]):
                console.print(f"[bold red]OCR fail →[/bold red] {path.name}")
                return {
                    "path": str(path),
                    "file_format": path.suffix[1:].lower(),
                    "pii_categories": {},
                    "total_findings": 0,
                    "uz_level": "УЗ-4",
                    "ocr_failed": True,
                    "error": "OCR не смог извлечь текст"
                }

            else:
                console.print(f"[bold red]Критическая ошибка[/bold red] → {path.name}")
                logger.error(f"Ошибка обработки файла {path}", exc_info=True)
                return {
                    "path": str(path),
                    "file_format": path.suffix[1:].lower(),
                    "pii_categories": {},
                    "total_findings": 0,
                    "uz_level": "УЗ-4",
                    "error": f"Критическая ошибка: {err_full[:200]}"
                }

    return process_file


def main():
    global _detector, _classifier

    start_time = time.perf_counter()
    args = parse_args()

    setup_logging(log_file=args.log, level=20)

    target_dir = Path(args.dir).resolve()

    console.print("\n[bold cyan]=== ЗАПУСК СКАНИРОВАНИЯ ===[/bold cyan]")
    console.print(f"Директория: [blue]{target_dir}[/blue]")

    if args.aggressive_ocr:
        args.paddle_fallback = True
        if args.max_ocr_attempts < 6:
            args.max_ocr_attempts = 6
        console.print("⚡ [bold yellow]Агрессивный режим OCR включён[/bold yellow]")

    n_workers = args.workers if args.workers is not None else optimal_workers("io")
    worker_info = get_worker_info()
    console.print(
        f"Потоки: [bold green]{n_workers}[/bold green] "
        f"[dim](CPU: {worker_info['cpu_count']}, "
        f"авто I/O: {worker_info['io_workers']})[/dim]"
    )
    if worker_info["env_override"]:
        console.print(f"[dim]  ↳ задано через PDN_WORKERS={worker_info['env_override']}[/dim]")

    try:
        file_paths = FileScanner(root_dir=str(target_dir)).scan()
    except Exception as e:
        console.print(f"[bold red]Ошибка сканирования: {e}[/bold red]")
        sys.exit(1)

    console.print(f"Найдено файлов: [bold]{len(file_paths)}[/bold]")

    _detector = PIIDetector()
    _classifier = UZClassifier()

    process_fn = build_process_fn(args)

    console.print("\n[bold cyan]=== ОБРАБОТКА ФАЙЛОВ ===[/bold cyan]")

    with Progress(
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task(
            f"[green]Обработка файлов ({n_workers} потоков)...",
            total=len(file_paths)
        )

        results, errors_count = process_files_parallel(
            file_paths,
            process_fn,
            workers=n_workers,
            progress=progress,
            task_id=task,
            console=console,
        )

    ocr_failed_count = sum(1 for r in results if r.get("ocr_failed"))

    log_memory_usage(message="Перед генерацией отчётов")

    saved = {}
    try:
        saved = ReportGenerator.generate(
            results=results,
            output_dir=args.output_dir,
            formats=args.formats
        )
    except Exception as e:
        console.print(f"[bold red]Ошибка генерации отчётов: {e}[/bold red]")

    log_memory_usage(message="Финальное потребление памяти")

    elapsed = time.perf_counter() - start_time

    console.print("\n[bold cyan]=== ГОТОВО ===[/bold cyan]")
    console.print(f"Обработано файлов: [bold green]{len(results)}[/bold green]")
    if errors_count:
        console.print(f"Ошибок (thread-level): [bold red]{errors_count}[/bold red]")
    if ocr_failed_count:
        console.print(f"OCR полностью провалился: [bold red]{ocr_failed_count}[/bold red]")
    console.print(f"Время выполнения: [bold]{elapsed:.1f} сек[/bold]")
    console.print(f"Использовано потоков: [bold]{n_workers}[/bold]")

    for fmt, path in saved.items():
        console.print(f" • {fmt.upper():4} → {Path(path).name}")


if __name__ == "__main__":
    main()